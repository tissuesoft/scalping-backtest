"""Binance USD-M Futures leverage limits for PORT5 backtest/live alignment.

Queried from demo-fapi leverageBracket (2026-08-16).
Policy: always min(want, exchange max) and size notionals so
required margin = notional / bracket_leverage never exceeds the slot budget.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

# Exchange maximum initial leverage (smallest notional bracket).
BINANCE_DEMO_MAX_LEVERAGE: Dict[str, float] = {
    "BTCUSDT": 125.0,
    "ETHUSDT": 100.0,
    "BNBUSDT": 75.0,
    "SOLUSDT": 50.0,
    "XRPUSDT": 75.0,
}

# Full notional brackets: floor < notional <= cap → initialLeverage max.
BINANCE_DEMO_BRACKETS: Dict[str, List[Dict[str, float]]] = {
    "BTCUSDT": [
        {"notionalFloor": 0.0, "notionalCap": 50_000.0, "initialLeverage": 125},
        {"notionalFloor": 50_000.0, "notionalCap": 250_000.0, "initialLeverage": 100},
        {"notionalFloor": 250_000.0, "notionalCap": 3_000_000.0, "initialLeverage": 50},
        {"notionalFloor": 3_000_000.0, "notionalCap": 20_000_000.0, "initialLeverage": 20},
        {"notionalFloor": 20_000_000.0, "notionalCap": 40_000_000.0, "initialLeverage": 10},
        {"notionalFloor": 40_000_000.0, "notionalCap": 100_000_000.0, "initialLeverage": 5},
        {"notionalFloor": 100_000_000.0, "notionalCap": 120_000_000.0, "initialLeverage": 4},
        {"notionalFloor": 120_000_000.0, "notionalCap": 200_000_000.0, "initialLeverage": 3},
        {"notionalFloor": 200_000_000.0, "notionalCap": 300_000_000.0, "initialLeverage": 2},
        {"notionalFloor": 300_000_000.0, "notionalCap": 500_000_000.0, "initialLeverage": 1},
    ],
    "ETHUSDT": [
        {"notionalFloor": 0.0, "notionalCap": 100_000.0, "initialLeverage": 100},
        {"notionalFloor": 100_000.0, "notionalCap": 250_000.0, "initialLeverage": 75},
        {"notionalFloor": 250_000.0, "notionalCap": 2_000_000.0, "initialLeverage": 50},
        {"notionalFloor": 2_000_000.0, "notionalCap": 15_000_000.0, "initialLeverage": 20},
        {"notionalFloor": 15_000_000.0, "notionalCap": 30_000_000.0, "initialLeverage": 10},
        {"notionalFloor": 30_000_000.0, "notionalCap": 60_000_000.0, "initialLeverage": 5},
        {"notionalFloor": 60_000_000.0, "notionalCap": 80_000_000.0, "initialLeverage": 4},
        {"notionalFloor": 80_000_000.0, "notionalCap": 100_000_000.0, "initialLeverage": 3},
        {"notionalFloor": 100_000_000.0, "notionalCap": 150_000_000.0, "initialLeverage": 2},
        {"notionalFloor": 150_000_000.0, "notionalCap": 300_000_000.0, "initialLeverage": 1},
    ],
    "BNBUSDT": [
        {"notionalFloor": 0.0, "notionalCap": 5_000.0, "initialLeverage": 75},
        {"notionalFloor": 5_000.0, "notionalCap": 10_000.0, "initialLeverage": 50},
        {"notionalFloor": 10_000.0, "notionalCap": 50_000.0, "initialLeverage": 40},
        {"notionalFloor": 50_000.0, "notionalCap": 250_000.0, "initialLeverage": 25},
        {"notionalFloor": 250_000.0, "notionalCap": 1_000_000.0, "initialLeverage": 10},
        {"notionalFloor": 1_000_000.0, "notionalCap": 5_000_000.0, "initialLeverage": 5},
        {"notionalFloor": 5_000_000.0, "notionalCap": 10_000_000.0, "initialLeverage": 4},
        {"notionalFloor": 10_000_000.0, "notionalCap": 20_000_000.0, "initialLeverage": 3},
        {"notionalFloor": 20_000_000.0, "notionalCap": 30_000_000.0, "initialLeverage": 2},
        {"notionalFloor": 30_000_000.0, "notionalCap": 50_000_000.0, "initialLeverage": 1},
    ],
    "SOLUSDT": [
        {"notionalFloor": 0.0, "notionalCap": 50_000.0, "initialLeverage": 50},
        {"notionalFloor": 50_000.0, "notionalCap": 150_000.0, "initialLeverage": 25},
        {"notionalFloor": 150_000.0, "notionalCap": 900_000.0, "initialLeverage": 20},
        {"notionalFloor": 900_000.0, "notionalCap": 1_800_000.0, "initialLeverage": 10},
        {"notionalFloor": 1_800_000.0, "notionalCap": 4_800_000.0, "initialLeverage": 5},
        {"notionalFloor": 4_800_000.0, "notionalCap": 6_000_000.0, "initialLeverage": 4},
        {"notionalFloor": 6_000_000.0, "notionalCap": 18_000_000.0, "initialLeverage": 2},
        {"notionalFloor": 18_000_000.0, "notionalCap": 30_000_000.0, "initialLeverage": 1},
    ],
    "XRPUSDT": [
        {"notionalFloor": 0.0, "notionalCap": 5_000.0, "initialLeverage": 75},
        {"notionalFloor": 5_000.0, "notionalCap": 10_000.0, "initialLeverage": 50},
        {"notionalFloor": 10_000.0, "notionalCap": 50_000.0, "initialLeverage": 40},
        {"notionalFloor": 50_000.0, "notionalCap": 500_000.0, "initialLeverage": 25},
        {"notionalFloor": 500_000.0, "notionalCap": 2_000_000.0, "initialLeverage": 10},
        {"notionalFloor": 2_000_000.0, "notionalCap": 8_000_000.0, "initialLeverage": 5},
        {"notionalFloor": 8_000_000.0, "notionalCap": 10_000_000.0, "initialLeverage": 4},
        {"notionalFloor": 10_000_000.0, "notionalCap": 20_000_000.0, "initialLeverage": 3},
        {"notionalFloor": 20_000_000.0, "notionalCap": 30_000_000.0, "initialLeverage": 2},
        {"notionalFloor": 30_000_000.0, "notionalCap": 50_000_000.0, "initialLeverage": 1},
    ],
}


def effective_leverage_map(want: float = 100.0, caps: Dict[str, float] | None = None) -> Dict[str, float]:
    """Per-symbol leverage = min(want, exchange max)."""
    src = caps or BINANCE_DEMO_MAX_LEVERAGE
    w = float(want)
    return {sym: float(min(w, mx)) for sym, mx in src.items()}


def leverage_for_notional(symbol: str, notional: float) -> float:
    """Max initial leverage allowed for this notional on demo brackets."""
    n = max(float(notional), 0.0)
    brackets = BINANCE_DEMO_BRACKETS.get(symbol)
    if not brackets:
        return float(BINANCE_DEMO_MAX_LEVERAGE.get(symbol, 1.0))
    for b in brackets:
        floor = float(b["notionalFloor"])
        cap = float(b["notionalCap"])
        if n <= cap and (n > floor or floor <= 0.0):
            return float(b["initialLeverage"])
    return float(brackets[-1]["initialLeverage"])


def size_for_margin_budget(
    symbol: str,
    budget: float,
    want_lev: float,
    notional_cap: float | None = None,
) -> Tuple[float, float, float]:
    """Pick (notional, margin, leverage) maximizing notional with margin <= budget.

    Respects Binance notional brackets so live margin lock matches backtest.
    """
    budget = max(float(budget), 0.0)
    want = max(float(want_lev), 1.0)
    n_lim = float(notional_cap) if notional_cap is not None and notional_cap > 0 else float("inf")
    if budget <= 0:
        return 0.0, 0.0, want

    brackets = BINANCE_DEMO_BRACKETS.get(symbol)
    if not brackets:
        lev = min(want, float(BINANCE_DEMO_MAX_LEVERAGE.get(symbol, want)))
        n = min(budget * lev, n_lim)
        return n, (n / lev if lev else 0.0), lev

    best_n = 0.0
    best_margin = 0.0
    best_lev = min(want, float(brackets[0]["initialLeverage"]))

    for b in brackets:
        L = min(want, float(b["initialLeverage"]))
        if L < 1e-12:
            continue
        floor = float(b["notionalFloor"])
        cap = float(b["notionalCap"])
        n = min(cap, budget * L, n_lim)
        if n <= 0:
            continue
        if floor > 0.0 and n <= floor:
            continue
        margin = n / L
        if margin > budget:
            n = budget * L
            margin = budget
            if floor > 0.0 and n <= floor:
                continue
            if n > cap:
                continue
        # Confirm bracket still allows L at this notional
        allowed = leverage_for_notional(symbol, n)
        L_eff = min(want, allowed)
        if L_eff < L - 1e-9:
            n = min(n, budget * L_eff, cap, n_lim)
            if floor > 0.0 and n <= floor:
                continue
            margin = n / L_eff if L_eff else 0.0
            L = L_eff
        if margin > budget:
            n = budget * L
            margin = budget
        if n > best_n:
            best_n, best_margin, best_lev = n, min(margin, budget), L

    return best_n, best_margin, best_lev
