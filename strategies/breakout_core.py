"""심볼별 돌파 전략용 공통 코어 (파라미터만 다르게 호출)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from indicators import atr, ht_ema_on_1m, sma


@dataclass
class BreakoutConfig:
    lookback: int = 360
    atr_period: int = 14
    ht_ema: int = 50
    ht_ema_cap: int = 40
    ht_rule: str = "1h"
    breakout_buffer_atr: float = 0.35
    cooldown_bars: int = 240
    cooldown_cap: int = 220
    reentry_bars: int = 180
    reentry_cap: int = 170
    atr_expand_mult: float = 1.15
    atr_expand_cap: float = 1.15
    atr_sma_period: int = 200
    daily_ema_period: int = 200
    body_min_floor: float = 0.45
    vol_ok_min: float = 0.0015
    range_ok_mult: float = 0.8
    slope_diff: int = 200
    roc_period: int = 120
    trail_atr: float = 6.0
    trail_soft_cap: float = 2.9865
    width_tr_mult: float = 0.25
    n_fast_div: int = 5
    size_boost_top: float = 1.35
    size_boost_mid: float = 1.325
    size_boost_low: float = 1.10
    use_day_path: bool = True
    use_fast_donchian: bool = True


def apply_cooldown(raw_long: pd.Series, raw_short: pd.Series, cooldown: int, reentry: int) -> tuple[pd.Series, pd.Series]:
    if cooldown <= 0:
        return raw_long, raw_short
    long_arr = raw_long.to_numpy(bool).copy()
    short_arr = raw_short.to_numpy(bool).copy()
    last = -10**9
    last_side = 0
    for i in range(len(long_arr)):
        if long_arr[i] or short_arr[i]:
            side = 1 if long_arr[i] else -1
            within = i - last < cooldown
            allow_re = (
                reentry > 0
                and within
                and side == last_side
                and (i - last) <= reentry
            )
            if within and not allow_re:
                long_arr[i] = False
                short_arr[i] = False
            else:
                last = i
                last_side = side
    return pd.Series(long_arr, index=raw_long.index), pd.Series(short_arr, index=raw_short.index)


def build_breakout_signals(df: pd.DataFrame, cfg: BreakoutConfig) -> pd.DataFrame:
    n = int(cfg.lookback)
    a = atr(df["high"], df["low"], df["close"], int(cfg.atr_period))
    hh = df["high"].shift(1).rolling(n, min_periods=n).max()
    ll = df["low"].shift(1).rolling(n, min_periods=n).min()
    n_fast = max(30, n // max(cfg.n_fast_div, 1))
    hh_f = df["high"].shift(1).rolling(n_fast, min_periods=n_fast).max()
    ll_f = df["low"].shift(1).rolling(n_fast, min_periods=n_fast).min()
    ema_ht = ht_ema_on_1m(df, min(int(cfg.ht_ema), int(cfg.ht_ema_cap)), cfg.ht_rule)
    atr_pct = a / df["close"]
    buf = float(cfg.breakout_buffer_atr) * a

    expand_mult = float(cfg.atr_expand_mult)
    if expand_mult > 0:
        expand_mult = min(expand_mult, float(cfg.atr_expand_cap))
        expand_sma = a > (sma(a, int(cfg.atr_sma_period)) * expand_mult)
        expand_med = atr_pct >= atr_pct.rolling(500, min_periods=100).median()
        expand_ok = expand_sma | expand_med.fillna(False)
    else:
        expand_ok = pd.Series(True, index=df.index)

    daily_n = int(cfg.daily_ema_period or 0)
    if daily_n > 0:
        daily = df.resample("1D", label="left", closed="left").agg({"close": "last"}).dropna()
        daily_ema = daily["close"].ewm(span=daily_n, adjust=False, min_periods=daily_n).mean()
        daily_ok_bull = (daily["close"] > daily_ema).shift(1).reindex(df.index, method="ffill")
        daily_ok_bear = (daily["close"] < daily_ema).shift(1).reindex(df.index, method="ffill")
    else:
        daily_ok_bull = daily_ok_bear = pd.Series(True, index=df.index)

    body_min = max(float(cfg.body_min_floor), 0.0)
    body_ok = (
        (df["close"] - df["open"]).abs() >= (body_min * a)
        if body_min > 0
        else pd.Series(True, index=df.index)
    )

    long_brk = (df["close"] > (hh + buf))
    short_brk = (df["close"] < (ll - buf))
    if cfg.use_fast_donchian:
        long_brk = long_brk | (df["close"] > (hh_f + buf))
        short_brk = short_brk | (df["close"] < (ll_f - buf))
    if cfg.use_day_path:
        day_hi = df["high"].resample("1D", label="left", closed="left").max().shift(1).reindex(df.index, method="ffill")
        day_lo = df["low"].resample("1D", label="left", closed="left").min().shift(1).reindex(df.index, method="ffill")
        day_long = (df["close"] > (day_hi + buf)) & (df["close"].shift(1) <= (day_hi + buf))
        day_short = (df["close"] < (day_lo - buf)) & (df["close"].shift(1) >= (day_lo - buf))
        long_brk = long_brk | day_long
        short_brk = short_brk | day_short

    vol_ok = atr_pct >= float(cfg.vol_ok_min)
    range_ok = (df["high"] - df["low"]) >= (float(cfg.range_ok_mult) * a)
    ema_slope = ema_ht.diff(int(cfg.slope_diff))
    roc = df["close"].pct_change(int(cfg.roc_period))
    bull = (df["close"] > ema_ht) & (ema_slope > 0) & (roc > 0)
    bear = (df["close"] < ema_ht) & (ema_slope < 0) & (roc < 0)

    raw_long = (
        long_brk & bull & vol_ok & expand_ok & body_ok & range_ok
        & daily_ok_bull.fillna(False) & a.notna() & ema_ht.notna()
    )
    raw_short = (
        short_brk & bear & vol_ok & expand_ok & body_ok & range_ok
        & daily_ok_bear.fillna(False) & a.notna() & ema_ht.notna()
    )
    cooldown = min(int(cfg.cooldown_bars), int(cfg.cooldown_cap))
    reentry = min(int(cfg.reentry_bars), int(cfg.reentry_cap))
    raw_long, raw_short = apply_cooldown(raw_long, raw_short, cooldown, reentry)

    out = pd.DataFrame(index=df.index)
    out["entry_long"] = raw_long
    out["entry_short"] = raw_short
    out["sl_long"] = df["low"]
    out["sl_short"] = df["high"]
    out["tp_long"] = np.nan
    out["tp_short"] = np.nan

    trail = max(float(cfg.trail_atr), 0.0)
    if trail > 0:
        trail = min(trail, float(cfg.trail_soft_cap))
    base_tr = (trail * a) if trail > 0 else np.nan
    width_tr = float(cfg.width_tr_mult) * (hh - ll)
    out["trail_atr"] = np.maximum(base_tr, width_tr) if trail > 0 else np.nan

    bar_rng = df["high"] - df["low"]
    out["size_boost"] = np.where(
        bar_rng >= (1.8 * a), float(cfg.size_boost_top),
        np.where(
            bar_rng >= (1.5 * a), float(cfg.size_boost_mid),
            np.where(bar_rng >= (1.2 * a), float(cfg.size_boost_low), 1.0),
        ),
    )
    return out
