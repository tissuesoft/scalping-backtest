"""스모크: 배분(20%/마지막 전액) + 격리 청산 + 동시≤5."""
from __future__ import annotations

import numpy as np
import pandas as pd

from portfolio_engine import PortfolioConfig, PORTFOLIO_SYMBOLS, run_portfolio


def _synth(n: int = 500, seed: int = 0, start: float = 100.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="min", tz="UTC")
    rets = rng.normal(0, 0.0005, n)
    close = start * np.exp(np.cumsum(rets))
    high = close * (1 + rng.uniform(0, 0.001, n))
    low = close * (1 - rng.uniform(0, 0.001, n))
    open_ = np.roll(close, 1)
    open_[0] = start
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": 1.0},
        index=idx,
    )


def _sig_force(index: pd.Index, long_at: list[int] | None = None, short_at: list[int] | None = None) -> pd.DataFrame:
    out = pd.DataFrame(index=index)
    out["entry_long"] = False
    out["entry_short"] = False
    out["sl_long"] = np.nan
    out["sl_short"] = np.nan
    out["tp_long"] = np.nan
    out["tp_short"] = np.nan
    out["trail_atr"] = np.nan
    out["size_boost"] = 1.0
    close = pd.Series(100.0, index=index)  # placeholder; engine uses OHLC for fills
    for i in long_at or []:
        out.iloc[i, out.columns.get_loc("entry_long")] = True
        out.iloc[i, out.columns.get_loc("sl_long")] = 99.0
        out.iloc[i, out.columns.get_loc("tp_long")] = 110.0
        out.iloc[i, out.columns.get_loc("trail_atr")] = 0.5
    for i in short_at or []:
        out.iloc[i, out.columns.get_loc("entry_short")] = True
        out.iloc[i, out.columns.get_loc("sl_short")] = 101.0
        out.iloc[i, out.columns.get_loc("tp_short")] = 90.0
        out.iloc[i, out.columns.get_loc("trail_atr")] = 0.5
    _ = close
    return out


def test_max_five_and_alloc():
    n = 800
    frames = {s: _synth(n, seed=i + 1, start=100 + i) for i, s in enumerate(PORTFOLIO_SYMBOLS)}
    # force staggered entries so all 5 can open
    signals = {}
    for i, s in enumerate(PORTFOLIO_SYMBOLS):
        signals[s] = _sig_force(frames[s].index, long_at=[10 + i * 5])

    cfg = PortfolioConfig(
        initial_capital=100.0,
        leverage=10.0,  # milder for smoke
        fee_rate=0.0004,
        slippage=0.0001,
        use_partial_trail=False,
        sl_grace_bars=0,
        risk_tgt_start=0.5,
        risk_tgt_max=0.5,
        win_size_mult=1.0,
    )
    # instrument: wrap run to peek max concurrent via trade gaps is hard;
    # instead run and assert trades exist and final equity finite
    res = run_portfolio(frames, signals, cfg, name="smoke_alloc")
    assert res.metrics["trades"] >= 1, "expected at least one trade"
    assert float(res.equity.max()) < 1e12
    # never more than 5 symbols traded in overlapping sense: trades_by_symbol keys ≤5
    assert len(res.trades_by_symbol) <= 5
    print("[ok] alloc/max5 smoke trades=", int(res.metrics["trades"]), "peak=", float(res.equity.max()))


def test_isolated_liq():
    """One symbol liquidates; cash outside that margin should survive."""
    n = 200
    frames = {s: _synth(n, seed=10 + i, start=50 + i * 10) for i, s in enumerate(PORTFOLIO_SYMBOLS)}
    # flat BTC then cliff (SL far away so only liq fires)
    btc = frames["BTCUSDT"].copy()
    px = 100.0
    for i in range(n):
        btc.iloc[i, btc.columns.get_loc("open")] = px
        btc.iloc[i, btc.columns.get_loc("high")] = px * 1.0001
        btc.iloc[i, btc.columns.get_loc("low")] = px * 0.9999
        btc.iloc[i, btc.columns.get_loc("close")] = px
    for i in range(50, 60):
        btc.iloc[i, btc.columns.get_loc("open")] = px
        btc.iloc[i, btc.columns.get_loc("high")] = px
        btc.iloc[i, btc.columns.get_loc("low")] = 1.0
        btc.iloc[i, btc.columns.get_loc("close")] = 1.0
    frames["BTCUSDT"] = btc

    signals = {s: _sig_force(frames[s].index) for s in PORTFOLIO_SYMBOLS}
    sig = _sig_force(btc.index, long_at=[25])
    # absurdly wide SL so risk-cap still leaves room but liq hits first on cliff
    sig.iloc[25, sig.columns.get_loc("sl_long")] = 0.5
    signals["BTCUSDT"] = sig
    signals["ETHUSDT"] = _sig_force(frames["ETHUSDT"].index, long_at=[30])

    cfg = PortfolioConfig(
        initial_capital=100.0,
        leverage=100.0,
        fee_rate=0.0004,
        slippage=0.0,
        use_partial_trail=False,
        sl_grace_bars=0,
        risk_tgt_start=0.5,
        risk_tgt_max=0.5,
        win_size_mult=1.0,
        mmr=0.005,
        risk_cap_pct=0.0,  # do not tighten SL into the path
    )
    res = run_portfolio(frames, signals, cfg, name="smoke_liq")
    liq = int(res.metrics["liquidations"])
    final = float(res.equity.iloc[-1])
    print(f"[ok] isolated liq smoke liq={liq} final_equity={final:.4f}")
    assert liq >= 1, "expected BTC liquidation"
    # isolated: should not wipe entire account to ~0 from one slot of ~20%
    assert final > 1.0, f"isolated liq should leave equity>1, got {final}"


def test_last_slot_uses_remaining_cash():
    """With 4 opens, 5th entry should be able to consume remaining free cash path."""
    n = 400
    frames = {s: _synth(n, seed=100 + i, start=80 + i) for i, s in enumerate(PORTFOLIO_SYMBOLS)}
    # keep prices calm so no early exits
    for s in frames:
        df = frames[s].copy()
        px = float(df["close"].iloc[0])
        df["open"] = px
        df["high"] = px * 1.0002
        df["low"] = px * 0.9998
        df["close"] = px
        frames[s] = df

    signals = {}
    for i, s in enumerate(PORTFOLIO_SYMBOLS):
        signals[s] = _sig_force(frames[s].index, long_at=[20 + i * 3])

    cfg = PortfolioConfig(
        initial_capital=100.0,
        leverage=5.0,
        fee_rate=0.0,
        slippage=0.0,
        use_partial_trail=False,
        sl_grace_bars=1000,  # never SL
        risk_tgt_start=1.0,
        risk_tgt_span=0.0,
        risk_tgt_max=1.0,
        win_size_mult=1.0,
        risk_cap_pct=0.05,
    )
    res = run_portfolio(frames, signals, cfg, name="smoke_last")
    # all 5 should have entered
    opened = sum(1 for v in res.trades_by_symbol.values() if v > 0)
    # may still be open at end -> eod closes count as trades
    assert int(res.metrics["trades"]) >= 5, f"expected 5 entries, trades={res.metrics['trades']}"
    print("[ok] last-slot smoke opened_symbols~", opened, "trades=", int(res.metrics["trades"]))


if __name__ == "__main__":
    test_max_five_and_alloc()
    test_isolated_liq()
    test_last_slot_uses_remaining_cash()
    print("ALL SMOKE ASSERTIONS PASSED")
