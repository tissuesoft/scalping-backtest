"""Kline → DataFrame + strategy signals (closed bar only)."""
from __future__ import annotations

import pandas as pd

from strategies.registry import build_symbol_signals


def klines_to_df(rows: list) -> pd.DataFrame:
    """Binance kline array → OHLCV indexed by open time (UTC)."""
    if not rows:
        raise ValueError("empty klines")
    df = pd.DataFrame(
        rows,
        columns=[
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_volume",
            "trades",
            "taker_buy_base",
            "taker_buy_quote",
            "ignore",
        ],
    )
    for c in ("open", "high", "low", "close", "volume", "quote_volume"):
        df[c] = df[c].astype(float)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df.set_index("open_time").sort_index()
    # drop forming candle: last row may still be open
    if len(df) >= 2:
        df = df.iloc[:-1].copy()
    return df[["open", "high", "low", "close", "volume", "quote_volume"]]


def build_closed_signals(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    sig = build_symbol_signals(symbol, df)
    return sig
