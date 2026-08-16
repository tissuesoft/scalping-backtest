"""5심볼 포트폴리오 엔진: 20% 배분 + 마지막 슬롯 잔액 전액, 격리 청산."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from compound_engine import Trade, _slip
from strategies.registry import PORTFOLIO_SYMBOLS

# 1m 선물 실전 근사: 심볼 스프레드 + 체결금액/봉거래대금 충격 + 봉 변동성
# cfg.slippage==0 이면 스모크용으로 슬리피지 없음
_LIVE_SLIP_BASE = {
    "BTCUSDT": 0.00015,  # ~1.5bp
    "ETHUSDT": 0.00020,
    "BNBUSDT": 0.00025,
    "SOLUSDT": 0.00035,
    "XRPUSDT": 0.00040,
}
_LIVE_SLIP_CAP = 0.006  # 60bp 상한 (대량·얇은 호가)


def live_slip_rate(
    symbol: str,
    notional: float,
    bar_quote_vol: float,
    range_pct: float,
    enabled: bool,
    fallback: float,
) -> float:
    """실전형 슬리피지 비율. enabled=False면 0, 구 fallback은 하한으로만 씀."""
    if not enabled:
        return 0.0
    base = _LIVE_SLIP_BASE.get(symbol, max(float(fallback), 0.00025))
    ntn = max(float(notional), 0.0)
    bqv = max(float(bar_quote_vol), 0.0)
    if bqv > 1.0:
        part = min(ntn / bqv, 2.0)
        impact = 0.0015 * float(np.sqrt(part))
    else:
        impact = 0.0004
    vol_add = 0.12 * max(float(range_pct), 0.0)
    return float(min(max(base, float(fallback)) + impact + vol_add, _LIVE_SLIP_CAP))


@dataclass
class PortfolioConfig:
    initial_capital: float = 100.0
    target_equity: float = 1_000_000.0
    leverage: float = 100.0
    fee_rate: float = 0.0004
    slippage: float = 0.0001
    mmr: float = 0.005
    slot_frac: float = 0.15  # P1064 REVERT: 0.22 crushed median under live slip
    trail_unlock_r: float = 3.0
    trail_unlock_mult: float = 1.4
    win_size_mult: float = 1.2
    win_size_max: float = 5.0
    sl_grace_bars: int = 46
    risk_cap_pct: float = 0.0012
    risk_tgt_start: float = 0.12
    risk_tgt_span: float = 0.38
    risk_tgt_max: float = 0.50
    same_bar_priority: str = "sl"
    # trail partials (aligned with compound champion spirit)
    use_partial_trail: bool = True
    first_close_frac: float = 0.0
    second_close_frac_fat: float = 0.10
    second_close_frac_thin: float = 0.264
    later_close_frac: float = 0.08
    trail_scale_max: int = 10
    fat_boost_thresh: float = 1.25
    # cap notional vs 1m quote volume so live-slip impact does not explode with equity
    liq_notional_frac: float = 0.22
    # skip entry if modeled live slip exceeds this (0 = off)
    max_entry_slip: float = 0.0020


@dataclass
class Slot:
    symbol: str
    side: int
    entry: float
    entry_i: int
    sl: float
    tp: float
    trail_atr: float
    notional: float
    margin: float
    peak: float
    risk: float
    boost: float
    trail_unlocked: bool = False
    scale_n: int = 0


@dataclass
class PortfolioResult:
    name: str
    trades: List[Trade]
    equity: pd.Series
    metrics: Dict[str, float]
    config: PortfolioConfig
    hit_target: bool
    trades_by_symbol: Dict[str, int] = field(default_factory=dict)
    liq_by_symbol: Dict[str, int] = field(default_factory=dict)


def align_frames(frames: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    """Intersect timestamps across symbols (inner join on 1m index)."""
    idx = None
    for df in frames.values():
        idx = df.index if idx is None else idx.intersection(df.index)
    if idx is None or len(idx) == 0:
        raise ValueError("no overlapping timestamps across symbols")
    idx = idx.sort_values()
    return {sym: df.loc[idx].copy() for sym, df in frames.items()}


def _empty_signals(index: pd.Index) -> pd.DataFrame:
    out = pd.DataFrame(index=index)
    out["entry_long"] = False
    out["entry_short"] = False
    out["sl_long"] = np.nan
    out["sl_short"] = np.nan
    out["tp_long"] = np.nan
    out["tp_short"] = np.nan
    out["trail_atr"] = np.nan
    out["size_boost"] = 1.0
    return out


def run_portfolio(
    frames: Dict[str, pd.DataFrame],
    signals: Dict[str, pd.DataFrame],
    config: Optional[PortfolioConfig] = None,
    name: str = "port5",
) -> PortfolioResult:
    cfg = config or PortfolioConfig()
    symbols = [s for s in PORTFOLIO_SYMBOLS if s in frames]
    if not symbols:
        raise ValueError("no portfolio symbols in frames")

    aligned = align_frames({s: frames[s] for s in symbols})
    index = next(iter(aligned.values())).index
    n = len(index)
    times = index.to_numpy()

    ohlc = {}
    sig = {}
    for s in symbols:
        df = aligned[s]
        vol = df["volume"].to_numpy(np.float64) if "volume" in df.columns else np.zeros(n, np.float64)
        ohlc[s] = {
            "open": df["open"].to_numpy(np.float64),
            "high": df["high"].to_numpy(np.float64),
            "low": df["low"].to_numpy(np.float64),
            "close": df["close"].to_numpy(np.float64),
            "volume": vol,
        }
        ss = signals.get(s)
        if ss is None:
            ss = _empty_signals(index)
        else:
            ss = ss.reindex(index)
        sig[s] = {
            "long": ss["entry_long"].fillna(False).to_numpy(bool),
            "short": ss["entry_short"].fillna(False).to_numpy(bool),
            "sl_long": ss["sl_long"].to_numpy(np.float64) if "sl_long" in ss else np.full(n, np.nan),
            "sl_short": ss["sl_short"].to_numpy(np.float64) if "sl_short" in ss else np.full(n, np.nan),
            "tp_long": ss["tp_long"].to_numpy(np.float64) if "tp_long" in ss else np.full(n, np.nan),
            "tp_short": ss["tp_short"].to_numpy(np.float64) if "tp_short" in ss else np.full(n, np.nan),
            "trail": ss["trail_atr"].to_numpy(np.float64) if "trail_atr" in ss else np.full(n, np.nan),
            "boost": ss["size_boost"].to_numpy(np.float64) if "size_boost" in ss else np.ones(n),
        }

    cash = float(cfg.initial_capital)
    slots: Dict[str, Slot] = {}
    pending: Dict[str, tuple] = {}  # symbol -> (side, sl, tp, trail, boost)
    size_mult = 1.0
    trades: List[Trade] = []
    eq_curve = np.zeros(n, np.float64)
    hit_target = False
    account_liq = False
    trades_by_symbol = {s: 0 for s in symbols}
    liq_by_symbol = {s: 0 for s in symbols}
    liq_dist = max(1.0 / cfg.leverage - cfg.mmr, 0.01)
    slip_on = float(cfg.slippage) > 0.0

    def _bar_range_pct(sym: str, i: int, px: float) -> float:
        hi = float(ohlc[sym]["high"][i])
        lo = float(ohlc[sym]["low"][i])
        mid = px if px > 0 else (hi + lo) * 0.5
        if mid <= 0:
            return 0.0
        return (hi - lo) / mid

    def _bar_quote_vol(sym: str, i: int, px: float) -> float:
        return float(ohlc[sym]["volume"][i]) * max(px, 0.0)

    def _apply_slip(sym: str, px: float, side: int, is_entry: bool, i: int, notional: float) -> float:
        rate = live_slip_rate(
            sym,
            notional,
            _bar_quote_vol(sym, i, px),
            _bar_range_pct(sym, i, px),
            slip_on,
            float(cfg.slippage),
        )
        return _slip(float(px), side, is_entry, rate)

    def locked_margin() -> float:
        return float(sum(sl.margin for sl in slots.values()))

    def mark_equity(i: int) -> float:
        eq = cash
        for sym, sl in slots.items():
            px = float(ohlc[sym]["close"][i])
            ur = sl.side * (px / sl.entry - 1.0) * sl.notional
            eq += sl.margin + ur
        return max(eq, 0.0)

    def free_cash() -> float:
        return max(cash, 0.0)

    def close_slot(sym: str, i: int, exit_px: float, reason: str, partial_frac: float = 1.0) -> None:
        nonlocal cash, size_mult
        sl = slots[sym]
        close_frac = float(partial_frac)
        fill_n = sl.notional * (1.0 if reason == "liquidation" else close_frac)
        fill = _apply_slip(sym, float(exit_px), sl.side, False, i, fill_n)
        if reason == "liquidation":
            # isolated: lose only this slot's margin
            net = -sl.margin
            close_frac = 1.0
            do_partial = False
            liq_by_symbol[sym] += 1
        else:
            ret = sl.side * (fill / sl.entry - 1.0)
            notion = sl.notional * close_frac
            gross = notion * ret
            fee = notion * cfg.fee_rate
            net = gross - fee
            do_partial = close_frac < 1.0 - 1e-12

        # release proportional margin back to cash, then apply net
        release = sl.margin * close_frac
        cash += release + net
        cash = max(cash, 0.0)

        trades.append(
            Trade(
                side=sl.side,
                entry_time=pd.Timestamp(times[sl.entry_i]),
                entry_price=sl.entry,
                exit_time=pd.Timestamp(times[i]),
                exit_price=fill if reason != "liquidation" else float(exit_px),
                bars_held=i - sl.entry_i,
                notional=sl.notional * close_frac,
                gross_pnl=net if reason == "liquidation" else (sl.notional * close_frac) * sl.side * (fill / sl.entry - 1.0),
                fee=0.0 if reason == "liquidation" else (sl.notional * close_frac) * cfg.fee_rate,
                net_pnl=net,
                return_pct=(net / max(sl.margin * close_frac, 1e-12)) * 100.0,
                exit_reason=("trail_partial" if do_partial else reason),
                equity_after=cash + locked_margin(),
            )
        )
        trades_by_symbol[sym] += 1

        if do_partial:
            sl.notional *= (1.0 - close_frac)
            sl.margin *= (1.0 - close_frac)
            sl.scale_n += 1
        else:
            if reason != "liquidation" and net > 0:
                size_mult = min(size_mult * cfg.win_size_mult, cfg.win_size_max)
            elif reason != "liquidation" and net <= 0:
                size_mult = 1.0
            # liquidation resets size_mult mildly
            if reason == "liquidation":
                size_mult = 1.0
            del slots[sym]

    for i in range(n):
        # 1) fill pendings at open — P008: at most one new slot per bar
        filled_this_bar = False
        for sym in list(pending.keys()):
            if filled_this_bar:
                break
            if sym in slots:
                del pending[sym]
                continue
            side, psl, ptp, ptr, pboost = pending[sym]
            mid = float(ohlc[sym]["open"][i])
            fill = _apply_slip(sym, mid, side, True, i, 0.0)
            # risk cap on SL
            if cfg.risk_cap_pct > 0 and not np.isnan(psl):
                if side == 1:
                    psl = max(psl, fill * (1.0 - cfg.risk_cap_pct))
                else:
                    psl = min(psl, fill * (1.0 + cfg.risk_cap_pct))

            open_n = len(slots)
            eq_now = mark_equity(i - 1) if i > 0 else (cash + locked_margin())
            if open_n >= 4:
                budget = free_cash()
            else:
                budget = min(eq_now * cfg.slot_frac, free_cash())
            if budget <= 1e-8 or cash < budget * 0.5:
                del pending[sym]
                continue

            boost = float(pboost) if not np.isnan(pboost) else 1.0
            risk = abs(fill - psl) if not np.isnan(psl) else fill * 0.01
            risk_frac = risk / fill if fill > 0 else 0.01
            progress = i / max(n - 1, 1)
            risk_tgt = min(cfg.risk_tgt_max, cfg.risk_tgt_start + cfg.risk_tgt_span * progress)
            # P001: hard-cap at stated leverage on alloc budget (no size_mult/1.5/boost inflate)
            lev_cap = budget * cfg.leverage
            notional = min(lev_cap, budget * risk_tgt * size_mult * boost / max(risk_frac, 1e-8))
            bqv = _bar_quote_vol(sym, i, mid)
            if cfg.liq_notional_frac > 0 and bqv > 1.0:
                notional = min(notional, bqv * cfg.liq_notional_frac)
            margin = min(budget, max(notional / cfg.leverage, budget * 0.01))
            if margin > cash:
                margin = cash
                notional = min(notional, margin * cfg.leverage)
            if notional <= 0 or margin <= 0:
                del pending[sym]
                continue
            entry_slip = live_slip_rate(
                sym,
                float(notional),
                bqv,
                _bar_range_pct(sym, i, mid),
                slip_on,
                float(cfg.slippage),
            )
            if cfg.max_entry_slip > 0 and entry_slip > cfg.max_entry_slip:
                del pending[sym]
                continue

            fill = _apply_slip(sym, mid, side, True, i, float(notional))
            if cfg.risk_cap_pct > 0 and not np.isnan(psl):
                if side == 1:
                    psl = max(psl, fill * (1.0 - cfg.risk_cap_pct))
                else:
                    psl = min(psl, fill * (1.0 + cfg.risk_cap_pct))
            risk = abs(fill - psl) if not np.isnan(psl) else fill * 0.01

            # entry fee
            fee = notional * cfg.fee_rate
            cash -= margin + fee
            if cash < 0:
                cash = 0.0

            slots[sym] = Slot(
                symbol=sym,
                side=side,
                entry=fill,
                entry_i=i,
                sl=float(psl),
                tp=float(ptp) if not np.isnan(ptp) else np.nan,
                trail_atr=float(ptr) if not np.isnan(ptr) else np.nan,
                notional=float(notional),
                margin=float(margin),
                peak=fill,
                risk=float(risk),
                boost=boost,
            )
            del pending[sym]
            filled_this_bar = True

        # 2) manage open slots
        for sym in list(slots.keys()):
            sl = slots[sym]
            high = ohlc[sym]["high"][i]
            low = ohlc[sym]["low"][i]
            tr = sig[sym]["trail"][i]
            if not np.isnan(tr):
                sl.trail_atr = float(tr)

            move_now = (high - sl.entry) if sl.side == 1 else (sl.entry - low)
            if cfg.trail_unlock_r > 0 and sl.risk > 0 and (not np.isnan(sl.trail_atr)):
                if move_now >= cfg.trail_unlock_r * sl.risk:
                    sl.trail_unlocked = True
            tr_use = sl.trail_atr
            if sl.trail_unlocked and not np.isnan(tr_use):
                tr_use = tr_use * cfg.trail_unlock_mult
            if sl.scale_n >= 1 and not np.isnan(tr_use):
                tr_use = tr_use * 6.1653697404852474e-12

            if sl.side == 1:
                sl.peak = max(sl.peak, high)
                if (not np.isnan(tr_use)) and tr_use > 0:
                    trail_sl = sl.peak - tr_use
                    if np.isnan(sl.sl) or trail_sl > sl.sl:
                        sl.sl = trail_sl
                hit_sl = (not np.isnan(sl.sl)) and low <= sl.sl
                hit_tp = (not np.isnan(sl.tp)) and high >= sl.tp
                liq_px = sl.entry * (1.0 - liq_dist)
                hit_liq = low <= liq_px
            else:
                sl.peak = min(sl.peak, low)
                if (not np.isnan(tr_use)) and tr_use > 0:
                    trail_sl = sl.peak + tr_use
                    if np.isnan(sl.sl) or trail_sl < sl.sl:
                        sl.sl = trail_sl
                hit_sl = (not np.isnan(sl.sl)) and high >= sl.sl
                hit_tp = (not np.isnan(sl.tp)) and low <= sl.tp
                liq_px = sl.entry * (1.0 + liq_dist)
                hit_liq = high >= liq_px

            if cfg.sl_grace_bars > 0 and (i - sl.entry_i) < cfg.sl_grace_bars:
                hit_sl = False

            reason = exit_px = None
            if hit_liq:
                reason, exit_px = "liquidation", liq_px
            elif hit_sl and hit_tp:
                reason, exit_px = ("sl", sl.sl) if cfg.same_bar_priority == "sl" else ("tp", sl.tp)
            elif hit_sl:
                reason, exit_px = "sl", sl.sl
            elif hit_tp:
                reason, exit_px = "tp", sl.tp

            if reason is None:
                continue

            frac = 1.0
            if (
                cfg.use_partial_trail
                and reason == "sl"
                and sl.scale_n < cfg.trail_scale_max
            ):
                in_profit = (sl.side == 1 and float(exit_px) > sl.entry) or (
                    sl.side == -1 and float(exit_px) < sl.entry
                )
                if in_profit:
                    if sl.scale_n == 0:
                        frac = cfg.first_close_frac
                    elif sl.scale_n == 1:
                        frac = (
                            cfg.second_close_frac_fat
                            if sl.boost >= cfg.fat_boost_thresh
                            else cfg.second_close_frac_thin
                        )
                    else:
                        frac = cfg.later_close_frac
                    if frac <= 0:
                        # champion first scale closes 0 — just bump scale and keep
                        sl.scale_n += 1
                        continue
            close_slot(sym, i, float(exit_px), reason, frac)

        # 3) queue new entries (next bar open) — at most one new pending per symbol
        open_syms = set(slots.keys()) | set(pending.keys())
        if len(slots) < 5:
            # prioritize symbols with signals; stable order
            for sym in symbols:
                if sym in open_syms:
                    continue
                if len(slots) + len(pending) >= 5:
                    break
                long = sig[sym]["long"][i]
                short = sig[sym]["short"][i]
                if long and not short:
                    pending[sym] = (
                        1,
                        sig[sym]["sl_long"][i],
                        sig[sym]["tp_long"][i],
                        sig[sym]["trail"][i],
                        sig[sym]["boost"][i],
                    )
                elif short and not long:
                    pending[sym] = (
                        -1,
                        sig[sym]["sl_short"][i],
                        sig[sym]["tp_short"][i],
                        sig[sym]["trail"][i],
                        sig[sym]["boost"][i],
                    )

        eq = mark_equity(i)
        eq_curve[i] = eq
        if (not hit_target) and eq >= cfg.target_equity:
            hit_target = True

        # 계좌 청산 = 합산 equity 전멸 (슬롯 격리 청산과 별개)
        if eq <= 1e-9 and not slots:
            account_liq = True
            eq_curve[i:] = 0.0
            break

    # flatten leftovers at last close
    if slots:
        i = n - 1
        for sym in list(slots.keys()):
            close_slot(sym, i, float(ohlc[sym]["close"][i]), "eod", 1.0)
        eq_curve[i] = mark_equity(i)

    equity = pd.Series(eq_curve, index=index, name="equity")
    final = float(equity.iloc[-1]) if len(equity) else cfg.initial_capital
    peak = float(equity.max()) if len(equity) else final
    if final <= 1.0:
        account_liq = True
    liq_n = float(sum(liq_by_symbol.values()))
    metrics = {
        "final_equity": final,
        "return_pct": (final / cfg.initial_capital - 1.0) * 100.0 if cfg.initial_capital else 0.0,
        "max_drawdown_pct": float(((equity / equity.cummax()) - 1.0).min() * 100.0) if len(equity) else 0.0,
        "trades": float(len(trades)),
        "liquidations": liq_n,  # isolated slot liqs (info)
        "account_liq": float(1.0 if account_liq else 0.0),
        "hit_target": float(1.0 if hit_target else 0.0),
        "peak_equity": peak,
        "profit_factor": 0.0,
        "win_rate_pct": 0.0,
        "avg_bars_held": float(np.mean([t.bars_held for t in trades])) if trades else 0.0,
        "total_fees": float(sum(t.fee for t in trades)),
    }
    wins = [t for t in trades if t.net_pnl > 0]
    losses = [t for t in trades if t.net_pnl <= 0]
    if trades:
        metrics["win_rate_pct"] = 100.0 * len(wins) / len(trades)
    gp = sum(t.net_pnl for t in wins)
    gl = abs(sum(t.net_pnl for t in losses))
    metrics["profit_factor"] = float(gp / gl) if gl > 0 else (float("inf") if gp > 0 else 0.0)

    return PortfolioResult(
        name=name,
        trades=trades,
        equity=equity,
        metrics=metrics,
        config=cfg,
        hit_target=hit_target or peak >= cfg.target_equity,
        trades_by_symbol=trades_by_symbol,
        liq_by_symbol=liq_by_symbol,
    )
