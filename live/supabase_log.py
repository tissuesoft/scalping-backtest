"""Supabase logging for PORT5 demo (dedicated project: scalping-backtest).

Env:
  SUPABASE_URL
  SUPABASE_ANON_KEY  (or SUPABASE_SERVICE_ROLE_KEY)

Tables:
  trade_events        ENTRY / SL / TP / TRAIL
  market_snapshots    1m OHLCV + indicators + regime
  ohlcv_bars          raw 1m candles
  runner_heartbeats   equity / open slots
"""
from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from indicators import atr, bollinger, ema, macd, rsi, volume_sma
from strategies.regime import classify_regime

BOT_ID = "scalping-backtest"


def _finite(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _ts_iso(ts: pd.Timestamp | datetime | None) -> str | None:
    if ts is None:
        return None
    if isinstance(ts, pd.Timestamp):
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        return ts.isoformat()
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).isoformat()


class SupabaseLogger:
    """PostgREST client; no-op if env missing. No extra pip package."""

    def __init__(self, *, dry_run: bool = False) -> None:
        self.url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
        self.key = (
            os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or ""
        ).strip()
        self.dry_run = bool(dry_run)
        self.enabled = bool(self.url and self.key)
        self._seeded = False
        if self.enabled:
            print(
                f"[supabase] enabled {self.url} bot={BOT_ID} dry_run={self.dry_run}",
                flush=True,
            )
        else:
            print("[supabase] disabled (set SUPABASE_URL + SUPABASE_ANON_KEY)", flush=True)

    def _request(
        self,
        method: str,
        path: str,
        payload: Any = None,
        *,
        prefer: str = "return=minimal",
        query: str = "",
    ) -> Any:
        if not self.enabled:
            return None
        qs = f"?{query}" if query else ""
        url = f"{self.url}/rest/v1/{path}{qs}"
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": prefer,
        }
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            print(f"[supabase] {method} {path} HTTP {e.code}: {body[:400]}", flush=True)
            return None
        except Exception as e:
            print(f"[supabase] {method} {path} error: {e}", flush=True)
            return None

    def insert_event(self, record: dict[str, Any]) -> int | None:
        payload = {k: v for k, v in record.items() if v is not None}
        payload.setdefault("bot", BOT_ID)
        payload.setdefault("timeframe", "1m")
        payload.setdefault("dry_run", self.dry_run)
        # Practice mode must not land in the live trade log.
        if payload.get("dry_run"):
            return None
        data = self._request(
            "POST",
            "trade_events",
            payload,
            prefer="return=representation",
        )
        if isinstance(data, list) and data and isinstance(data[0], dict) and "id" in data[0]:
            return int(data[0]["id"])
        return None

    def upsert_snapshot(self, record: dict[str, Any]) -> None:
        payload = {k: v for k, v in record.items() if v is not None}
        payload.setdefault("bot", BOT_ID)
        self._request(
            "POST",
            "market_snapshots",
            payload,
            prefer="resolution=merge-duplicates,return=minimal",
            query="on_conflict=symbol,timeframe,timestamp",
        )

    def upsert_ohlcv_bars(self, symbol: str, df: pd.DataFrame, *, last_n: int | None = None) -> int:
        if df is None or df.empty:
            return 0
        use = df.tail(last_n) if last_n else df
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        payload = []
        for ts, row in use.iterrows():
            payload.append(
                {
                    "symbol": symbol,
                    "interval": "1m",
                    "open_time": int(pd.Timestamp(ts).timestamp() * 1000),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                    "quote_volume": float(row["quote_volume"]) if "quote_volume" in use.columns else None,
                    "updated_at": now_iso,
                }
            )
        n = 0
        for i in range(0, len(payload), 500):
            chunk = payload[i : i + 500]
            res = self._request(
                "POST",
                "ohlcv_bars",
                chunk,
                prefer="resolution=merge-duplicates,return=minimal",
                query="on_conflict=symbol,interval,open_time",
            )
            if res is None and not self.enabled:
                return n
            n += len(chunk)
        return n

    def insert_heartbeat(self, record: dict[str, Any]) -> None:
        payload = {k: v for k, v in record.items() if v is not None}
        payload.setdefault("bot", BOT_ID)
        self._request("POST", "runner_heartbeats", payload)

    def seed_frames_once(self, frames: dict[str, pd.DataFrame]) -> None:
        if self._seeded or not self.enabled:
            return
        self._seeded = True
        for sym, df in frames.items():
            n = self.upsert_ohlcv_bars(sym, df)
            print(f"[supabase] seed ohlcv {sym} n={n}", flush=True)


def bar_context(df: pd.DataFrame, *, timeframe: str = "1m") -> dict[str, Any]:
    """Indicators + regime for the last closed bar."""
    bar = df.iloc[-1]
    ts = df.index[-1]
    close = _finite(bar["close"])
    high = _finite(bar["high"])
    low = _finite(bar["low"])
    a = atr(df["high"], df["low"], df["close"], 14)
    r = rsi(df["close"], 14)
    bb_l, bb_m, bb_u = bollinger(df["close"], 20, 2.0)
    e20 = ema(df["close"], 20)
    e50 = ema(df["close"], 50)
    macd_line, macd_sig, hist = macd(df["close"])
    vma = volume_sma(df["volume"], 20)
    vol = _finite(bar["volume"])
    atr_v = _finite(a.iloc[-1]) if len(a) else None
    rsi_v = _finite(r.iloc[-1]) if len(r) else None
    bb_u_v = _finite(bb_u.iloc[-1])
    bb_m_v = _finite(bb_m.iloc[-1])
    bb_l_v = _finite(bb_l.iloc[-1])
    bb_pos = None
    if close is not None and bb_u_v is not None and bb_l_v is not None and bb_u_v != bb_l_v:
        ratio = (close - bb_l_v) / (bb_u_v - bb_l_v)
        if ratio >= 0.8:
            bb_pos = "upper"
        elif ratio <= 0.2:
            bb_pos = "lower"
        else:
            bb_pos = "middle"
    hist_v = _finite(hist.iloc[-1])
    vol_ma = _finite(vma.iloc[-1]) if len(vma) else None
    regime = None
    try:
        regime = str(classify_regime(df).iloc[-1])
    except Exception:
        regime = None
    return {
        "high_price": high,
        "low_price": low,
        "close_price": close,
        "volume": vol,
        "timeframe": timeframe,
        "market_timestamp": _ts_iso(ts),
        "rsi": rsi_v,
        "rsi_overbought": (rsi_v is not None and rsi_v >= 70),
        "rsi_oversold": (rsi_v is not None and rsi_v <= 30),
        "macd_value": _finite(macd_line.iloc[-1]),
        "macd_signal": _finite(macd_sig.iloc[-1]),
        "macd_histogram": hist_v,
        "macd_cross": ("bullish" if hist_v is not None and hist_v > 0 else "bearish" if hist_v is not None else None),
        "ema20": _finite(e20.iloc[-1]),
        "ema50": _finite(e50.iloc[-1]),
        "ema_distance_percent": (
            ((close / float(e20.iloc[-1])) - 1.0) * 100.0
            if close and _finite(e20.iloc[-1])
            else None
        ),
        "bb_upper": bb_u_v,
        "bb_middle": bb_m_v,
        "bb_lower": bb_l_v,
        "bb_position": bb_pos,
        "atr_value": atr_v,
        "atr_percent_of_price": (atr_v / close * 100.0) if atr_v and close else None,
        "volume_ma": vol_ma,
        "volume_spike_ratio": (vol / vol_ma) if vol and vol_ma else None,
        "regime": regime,
    }


def snapshot_from_df(symbol: str, df: pd.DataFrame) -> dict[str, Any]:
    ctx = bar_context(df)
    ts = df.index[-1]
    bar = df.iloc[-1]
    close_ts = pd.Timestamp(ts) + pd.Timedelta(minutes=1)
    return {
        "symbol": symbol,
        "timeframe": "1m",
        "timestamp": _ts_iso(close_ts),
        "open": _finite(bar["open"]),
        "high": ctx.get("high_price"),
        "low": ctx.get("low_price"),
        "close": ctx.get("close_price"),
        "volume": ctx.get("volume"),
        "rsi": ctx.get("rsi"),
        "macd": ctx.get("macd_value"),
        "ema20": ctx.get("ema20"),
        "ema50": ctx.get("ema50"),
        "atr": ctx.get("atr_value"),
        "bb_upper": ctx.get("bb_upper"),
        "bb_middle": ctx.get("bb_middle"),
        "bb_lower": ctx.get("bb_lower"),
        "bb_position": ctx.get("bb_position"),
        "volume_ma": ctx.get("volume_ma"),
        "volume_spike_ratio": ctx.get("volume_spike_ratio"),
        "regime": ctx.get("regime"),
        "bot": BOT_ID,
    }


def exit_event_type(reason: str) -> str:
    return {
        "sl": "SL",
        "sl_tick": "SL",
        "tp": "TP_FULL",
        "trail_partial": "TRAIL",
        "liquidation": "LIQ",
    }.get(reason, reason.upper())
