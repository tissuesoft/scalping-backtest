"""OHLCV 로더."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    colmap = {"open_time": "timestamp", "Open time": "timestamp", "Date": "timestamp"}
    out = out.rename(columns={k: v for k, v in colmap.items() if k in out.columns})
    if "timestamp" not in out.columns:
        raise ValueError("timestamp/open_time required")
    ts = out["timestamp"]
    if np.issubdtype(ts.dtype, np.number):
        unit = "ms" if float(ts.iloc[0]) > 1e12 else "s"
        out["timestamp"] = pd.to_datetime(ts, unit=unit, utc=True)
    else:
        out["timestamp"] = pd.to_datetime(ts, utc=True)
    for c in ["open", "high", "low", "close", "volume"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.dropna(subset=["timestamp", "open", "high", "low", "close"])
    out = out.sort_values("timestamp").drop_duplicates("timestamp", keep="last")
    return out.set_index("timestamp")[["open", "high", "low", "close", "volume"]]


def load_parquet_dir(data_dir: str | Path, start: Optional[str] = None, end: Optional[str] = None) -> pd.DataFrame:
    data_dir = Path(data_dir)
    files = sorted(data_dir.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(data_dir)
    if start:
        files = [f for f in files if f.stem >= pd.Timestamp(start, tz="UTC").strftime("%Y-%m")]
    if end:
        files = [f for f in files if f.stem <= pd.Timestamp(end, tz="UTC").strftime("%Y-%m")]
    df = _normalize_ohlcv(pd.concat([pd.read_parquet(f) for f in files], ignore_index=True))
    if start:
        df = df[df.index >= pd.Timestamp(start, tz="UTC")]
    if end:
        end_ts = pd.Timestamp(end, tz="UTC")
        if len(str(end)) <= 7:
            end_ts = (end_ts + pd.offsets.MonthEnd(0)).replace(hour=23, minute=59, second=59)
        df = df[df.index <= end_ts]
    return df
