"""P3208-champion-aligned mutation pool (hits32 med12068 min245; summer SOL/BNB focus)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Mutation:
    mid: str
    axis: str
    hypothesis: str
    file: str
    old: str
    new: str


def mutations() -> list[Mutation]:
    m: list[Mutation] = []

    def add(mid, axis, hyp, file, old, new):
        m.append(Mutation(mid, axis, hyp, file, old, new))

    # ===== BNB side (summer) =====
    add(
        "bnb_side_stoch_body_0.25",
        "bnb_side",
        "BNB side min body 0.25*ATR — skip doji fades",
        "strategies/bnb_structure.py",
        'raw_long = touch_low & (r < 22) & (r > r.shift(1)) & (df["close"] > df["open"]) & (df["close"] > vw) & vol_ok & a.notna()\n'
        '    raw_short = touch_hi & (r > 78) & (r < r.shift(1)) & (df["close"] < df["open"]) & (df["close"] < vw) & vol_ok & a.notna()',
        'body_fade = (df["close"] - df["open"]).abs() >= (0.25 * a)\n'
        '    raw_long = touch_low & (r < 22) & (r > r.shift(1)) & (df["close"] > df["open"]) & (df["close"] > vw) & vol_ok & body_fade & a.notna()\n'
        '    raw_short = touch_hi & (r > 78) & (r < r.shift(1)) & (df["close"] < df["open"]) & (df["close"] < vw) & vol_ok & body_fade & a.notna()',
    )
    add(
        "bnb_side_rsi_20_80",
        "bnb_side",
        "BNB side RSI 22/78→20/80",
        "strategies/bnb_structure.py",
        'raw_long = touch_low & (r < 22) & (r > r.shift(1)) & (df["close"] > df["open"]) & (df["close"] > vw) & vol_ok & a.notna()\n'
        '    raw_short = touch_hi & (r > 78) & (r < r.shift(1)) & (df["close"] < df["open"]) & (df["close"] < vw) & vol_ok & a.notna()',
        'raw_long = touch_low & (r < 20) & (r > r.shift(1)) & (df["close"] > df["open"]) & (df["close"] > vw) & vol_ok & a.notna()\n'
        '    raw_short = touch_hi & (r > 80) & (r < r.shift(1)) & (df["close"] < df["open"]) & (df["close"] < vw) & vol_ok & a.notna()',
    )
    add(
        "bnb_side_rsi_24_76",
        "bnb_side",
        "BNB side RSI 22/78→24/76",
        "strategies/bnb_structure.py",
        'raw_long = touch_low & (r < 22) & (r > r.shift(1)) & (df["close"] > df["open"]) & (df["close"] > vw) & vol_ok & a.notna()\n'
        '    raw_short = touch_hi & (r > 78) & (r < r.shift(1)) & (df["close"] < df["open"]) & (df["close"] < vw) & vol_ok & a.notna()',
        'raw_long = touch_low & (r < 24) & (r > r.shift(1)) & (df["close"] > df["open"]) & (df["close"] > vw) & vol_ok & a.notna()\n'
        '    raw_short = touch_hi & (r > 76) & (r < r.shift(1)) & (df["close"] < df["open"]) & (df["close"] < vw) & vol_ok & a.notna()',
    )
    add(
        "bnb_side_vol_1.70",
        "bnb_side",
        "BNB side vol 1.55→1.70",
        "strategies/bnb_structure.py",
        'vol_ok = df["volume"] >= (1.55 * vol_ma)  # P1069: skip thin BNB fades',
        'vol_ok = df["volume"] >= (1.70 * vol_ma)  # P1069: skip thin BNB fades',
    )
    add(
        "bnb_side_vol_1.45",
        "bnb_side",
        "BNB side vol 1.55→1.45",
        "strategies/bnb_structure.py",
        'vol_ok = df["volume"] >= (1.55 * vol_ma)  # P1069: skip thin BNB fades',
        'vol_ok = df["volume"] >= (1.45 * vol_ma)  # P1069: skip thin BNB fades',
    )
    add(
        "bnb_side_cd_230_150",
        "bnb_side",
        "BNB side CD 200/130→230/150",
        "strategies/bnb_structure.py",
        "apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 200, 130)",
        "apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 230, 150)",
    )
    add(
        "bnb_side_trail_0.4",
        "bnb_side",
        "BNB side trail 0.5→0.4",
        "strategies/bnb_structure.py",
        'out["tp_long"] = mid\n    out["tp_short"] = mid\n    out["trail_atr"] = 0.5 * a',
        'out["tp_long"] = mid\n    out["tp_short"] = mid\n    out["trail_atr"] = 0.4 * a',
    )
    add(
        "bnb_side_trail_0.6",
        "bnb_side",
        "BNB side trail 0.5→0.6",
        "strategies/bnb_structure.py",
        'out["tp_long"] = mid\n    out["tp_short"] = mid\n    out["trail_atr"] = 0.5 * a',
        'out["tp_long"] = mid\n    out["tp_short"] = mid\n    out["trail_atr"] = 0.6 * a',
    )
    add(
        "bnb_side_sl_0.14",
        "bnb_side",
        "BNB side SL 0.12→0.14",
        "strategies/bnb_structure.py",
        'out["sl_long"] = np.minimum(df["low"], lower) - 0.12 * a\n    out["sl_short"] = np.maximum(df["high"], upper) + 0.12 * a',
        'out["sl_long"] = np.minimum(df["low"], lower) - 0.14 * a\n    out["sl_short"] = np.maximum(df["high"], upper) + 0.14 * a',
    )
    add(
        "bnb_side_drop_vw",
        "bnb_side",
        "BNB side drop VWAP filter",
        "strategies/bnb_structure.py",
        'raw_long = touch_low & (r < 22) & (r > r.shift(1)) & (df["close"] > df["open"]) & (df["close"] > vw) & vol_ok & a.notna()\n'
        '    raw_short = touch_hi & (r > 78) & (r < r.shift(1)) & (df["close"] < df["open"]) & (df["close"] < vw) & vol_ok & a.notna()',
        'raw_long = touch_low & (r < 22) & (r > r.shift(1)) & (df["close"] > df["open"]) & vol_ok & a.notna()\n'
        '    raw_short = touch_hi & (r > 78) & (r < r.shift(1)) & (df["close"] < df["open"]) & vol_ok & a.notna()',
    )

    # ===== SOL side (summer — soft stoch from P3280 signal) =====
    add(
        "sol_side_stoch_19_81",
        "sol_side",
        "SOL side stoch 20/80→19/81 soft (18/82 lifted summer but cut med)",
        "strategies/sol_momentum.py",
        "raw_long = (k < 20) & (k > d) & (k.shift(1) <= d.shift(1)) & (k > k.shift(1)) & vol_ok & a.notna()\n"
        "    raw_short = (k > 80) & (k < d) & (k.shift(1) >= d.shift(1)) & (k < k.shift(1)) & vol_ok & a.notna()",
        "raw_long = (k < 19) & (k > d) & (k.shift(1) <= d.shift(1)) & (k > k.shift(1)) & vol_ok & a.notna()\n"
        "    raw_short = (k > 81) & (k < d) & (k.shift(1) >= d.shift(1)) & (k < k.shift(1)) & vol_ok & a.notna()",
    )
    add(
        "sol_side_stoch_18_82",
        "sol_side",
        "SOL side stoch 20/80→18/82",
        "strategies/sol_momentum.py",
        "raw_long = (k < 20) & (k > d) & (k.shift(1) <= d.shift(1)) & (k > k.shift(1)) & vol_ok & a.notna()\n"
        "    raw_short = (k > 80) & (k < d) & (k.shift(1) >= d.shift(1)) & (k < k.shift(1)) & vol_ok & a.notna()",
        "raw_long = (k < 18) & (k > d) & (k.shift(1) <= d.shift(1)) & (k > k.shift(1)) & vol_ok & a.notna()\n"
        "    raw_short = (k > 82) & (k < d) & (k.shift(1) >= d.shift(1)) & (k < k.shift(1)) & vol_ok & a.notna()",
    )
    add(
        "sol_side_stoch_21_79",
        "sol_side",
        "SOL side stoch 20/80→21/79 slightly wider",
        "strategies/sol_momentum.py",
        "raw_long = (k < 20) & (k > d) & (k.shift(1) <= d.shift(1)) & (k > k.shift(1)) & vol_ok & a.notna()\n"
        "    raw_short = (k > 80) & (k < d) & (k.shift(1) >= d.shift(1)) & (k < k.shift(1)) & vol_ok & a.notna()",
        "raw_long = (k < 21) & (k > d) & (k.shift(1) <= d.shift(1)) & (k > k.shift(1)) & vol_ok & a.notna()\n"
        "    raw_short = (k > 79) & (k < d) & (k.shift(1) >= d.shift(1)) & (k < k.shift(1)) & vol_ok & a.notna()",
    )
    add(
        "sol_side_require_macd_hist",
        "sol_side",
        "SOL side require rising/falling k already; add close vs open candle",
        "strategies/sol_momentum.py",
        "raw_long = (k < 20) & (k > d) & (k.shift(1) <= d.shift(1)) & (k > k.shift(1)) & vol_ok & a.notna()\n"
        "    raw_short = (k > 80) & (k < d) & (k.shift(1) >= d.shift(1)) & (k < k.shift(1)) & vol_ok & a.notna()",
        'raw_long = (k < 20) & (k > d) & (k.shift(1) <= d.shift(1)) & (k > k.shift(1)) & (df["close"] > df["open"]) & vol_ok & a.notna()\n'
        '    raw_short = (k > 80) & (k < d) & (k.shift(1) >= d.shift(1)) & (k < k.shift(1)) & (df["close"] < df["open"]) & vol_ok & a.notna()',
    )
    add(
        "sol_side_vol_1.10",
        "sol_side",
        "SOL side vol 1.05→1.10 soft tighten",
        "strategies/sol_momentum.py",
        'vol_ok = df["volume"] >= (1.05 * vol_ma)',
        'vol_ok = df["volume"] >= (1.10 * vol_ma)',
    )
    add(
        "sol_side_vol_1.00",
        "sol_side",
        "SOL side vol 1.05→1.00",
        "strategies/sol_momentum.py",
        'vol_ok = df["volume"] >= (1.05 * vol_ma)',
        'vol_ok = df["volume"] >= (1.00 * vol_ma)',
    )
    add(
        "sol_side_cd_75_52",
        "sol_side",
        "SOL side CD 70/50→75/52 soft",
        "strategies/sol_momentum.py",
        "apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 70, 50)",
        "apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 75, 52)",
    )
    add(
        "sol_side_cd_85_60",
        "sol_side",
        "SOL side CD 70/50→85/60",
        "strategies/sol_momentum.py",
        "apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 70, 50)",
        "apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 85, 60)",
    )
    add(
        "sol_side_trail_0.4",
        "sol_side",
        "SOL side trail 0.5→0.4",
        "strategies/sol_momentum.py",
        'out["tp_long"] = np.nan\n    out["tp_short"] = np.nan\n    out["trail_atr"] = 0.5 * a',
        'out["tp_long"] = np.nan\n    out["tp_short"] = np.nan\n    out["trail_atr"] = 0.4 * a',
    )
    add(
        "sol_side_trail_0.6",
        "sol_side",
        "SOL side trail 0.5→0.6",
        "strategies/sol_momentum.py",
        'out["tp_long"] = np.nan\n    out["tp_short"] = np.nan\n    out["trail_atr"] = 0.5 * a',
        'out["tp_long"] = np.nan\n    out["tp_short"] = np.nan\n    out["trail_atr"] = 0.6 * a',
    )
    add(
        "sol_side_sl_0.18",
        "sol_side",
        "SOL side SL 0.15→0.18",
        "strategies/sol_momentum.py",
        'out["sl_long"] = df["low"] - 0.15 * a\n    out["sl_short"] = df["high"] + 0.15 * a\n    out["tp_long"] = np.nan\n    out["tp_short"] = np.nan\n    out["trail_atr"] = 0.5 * a',
        'out["sl_long"] = df["low"] - 0.18 * a\n    out["sl_short"] = df["high"] + 0.18 * a\n    out["tp_long"] = np.nan\n    out["tp_short"] = np.nan\n    out["trail_atr"] = 0.5 * a',
    )
    add(
        "sol_side_sl_0.12",
        "sol_side",
        "SOL side SL 0.15→0.12",
        "strategies/sol_momentum.py",
        'out["sl_long"] = df["low"] - 0.15 * a\n    out["sl_short"] = df["high"] + 0.15 * a\n    out["tp_long"] = np.nan\n    out["tp_short"] = np.nan\n    out["trail_atr"] = 0.5 * a',
        'out["sl_long"] = df["low"] - 0.12 * a\n    out["sl_short"] = df["high"] + 0.12 * a\n    out["tp_long"] = np.nan\n    out["tp_short"] = np.nan\n    out["trail_atr"] = 0.5 * a',
    )

    # ===== BNB bear =====
    add(
        "bnb_bear_rsi_floor_20",
        "bnb_bear",
        "BNB bear RSI floor 18→20",
        "strategies/bnb_structure.py",
        "& (r < 42) & (r > 18) & (df[\"close\"] < mid) & (df[\"close\"] < vw) & vol_ok & body_ok & a.notna()",
        "& (r < 42) & (r > 20) & (df[\"close\"] < mid) & (df[\"close\"] < vw) & vol_ok & body_ok & a.notna()",
    )
    add(
        "bnb_bear_rsi_cap_40",
        "bnb_bear",
        "BNB bear RSI cap 42→40",
        "strategies/bnb_structure.py",
        "& (r < 42) & (r > 18) & (df[\"close\"] < mid) & (df[\"close\"] < vw) & vol_ok & body_ok & a.notna()",
        "& (r < 40) & (r > 18) & (df[\"close\"] < mid) & (df[\"close\"] < vw) & vol_ok & body_ok & a.notna()",
    )
    add(
        "bnb_bear_trail_0.9",
        "bnb_bear",
        "BNB bear trail 1.0→0.9",
        "strategies/bnb_structure.py",
        'out["trail_atr"] = np.maximum(1.0 * a, 0.35 * (upper - lower))',
        'out["trail_atr"] = np.maximum(0.9 * a, 0.35 * (upper - lower))',
    )
    add(
        "bnb_bear_trail_1.1",
        "bnb_bear",
        "BNB bear trail 1.0→1.1",
        "strategies/bnb_structure.py",
        'out["trail_atr"] = np.maximum(1.0 * a, 0.35 * (upper - lower))',
        'out["trail_atr"] = np.maximum(1.1 * a, 0.35 * (upper - lower))',
    )
    add(
        "bnb_body_0.45",
        "bnb_bear",
        "BNB shared body_ok 0.40→0.45",
        "strategies/bnb_structure.py",
        "body_ok = (df[\"close\"] - df[\"open\"]).abs() >= (0.40 * a)",
        "body_ok = (df[\"close\"] - df[\"open\"]).abs() >= (0.45 * a)",
    )
    add(
        "bnb_body_0.35",
        "bnb_bear",
        "BNB shared body_ok 0.40→0.35",
        "strategies/bnb_structure.py",
        "body_ok = (df[\"close\"] - df[\"open\"]).abs() >= (0.40 * a)",
        "body_ok = (df[\"close\"] - df[\"open\"]).abs() >= (0.35 * a)",
    )
    add(
        "bnb_squeeze_0.90",
        "bnb_bear",
        "BNB squeeze 0.92→0.90",
        "strategies/bnb_structure.py",
        "squeeze = width < (0.92 * width_ma)",
        "squeeze = width < (0.90 * width_ma)",
    )
    add(
        "bnb_bear_cd_280_170",
        "bnb_bear",
        "BNB bear CD 260/160→280/170",
        "strategies/bnb_structure.py",
        "apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 260, 160)",
        "apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 280, 170)",
    )
    add(
        "bnb_bear_sl_0.17",
        "bnb_bear",
        "BNB bear SL 0.15→0.17",
        "strategies/bnb_structure.py",
        'out["sl_long"] = np.minimum(df["low"], mid) - 0.15 * a\n    out["sl_short"] = np.maximum(df["high"], mid) + 0.15 * a\n    out["tp_long"] = np.nan\n    out["tp_short"] = np.nan\n    out["trail_atr"] = np.maximum(1.0 * a, 0.35 * (upper - lower))',
        'out["sl_long"] = np.minimum(df["low"], mid) - 0.17 * a\n    out["sl_short"] = np.maximum(df["high"], mid) + 0.17 * a\n    out["tp_long"] = np.nan\n    out["tp_short"] = np.nan\n    out["trail_atr"] = np.maximum(1.0 * a, 0.35 * (upper - lower))',
    )
    add(
        "bnb_shared_vol_1.40",
        "bnb_bear",
        "BNB shared vol 1.35→1.40",
        "strategies/bnb_structure.py",
        "vol_ok = df[\"volume\"] >= (1.35 * vol_ma)",
        "vol_ok = df[\"volume\"] >= (1.40 * vol_ma)",
    )

    # ===== SOL bear =====
    add(
        "sol_bear_atr_1.30",
        "sol_bear",
        "SOL bear ATR_MA 1.25→1.30",
        "strategies/sol_momentum.py",
        "vol_expand = (a > 1.25 * atr_ma) & (atr_pct >= 0.0020)",
        "vol_expand = (a > 1.30 * atr_ma) & (atr_pct >= 0.0020)",
    )
    add(
        "sol_bear_atr_1.22",
        "sol_bear",
        "SOL bear ATR_MA 1.25→1.22",
        "strategies/sol_momentum.py",
        "vol_expand = (a > 1.25 * atr_ma) & (atr_pct >= 0.0020)",
        "vol_expand = (a > 1.22 * atr_ma) & (atr_pct >= 0.0020)",
    )
    add(
        "sol_bear_trail_1.2",
        "sol_bear",
        "SOL bear trail 1.4→1.2",
        "strategies/sol_momentum.py",
        'out["trail_atr"] = (1.4 * a) if short_bias else (2.6 * a)',
        'out["trail_atr"] = (1.2 * a) if short_bias else (2.6 * a)',
    )
    add(
        "sol_bear_trail_1.6",
        "sol_bear",
        "SOL bear trail 1.4→1.6",
        "strategies/sol_momentum.py",
        'out["trail_atr"] = (1.4 * a) if short_bias else (2.6 * a)',
        'out["trail_atr"] = (1.6 * a) if short_bias else (2.6 * a)',
    )
    add(
        "sol_bear_long_k30",
        "sol_bear",
        "SOL bear long k<35→k<30",
        "strategies/sol_momentum.py",
        "raw_long = raw_long & (k < 35) & (hist > hist.shift(1))",
        "raw_long = raw_long & (k < 30) & (hist > hist.shift(1))",
    )
    add(
        "sol_bear_no_longs",
        "sol_bear",
        "Disable SOL bear bounce longs",
        "strategies/sol_momentum.py",
        "if short_bias:\n        raw_long = raw_long & (k < 35) & (hist > hist.shift(1))",
        "if short_bias:\n        raw_long = pd.Series(False, index=df.index)",
    )
    add(
        "sol_stoch_dn_k25",
        "sol_bear",
        "stoch_dn k>20→k>25",
        "strategies/sol_momentum.py",
        "stoch_dn = (k < d) & (k.shift(1) >= d.shift(1)) & (k > 20)",
        "stoch_dn = (k < d) & (k.shift(1) >= d.shift(1)) & (k > 25)",
    )

    # ===== BNB bull =====
    add(
        "bnb_bull_rsi_floor_54",
        "bnb_bull",
        "BNB bull RSI floor 52→54",
        "strategies/bnb_structure.py",
        "& (r > 52) & (r < 72) & (df[\"close\"] > mid) & (df[\"close\"] > vw) & vol_ok & body_strict & a.notna()",
        "& (r > 54) & (r < 72) & (df[\"close\"] > mid) & (df[\"close\"] > vw) & vol_ok & body_strict & a.notna()",
    )
    add(
        "bnb_bull_rsi_cap_70",
        "bnb_bull",
        "BNB bull RSI cap 72→70",
        "strategies/bnb_structure.py",
        "& (r > 52) & (r < 72) & (df[\"close\"] > mid) & (df[\"close\"] > vw) & vol_ok & body_strict & a.notna()",
        "& (r > 52) & (r < 70) & (df[\"close\"] > mid) & (df[\"close\"] > vw) & vol_ok & body_strict & a.notna()",
    )
    add(
        "bnb_bull_body_0.65",
        "bnb_bull",
        "BNB bull body 0.60→0.65",
        "strategies/bnb_structure.py",
        "body_strict = (df[\"close\"] - df[\"open\"]).abs() >= (0.60 * a)",
        "body_strict = (df[\"close\"] - df[\"open\"]).abs() >= (0.65 * a)",
    )
    add(
        "bnb_bull_body_0.55",
        "bnb_bull",
        "BNB bull body 0.60→0.55",
        "strategies/bnb_structure.py",
        "body_strict = (df[\"close\"] - df[\"open\"]).abs() >= (0.60 * a)",
        "body_strict = (df[\"close\"] - df[\"open\"]).abs() >= (0.55 * a)",
    )
    add(
        "bnb_bull_vol_2.05",
        "bnb_bull",
        "BNB bull vol 1.95→2.05",
        "strategies/bnb_structure.py",
        'vol_ok = df["volume"] >= (1.95 * volume_sma(df["volume"], 20))  # P1084: skip thin BNB breakouts',
        'vol_ok = df["volume"] >= (2.05 * volume_sma(df["volume"], 20))  # P1084: skip thin BNB breakouts',
    )
    add(
        "bnb_bull_vol_1.85",
        "bnb_bull",
        "BNB bull vol 1.95→1.85",
        "strategies/bnb_structure.py",
        'vol_ok = df["volume"] >= (1.95 * volume_sma(df["volume"], 20))  # P1084: skip thin BNB breakouts',
        'vol_ok = df["volume"] >= (1.85 * volume_sma(df["volume"], 20))  # P1084: skip thin BNB breakouts',
    )
    add(
        "bnb_bull_trail_2.4",
        "bnb_bull",
        "BNB bull trail 2.2→2.4",
        "strategies/bnb_structure.py",
        'out["trail_atr"] = np.maximum(2.2 * a, 0.45 * (upper - lower))',
        'out["trail_atr"] = np.maximum(2.4 * a, 0.45 * (upper - lower))',
    )
    add(
        "bnb_bull_cd_300_190",
        "bnb_bull",
        "BNB bull CD 280/180→300/190",
        "strategies/bnb_structure.py",
        "apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 280, 180)",
        "apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 300, 190)",
    )
    add(
        "bnb_bull_sl_0.20",
        "bnb_bull",
        "BNB bull SL 0.22→0.20",
        "strategies/bnb_structure.py",
        'out["sl_long"] = np.minimum(df["low"], mid) - 0.22 * a\n    out["sl_short"] = np.maximum(df["high"], mid) + 0.22 * a',
        'out["sl_long"] = np.minimum(df["low"], mid) - 0.20 * a\n    out["sl_short"] = np.maximum(df["high"], mid) + 0.20 * a',
    )
    add(
        "bnb_bull_size_1.22",
        "bnb_bull",
        "BNB bull size 1.18→1.22",
        "strategies/bnb_structure.py",
        'out["size_boost"] = np.where(atr_pct >= 0.0022, 1.18, 1.0)\n    return out\n\n\ndef _bear',
        'out["size_boost"] = np.where(atr_pct >= 0.0022, 1.22, 1.0)\n    return out\n\n\ndef _bear',
    )

    # ===== SOL bull =====
    add(
        "sol_bull_atr_1.10",
        "sol_bull",
        "SOL bull ATR_MA 1.08→1.10",
        "strategies/sol_momentum.py",
        "vol_expand = (a > 1.08 * atr_ma) & (atr_pct >= 0.0020)",
        "vol_expand = (a > 1.10 * atr_ma) & (atr_pct >= 0.0020)",
    )
    add(
        "sol_bull_atr_1.05",
        "sol_bull",
        "SOL bull ATR_MA 1.08→1.05",
        "strategies/sol_momentum.py",
        "vol_expand = (a > 1.08 * atr_ma) & (atr_pct >= 0.0020)",
        "vol_expand = (a > 1.05 * atr_ma) & (atr_pct >= 0.0020)",
    )
    add(
        "sol_vol_ok_1.25",
        "sol_bull",
        "SOL vol_ok 1.20→1.25",
        "strategies/sol_momentum.py",
        'vol_ok = df["volume"] >= (1.20 * vol_ma)',
        'vol_ok = df["volume"] >= (1.25 * vol_ma)',
    )
    add(
        "sol_vol_ok_1.15",
        "sol_bull",
        "SOL vol_ok 1.20→1.15",
        "strategies/sol_momentum.py",
        'vol_ok = df["volume"] >= (1.20 * vol_ma)',
        'vol_ok = df["volume"] >= (1.15 * vol_ma)',
    )
    add(
        "sol_bull_trail_2.8",
        "sol_bull",
        "SOL bull trail 2.6→2.8",
        "strategies/sol_momentum.py",
        'out["trail_atr"] = (1.4 * a) if short_bias else (2.6 * a)',
        'out["trail_atr"] = (1.4 * a) if short_bias else (2.8 * a)',
    )
    add(
        "sol_bull_trail_2.4",
        "sol_bull",
        "SOL bull trail 2.6→2.4",
        "strategies/sol_momentum.py",
        'out["trail_atr"] = (1.4 * a) if short_bias else (2.6 * a)',
        'out["trail_atr"] = (1.4 * a) if short_bias else (2.4 * a)',
    )
    add(
        "sol_stoch_up_k75",
        "sol_bull",
        "stoch_up k<80→k<75",
        "strategies/sol_momentum.py",
        "stoch_up = (k > d) & (k.shift(1) <= d.shift(1)) & (k < 80)",
        "stoch_up = (k > d) & (k.shift(1) <= d.shift(1)) & (k < 75)",
    )
    add(
        "sol_bull_short_k70",
        "sol_bull",
        "SOL bull short k>65→k>70",
        "strategies/sol_momentum.py",
        "raw_short = raw_short & (k > 65) & (hist < hist.shift(1))",
        "raw_short = raw_short & (k > 70) & (hist < hist.shift(1))",
    )
    add(
        "sol_cd_120_90",
        "sol_bull",
        "SOL CD 110/80→120/90",
        "strategies/sol_momentum.py",
        "apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 110, 80)",
        "apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 120, 90)",
    )
    add(
        "sol_sl_0.30",
        "sol_bull",
        "SOL SL 0.28→0.30",
        "strategies/sol_momentum.py",
        'out["sl_long"] = df["low"] - 0.28 * a\n    out["sl_short"] = df["high"] + 0.28 * a',
        'out["sl_long"] = df["low"] - 0.30 * a\n    out["sl_short"] = df["high"] + 0.30 * a',
    )

    # ===== ETH =====
    add(
        "eth_bull_rsi_cap_72",
        "eth_bull",
        "ETH bull RSI cap 75→72",
        "strategies/eth_breakout.py",
        "rsi_up = (r > 62) & (r.shift(1) <= 62) & (r < 75)",
        "rsi_up = (r > 62) & (r.shift(1) <= 62) & (r < 72)",
    )
    add(
        "eth_bull_rsi_floor_64",
        "eth_bull",
        "ETH bull RSI 62→64",
        "strategies/eth_breakout.py",
        "rsi_up = (r > 62) & (r.shift(1) <= 62) & (r < 75)",
        "rsi_up = (r > 64) & (r.shift(1) <= 64) & (r < 75)",
    )
    add(
        "eth_bull_trail_1.2",
        "eth_bull",
        "ETH bull trail 1.4→1.2",
        "strategies/eth_breakout.py",
        'out["trail_atr"] = 1.4 * a\n    atr_pct = a / df["close"]\n    out["size_boost"] = np.where(atr_pct >= 0.003, 1.25',
        'out["trail_atr"] = 1.2 * a\n    atr_pct = a / df["close"]\n    out["size_boost"] = np.where(atr_pct >= 0.003, 1.25',
    )
    add(
        "eth_bull_trail_1.6",
        "eth_bull",
        "ETH bull trail 1.4→1.6",
        "strategies/eth_breakout.py",
        'out["trail_atr"] = 1.4 * a\n    atr_pct = a / df["close"]\n    out["size_boost"] = np.where(atr_pct >= 0.003, 1.25',
        'out["trail_atr"] = 1.6 * a\n    atr_pct = a / df["close"]\n    out["size_boost"] = np.where(atr_pct >= 0.003, 1.25',
    )
    add(
        "eth_bull_vol_1.35",
        "eth_bull",
        "ETH bull vol 1.25→1.35",
        "strategies/eth_breakout.py",
        'vol_ok = df["volume"] >= (1.25 * vol_ma)\n\n    rsi_up = (r > 62)',
        'vol_ok = df["volume"] >= (1.35 * vol_ma)\n\n    rsi_up = (r > 62)',
    )
    add(
        "eth_bull_cd_150_100",
        "eth_bull",
        "ETH bull CD 130/90→150/100",
        "strategies/eth_breakout.py",
        "apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 130, 90)",
        "apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 150, 100)",
    )
    add(
        "eth_bear_trail_1.5",
        "eth_bear",
        "ETH bear trail 1.7→1.5",
        "strategies/eth_breakout.py",
        'out["trail_atr"] = 1.7 * a\n    atr_pct = a / df["close"]\n    out["size_boost"] = np.where(atr_pct >= 0.003, 1.12, 1.0)',
        'out["trail_atr"] = 1.5 * a\n    atr_pct = a / df["close"]\n    out["size_boost"] = np.where(atr_pct >= 0.003, 1.12, 1.0)',
    )
    add(
        "eth_bear_trail_1.9",
        "eth_bear",
        "ETH bear trail 1.7→1.9",
        "strategies/eth_breakout.py",
        'out["trail_atr"] = 1.7 * a\n    atr_pct = a / df["close"]\n    out["size_boost"] = np.where(atr_pct >= 0.003, 1.12, 1.0)',
        'out["trail_atr"] = 1.9 * a\n    atr_pct = a / df["close"]\n    out["size_boost"] = np.where(atr_pct >= 0.003, 1.12, 1.0)',
    )
    add(
        "eth_bear_no_bounce",
        "eth_bear",
        "Disable ETH bear bounce longs",
        "strategies/eth_breakout.py",
        'raw_long = rsi_up & (df["close"] > vw) & (r < 40) & (e8 < e21) & vol_ok & a.notna()',
        "raw_long = pd.Series(False, index=df.index)",
    )
    add(
        "eth_bear_rsi_dn_28",
        "eth_bear",
        "ETH bear rsi_dn floor 25→28",
        "strategies/eth_breakout.py",
        "rsi_dn = (r < 45) & (r.shift(1) >= 45) & (r > 25)",
        "rsi_dn = (r < 45) & (r.shift(1) >= 45) & (r > 28)",
    )
    add(
        "eth_side_rsi_20_80",
        "eth_side",
        "ETH side 22/78→20/80",
        "strategies/eth_breakout.py",
        'raw_long = (df["low"] <= lower) & (r < 22) & (r > r.shift(1)) & (df["close"] > df["open"]) & vol_ok & a.notna()\n'
        '    raw_short = (df["high"] >= upper) & (r > 78) & (r < r.shift(1)) & (df["close"] < df["open"]) & vol_ok & a.notna()',
        'raw_long = (df["low"] <= lower) & (r < 20) & (r > r.shift(1)) & (df["close"] > df["open"]) & vol_ok & a.notna()\n'
        '    raw_short = (df["high"] >= upper) & (r > 80) & (r < r.shift(1)) & (df["close"] < df["open"]) & vol_ok & a.notna()',
    )
    add(
        "eth_side_trail_0.6",
        "eth_side",
        "ETH side trail 0.7→0.6",
        "strategies/eth_breakout.py",
        'out["trail_atr"] = 0.7 * a\n    out["size_boost"] = 1.0\n    return out\n\n\ndef build_signals',
        'out["trail_atr"] = 0.6 * a\n    out["size_boost"] = 1.0\n    return out\n\n\ndef build_signals',
    )
    add(
        "eth_side_vol_1.90",
        "eth_side",
        "ETH side vol 1.80→1.90",
        "strategies/eth_breakout.py",
        'vol_ok = df["volume"] >= (1.80 * vol_ma)',
        'vol_ok = df["volume"] >= (1.90 * vol_ma)',
    )
    add(
        "eth_side_cd_280_170",
        "eth_side",
        "ETH side CD 260/160→280/170",
        "strategies/eth_breakout.py",
        "apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 260, 160)",
        "apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 280, 170)",
    )

    # ===== BTC =====
    add(
        "btc_bull_trail_2.6",
        "btc_bull",
        "BTC bull trail 2.4→2.6",
        "strategies/btc_trend.py",
        'out["trail_atr"] = 2.4 * a\n    atr_pct = a / df["close"]\n    out["size_boost"] = np.where(atr_pct >= 0.0025, 1.2',
        'out["trail_atr"] = 2.6 * a\n    atr_pct = a / df["close"]\n    out["size_boost"] = np.where(atr_pct >= 0.0025, 1.2',
    )
    add(
        "btc_bull_trail_2.2",
        "btc_bull",
        "BTC bull trail 2.4→2.2",
        "strategies/btc_trend.py",
        'out["trail_atr"] = 2.4 * a\n    atr_pct = a / df["close"]\n    out["size_boost"] = np.where(atr_pct >= 0.0025, 1.2',
        'out["trail_atr"] = 2.2 * a\n    atr_pct = a / df["close"]\n    out["size_boost"] = np.where(atr_pct >= 0.0025, 1.2',
    )
    add(
        "btc_bull_rsi_cap_66",
        "btc_bull",
        "BTC bull RSI cap 68→66",
        "strategies/btc_trend.py",
        "(r > 48) & (r < 68) & (hist > 0)",
        "(r > 48) & (r < 66) & (hist > 0)",
    )
    add(
        "btc_bull_vol_1.95",
        "btc_bull",
        "BTC bull vol 1.85→1.95",
        "strategies/btc_trend.py",
        'vol_ok = df["volume"] >= (1.85 * vol_ma)\n\n    raw_long = (\n        cross_up',
        'vol_ok = df["volume"] >= (1.95 * vol_ma)\n\n    raw_long = (\n        cross_up',
    )
    add(
        "btc_bull_cd_260_170",
        "btc_bull",
        "BTC bull CD 240/160→260/170",
        "strategies/btc_trend.py",
        "apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 240, 160)",
        "apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 260, 170)",
    )
    add(
        "btc_bear_trail_1.8",
        "btc_bear",
        "BTC bear trail 2.0→1.8",
        "strategies/btc_trend.py",
        'out["trail_atr"] = 2.0 * a\n    atr_pct = a / df["close"]\n    out["size_boost"] = np.where(atr_pct >= 0.0025, 1.15, 1.0)',
        'out["trail_atr"] = 1.8 * a\n    atr_pct = a / df["close"]\n    out["size_boost"] = np.where(atr_pct >= 0.0025, 1.15, 1.0)',
    )
    add(
        "btc_bear_trail_2.2",
        "btc_bear",
        "BTC bear trail 2.0→2.2",
        "strategies/btc_trend.py",
        'out["trail_atr"] = 2.0 * a\n    atr_pct = a / df["close"]\n    out["size_boost"] = np.where(atr_pct >= 0.0025, 1.15, 1.0)',
        'out["trail_atr"] = 2.2 * a\n    atr_pct = a / df["close"]\n    out["size_boost"] = np.where(atr_pct >= 0.0025, 1.15, 1.0)',
    )
    add(
        "btc_bear_no_bounce",
        "btc_bear",
        "Disable BTC bear bounce longs",
        "strategies/btc_trend.py",
        "raw_long = (\n        cross_up & (df[\"close\"] < vw) & (r < 35) & (r > r.shift(1)) & (hist > hist.shift(1)) & vol_ok & a.notna()\n    )",
        "raw_long = pd.Series(False, index=df.index)",
    )
    add(
        "btc_bear_cd_200_130",
        "btc_bear",
        "BTC bear CD 180/120→200/130",
        "strategies/btc_trend.py",
        "apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 180, 120)",
        "apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 200, 130)",
    )
    add(
        "btc_side_trail_0.5",
        "btc_side",
        "BTC side trail 0.6→0.5",
        "strategies/btc_trend.py",
        'out["trail_atr"] = 0.6 * a\n    out["size_boost"] = 1.0\n    return out\n\n\ndef build_signals',
        'out["trail_atr"] = 0.5 * a\n    out["size_boost"] = 1.0\n    return out\n\n\ndef build_signals',
    )
    add(
        "btc_side_rsi_24_76",
        "btc_side",
        "BTC side 26/74→24/76",
        "strategies/btc_trend.py",
        "raw_long = touch_low & bounce & (r < 26) & (r > r.shift(1)) & vol_ok & a.notna()\n    raw_short = touch_hi & reject & (r > 74) & (r < r.shift(1)) & vol_ok & a.notna()",
        "raw_long = touch_low & bounce & (r < 24) & (r > r.shift(1)) & vol_ok & a.notna()\n    raw_short = touch_hi & reject & (r > 76) & (r < r.shift(1)) & vol_ok & a.notna()",
    )
    add(
        "btc_side_vol_1.55",
        "btc_side",
        "BTC side vol 1.45→1.55",
        "strategies/btc_trend.py",
        'vol_ok = df["volume"] >= (1.45 * vol_ma)',
        'vol_ok = df["volume"] >= (1.55 * vol_ma)',
    )

    # ===== XRP =====
    add(
        "xrp_side_trail_0.6",
        "xrp_side",
        "XRP side trail 0.7→0.6",
        "strategies/xrp_meanrev.py",
        'out["trail_atr"] = 0.7 * a\n    atr_pct = a / df["close"]\n    out["size_boost"] = np.where(atr_pct >= 0.0028, 1.1, 1.0)',
        'out["trail_atr"] = 0.6 * a\n    atr_pct = a / df["close"]\n    out["size_boost"] = np.where(atr_pct >= 0.0028, 1.1, 1.0)',
    )
    add(
        "xrp_side_trail_0.8",
        "xrp_side",
        "XRP side trail 0.7→0.8",
        "strategies/xrp_meanrev.py",
        'out["trail_atr"] = 0.7 * a\n    atr_pct = a / df["close"]\n    out["size_boost"] = np.where(atr_pct >= 0.0028, 1.1, 1.0)',
        'out["trail_atr"] = 0.8 * a\n    atr_pct = a / df["close"]\n    out["size_boost"] = np.where(atr_pct >= 0.0028, 1.1, 1.0)',
    )
    add(
        "xrp_side_rsi_22",
        "xrp_side",
        "XRP side RSI 25→22",
        "strategies/xrp_meanrev.py",
        "touch_low & bounce & (r < 25) & (r > 10)",
        "touch_low & bounce & (r < 22) & (r > 10)",
    )
    add(
        "xrp_side_vol_1.4",
        "xrp_side",
        "XRP side vol 1.3→1.4",
        "strategies/xrp_meanrev.py",
        'vol_ok = df["volume"] >= (1.3 * vol_ma)  # P1018: skip weak fades',
        'vol_ok = df["volume"] >= (1.4 * vol_ma)  # P1018: skip weak fades',
    )
    add(
        "xrp_side_cd_120_80",
        "xrp_side",
        "XRP side CD 100/65→120/80",
        "strategies/xrp_meanrev.py",
        "apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 100, 65)",
        "apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 120, 80)",
    )
    add(
        "xrp_bull_trail_2.4",
        "xrp_bull",
        "XRP bull trail 2.2→2.4",
        "strategies/xrp_meanrev.py",
        'out["trail_atr"] = 2.2 * a\n    out["size_boost"] = 1.0\n    return out\n\n\ndef _bear',
        'out["trail_atr"] = 2.4 * a\n    out["size_boost"] = 1.0\n    return out\n\n\ndef _bear',
    )
    add(
        "xrp_bull_dip_r32",
        "xrp_bull",
        "XRP dip floor 30→32",
        "strategies/xrp_meanrev.py",
        "dip = (df[\"close\"] > e21) & (r < 45) & (r > r.shift(1)) & (r > 30)",
        "dip = (df[\"close\"] > e21) & (r < 45) & (r > r.shift(1)) & (r > 32)",
    )
    add(
        "xrp_bear_trail_1.6",
        "xrp_bear",
        "XRP bear trail 1.8→1.6",
        "strategies/xrp_meanrev.py",
        'out["trail_atr"] = 1.8 * a\n    out["size_boost"] = 1.0\n    return out\n\n\ndef build_signals',
        'out["trail_atr"] = 1.6 * a\n    out["size_boost"] = 1.0\n    return out\n\n\ndef build_signals',
    )
    add(
        "xrp_bear_rally_r65",
        "xrp_bear",
        "XRP rally cap 70→65",
        "strategies/xrp_meanrev.py",
        "rally = (df[\"close\"] < e21) & (r > 55) & (r < r.shift(1)) & (r < 70)",
        "rally = (df[\"close\"] < e21) & (r > 55) & (r < r.shift(1)) & (r < 65)",
    )

    # ===== regime =====
    add("reg_roc_0.0010", "regime", "roc 0.0008→0.0010", "strategies/regime.py", "roc_thresh: float = 0.0008", "roc_thresh: float = 0.0010")
    add("reg_roc_0.0006", "regime", "roc 0.0008→0.0006", "strategies/regime.py", "roc_thresh: float = 0.0008", "roc_thresh: float = 0.0006")
    add("reg_squeeze_0.70", "regime", "squeeze 0.75→0.70", "strategies/regime.py", "squeeze_mult: float = 0.75", "squeeze_mult: float = 0.70")
    add("reg_squeeze_0.80", "regime", "squeeze 0.75→0.80", "strategies/regime.py", "squeeze_mult: float = 0.75", "squeeze_mult: float = 0.80")
    add("reg_slope_15", "regime", "slope 20→15", "strategies/regime.py", "slope_bars: int = 20", "slope_bars: int = 15")
    add("reg_slope_25", "regime", "slope 20→25", "strategies/regime.py", "slope_bars: int = 20", "slope_bars: int = 25")
    add("reg_roc_bars_45", "regime", "roc_bars 60→45", "strategies/regime.py", "roc_bars: int = 60", "roc_bars: int = 45")
    add("reg_ht_45", "regime", "ht 50→45", "strategies/regime.py", "ht_period: int = 50", "ht_period: int = 45")
    add("reg_ht_55", "regime", "ht 50→55", "strategies/regime.py", "ht_period: int = 50", "ht_period: int = 55")

    # ===== engine =====
    add("eng_sl_grace_46", "engine", "sl_grace 42→46", "portfolio_engine.py", "sl_grace_bars: int = 42", "sl_grace_bars: int = 46")
    add("eng_sl_grace_38", "engine", "sl_grace 42→38", "portfolio_engine.py", "sl_grace_bars: int = 42", "sl_grace_bars: int = 38")
    add("eng_risk_cap_0.0010", "engine", "risk_cap 0.0012→0.0010", "portfolio_engine.py", "risk_cap_pct: float = 0.0012", "risk_cap_pct: float = 0.0010")
    add("eng_risk_cap_0.0014", "engine", "risk_cap 0.0012→0.0014", "portfolio_engine.py", "risk_cap_pct: float = 0.0012", "risk_cap_pct: float = 0.0014")
    add("eng_later_0.07", "engine", "later 0.08→0.07", "portfolio_engine.py", "later_close_frac: float = 0.08", "later_close_frac: float = 0.07")
    add("eng_later_0.09", "engine", "later 0.08→0.09", "portfolio_engine.py", "later_close_frac: float = 0.08", "later_close_frac: float = 0.09")
    add("eng_unlock_r_2.5", "engine", "unlock_r 3.0→2.5", "portfolio_engine.py", "trail_unlock_r: float = 3.0", "trail_unlock_r: float = 2.5")
    add("eng_unlock_r_3.5", "engine", "unlock_r 3.0→3.5", "portfolio_engine.py", "trail_unlock_r: float = 3.0", "trail_unlock_r: float = 3.5")
    add("eng_unlock_mult_1.3", "engine", "unlock_mult 1.4→1.3", "portfolio_engine.py", "trail_unlock_mult: float = 1.4", "trail_unlock_mult: float = 1.3")
    add("eng_unlock_mult_1.5", "engine", "unlock_mult 1.4→1.5", "portfolio_engine.py", "trail_unlock_mult: float = 1.4", "trail_unlock_mult: float = 1.5")
    add("eng_win_mult_1.3", "engine", "win_mult 1.2→1.3", "portfolio_engine.py", "win_size_mult: float = 1.2", "win_size_mult: float = 1.3")
    add("eng_win_mult_1.1", "engine", "win_mult 1.2→1.1", "portfolio_engine.py", "win_size_mult: float = 1.2", "win_size_mult: float = 1.1")
    add("eng_liq_0.20", "engine", "liq 0.22→0.20", "portfolio_engine.py", "liq_notional_frac: float = 0.22", "liq_notional_frac: float = 0.20")
    add("eng_liq_0.24", "engine", "liq 0.22→0.24", "portfolio_engine.py", "liq_notional_frac: float = 0.22", "liq_notional_frac: float = 0.24")
    add("eng_second_fat_0.08", "engine", "second_fat 0.10→0.08", "portfolio_engine.py", "second_close_frac_fat: float = 0.10", "second_close_frac_fat: float = 0.08")
    add("eng_second_fat_0.12", "engine", "second_fat 0.10→0.12", "portfolio_engine.py", "second_close_frac_fat: float = 0.10", "second_close_frac_fat: float = 0.12")
    add("eng_fat_1.15", "engine", "fat_boost 1.25→1.15", "portfolio_engine.py", "fat_boost_thresh: float = 1.25", "fat_boost_thresh: float = 1.15")
    add("eng_fat_1.35", "engine", "fat_boost 1.25→1.35", "portfolio_engine.py", "fat_boost_thresh: float = 1.25", "fat_boost_thresh: float = 1.35")
    add("eng_max_slip_0.0015", "engine", "max_slip 0.0020→0.0015", "portfolio_engine.py", "max_entry_slip: float = 0.0020", "max_entry_slip: float = 0.0015")
    add("eng_win_max_4", "engine", "win_max 5→4", "portfolio_engine.py", "win_size_max: float = 5.0", "win_size_max: float = 4.0")

    return m
