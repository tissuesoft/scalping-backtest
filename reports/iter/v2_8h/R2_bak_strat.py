"""전 구간 커버용 레짐 브레이크아웃 (v2).

목표: 모든 1~2개월 창에서 $100 → 10,000x.
v1(숏 전용 + 폭락 size_boost)은 한 창 max만 키워 폐기.

규칙:
- 일봉 EMA 레짐 + HTF EMA 정렬된 쪽으로만 진입 (롱/숏 둘 다)
- Donchian 돌파 + 최소 ATR + (완화된) ATR 확장
- 구조 SL(시그널 봉 wick), ATR 트레일
- size_boost 없음 (전 구간 균일 사이징)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from indicators import atr, ht_ema_on_1m, sma

DEFAULT_PARAMS = {
    "lookback": 360,
    "atr_period": 14,
    "min_atr_pct": 0.0008,
    "sl_atr": 0.8,
    "trail_atr": 6.0,
    "ht_ema": 50,
    "ht_rule": "1h",
    "breakout_buffer_atr": 0.35,
    "cooldown_bars": 240,
    "atr_expand_mult": 1.15,
    "atr_sma_period": 200,
    "daily_ema_period": 200,
    "tp_atr": 0.0,
    "body_min_atr": 0.0,
    "reentry_bars": 180,
    "allow_long": True,
    "allow_short": True,
}


def build_signals(df: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:
    p = dict(DEFAULT_PARAMS)
    if params:
        p.update(params)

    # v2: force dual-side regime trading regardless of stale champion JSON flags
    allow_long = True
    allow_short = True

    n = int(p["lookback"])
    a = atr(df["high"], df["low"], df["close"], int(p["atr_period"]))
    hh = df["high"].shift(1).rolling(n, min_periods=n).max()
    ll = df["low"].shift(1).rolling(n, min_periods=n).min()
    ema_ht = ht_ema_on_1m(df, int(p["ht_ema"]), p["ht_rule"])
    atr_pct = a / df["close"]
    buf = float(p["breakout_buffer_atr"]) * a

    expand_mult = float(p["atr_expand_mult"])
    # v2: milder expand so non-crash windows still fire
    if expand_mult > 0:
        expand_mult = min(expand_mult, 1.15)
        expand_ok = a > (sma(a, int(p["atr_sma_period"])) * expand_mult)
    else:
        expand_ok = pd.Series(True, index=df.index)

    daily_n = int(p.get("daily_ema_period", 0) or 0)
    if daily_n > 0:
        daily = df.resample("1D", label="left", closed="left").agg({"close": "last"}).dropna()
        daily_ema = daily["close"].ewm(span=daily_n, adjust=False, min_periods=daily_n).mean()
        daily_ok_bull = (daily["close"] > daily_ema).shift(1).reindex(df.index, method="ffill")
        daily_ok_bear = (daily["close"] < daily_ema).shift(1).reindex(df.index, method="ffill")
    else:
        daily_ok_bull = daily_ok_bear = pd.Series(True, index=df.index)

    body_min = float(p.get("body_min_atr", 0.0) or 0.0)
    body_ok = (
        (df["close"] - df["open"]).abs() >= (body_min * a)
        if body_min > 0
        else pd.Series(True, index=df.index)
    )

    long_brk = df["close"] > (hh + buf)
    short_brk = df["close"] < (ll - buf)
    vol_ok = atr_pct >= float(p["min_atr_pct"])
    bull = df["close"] > ema_ht
    bear = df["close"] < ema_ht

    raw_long = (
        allow_long & long_brk & bull & vol_ok & expand_ok & body_ok
        & daily_ok_bull.fillna(False) & a.notna() & ema_ht.notna()
    )
    raw_short = (
        allow_short & short_brk & bear & vol_ok & expand_ok & body_ok
        & daily_ok_bear.fillna(False) & a.notna() & ema_ht.notna()
    )

    cooldown = int(p["cooldown_bars"])
    reentry = int(p.get("reentry_bars", 180) or 180)
    if cooldown > 0:
        long_arr = raw_long.to_numpy(bool).copy()
        short_arr = raw_short.to_numpy(bool).copy()
        last = -10**9
        last_side = 0
        for i in range(len(long_arr)):
            if long_arr[i] or short_arr[i]:
                side = 1 if long_arr[i] else -1
                within = i - last < cooldown
                allow_re = (
                    reentry > 0
                    and within
                    and side == last_side
                    and (i - last) <= reentry
                )
                if within and not allow_re:
                    long_arr[i] = False
                    short_arr[i] = False
                else:
                    last = i
                    last_side = side
        raw_long = pd.Series(long_arr, index=df.index)
        raw_short = pd.Series(short_arr, index=df.index)

    out = pd.DataFrame(index=df.index)
    out["entry_long"] = raw_long
    out["entry_short"] = raw_short
    out["sl_long"] = df["low"]
    out["sl_short"] = df["high"]
    tp_atr = float(p.get("tp_atr", 0.0) or 0.0)
    if tp_atr > 0:
        out["tp_long"] = df["close"] + tp_atr * a
        out["tp_short"] = df["close"] - tp_atr * a
    else:
        out["tp_long"] = np.nan
        out["tp_short"] = np.nan
    trail = float(p["trail_atr"])
    out["trail_atr"] = (trail * a) if trail > 0 else np.nan
    # v2: uniform size — no crash boost
    out["size_boost"] = 1.0
    return out
