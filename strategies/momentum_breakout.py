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
    # KEEP A75/A361/A362: dual Donchian fast path
    n_fast = max(30, n // 5)  # KEEP A361/A362 (A363/A406 REVERT)
    hh_f = df["high"].shift(1).rolling(n_fast, min_periods=n_fast).max()
    ll_f = df["low"].shift(1).rolling(n_fast, min_periods=n_fast).min()
    ema_ht = ht_ema_on_1m(df, min(int(p["ht_ema"]), 40), p["ht_rule"])  # KEEP A117: faster HTF EMA than 50
    atr_pct = a / df["close"]
    buf = float(p["breakout_buffer_atr"]) * a

    expand_mult = float(p["atr_expand_mult"])
    # v2: milder expand so non-crash windows still fire
    if expand_mult > 0:
        expand_mult = min(expand_mult, 1.15)
        expand_sma = a > (sma(a, int(p["atr_sma_period"])) * expand_mult)
        # KEEP A71: OR ATR% at/above rolling median (vol regime)
        expand_med = atr_pct >= atr_pct.rolling(500, min_periods=100).median()
        expand_ok = expand_sma | expand_med.fillna(False)
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

    # KEEP A100+A104: body floor 0.45 ATR (C326 REVERT noop)
    body_min = max(float(p.get("body_min_atr", 0.0) or 0.0), 0.45)
    body_ok = (
        (df["close"] - df["open"]).abs() >= (body_min * a)
        if body_min > 0
        else pd.Series(True, index=df.index)
    )

    # KEEP A26+A28: day path = first-cross beyond day_hi/lo +/- buf
    day_hi = df["high"].resample("1D", label="left", closed="left").max().shift(1).reindex(df.index, method="ffill")
    day_lo = df["low"].resample("1D", label="left", closed="left").min().shift(1).reindex(df.index, method="ffill")
    day_long_lvl = day_hi + buf
    day_short_lvl = day_lo - buf
    day_long = (df["close"] > day_long_lvl) & (df["close"].shift(1) <= day_long_lvl)
    day_short = (df["close"] < day_short_lvl) & (df["close"].shift(1) >= day_short_lvl)
    long_brk = (df["close"] > (hh + buf)) | (df["close"] > (hh_f + buf)) | day_long
    short_brk = (df["close"] < (ll - buf)) | (df["close"] < (ll_f - buf)) | day_short
    vol_ok = atr_pct >= 0.0015  # KEEP R4: min_atr 0.0015
    range_ok = (df["high"] - df["low"]) >= (0.8 * a)  # KEEP A257: skip doji/inside-bar fake breaks
    # KEEP A35: HTF EMA slope must agree with side
    ema_slope = ema_ht.diff(200)  # KEEP A447
    # KEEP A58: ROC(120) must agree with side
    roc = df["close"].pct_change(120)  # KEEP A58 (C444 REVERT med↓ liq↑)
    bull = (df["close"] > ema_ht) & (ema_slope > 0) & (roc > 0)
    bear = (df["close"] < ema_ht) & (ema_slope < 0) & (roc < 0)
    raw_long = (
        allow_long & long_brk & bull & vol_ok & expand_ok & body_ok & range_ok
        & daily_ok_bull.fillna(False) & a.notna() & ema_ht.notna()
    )
    raw_short = (
        allow_short & short_brk & bear & vol_ok & expand_ok & body_ok & range_ok
        & daily_ok_bear.fillna(False) & a.notna() & ema_ht.notna()
    )

    cooldown = min(int(p["cooldown_bars"]), 220)  # KEEP B002
    reentry = min(int(p.get("reentry_bars", 180) or 180), 170)  # KEEP B131
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
    trail = max(float(p["trail_atr"]), 0.0)
    # A365: trail_atr floor soft-cap 5.0 (JSON 6.0) — tighter base trail before unlock
    if trail > 0:
        trail = min(trail, 2.9865)  # KEEP C184
    # KEEP A31: trail at least 25% of Donchian width
    base_tr = (trail * a) if trail > 0 else np.nan
    width_tr = 0.25 * (hh - ll)
    out["trail_atr"] = np.maximum(base_tr, width_tr) if trail > 0 else np.nan
    # KEEP A269+A277+A278+A288: 1.10@1.2ATR, 1.25@1.5ATR, 1.35@1.8ATR
    bar_rng = df["high"] - df["low"]
    out["size_boost"] = np.where(
        bar_rng >= (1.8 * a), 1.35,
        np.where(bar_rng >= (1.5 * a), 1.325, np.where(bar_rng >= (1.2 * a), 1.10, 1.0)),  # KEEP B190
    )
    return out
