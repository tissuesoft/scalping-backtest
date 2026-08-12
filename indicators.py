"""공통 기술적 지표."""
from __future__ import annotations

import numpy as np
import pandas as pd


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    return pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    return true_range(high, low, close).ewm(
        alpha=1 / period, adjust=False, min_periods=period
    ).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period, min_periods=period).mean()


def resample_ohlcv(df: pd.DataFrame, rule: str = "15min") -> pd.DataFrame:
    return (
        df.resample(rule, label="left", closed="left")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna(subset=["open", "high", "low", "close"])
    )


def ht_ema_on_1m(df_1m: pd.DataFrame, period: int = 200, rule: str = "15min") -> pd.Series:
    ht = resample_ohlcv(df_1m, rule)
    return ema(ht["close"], period).shift(1).reindex(df_1m.index, method="ffill")
