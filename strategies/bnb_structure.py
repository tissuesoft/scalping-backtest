"""BNB: 국면별 1m — bull 돌파 / bear 돌파 / sideways 밴드 페이드."""
from __future__ import annotations

import numpy as np
import pandas as pd

from indicators import atr, bb_width, bollinger, rsi, vwap, volume_sma
from strategies.breakout_core import apply_cooldown
from strategies.regime import classify_regime, merge_regime_signals


def _shared_bb(df: pd.DataFrame, a: pd.Series):
    lower, mid, upper = bollinger(df["close"], 20, 2.0)
    width = bb_width(df["close"], 20, 2.0)
    width_ma = width.rolling(100, min_periods=50).mean()
    r = rsi(df["close"], 14)
    vw = vwap(df)
    vol_ma = volume_sma(df["volume"], 20)
    vol_ok = df["volume"] >= (1.35 * vol_ma)
    body_ok = (df["close"] - df["open"]).abs() >= (0.40 * a)
    squeeze = width < (0.92 * width_ma)
    break_up = (df["close"] > upper) & (df["close"].shift(1) <= upper.shift(1))
    break_dn = (df["close"] < lower) & (df["close"].shift(1) >= lower.shift(1))
    return lower, mid, upper, r, vw, vol_ok, body_ok, squeeze, break_up, break_dn


def _bull(df: pd.DataFrame, a: pd.Series) -> pd.DataFrame:
    lower, mid, upper, r, vw, _vol_ok, body_ok, squeeze, break_up, break_dn = _shared_bb(df, a)
    body_strict = (df["close"] - df["open"]).abs() >= (0.60 * a)
    vol_ok = df["volume"] >= (2.05 * volume_sma(df["volume"], 20))  # P1084: skip thin BNB breakouts

    raw_long = (
        break_up
        & (r > 52) & (r < 72) & (df["close"] > mid) & (df["close"] > vw) & vol_ok & body_strict & a.notna()
    )
    raw_short = pd.Series(False, index=df.index)
    raw_long, raw_short = apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 300, 190)

    out = pd.DataFrame(index=df.index)
    out["entry_long"] = raw_long
    out["entry_short"] = raw_short
    out["sl_long"] = np.minimum(df["low"], mid) - 0.22 * a
    out["sl_short"] = np.maximum(df["high"], mid) + 0.22 * a
    out["tp_long"] = np.nan
    out["tp_short"] = np.nan
    out["trail_atr"] = np.maximum(2.2 * a, 0.45 * (upper - lower))
    atr_pct = a / df["close"]
    out["size_boost"] = np.where(atr_pct >= 0.0022, 1.18, 1.0)
    return out


def _bear(df: pd.DataFrame, a: pd.Series) -> pd.DataFrame:
    lower, mid, upper, r, vw, vol_ok, body_ok, squeeze, break_up, break_dn = _shared_bb(df, a)

    raw_short = (
        break_dn
        & (r < 42) & (r > 18) & (df["close"] < mid) & (df["close"] < vw) & vol_ok & body_ok & a.notna()
    )
    raw_long = pd.Series(False, index=df.index)  # P1072: no breakout longs in bear
    raw_long, raw_short = apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 260, 160)

    out = pd.DataFrame(index=df.index)
    out["entry_long"] = raw_long
    out["entry_short"] = raw_short
    out["sl_long"] = np.minimum(df["low"], mid) - 0.15 * a
    out["sl_short"] = np.maximum(df["high"], mid) + 0.15 * a
    out["tp_long"] = np.nan
    out["tp_short"] = np.nan
    out["trail_atr"] = np.maximum(0.9 * a, 0.35 * (upper - lower))
    atr_pct = a / df["close"]
    out["size_boost"] = np.where(atr_pct >= 0.0022, 1.18, 1.0)
    return out


def _sideways(df: pd.DataFrame, a: pd.Series) -> pd.DataFrame:
    lower, mid, upper, r, vw, _vol_ok, _body_ok, _squeeze, _break_up, _break_dn = _shared_bb(df, a)
    vol_ma = volume_sma(df["volume"], 20)
    vol_ok = df["volume"] >= (1.55 * vol_ma)  # P1069: skip thin BNB fades

    touch_low = df["low"] <= lower
    touch_hi = df["high"] >= upper
    raw_long = touch_low & (r < 22) & (r > r.shift(1)) & (df["close"] > df["open"]) & (df["close"] > vw) & vol_ok & a.notna()
    raw_short = touch_hi & (r > 78) & (r < r.shift(1)) & (df["close"] < df["open"]) & (df["close"] < vw) & vol_ok & a.notna()
    raw_long, raw_short = apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 200, 130)

    out = pd.DataFrame(index=df.index)
    out["entry_long"] = raw_long
    out["entry_short"] = raw_short
    out["sl_long"] = np.minimum(df["low"], lower) - 0.12 * a
    out["sl_short"] = np.maximum(df["high"], upper) + 0.12 * a
    out["tp_long"] = mid
    out["tp_short"] = mid
    out["trail_atr"] = 0.5 * a
    out["size_boost"] = 1.0
    return out


def build_signals(df: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:
    _ = params
    a = atr(df["high"], df["low"], df["close"], 14)
    regime = classify_regime(df)
    return merge_regime_signals(regime, _bull(df, a), _bear(df, a), _sideways(df, a))
