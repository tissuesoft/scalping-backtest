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
from live.supabase_log import (
    SupabaseLogger,
    bar_context,
    exit_event_type,
    snapshot_from_df,
)
from leverage_limits import (
    BINANCE_DEMO_MAX_LEVERAGE,
    effective_leverage_map,
    leverage_for_notional,
    size_for_margin_budget,
)


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
        self.lev_map = effective_leverage_map(cfg.leverage, BINANCE_DEMO_MAX_LEVERAGE)
        self.cfg.log_dir.mkdir(parents=True, exist_ok=True)
        self.sb = SupabaseLogger(dry_run=cfg.dry_run)
        self._hb_bar_ms = 0

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
        self.lev_map = effective_leverage_map(want, BINANCE_DEMO_MAX_LEVERAGE)
        for sym in self.cfg.symbols:
            try:
                self.trade.change_margin_type(sym, "ISOLATED")
            except BinanceFapiError as e:
                if "No need to change" not in e.body and "-4046" not in e.body:
                    _log(f"marginType {sym}: {e}")
            lev = int(self.lev_map.get(sym, want))
            # still resolve against live bracket in case exchange changed
            lev = self._resolve_leverage(sym, lev)
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
                self.lev_map[sym] = float(applied)
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

    def _signed_position_amt(self, symbol: str) -> float:
        """Exchange signed positionAmt. nan = lookup failed."""
        if self.cfg.dry_run:
            slot = self.state.slots.get(symbol)
            return float(slot.qty * slot.side) if slot else 0.0
        try:
            rows = self.trade.position_risk(symbol)
        except Exception as e:
            _log(f"positionRisk {symbol}: {e}")
            return float("nan")
        if not isinstance(rows, list):
            rows = [rows] if rows else []
        for r in rows:
            if r.get("symbol") == symbol:
                return float(r.get("positionAmt") or 0)
        return 0.0

    def _drop_if_exchange_flat(self, slot: LiveSlot, why: str) -> bool:
        """Drop ghost slot when demo account has no matching position."""
        amt = self._signed_position_amt(slot.symbol)
        if math.isnan(amt):
            return False
        same_side = (slot.side > 0 and amt > 0) or (slot.side < 0 and amt < 0)
        if abs(amt) < 1e-12 or not same_side:
            _log(f"FLAT {slot.symbol} {why} exch_amt={amt} drop slot")
            self.state.slots.pop(slot.symbol, None)
            return True
        return False

    def _fill_price(self, order: dict, fallback: float) -> float:
        for k in ("avgPrice", "price"):
            v = order.get(k)
            if v is not None and float(v) > 0:
                return float(v)
        return fallback

    def manage_slot(self, slot: LiveSlot, bar: pd.Series, price: float) -> str | None:
        """Bar-close trail/SL/TP — same rules as portfolio_engine (incl. partial trail)."""
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
        if slot.scale_n >= 1 and not math.isnan(tr_use):
            tr_use = tr_use * 6.1653697404852474e-12

        if slot.side == 1:
            slot.peak = max(slot.peak, high)
            if not math.isnan(tr_use) and tr_use > 0:
                trail_sl = slot.peak - tr_use
                if math.isnan(slot.sl) or trail_sl > slot.sl:
                    slot.sl = trail_sl
            hit_sl = (not math.isnan(slot.sl)) and low <= slot.sl
            hit_tp = (not math.isnan(slot.tp)) and high >= slot.tp
        else:
            slot.peak = min(slot.peak, low)
            if not math.isnan(tr_use) and tr_use > 0:
                trail_sl = slot.peak + tr_use
                if math.isnan(slot.sl) or trail_sl < slot.sl:
                    slot.sl = trail_sl
            hit_sl = (not math.isnan(slot.sl)) and high >= slot.sl
            hit_tp = (not math.isnan(slot.tp)) and low <= slot.tp

        grace = slot.bars_held < pc.sl_grace_bars
        if grace:
            hit_sl = False

        reason = None
        if hit_sl and hit_tp:
            reason = "sl" if pc.same_bar_priority == "sl" else "tp"
        elif hit_sl:
            reason = "sl"
        elif hit_tp:
            reason = "tp"
        return reason

    def _persist_bar(self, symbol: str, df: pd.DataFrame) -> dict[str, Any]:
        ctx = bar_context(df)
        self.sb.upsert_ohlcv_bars(symbol, df.iloc[[-1]])
        self.sb.upsert_snapshot(snapshot_from_df(symbol, df))
        return ctx

    def tick_stop(self, slot: LiveSlot, price: float) -> str | None:
        """Intra-bar stop vs last price (live-only; backtest uses bar H/L)."""
        pc = self.pc
        assert pc is not None
        if slot.bars_held < pc.sl_grace_bars:
            return None
        if math.isnan(slot.sl):
            return None
        if slot.side == 1 and price <= slot.sl:
            return "sl_tick"
        if slot.side == -1 and price >= slot.sl:
            return "sl_tick"
        return None

    def _partial_frac(self, slot: LiveSlot, reason: str, exit_px: float) -> float:
        pc = self.pc
        assert pc is not None
        if not pc.use_partial_trail or reason != "sl" or slot.scale_n >= pc.trail_scale_max:
            return 1.0
        in_profit = (slot.side == 1 and exit_px > slot.entry) or (
            slot.side == -1 and exit_px < slot.entry
        )
        if not in_profit:
            return 1.0
        if slot.scale_n == 0:
            return float(pc.first_close_frac)
        if slot.scale_n == 1:
            return float(
                pc.second_close_frac_fat
                if slot.boost >= pc.fat_boost_thresh
                else pc.second_close_frac_thin
            )
        return float(pc.later_close_frac)

    def close_slot(self, slot: LiveSlot, reason: str, exit_px: float | None = None) -> None:
        pc = self.pc
        assert pc is not None
        px = float(exit_px) if exit_px is not None else 0.0
        if exit_px is None:
            try:
                px = self.market.ticker_price(slot.symbol)
            except Exception:
                px = slot.entry
        frac = self._partial_frac(slot, reason, px)
        if frac <= 0:
            slot.scale_n += 1
            _log(
                f"TRAIL_SCALE {slot.symbol} scale_n={slot.scale_n} (close_frac=0, keep position)"
            )
            return

        flt = self.filters[slot.symbol]
        close_qty = slot.qty if frac >= 1.0 - 1e-12 else slot.qty * frac
        qty = round_qty(close_qty, flt.step_size)
        if qty <= 0:
            _log(f"close skip {slot.symbol}: qty=0")
            self.state.slots.pop(slot.symbol, None)
            return
        if not self.cfg.dry_run:
            amt = self._signed_position_amt(slot.symbol)
            if not math.isnan(amt):
                same_side = (slot.side > 0 and amt > 0) or (slot.side < 0 and amt < 0)
                if abs(amt) < 1e-12 or not same_side:
                    _log(f"CLOSE skip {slot.symbol}: already flat amt={amt} ({reason})")
                    self.state.slots.pop(slot.symbol, None)
                    return
                qty = min(qty, round_qty(abs(amt), flt.step_size))
                if qty <= 0:
                    self.state.slots.pop(slot.symbol, None)
                    return
        side = "SELL" if slot.side == 1 else "BUY"
        try:
            order = self._place_market(slot.symbol, side, qty, reduce_only=True)
            fill = self._fill_price(order, px)
            pnl = slot.side * (fill / slot.entry - 1.0) * (qty * fill)
            do_partial = frac < 1.0 - 1e-12 and qty + 1e-12 < slot.qty
            tag = "trail_partial" if do_partial else reason
            _log(
                f"CLOSE {slot.symbol} {tag} side={slot.side} qty={qty}/{slot.qty} "
                f"entry={slot.entry:.6g} exit={fill:.6g} pnl~{pnl:.4f}"
            )
            ev_type = "TRAIL" if do_partial else exit_event_type(reason)
            left_qty = slot.qty
            if do_partial:
                left = round_qty(slot.qty - qty, flt.step_size)
                left_qty = left if left > 0 else 0.0
            self.sb.insert_event(
                {
                    "symbol": slot.symbol,
                    "event_type": ev_type,
                    "direction": "LONG" if slot.side == 1 else "SHORT",
                    "entry_price": slot.entry,
                    "close_price": fill,
                    "signal_price": px,
                    "fill_price": fill,
                    "quantity": qty,
                    "quantity_remaining": left_qty if do_partial else 0.0,
                    "executed_qty": qty,
                    "profit_pct": slot.side * (fill / slot.entry - 1.0) * 100.0,
                    "pnl_usd": pnl,
                    "sl_price": slot.sl if not math.isnan(slot.sl) else None,
                    "leverage": slot.leverage,
                    "position_usd": slot.notional,
                    "account_balance_usd": self.equity_estimate(),
                    "holding_time_seconds": slot.bars_held * 60,
                    "entry_event_id": slot.entry_event_id,
                    "memo": tag,
                    "regime": slot.regime,
                    "trail_armed": slot.trail_unlocked,
                    "add_count": slot.scale_n,
                    "model_version": "port5_demo",
                }
            )
            if do_partial:
                left = round_qty(slot.qty - qty, flt.step_size)
                if left <= 0:
                    do_partial = False
                else:
                    remain = left / slot.qty if slot.qty else 0.0
                    slot.qty = left
                    slot.notional *= remain
                    slot.margin *= remain
                    slot.scale_n += 1
                    self.state.slots[slot.symbol] = slot
                    return
            if pnl > 0:
                self.state.size_mult = min(self.state.size_mult * pc.win_size_mult, pc.win_size_max)
            else:
                self.state.size_mult = 1.0
        except BinanceFapiError as e:
            if "-2022" in e.body or "ReduceOnly" in e.body:
                if self._drop_if_exchange_flat(slot, "reduceOnly rejected"):
                    return
            _log(f"CLOSE ERROR {slot.symbol}: {e}")
            return
        except Exception as e:
            _log(f"CLOSE ERROR {slot.symbol}: {e}")
            return
        self.state.slots.pop(slot.symbol, None)

    def try_enter(
        self,
        symbol: str,
        sig_row: pd.Series,
        bar: pd.Series,
        bar_ms: int,
        ctx: dict | None = None,
    ) -> None:
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
        # 0~3 open: 18% of equity; already 4 open → dump remaining free into last slot
        if open_n >= 4:
            budget = free
        else:
            budget = min(eq_now * pc.slot_frac, free)
        if budget <= 1e-8 or free < budget * 0.5:
            return

        risk = abs(fill_px - sl) if not math.isnan(sl) else fill_px * 0.01
        risk_frac = risk / fill_px if fill_px > 0 else 0.01
        risk_tgt = min(pc.risk_tgt_max, pc.risk_tgt_start + pc.risk_tgt_span * 0.5)
        want_lev = float(getattr(self, "lev_map", {}).get(symbol) or pc.leverage_for(symbol))
        risk_wish = budget * risk_tgt * self.state.size_mult * boost / max(risk_frac, 1e-8)
        bqv = float(bar.get("quote_volume", 0) or 0)
        if pc.liq_notional_frac > 0 and bqv > 1.0:
            risk_wish = min(risk_wish, bqv * pc.liq_notional_frac)

        cap_budget = min(budget, free)
        notional, margin, lev = size_for_margin_budget(symbol, cap_budget, want_lev, risk_wish)
        if notional <= 0 or margin <= 0:
            return

        flt = self.filters[symbol]
        qty = round_qty(notional / fill_px, flt.step_size)
        if qty < flt.min_qty or qty * fill_px < flt.min_notional:
            _log(f"skip {symbol}: qty/notional too small qty={qty}")
            return
        notional = qty * fill_px
        lev = min(want_lev, leverage_for_notional(symbol, notional))
        margin = min(cap_budget, notional / max(lev, 1e-9))
        # If rounding pushed notional into a lower bracket, shrink to budget again
        if margin > cap_budget + 1e-9:
            notional, margin, lev = size_for_margin_budget(symbol, cap_budget, want_lev, notional)
            qty = round_qty(notional / fill_px, flt.step_size)
            if qty < flt.min_qty or qty * fill_px < flt.min_notional:
                return
            notional = qty * fill_px
            lev = min(want_lev, leverage_for_notional(symbol, notional))
            margin = min(cap_budget, notional / max(lev, 1e-9))

        order_side = "BUY" if side == 1 else "SELL"
        try:
            if not self.cfg.dry_run:
                try:
                    self.trade.change_leverage(symbol, int(max(1, round(lev))))
                except BinanceFapiError as e:
                    _log(f"change_leverage {symbol}→{lev}: {e}")
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
                leverage=float(lev),
                signal_price=float(fill_px),
                regime=(ctx or {}).get("regime"),
            )
            self.state.slots[symbol] = slot
            self.state.pending[symbol] = {"bar_ms": bar_ms}
            eid = self.sb.insert_event(
                {
                    "symbol": symbol,
                    "event_type": "ENTRY",
                    "direction": "LONG" if side == 1 else "SHORT",
                    "entry_price": entry,
                    "close_price": entry,
                    "signal_price": fill_px,
                    "fill_price": entry,
                    "quantity": qty,
                    "quantity_remaining": qty,
                    "executed_qty": qty,
                    "sl_price": sl if not math.isnan(sl) else None,
                    "leverage": lev,
                    "position_usd": slot.notional,
                    "account_balance_usd": self.equity_estimate(),
                    "entry_reason": f"regime_{(ctx or {}).get('regime')}_entry",
                    "memo": f"lev={lev:.0f} margin={margin:.2f}",
                    "model_version": "port5_demo",
                    "trail_armed": False,
                    "add_count": 0,
                    **{k: v for k, v in (ctx or {}).items() if k != "close_price"},
                    "close_price": entry,
                }
            )
            slot.entry_event_id = eid
            _log(
                f"OPEN {symbol} side={side} qty={qty} entry={entry:.6g} lev={lev:.0f}x "
                f"sl={sl:.6g} trail={trail:.6g} margin~{margin:.4f} notional~{slot.notional:.2f} "
                f"budget~{cap_budget:.2f}"
            )
        except Exception as e:
            _log(f"OPEN ERROR {symbol}: {e}")

    def on_new_bars(self, frames: dict[str, pd.DataFrame]) -> None:
        # drop slots the demo account already flattened (liq / UI / reduceOnly miss)
        for slot in list(self.state.slots.values()):
            self._drop_if_exchange_flat(slot, "reconcile")
        # manage existing: bar-close rules only on a newly closed 1m; tick stop between bars
        for sym, slot in list(self.state.slots.items()):
            df = frames[sym]
            bar = df.iloc[-1]
            bar_ms = int(df.index[-1].timestamp() * 1000)
            try:
                px = self.market.ticker_price(sym)
            except Exception:
                px = float(bar["close"])
            prev = self.state.last_bar_ms.get(sym)
            is_new = prev is None or bar_ms != prev
            if is_new:
                try:
                    sig = build_closed_signals(df, sym)
                    tr = float(sig["trail_atr"].iloc[-1])
                    if not math.isnan(tr):
                        slot.trail_atr = tr
                except Exception:
                    pass
                reason = self.manage_slot(slot, bar, px)
                if reason:
                    exit_px = slot.sl if reason == "sl" else (slot.tp if reason == "tp" else px)
                    self.close_slot(slot, reason, exit_px)
                    continue
            else:
                reason = self.tick_stop(slot, px)
                if reason:
                    self.close_slot(slot, reason, px)

        # entries: only when symbol got a new closed bar
        filled_bar_ms = None
        for sym in self.cfg.symbols:
            df = frames[sym]
            bar_ms = int(df.index[-1].timestamp() * 1000)
            prev = self.state.last_bar_ms.get(sym)
            self.state.last_bar_ms[sym] = bar_ms
            if prev is not None and bar_ms == prev:
                continue
            ctx = self._persist_bar(sym, df)
            if len(self.state.slots) >= 5:
                break
            if any(int(p.get("bar_ms", -1)) == bar_ms for p in self.state.pending.values()):
                continue

            sig = build_closed_signals(df, sym)
            self.try_enter(sym, sig.iloc[-1], df.iloc[-1], bar_ms, ctx)
            if sym in self.state.slots and self.state.slots[sym].entry_bar_ms == bar_ms:
                filled_bar_ms = bar_ms
                for s in self.cfg.symbols:
                    self.state.pending[s] = {"bar_ms": bar_ms}

        newest = max(self.state.last_bar_ms.values()) if self.state.last_bar_ms else 0
        self.state.pending = {
            k: v for k, v in self.state.pending.items() if int(v.get("bar_ms", 0)) >= newest - 120_000
        }

    def loop_once(self) -> None:
        frames = self.fetch_frames()
        self.sb.seed_frames_once(frames)
        self.on_new_bars(frames)
        save_state(self.cfg.state_path, self.state)
        newest = max(self.state.last_bar_ms.values()) if self.state.last_bar_ms else 0
        if newest and newest != self._hb_bar_ms:
            self._hb_bar_ms = newest
            self.sb.insert_heartbeat(
                {
                    "equity": self.equity_estimate(),
                    "free_cash": self.free_cash(),
                    "size_mult": self.state.size_mult,
                    "n_slots": len(self.state.slots),
                    "dry_run": self.cfg.dry_run,
                    "slots_json": {
                        s.symbol: {
                            "side": s.side,
                            "entry": s.entry,
                            "qty": s.qty,
                            "sl": s.sl,
                            "regime": s.regime,
                        }
                        for s in self.state.slots.values()
                    },
                }
            )
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
        pc = self.pc
        assert pc is not None
        _log(
            f"start demo runner dry_run={self.cfg.dry_run} want_lev={self.cfg.leverage} "
            f"per-symbol={self.lev_map} slot_frac={pc.slot_frac} "
            f"partial_trail={pc.use_partial_trail} sl_grace={pc.sl_grace_bars} "
            f"klines={self.cfg.kline_limit} poll={self.cfg.poll_sec}s stop_file={self.cfg.stop_file}"
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
