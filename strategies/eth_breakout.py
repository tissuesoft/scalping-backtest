"""ETH: 국면별 1m — bull 모멘텀 / bear 모멘텀 / sideways RSI 페이드."""
from __future__ import annotations

import numpy as np
import pandas as pd

from indicators import atr, bollinger, ema, rsi, vwap, volume_sma
from strategies.breakout_core import apply_cooldown
from strategies.regime import classify_regime, merge_regime_signals


def _bull(df: pd.DataFrame, a: pd.Series) -> pd.DataFrame:
    e8 = ema(df["close"], 8)
    e21 = ema(df["close"], 21)
    r = rsi(df["close"], 7)
    vw = vwap(df)
    vol_ma = volume_sma(df["volume"], 20)
    vol_ok = df["volume"] >= (1.25 * vol_ma)

    rsi_up = (r > 64) & (r.shift(1) <= 64) & (r < 75)
    rsi_dn = (r < 45) & (r.shift(1) >= 45) & (r > 25)
    raw_long = rsi_up & (df["close"] > e8) & (e8 > e21) & (df["close"] > vw) & vol_ok & a.notna()
    raw_short = rsi_dn & (df["close"] < e8) & (e8 < e21) & (df["close"] < vw) & vol_ok & a.notna()
    raw_long, raw_short = apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 150, 100)

    out = pd.DataFrame(index=df.index)
    out["entry_long"] = raw_long
    out["entry_short"] = raw_short
    out["sl_long"] = df["low"] - 0.12 * a
    out["sl_short"] = df["high"] + 0.12 * a
    out["tp_long"] = np.nan
    out["tp_short"] = np.nan
    out["trail_atr"] = 1.2 * a
    atr_pct = a / df["close"]
    out["size_boost"] = np.where(atr_pct >= 0.003, 1.25, np.where(atr_pct >= 0.0018, 1.08, 1.0))
    return out


def _bear(df: pd.DataFrame, a: pd.Series) -> pd.DataFrame:
    e8 = ema(df["close"], 8)
    e21 = ema(df["close"], 21)
    r = rsi(df["close"], 7)
    vw = vwap(df)
    vol_ma = volume_sma(df["volume"], 20)
    vol_ok = df["volume"] >= (1.25 * vol_ma)

    rsi_dn = (r < 45) & (r.shift(1) >= 45) & (r > 25)
    rsi_up = (r > 55) & (r.shift(1) <= 55) & (r < 65)
    raw_short = rsi_dn & (df["close"] < e8) & (e8 < e21) & (df["close"] < vw) & vol_ok & a.notna()
    raw_long = rsi_up & (df["close"] > vw) & (r < 40) & (e8 < e21) & vol_ok & a.notna()
    raw_long, raw_short = apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 110, 75)

    out = pd.DataFrame(index=df.index)
    out["entry_long"] = raw_long
    out["entry_short"] = raw_short
    out["sl_long"] = df["low"] - 0.16 * a
    out["sl_short"] = df["high"] + 0.14 * a
    out["tp_long"] = np.nan
    out["tp_short"] = np.nan
    out["trail_atr"] = 1.5 * a
    atr_pct = a / df["close"]
    out["size_boost"] = np.where(atr_pct >= 0.003, 1.12, 1.0)
    return out


def _sideways(df: pd.DataFrame, a: pd.Series) -> pd.DataFrame:
    lower, mid, upper = bollinger(df["close"], 20, 2.0)
    r = rsi(df["close"], 7)
    vol_ma = volume_sma(df["volume"], 20)
    vol_ok = df["volume"] >= (1.90 * vol_ma)

    raw_long = (df["low"] <= lower) & (r < 20) & (r > r.shift(1)) & (df["close"] > df["open"]) & vol_ok & a.notna()
    raw_short = (df["high"] >= upper) & (r > 80) & (r < r.shift(1)) & (df["close"] < df["open"]) & vol_ok & a.notna()
    raw_long, raw_short = apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 260, 160)

    out = pd.DataFrame(index=df.index)
    out["entry_long"] = raw_long
    out["entry_short"] = raw_short
    out["sl_long"] = np.minimum(df["low"], lower) - 0.12 * a
    out["sl_short"] = np.maximum(df["high"], upper) + 0.12 * a
    out["tp_long"] = mid
    out["tp_short"] = mid
    out["trail_atr"] = 0.6 * a
    out["size_boost"] = 1.0
    return out


def build_signals(df: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:
    _ = params
    a = atr(df["high"], df["low"], df["close"], 14)
    regime = classify_regime(df)
    return merge_regime_signals(regime, _bull(df, a), _bear(df, a), _sideways(df, a))
