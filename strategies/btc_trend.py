"""BTC: 국면별 1m 단타 — bull 추세 / bear 추세 / sideways BB 페이드."""
from __future__ import annotations

import numpy as np
import pandas as pd

from indicators import atr, bollinger, ema, macd, rsi, vwap, volume_sma
from strategies.breakout_core import apply_cooldown
from strategies.regime import classify_regime, merge_regime_signals


def _bull(df: pd.DataFrame, a: pd.Series) -> pd.DataFrame:
    e9 = ema(df["close"], 9)
    e21 = ema(df["close"], 21)
    r = rsi(df["close"], 14)
    vw = vwap(df)
    vol_ma = volume_sma(df["volume"], 20)
    _macd, _sig, hist = macd(df["close"], 12, 26, 9)
    cross_up = (e9 > e21) & (e9.shift(1) <= e21.shift(1))
    cross_dn = (e9 < e21) & (e9.shift(1) >= e21.shift(1))
    vol_ok = df["volume"] >= (1.95 * vol_ma)

    raw_long = (
        cross_up & (df["close"] > vw) & (r > 48) & (r < 66) & (hist > 0) & vol_ok & a.notna()
    )
    raw_short = (
        cross_dn & (df["close"] < vw) & (r < 55) & (r > 28) & (hist < 0) & vol_ok & a.notna()
    )
    raw_long, raw_short = apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 260, 170)

    out = pd.DataFrame(index=df.index)
    out["entry_long"] = raw_long
    out["entry_short"] = raw_short
    out["sl_long"] = df["low"] - 0.2 * a
    out["sl_short"] = df["high"] + 0.2 * a
    out["tp_long"] = np.nan
    out["tp_short"] = np.nan
    out["trail_atr"] = 2.2 * a
    atr_pct = a / df["close"]
    out["size_boost"] = np.where(atr_pct >= 0.0025, 1.2, np.where(atr_pct >= 0.0015, 1.1, 1.0))
    return out


def _bear(df: pd.DataFrame, a: pd.Series) -> pd.DataFrame:
    e9 = ema(df["close"], 9)
    e21 = ema(df["close"], 21)
    r = rsi(df["close"], 14)
    vw = vwap(df)
    vol_ma = volume_sma(df["volume"], 20)
    _macd, _sig, hist = macd(df["close"], 12, 26, 9)
    cross_dn = (e9 < e21) & (e9.shift(1) >= e21.shift(1))
    cross_up = (e9 > e21) & (e9.shift(1) <= e21.shift(1))
    vol_ok = df["volume"] >= (1.55 * vol_ma)

    raw_short = (
        cross_dn & (df["close"] < vw) & (r < 52) & (r > 22) & (hist < 0) & vol_ok & a.notna()
    )
    raw_long = (
        cross_up & (df["close"] < vw) & (r < 35) & (r > r.shift(1)) & (hist > hist.shift(1)) & vol_ok & a.notna()
    )
    raw_long, raw_short = apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 180, 120)

    out = pd.DataFrame(index=df.index)
    out["entry_long"] = raw_long
    out["entry_short"] = raw_short
    out["sl_long"] = df["low"] - 0.22 * a
    out["sl_short"] = df["high"] + 0.18 * a
    out["tp_long"] = np.nan
    out["tp_short"] = np.nan
    out["trail_atr"] = 2.2 * a
    atr_pct = a / df["close"]
    out["size_boost"] = np.where(atr_pct >= 0.0025, 1.15, 1.0)
    return out


def _sideways(df: pd.DataFrame, a: pd.Series) -> pd.DataFrame:
    lower, mid, upper = bollinger(df["close"], 20, 2.0)
    r = rsi(df["close"], 14)
    vol_ma = volume_sma(df["volume"], 20)
    vol_ok = df["volume"] >= (1.45 * vol_ma)

    touch_low = df["low"] <= lower
    touch_hi = df["high"] >= upper
    bounce = (df["close"] > df["open"]) & (df["close"] > lower)
    reject = (df["close"] < df["open"]) & (df["close"] < upper)

    raw_long = touch_low & bounce & (r < 26) & (r > r.shift(1)) & vol_ok & a.notna()
    raw_short = touch_hi & reject & (r > 74) & (r < r.shift(1)) & vol_ok & a.notna()
    raw_long, raw_short = apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 90, 60)

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
