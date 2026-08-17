"""1m 단타용 HTF(15m) 국면 분류 + 심볼별 bull/bear/sideways 신호 병합."""
from __future__ import annotations

import numpy as np
import pandas as pd

from indicators import bb_width, ht_ema_on_1m


def classify_regime(
    df: pd.DataFrame,
    ht_period: int = 45,
    ht_rule: str = "15min",
    slope_bars: int = 20,
    roc_bars: int = 60,
    roc_thresh: float = 0.0008,
    squeeze_mult: float = 0.75,
) -> pd.Series:
    """각 1m 봉에 bull | bear | sideways 레이블 (look-ahead 없음, HTF shift(1))."""
    ht = ht_ema_on_1m(df, ht_period, ht_rule)
    slope = ht.diff(slope_bars)
    roc = df["close"].pct_change(roc_bars)
    width = bb_width(df["close"], 20, 2.0)
    width_ma = width.rolling(100, min_periods=50).mean()
    narrow = width < (squeeze_mult * width_ma)

    bull = (
        (df["close"] > ht)
        & (slope > 0)
        & (roc > roc_thresh)
        & ~narrow.fillna(False)
        & ht.notna()
    )
    bear = (
        (df["close"] < ht)
        & (slope < 0)
        & (roc < -roc_thresh)
        & ~narrow.fillna(False)
        & ht.notna()
    )

    regime = pd.Series("sideways", index=df.index, dtype=object)
    regime[bull.fillna(False)] = "bull"
    regime[bear.fillna(False)] = "bear"
    # sideways = squeeze chop only; weak trend → HT side (less fade bleed)
    undec = regime == "sideways"
    side_mask = undec & narrow.fillna(False)
    regime[undec & ~narrow.fillna(False) & (df["close"] > ht)] = "bull"
    regime[undec & ~narrow.fillna(False) & (df["close"] < ht)] = "bear"
    regime[side_mask] = "sideways"
    return regime


def merge_regime_signals(
    regime: pd.Series,
    bull: pd.DataFrame,
    bear: pd.DataFrame,
    sideways: pd.DataFrame,
) -> pd.DataFrame:
    """국면별 신호·SL/trail 중 해당 바만 채택."""
    is_bull = regime == "bull"
    is_bear = regime == "bear"
    is_side = regime == "sideways"

    out = pd.DataFrame(index=bull.index)
    bool_cols = {"entry_long", "entry_short"}
    for col in bull.columns:
        if col in bool_cols:
            out[col] = (
                (is_bull & bull[col].fillna(False))
                | (is_bear & bear[col].fillna(False))
                | (is_side & sideways[col].fillna(False))
            )
        else:
            out[col] = np.where(
                is_bull,
                bull[col],
                np.where(is_bear, bear[col], sideways[col]),
            )
    return out


def empty_signals(index: pd.Index) -> pd.DataFrame:
    out = pd.DataFrame(index=index)
    out["entry_long"] = False
    out["entry_short"] = False
    out["sl_long"] = np.nan
    out["sl_short"] = np.nan
    out["tp_long"] = np.nan
    out["tp_short"] = np.nan
    out["trail_atr"] = np.nan
    out["size_boost"] = 1.0
    return out
