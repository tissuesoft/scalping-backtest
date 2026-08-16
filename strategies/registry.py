"""5심볼 → 전략 빌더 레지스트리."""
from __future__ import annotations

from typing import Callable

import pandas as pd

from strategies import bnb_structure, btc_trend, eth_breakout, sol_momentum, xrp_meanrev

PORTFOLIO_SYMBOLS = (
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "XRPUSDT",
)

SignalBuilder = Callable[[pd.DataFrame, dict | None], pd.DataFrame]

STRATEGY_BUILDERS: dict[str, SignalBuilder] = {
    "BTCUSDT": btc_trend.build_signals,
    "ETHUSDT": eth_breakout.build_signals,
    "BNBUSDT": bnb_structure.build_signals,
    "SOLUSDT": sol_momentum.build_signals,
    "XRPUSDT": xrp_meanrev.build_signals,
}


def build_symbol_signals(symbol: str, df: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:
    if symbol not in STRATEGY_BUILDERS:
        raise KeyError(f"no strategy for {symbol}")
    return STRATEGY_BUILDERS[symbol](df, params)
