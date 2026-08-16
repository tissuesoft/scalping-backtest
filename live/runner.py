"""PORT5 live demo runner — real Binance charts + demo orders.

- Market data (1m klines / price): https://fapi.binance.com (실차트)
- Orders / account: https://demo-fapi.binance.com (데모)
- Default dry-run (no orders). STOP file halts the loop.
"""
from __future__ import annotations

import math
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from live.binance_fapi import BinanceFapi, BinanceFapiError
from live.config import LiveConfig
from live.filters import SymbolFilters, parse_exchange_filters, round_price, round_qty
from live.signals import build_closed_signals, klines_to_df
from live.state import LiveSlot, LiveState, load_state, save_state


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}Z] {msg}", flush=True)


def _usdt_balance(account: dict) -> float:
    for a in account.get("assets", []):
        if a.get("asset") == "USDT":
            return float(a.get("availableBalance", a.get("walletBalance", 0)))
    # fallback balance endpoint shape
    return float(account.get("availableBalance", 0) or 0)


def _wallet_usdt(client: BinanceFapi) -> tuple[float, float]:
    """Return (wallet_balance, available)."""
    acc = client.account()
    wallet = 0.0
    avail = 0.0
    for a in acc.get("assets", []):
        if a.get("asset") == "USDT":
            wallet = float(a.get("walletBalance", 0))
            avail = float(a.get("availableBalance", 0))
            break
    return wallet, avail


class DemoRunner:
    def __init__(self, cfg: LiveConfig):
        self.cfg = cfg
        self.pc = cfg.portfolio
        assert self.pc is not None
        # Real market data (public). Demo account only for trading.
        self.market = BinanceFapi("", "", cfg.market_url)
        self.trade = BinanceFapi(cfg.api_key, cfg.api_secret, cfg.trade_url)
        self.filters: dict[str, SymbolFilters] = {}
        self.state = load_state(cfg.state_path)
        self.cfg.log_dir.mkdir(parents=True, exist_ok=True)

    def setup_exchange(self) -> None:
        _log(f"market(charts) {self.cfg.market_url} ...")
        self.market.ping()
        info = self.market.exchange_info()
        self.filters = parse_exchange_filters(info, self.cfg.symbols)
        _log(f"real market exchangeInfo ok; symbols={list(self.filters)}")

        if self.cfg.dry_run:
            _log(f"DRY-RUN: trade host={self.cfg.trade_url} (no orders)")
            return

        if not self.cfg.api_key or not self.cfg.api_secret:
            raise RuntimeError("Set BINANCE_DEMO_API_KEY / BINANCE_DEMO_API_SECRET in .env")

        _log(f"trade(demo) {self.cfg.trade_url} ...")
        self.trade.ping()
        want = max(1, min(int(self.cfg.leverage), 125))
        for sym in self.cfg.symbols:
            try:
                self.trade.change_margin_type(sym, "ISOLATED")
            except BinanceFapiError as e:
                if "No need to change" not in e.body and "-4046" not in e.body:
                    _log(f"marginType {sym}: {e}")
            lev = self._resolve_leverage(sym, want)
            applied = None
            err = None
            for try_lev in range(lev, 0, -1):
                try:
                    self.trade.change_leverage(sym, try_lev)
                    applied = try_lev
                    break
                except BinanceFapiError as e:
                    err = e
                    continue
            if applied is not None:
                note = "" if applied == want else f" (capped from {want})"
                _log(f"leverage {sym}={applied} ISOLATED{note}")
            else:
                _log(f"leverage {sym}: {err}")

    def _resolve_leverage(self, symbol: str, want: int) -> int:
        """Use min(want, exchange max leverage for symbol)."""
        try:
            data = self.trade.leverage_bracket(symbol)
            # [{"symbol":"BTCUSDT","brackets":[{"initialLeverage":125,...}, ...]}]
            if isinstance(data, list) and data:
                brackets = data[0].get("brackets") or []
                if brackets:
                    max_lev = max(int(b.get("initialLeverage", 1)) for b in brackets)
                    return max(1, min(want, max_lev))
        except Exception as e:
            _log(f"leverageBracket {symbol}: {e}; using want={want}")
        return want
    def fetch_frames(self) -> dict[str, pd.DataFrame]:
        out = {}
        for sym in self.cfg.symbols:
            rows = self.market.klines(sym, "1m", self.cfg.kline_limit)
            out[sym] = klines_to_df(rows)
        return out

    def equity_estimate(self) -> float:
        if self.cfg.dry_run:
            # paper equity: start from env or 100, apply slot margins in state
            base = float(__import__("os").environ.get("BINANCE_DEMO_PAPER_EQUITY", "100"))
            locked = sum(s.margin for s in self.state.slots.values())
            # simplistic: treat free = base - locked + unrealized ignored
            return max(base, locked + 1.0)
        wallet, avail = _wallet_usdt(self.trade)
        return max(wallet, avail)

    def free_cash(self) -> float:
        if self.cfg.dry_run:
            base = float(__import__("os").environ.get("BINANCE_DEMO_PAPER_EQUITY", "100"))
            locked = sum(s.margin for s in self.state.slots.values())
            return max(base - locked, 0.0)
        _, avail = _wallet_usdt(self.trade)
        return max(avail, 0.0)

    def _place_market(self, symbol: str, side: str, qty: float, reduce_only: bool = False) -> dict:
        params: dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "quantity": qty,
        }
        if reduce_only:
            params["reduceOnly"] = "true"
        if self.cfg.dry_run:
            px = self.market.ticker_price(symbol)
            _log(f"DRY order {side} {symbol} qty={qty} px~{px} reduceOnly={reduce_only}")
            return {"avgPrice": str(px), "executedQty": str(qty), "status": "DRY"}
        return self.trade.new_order(**params)

    def _fill_price(self, order: dict, fallback: float) -> float:
        for k in ("avgPrice", "price"):
            v = order.get(k)
            if v is not None and float(v) > 0:
                return float(v)
        return fallback

    def manage_slot(self, slot: LiveSlot, bar: pd.Series, price: float) -> str | None:
        """Update trail/SL on closed bar; return exit reason or None."""
        pc = self.pc
        assert pc is not None
        high = float(bar["high"])
        low = float(bar["low"])
        slot.bars_held += 1

        move_now = (high - slot.entry) if slot.side == 1 else (slot.entry - low)
        if pc.trail_unlock_r > 0 and slot.risk > 0 and not math.isnan(slot.trail_atr):
            if move_now >= pc.trail_unlock_r * slot.risk:
                slot.trail_unlocked = True

        tr_use = slot.trail_atr
        if slot.trail_unlocked and not math.isnan(tr_use):
            tr_use = tr_use * pc.trail_unlock_mult

        if slot.side == 1:
            slot.peak = max(slot.peak, high)
            if not math.isnan(tr_use) and tr_use > 0:
                trail_sl = slot.peak - tr_use
                if math.isnan(slot.sl) or trail_sl > slot.sl:
                    slot.sl = trail_sl
            # SL hit on bar
            grace = slot.bars_held < pc.sl_grace_bars
            if not grace and not math.isnan(slot.sl) and low <= slot.sl:
                return "sl"
            if not math.isnan(slot.tp) and high >= slot.tp:
                return "tp"
        else:
            slot.peak = min(slot.peak, low)
            if not math.isnan(tr_use) and tr_use > 0:
                trail_sl = slot.peak + tr_use
                if math.isnan(slot.sl) or trail_sl < slot.sl:
                    slot.sl = trail_sl
            grace = slot.bars_held < pc.sl_grace_bars
            if not grace and not math.isnan(slot.sl) and high >= slot.sl:
                return "sl"
            if not math.isnan(slot.tp) and low <= slot.tp:
                return "tp"

        # live tick stop vs last price
        if not grace and not math.isnan(slot.sl):
            if slot.side == 1 and price <= slot.sl:
                return "sl_tick"
            if slot.side == -1 and price >= slot.sl:
                return "sl_tick"
        return None

    def close_slot(self, slot: LiveSlot, reason: str) -> None:
        side = "SELL" if slot.side == 1 else "BUY"
        qty = round_qty(slot.qty, self.filters[slot.symbol].step_size)
        if qty <= 0:
            _log(f"close skip {slot.symbol}: qty=0")
            self.state.slots.pop(slot.symbol, None)
            return
        try:
            order = self._place_market(slot.symbol, side, qty, reduce_only=True)
            px = self._fill_price(order, self.market.ticker_price(slot.symbol))
            pnl = slot.side * (px / slot.entry - 1.0) * slot.notional
            _log(
                f"CLOSE {slot.symbol} {reason} side={slot.side} qty={qty} "
                f"entry={slot.entry:.6g} exit={px:.6g} pnl~{pnl:.4f}"
            )
            if pnl > 0:
                self.state.size_mult = min(self.state.size_mult * self.pc.win_size_mult, self.pc.win_size_max)
            else:
                self.state.size_mult = 1.0
        except Exception as e:
            _log(f"CLOSE ERROR {slot.symbol}: {e}")
            return
        self.state.slots.pop(slot.symbol, None)

    def try_enter(self, symbol: str, sig_row: pd.Series, bar: pd.Series, bar_ms: int) -> None:
        if symbol in self.state.slots:
            return
        if len(self.state.slots) >= 5:
            return

        long = bool(sig_row.get("entry_long", False))
        short = bool(sig_row.get("entry_short", False))
        if long == short:
            return
        side = 1 if long else -1
        sl = float(sig_row["sl_long"] if side == 1 else sig_row["sl_short"])
        tp = float(sig_row["tp_long"] if side == 1 else sig_row["tp_short"])
        trail = float(sig_row.get("trail_atr", np.nan))
        boost = float(sig_row.get("size_boost", 1.0) or 1.0)
        if math.isnan(boost):
            boost = 1.0

        # only one new slot per bar across portfolio
        if any(int(p.get("bar_ms", -1)) == bar_ms for p in self.state.pending.values()):
            return

        mid = float(bar["open"])  # backtest fills next bar open; here use closed bar close≈next open
        # Prefer next open approximation: use current ticker as fill proxy
        try:
            fill_px = self.market.ticker_price(symbol)
        except Exception:
            fill_px = float(bar["close"])

        pc = self.pc
        assert pc is not None
        if pc.risk_cap_pct > 0 and not math.isnan(sl):
            if side == 1:
                sl = max(sl, fill_px * (1.0 - pc.risk_cap_pct))
            else:
                sl = min(sl, fill_px * (1.0 + pc.risk_cap_pct))

        open_n = len(self.state.slots)
        eq_now = self.equity_estimate()
        free = self.free_cash()
        if open_n >= 4:
            budget = free
        else:
            budget = min(eq_now * pc.slot_frac, free)
        if budget <= 1e-8 or free < budget * 0.5:
            return

        risk = abs(fill_px - sl) if not math.isnan(sl) else fill_px * 0.01
        risk_frac = risk / fill_px if fill_px > 0 else 0.01
        risk_tgt = min(pc.risk_tgt_max, pc.risk_tgt_start + pc.risk_tgt_span * 0.5)
        lev_cap = budget * pc.leverage
        notional = min(
            lev_cap,
            budget * risk_tgt * self.state.size_mult * boost / max(risk_frac, 1e-8),
        )
        # soft cap vs bar quote volume
        bqv = float(bar.get("quote_volume", 0) or 0)
        if pc.liq_notional_frac > 0 and bqv > 1.0:
            notional = min(notional, bqv * pc.liq_notional_frac)

        margin = min(budget, max(notional / pc.leverage, budget * 0.01))
        if margin > free:
            margin = free
            notional = min(notional, margin * pc.leverage)
        if notional <= 0 or margin <= 0:
            return

        flt = self.filters[symbol]
        qty = round_qty(notional / fill_px, flt.step_size)
        if qty < flt.min_qty or qty * fill_px < flt.min_notional:
            _log(f"skip {symbol}: qty/notional too small qty={qty}")
            return

        order_side = "BUY" if side == 1 else "SELL"
        try:
            order = self._place_market(symbol, order_side, qty, reduce_only=False)
            entry = self._fill_price(order, fill_px)
            risk = abs(entry - sl) if not math.isnan(sl) else entry * 0.01
            slot = LiveSlot(
                symbol=symbol,
                side=side,
                entry=entry,
                qty=qty,
                notional=qty * entry,
                margin=margin,
                sl=sl,
                tp=tp,
                trail_atr=trail,
                peak=entry,
                risk=risk,
                boost=boost,
                entry_bar_ms=bar_ms,
                bars_held=0,
            )
            self.state.slots[symbol] = slot
            self.state.pending[symbol] = {"bar_ms": bar_ms}
            _log(
                f"OPEN {symbol} side={side} qty={qty} entry={entry:.6g} "
                f"sl={sl:.6g} trail={trail:.6g} margin~{margin:.4f} notional~{slot.notional:.2f}"
            )
        except Exception as e:
            _log(f"OPEN ERROR {symbol}: {e}")

    def on_new_bars(self, frames: dict[str, pd.DataFrame]) -> None:
        # manage existing first
        for sym, slot in list(self.state.slots.items()):
            df = frames[sym]
            bar = df.iloc[-1]
            try:
                px = self.market.ticker_price(sym)
            except Exception:
                px = float(bar["close"])
            # refresh trail atr from latest signal row if present
            try:
                sig = build_closed_signals(df, sym)
                tr = float(sig["trail_atr"].iloc[-1])
                if not math.isnan(tr):
                    slot.trail_atr = tr
            except Exception:
                pass
            reason = self.manage_slot(slot, bar, px)
            if reason:
                self.close_slot(slot, reason)

        # entries: only when symbol got a new closed bar
        filled_bar_ms = None
        for sym in self.cfg.symbols:
            df = frames[sym]
            bar_ms = int(df.index[-1].timestamp() * 1000)
            prev = self.state.last_bar_ms.get(sym)
            self.state.last_bar_ms[sym] = bar_ms
            if prev is not None and bar_ms == prev:
                continue
            if filled_bar_ms is not None and bar_ms != filled_bar_ms:
                # keep one entry per wall-clock bar across symbols
                pass
            if len(self.state.slots) >= 5:
                break
            # already opened one this cycle
            if any(int(p.get("bar_ms", -1)) == bar_ms for p in self.state.pending.values()):
                # allow other symbols same bar? backtest = one per bar total
                continue

            sig = build_closed_signals(df, sym)
            self.try_enter(sym, sig.iloc[-1], df.iloc[-1], bar_ms)
            if sym in self.state.slots and self.state.slots[sym].entry_bar_ms == bar_ms:
                filled_bar_ms = bar_ms
                # mark all pending for this bar so only one entry
                for s in self.cfg.symbols:
                    self.state.pending[s] = {"bar_ms": bar_ms}

        # prune stale pending markers
        newest = max(self.state.last_bar_ms.values()) if self.state.last_bar_ms else 0
        self.state.pending = {
            k: v for k, v in self.state.pending.items() if int(v.get("bar_ms", 0)) >= newest - 120_000
        }

    def loop_once(self) -> None:
        frames = self.fetch_frames()
        self.on_new_bars(frames)
        save_state(self.cfg.state_path, self.state)
        slots = ", ".join(
            f"{s.symbol}:{'L' if s.side==1 else 'S'}@{s.entry:.4g}/sl={s.sl:.4g}"
            for s in self.state.slots.values()
        ) or "-"
        _log(
            f"heartbeat dry={self.cfg.dry_run} equity~{self.equity_estimate():.2f} "
            f"free~{self.free_cash():.2f} slots=[{slots}] size_mult={self.state.size_mult:.2f}"
        )

    def run(self) -> None:
        self.setup_exchange()
        _log(
            f"start demo runner dry_run={self.cfg.dry_run} lev={self.cfg.leverage} "
            f"poll={self.cfg.poll_sec}s stop_file={self.cfg.stop_file}"
        )
        while True:
            if self.cfg.stop_file.exists():
                _log("STOP file detected; exiting")
                break
            try:
                self.loop_once()
            except BinanceFapiError as e:
                _log(f"API error: {e}")
            except Exception:
                _log("loop error:\n" + traceback.format_exc())
            time.sleep(self.cfg.poll_sec)
