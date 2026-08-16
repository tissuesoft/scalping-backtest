"""Exchange filters + quantity/price rounding."""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class SymbolFilters:
    symbol: str
    tick_size: float
    step_size: float
    min_qty: float
    min_notional: float


def _decimals(step: float) -> int:
    s = f"{step:.16f}".rstrip("0")
    if "." not in s:
        return 0
    return len(s.split(".")[1])


def parse_exchange_filters(info: dict, symbols: tuple[str, ...]) -> dict[str, SymbolFilters]:
    out: dict[str, SymbolFilters] = {}
    want = set(symbols)
    for s in info.get("symbols", []):
        sym = s.get("symbol")
        if sym not in want:
            continue
        tick = step = 0.01
        min_qty = 0.0
        min_notional = 5.0
        for f in s.get("filters", []):
            t = f.get("filterType")
            if t == "PRICE_FILTER":
                tick = float(f["tickSize"])
            elif t == "LOT_SIZE":
                step = float(f["stepSize"])
                min_qty = float(f["minQty"])
            elif t == "MIN_NOTIONAL":
                min_notional = float(f.get("notional", f.get("minNotional", 5)))
        out[sym] = SymbolFilters(sym, tick, step, min_qty, min_notional)
    missing = want - set(out)
    if missing:
        raise RuntimeError(f"symbols missing from exchangeInfo: {sorted(missing)}")
    return out


def round_price(price: float, tick: float, side: str) -> float:
    if tick <= 0:
        return price
    n = _decimals(tick)
    if side == "BUY":
        return float(f"{math.floor(price / tick) * tick:.{n}f}")
    return float(f"{math.ceil(price / tick) * tick:.{n}f}")


def round_qty(qty: float, step: float) -> float:
    if step <= 0:
        return qty
    n = _decimals(step)
    q = math.floor(qty / step) * step
    return float(f"{q:.{n}f}")
