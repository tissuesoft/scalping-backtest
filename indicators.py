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


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder RSI (1m 단타에서 period 7~14 흔함)."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def bollinger(
    close: pd.Series, period: int = 20, n_std: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = sma(close, period)
    std = close.rolling(period, min_periods=period).std()
    upper = mid + n_std * std
    lower = mid - n_std * std
    return lower, mid, upper


def bb_width(close: pd.Series, period: int = 20, n_std: float = 2.0) -> pd.Series:
    lower, mid, upper = bollinger(close, period, n_std)
    return (upper - lower) / mid.replace(0, np.nan)


def vwap(df: pd.DataFrame) -> pd.Series:
    """세션(UTC 일) VWAP — 1m 단타 기준선."""
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    day = df.index.floor("D")
    pv = tp * df["volume"]
    cum_pv = pv.groupby(day).cumsum()
    cum_vol = df["volume"].groupby(day).cumsum().replace(0, np.nan)
    return cum_pv / cum_vol


def stochastic(
    high: pd.Series, low: pd.Series, close: pd.Series, k_period: int = 14, d_period: int = 3
) -> tuple[pd.Series, pd.Series]:
    lowest = low.rolling(k_period, min_periods=k_period).min()
    highest = high.rolling(k_period, min_periods=k_period).max()
    k = 100.0 * (close - lowest) / (highest - lowest).replace(0, np.nan)
    d = k.rolling(d_period, min_periods=d_period).mean()
    return k, d


def macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    hist = line - sig
    return line, sig, hist


def volume_sma(volume: pd.Series, period: int = 20) -> pd.Series:
    return sma(volume, period)
