"""SOL: 국면별 1m — bull/bear 모멘텀 / sideways Stoch 페이드."""
from __future__ import annotations

import numpy as np
import pandas as pd

from indicators import atr, ema, macd, sma, stochastic, volume_sma
from strategies.breakout_core import apply_cooldown
from strategies.regime import classify_regime, merge_regime_signals


def _momentum_core(df: pd.DataFrame, a: pd.Series, short_bias: bool = False) -> pd.DataFrame:
    atr_pct = a / df["close"]
    atr_ma = sma(a, 50)
    k, d = stochastic(df["high"], df["low"], df["close"], 14, 3)
    macd_line, macd_sig, hist = macd(df["close"], 12, 26, 9)
    e9 = ema(df["close"], 9)
    vol_ma = volume_sma(df["volume"], 20)

    stoch_up = (k > d) & (k.shift(1) <= d.shift(1)) & (k < 80)
    stoch_dn = (k < d) & (k.shift(1) >= d.shift(1)) & (k > 20)
    macd_bull = (hist > 0) & (macd_line > macd_sig)
    macd_bear = (hist < 0) & (macd_line < macd_sig)
    vol_expand = (a > 1.08 * atr_ma) & (atr_pct >= 0.0020)
    if short_bias:
        vol_expand = (a > 1.22 * atr_ma) & (atr_pct >= 0.0020)
    vol_ok = df["volume"] >= (1.20 * vol_ma)

    raw_long = stoch_up & macd_bull & (df["close"] > e9) & vol_expand & vol_ok & a.notna()
    raw_short = stoch_dn & macd_bear & (df["close"] < e9) & vol_expand & vol_ok & a.notna()

    if short_bias:
        raw_long = raw_long & (k < 35) & (hist > hist.shift(1))
    else:
        raw_short = raw_short & (k > 65) & (hist < hist.shift(1))

    raw_long, raw_short = apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 110, 80)

    out = pd.DataFrame(index=df.index)
    out["entry_long"] = raw_long
    out["entry_short"] = raw_short
    out["sl_long"] = df["low"] - 0.28 * a
    out["sl_short"] = df["high"] + 0.28 * a
    out["tp_long"] = np.nan
    out["tp_short"] = np.nan
    out["trail_atr"] = (1.2 * a) if short_bias else (2.6 * a)
    out["size_boost"] = np.where(atr_pct >= 0.004, 1.15, np.where(atr_pct >= 0.0025, 1.05, 1.0))
    return out


def _sideways(df: pd.DataFrame, a: pd.Series) -> pd.DataFrame:
    k, d = stochastic(df["high"], df["low"], df["close"], 14, 3)
    vol_ma = volume_sma(df["volume"], 20)
    vol_ok = df["volume"] >= (1.00 * vol_ma)

    raw_long = (k < 19) & (k > d) & (k.shift(1) <= d.shift(1)) & (k > k.shift(1)) & vol_ok & a.notna()
    raw_short = (k > 81) & (k < d) & (k.shift(1) >= d.shift(1)) & (k < k.shift(1)) & vol_ok & a.notna()
    raw_long, raw_short = apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 70, 50)

    out = pd.DataFrame(index=df.index)
    out["entry_long"] = raw_long
    out["entry_short"] = raw_short
    out["sl_long"] = df["low"] - 0.15 * a
    out["sl_short"] = df["high"] + 0.15 * a
    out["tp_long"] = np.nan
    out["tp_short"] = np.nan
    out["trail_atr"] = 0.4 * a
    out["size_boost"] = 1.0
    return out


def build_signals(df: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:
    _ = params
    a = atr(df["high"], df["low"], df["close"], 14)
    regime = classify_regime(df)
    bull = _momentum_core(df, a, short_bias=False)
    bear = _momentum_core(df, a, short_bias=True)
    return merge_regime_signals(regime, bull, bear, _sideways(df, a))
