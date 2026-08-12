"""복리 엔진: equity*leverage, $0 stop, target tracking, optional pyramid."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd


@dataclass
class CompoundConfig:
    initial_capital: float = 100.0
    target_equity: float = 1_000_000.0
    leverage: float = 20.0
    fee_rate: float = 0.0004
    slippage: float = 0.0001
    mmr: float = 0.005
    same_bar_priority: str = "sl"
    max_bars: Optional[int] = None
    pyramid_at_r: float = 0.0
    pyramid_frac: float = 1.0
    pyramid_be: bool = True
    # after +unlock_r, multiply trail distance (let winners run)
    trail_unlock_r: float = 0.0
    trail_unlock_mult: float = 1.0
    # after a winning exit, multiply next entry size (anti-martingale); 1.0=off
    win_size_mult: float = 1.0
    win_size_max: float = 4.0
    # do not apply ATR trail until price moved +trail_arm_r * initial risk; 0=always trail
    trail_arm_r: float = 0.0
    # SET10: first trail touch closes frac; 0=off
    partial_trail_frac: float = 0.0


@dataclass
class Trade:
    side: int
    entry_time: pd.Timestamp
    entry_price: float
    exit_time: pd.Timestamp
    exit_price: float
    bars_held: int
    notional: float
    gross_pnl: float
    fee: float
    net_pnl: float
    return_pct: float
    exit_reason: str
    equity_after: float


@dataclass
class CompoundResult:
    name: str
    trades: List[Trade]
    equity: pd.Series
    metrics: Dict[str, float]
    config: CompoundConfig
    hit_target: bool
    time_to_target: Optional[pd.Timestamp]
    bars_to_target: Optional[int]


def _slip(price: float, side: int, is_entry: bool, slip: float) -> float:
    buy = (side == 1 and is_entry) or (side == -1 and not is_entry)
    return price * (1 + slip) if buy else price * (1 - slip)


def _compute_metrics(trades, equity, cfg, hit_target, time_to_target, bars_to_target):
    final = float(equity.iloc[-1]) if len(equity) else cfg.initial_capital
    mult = final / cfg.initial_capital if cfg.initial_capital > 0 else 0.0
    peak = equity.cummax()
    dd = (equity / peak.replace(0, np.nan) - 1.0) * 100.0
    mdd = float(dd.min()) if len(dd) else 0.0
    if trades:
        nets = np.array([t.net_pnl for t in trades])
        fees = np.array([t.fee for t in trades])
        bars = np.array([t.bars_held for t in trades], dtype=float)
        wins, losses = nets[nets > 0], nets[nets < 0]
        gp, gl = float(wins.sum()) if len(wins) else 0.0, float(-losses.sum()) if len(losses) else 0.0
        pf = (gp / gl) if gl > 0 else (999.0 if gp > 0 else 0.0)
        wr = float((nets > 0).mean() * 100.0)
        avg_bars, total_fees = float(bars.mean()), float(fees.sum())
        liq_n = sum(1 for t in trades if t.exit_reason == "liquidation")
    else:
        pf = wr = avg_bars = total_fees = 0.0
        liq_n = 0
    return {
        "final_equity": final,
        "multiple": float(mult),
        "max_drawdown_pct": mdd,
        "trades": float(len(trades)),
        "win_rate_pct": wr,
        "profit_factor": float(pf),
        "total_fees": total_fees,
        "avg_bars_held": avg_bars,
        "liquidations": float(liq_n),
        "hit_target": float(1.0 if hit_target else 0.0),
        "bars_to_target": float(bars_to_target if bars_to_target is not None else -1),
        "peak_equity": float(equity.max()) if len(equity) else final,
    }


def run_compound(df, signals, name, config=None) -> CompoundResult:
    cfg = config or CompoundConfig()
    n = len(df)
    if cfg.max_bars is not None:
        n = min(n, cfg.max_bars)
        df, signals = df.iloc[:n], signals.iloc[:n]

    open_ = df["open"].to_numpy(np.float64)
    high = df["high"].to_numpy(np.float64)
    low = df["low"].to_numpy(np.float64)
    close = df["close"].to_numpy(np.float64)
    times = df.index.to_numpy()

    entry_long = signals["entry_long"].fillna(False).to_numpy(bool)
    entry_short = signals["entry_short"].fillna(False).to_numpy(bool)
    sl_long = signals["sl_long"].to_numpy(np.float64) if "sl_long" in signals else np.full(n, np.nan)
    sl_short = signals["sl_short"].to_numpy(np.float64) if "sl_short" in signals else np.full(n, np.nan)
    tp_long = signals["tp_long"].to_numpy(np.float64) if "tp_long" in signals else np.full(n, np.nan)
    tp_short = signals["tp_short"].to_numpy(np.float64) if "tp_short" in signals else np.full(n, np.nan)
    trail_atr = signals["trail_atr"].to_numpy(np.float64) if "trail_atr" in signals else np.full(n, np.nan)

    equity = cfg.initial_capital
    eq_curve = np.zeros(n, np.float64)
    trades: List[Trade] = []
    pos_side = 0
    pos_entry = pos_i = 0.0
    pos_i = -1
    pos_sl = pos_tp = pos_notional = pos_peak = pos_risk = np.nan
    pos_pyramided = False
    pos_trail_unlocked = False
    pos_partial_done = False
    pending = 0
    pending_sl = pending_tp = np.nan
    size_mult = 1.0
    hit_target = False
    time_to_target = None
    bars_to_target = None
    liq_dist = max(1.0 / cfg.leverage - cfg.mmr, 0.01)

    for i in range(n):
        if equity <= 0:
            eq_curve[i:] = 0.0
            break

        if pending != 0 and pos_side == 0:
            fill = _slip(float(open_[i]), pending, True, cfg.slippage)
            pos_side, pos_entry, pos_i = pending, fill, i
            pos_sl, pos_tp = pending_sl, pending_tp
            pos_notional = equity * cfg.leverage * size_mult
            pos_peak = fill
            pos_risk = abs(fill - pending_sl) if not np.isnan(pending_sl) else fill * 0.01
            pos_pyramided = False
            pos_trail_unlocked = False
            pos_partial_done = False
            pending = 0

        if pos_side != 0:
            if cfg.pyramid_at_r > 0 and (not pos_pyramided) and pos_risk > 0:
                move = (high[i] - pos_entry) if pos_side == 1 else (pos_entry - low[i])
                if move >= cfg.pyramid_at_r * pos_risk:
                    add_px = _slip(float(close[i]), pos_side, True, cfg.slippage)
                    add_n = pos_notional * cfg.pyramid_frac
                    equity = max(equity - add_n * cfg.fee_rate, 0.0)
                    new_n = pos_notional + add_n
                    pos_entry = (pos_entry * pos_notional + add_px * add_n) / new_n
                    pos_notional = new_n
                    pos_pyramided = True
                    if cfg.pyramid_be:
                        pos_sl = pos_entry

            tr = trail_atr[i]
            move_now = (high[i] - pos_entry) if pos_side == 1 else (pos_entry - low[i])
            trail_armed = (cfg.trail_arm_r <= 0) or (pos_risk > 0 and move_now >= cfg.trail_arm_r * pos_risk)
            if cfg.trail_unlock_r > 0 and pos_risk > 0 and (not np.isnan(tr)):
                if move_now >= cfg.trail_unlock_r * pos_risk:
                    pos_trail_unlocked = True
            if pos_trail_unlocked and not np.isnan(tr):
                tr = tr * cfg.trail_unlock_mult

            if pos_side == 1:
                pos_peak = max(pos_peak, high[i])
                if trail_armed and (not np.isnan(tr)) and tr > 0:
                    trail_sl = pos_peak - tr
                    if np.isnan(pos_sl) or trail_sl > pos_sl:
                        pos_sl = trail_sl
                hit_sl = (not np.isnan(pos_sl)) and low[i] <= pos_sl
                hit_tp = (not np.isnan(pos_tp)) and high[i] >= pos_tp
                liq_px = pos_entry * (1.0 - liq_dist)
                hit_liq = low[i] <= liq_px
            else:
                pos_peak = min(pos_peak, low[i])
                if trail_armed and (not np.isnan(tr)) and tr > 0:
                    trail_sl = pos_peak + tr
                    if np.isnan(pos_sl) or trail_sl < pos_sl:
                        pos_sl = trail_sl
                hit_sl = (not np.isnan(pos_sl)) and high[i] >= pos_sl
                hit_tp = (not np.isnan(pos_tp)) and low[i] <= pos_tp
                liq_px = pos_entry * (1.0 + liq_dist)
                hit_liq = high[i] >= liq_px

            reason = exit_px = None
            if hit_liq:
                reason, exit_px = "liquidation", liq_px
            elif hit_sl and hit_tp:
                reason, exit_px = ("sl", pos_sl) if cfg.same_bar_priority == "sl" else ("tp", pos_tp)
            elif hit_sl:
                reason, exit_px = "sl", pos_sl
            elif hit_tp:
                reason, exit_px = "tp", pos_tp

            if reason is not None:
                # partial trail: first SL while in profit closes only frac
                in_profit = (pos_side == 1 and float(exit_px) > pos_entry) or (
                    pos_side == -1 and float(exit_px) < pos_entry
                )
                do_partial = (
                    cfg.partial_trail_frac > 0
                    and cfg.partial_trail_frac < 1
                    and (not pos_partial_done)
                    and reason == "sl"
                    and in_profit
                )
                close_frac = cfg.partial_trail_frac if do_partial else 1.0
                fill = _slip(float(exit_px), pos_side, False, cfg.slippage)
                ret = pos_side * (fill / pos_entry - 1.0)
                notion = pos_notional * close_frac
                gross = notion * ret
                fee = notion * cfg.fee_rate * (1.0 if do_partial else 2.0)
                if do_partial:
                    # entry fee already conceptually on full; charge exit fee on partial only
                    fee = notion * cfg.fee_rate
                if reason == "liquidation":
                    net = -equity * 0.99
                    close_frac = 1.0
                    do_partial = False
                else:
                    net = gross - fee
                equity = max(equity + net, 0.0)
                if (not do_partial):
                    if net > 0:
                        size_mult = min(size_mult * cfg.win_size_mult, cfg.win_size_max)
                    else:
                        size_mult = 1.0
                trades.append(
                    Trade(
                        side=pos_side,
                        entry_time=pd.Timestamp(times[pos_i]),
                        entry_price=pos_entry,
                        exit_time=pd.Timestamp(times[i]),
                        exit_price=fill,
                        bars_held=i - pos_i,
                        notional=notion,
                        gross_pnl=gross,
                        fee=fee,
                        net_pnl=net,
                        return_pct=ret * 100.0,
                        exit_reason=("trail_partial" if do_partial else reason),
                        equity_after=equity,
                    )
                )
                if do_partial:
                    pos_notional *= (1.0 - close_frac)
                    pos_partial_done = True
                    pos_sl = pos_entry  # BE for runner
                else:
                    pos_side = 0

        if pos_side == 0 and pending == 0 and i < n - 1 and equity > 0:
            if entry_long[i] and not entry_short[i]:
                pending, pending_sl, pending_tp = 1, sl_long[i], tp_long[i]
            elif entry_short[i] and not entry_long[i]:
                pending, pending_sl, pending_tp = -1, sl_short[i], tp_short[i]

        eq_curve[i] = equity
        if (not hit_target) and equity >= cfg.target_equity:
            hit_target, time_to_target, bars_to_target = True, pd.Timestamp(times[i]), i

    if pos_side != 0 and equity > 0:
        i = n - 1
        fill = _slip(float(close[i]), pos_side, False, cfg.slippage)
        ret = pos_side * (fill / pos_entry - 1.0)
        gross = pos_notional * ret
        fee = pos_notional * cfg.fee_rate * 2.0
        net = gross - fee
        equity = max(equity + net, 0.0)
        eq_curve[i] = equity
        if net > 0:
            size_mult = min(size_mult * cfg.win_size_mult, cfg.win_size_max)
        else:
            size_mult = 1.0
        trades.append(
            Trade(
                side=pos_side,
                entry_time=pd.Timestamp(times[pos_i]),
                entry_price=pos_entry,
                exit_time=pd.Timestamp(times[i]),
                exit_price=fill,
                bars_held=i - pos_i,
                notional=pos_notional,
                gross_pnl=gross,
                fee=fee,
                net_pnl=net,
                return_pct=ret * 100.0,
                exit_reason="eod",
                equity_after=equity,
            )
        )

    eq = pd.Series(eq_curve, index=df.index, name="equity")
    metrics = _compute_metrics(trades, eq, cfg, hit_target, time_to_target, bars_to_target)
    return CompoundResult(name, trades, eq, metrics, cfg, hit_target, time_to_target, bars_to_target)
