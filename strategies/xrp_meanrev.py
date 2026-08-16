"""XRP: 국면별 1m — bull/bear 추세 되돌림 / sideways BB+RSI 페이드."""
from __future__ import annotations

import numpy as np
import pandas as pd

from indicators import atr, bollinger, ema, rsi, volume_sma
from strategies.breakout_core import apply_cooldown
from strategies.regime import classify_regime, merge_regime_signals


def _sideways(df: pd.DataFrame, a: pd.Series) -> pd.DataFrame:
    lower, mid, upper = bollinger(df["close"], 20, 2.0)
    r = rsi(df["close"], 14)
    vol_ma = volume_sma(df["volume"], 20)
    vol_ok = df["volume"] >= (1.3 * vol_ma)  # P1018: skip weak fades

    touch_low = df["low"] <= lower
    touch_hi = df["high"] >= upper
    bounce = (df["close"] > df["open"]) & (df["close"] > lower)
    reject = (df["close"] < df["open"]) & (df["close"] < upper)

    raw_long = (
        touch_low & bounce & (r < 25) & (r > 10) & (r > r.shift(1))
        & (df["close"] < mid) & vol_ok & a.notna()
    )
    raw_short = (
        touch_hi & reject & (r > 72) & (r < 88) & (r < r.shift(1))
        & (df["close"] > mid) & vol_ok & a.notna()
    )
    raw_long, raw_short = apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 100, 65)

    out = pd.DataFrame(index=df.index)
    out["entry_long"] = raw_long
    out["entry_short"] = raw_short
    out["sl_long"] = np.minimum(df["low"], lower) - 0.1 * a
    out["sl_short"] = np.maximum(df["high"], upper) + 0.1 * a
    out["tp_long"] = mid
    out["tp_short"] = mid
    out["trail_atr"] = 0.6 * a
    atr_pct = a / df["close"]
    out["size_boost"] = np.where(atr_pct >= 0.0028, 1.1, 1.0)
    return out


def _bull(df: pd.DataFrame, a: pd.Series) -> pd.DataFrame:
    e21 = ema(df["close"], 21)
    r = rsi(df["close"], 14)
    vol_ma = volume_sma(df["volume"], 20)
    vol_ok = df["volume"] >= (1.0 * vol_ma)

    dip = (df["close"] > e21) & (r < 45) & (r > r.shift(1)) & (r > 30)
    ext = (df["close"] > e21) & (r > 78) & (r < r.shift(1))
    raw_long = dip & vol_ok & a.notna()
    raw_short = ext & vol_ok & a.notna()
    raw_long, raw_short = apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 90, 60)

    out = pd.DataFrame(index=df.index)
    out["entry_long"] = raw_long
    out["entry_short"] = raw_short
    out["sl_long"] = df["low"] - 0.15 * a
    out["sl_short"] = df["high"] + 0.15 * a
    out["tp_long"] = np.nan
    out["tp_short"] = np.nan
    out["trail_atr"] = 2.2 * a
    out["size_boost"] = 1.0
    return out


def _bear(df: pd.DataFrame, a: pd.Series) -> pd.DataFrame:
    e21 = ema(df["close"], 21)
    r = rsi(df["close"], 14)
    vol_ma = volume_sma(df["volume"], 20)
    vol_ok = df["volume"] >= (1.0 * vol_ma)

    rally = (df["close"] < e21) & (r > 55) & (r < r.shift(1)) & (r < 70)
    raw_short = rally & vol_ok & a.notna()
    raw_long = pd.Series(False, index=df.index)  # P1025: no dump-bounce longs in bear
    raw_long, raw_short = apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 90, 60)

    out = pd.DataFrame(index=df.index)
    out["entry_long"] = raw_long
    out["entry_short"] = raw_short
    out["sl_long"] = df["low"] - 0.15 * a
    out["sl_short"] = df["high"] + 0.15 * a
    out["tp_long"] = np.nan
    out["tp_short"] = np.nan
    out["trail_atr"] = 1.6 * a
    out["size_boost"] = 1.0
    return out


def build_signals(df: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:
    _ = params
    a = atr(df["high"], df["low"], df["close"], 14)
    regime = classify_regime(df)
    return merge_regime_signals(regime, _bull(df, a), _bear(df, a), _sideways(df, a))
