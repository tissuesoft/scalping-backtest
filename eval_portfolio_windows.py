"""5심볼 포트폴리오 롤링 창 평가 (합산 계좌 $100 → 10,000x)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from data_loader import load_parquet_dir
from portfolio_engine import PortfolioConfig, PORTFOLIO_SYMBOLS, align_frames, run_portfolio
from strategies.registry import STRATEGY_BUILDERS, build_symbol_signals


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--data-root", default="data")
    p.add_argument("--capital", type=float, default=100.0)
    p.add_argument("--target-mult", type=float, default=10_000.0)
    p.add_argument("--leverage", type=float, default=100.0)
    p.add_argument("--fee", type=float, default=0.0004)
    p.add_argument("--slippage", type=float, default=0.0001)
    p.add_argument("--window-days", type=int, default=60)
    p.add_argument("--step-days", type=int, default=30)
    p.add_argument("--out-dir", default="reports/iter")
    p.add_argument("--tag", default="port5")
    p.add_argument("--max-windows", type=int, default=0)
    p.add_argument(
        "--symbols",
        default=",".join(PORTFOLIO_SYMBOLS),
        help="comma-separated symbols (default: all 5)",
    )
    p.add_argument("--start", default=None, help="optional UTC start (YYYY-MM or YYYY-MM-DD)")
    p.add_argument("--end", default=None, help="optional UTC end (YYYY-MM or YYYY-MM-DD)")
    return p.parse_args()


def load_portfolio_frames(
    data_root: Path,
    symbols: list[str],
    start: str | None = None,
    end: str | None = None,
    warmup_days: int = 400,
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    """Load OHLCV; if start is set, also pull warmup for indicator readiness.

    Returns (eval_frames, signal_frames). signal_frames may start earlier.
    """
    load_start = start
    if start and warmup_days > 0:
        ts = pd.Timestamp(start, tz="UTC")
        load_start = (ts - pd.Timedelta(days=warmup_days)).strftime("%Y-%m-%d")

    signal_frames: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        path = data_root / sym / "1m"
        df = load_parquet_dir(path, start=load_start, end=end)
        signal_frames[sym] = df
        print(f"[data] {sym} rows={len(df):,} {df.index[0]} -> {df.index[-1]}")

    if not start:
        return signal_frames, signal_frames

    cut = pd.Timestamp(start, tz="UTC")
    eval_frames = {s: df[df.index >= cut].copy() for s, df in signal_frames.items()}
    for s, df in eval_frames.items():
        if len(df) == 0:
            raise ValueError(f"{s}: no bars after start={start}")
        print(f"[eval-slice] {s} rows={len(df):,} {df.index[0]} -> {df.index[-1]}")
    return eval_frames, signal_frames


def build_all_signals(frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    out = {}
    for sym, df in frames.items():
        print(f"[signals] {sym} via {STRATEGY_BUILDERS[sym].__module__}")
        out[sym] = build_symbol_signals(sym, df)
    return out


def evaluate_portfolio_windows(
    frames: dict[str, pd.DataFrame],
    signals: dict[str, pd.DataFrame],
    cfg: PortfolioConfig,
    window_days: int,
    step_days: int,
    target_mult: float,
    max_windows: int = 0,
):
    aligned = align_frames(frames)
    # use BTC index span if present else first symbol
    base = aligned.get("BTCUSDT", next(iter(aligned.values())))
    target_eq = cfg.initial_capital * target_mult
    cfg = PortfolioConfig(
        initial_capital=cfg.initial_capital,
        target_equity=target_eq,
        leverage=cfg.leverage,
        fee_rate=cfg.fee_rate,
        slippage=cfg.slippage,
        mmr=cfg.mmr,
        slot_frac=cfg.slot_frac,
        trail_unlock_r=cfg.trail_unlock_r,
        trail_unlock_mult=cfg.trail_unlock_mult,
        win_size_mult=cfg.win_size_mult,
        win_size_max=cfg.win_size_max,
        sl_grace_bars=cfg.sl_grace_bars,
        risk_cap_pct=cfg.risk_cap_pct,
        use_partial_trail=cfg.use_partial_trail,
        first_close_frac=cfg.first_close_frac,
        second_close_frac_fat=cfg.second_close_frac_fat,
        second_close_frac_thin=cfg.second_close_frac_thin,
        later_close_frac=cfg.later_close_frac,
        trail_scale_max=cfg.trail_scale_max,
    )

    start, end = base.index[0], base.index[-1]
    window, step = pd.Timedelta(days=window_days), pd.Timedelta(days=step_days)
    rows, cur = [], start
    while cur + window <= end:
        w_end = cur + window
        w_frames = {s: df.loc[cur:w_end] for s, df in aligned.items()}
        # require enough bars on intersection
        try:
            w_aligned = align_frames(w_frames)
        except ValueError:
            cur += step
            continue
        n_bars = len(next(iter(w_aligned.values())))
        if n_bars >= 1000:
            w_sig = {s: signals[s].reindex(w_aligned[s].index) for s in w_aligned}
            res = run_portfolio(w_aligned, w_sig, cfg, name="win")
            peak = float(res.equity.max()) if len(res.equity) else cfg.initial_capital
            final = float(res.metrics["final_equity"])
            row = {
                "start": str(cur),
                "end": str(w_end),
                "bars": n_bars,
                "final": final,
                "peak": peak,
                "mult_final": final / cfg.initial_capital,
                "mult_peak": peak / cfg.initial_capital,
                "hit_10000x": bool(res.hit_target) or peak >= target_eq,
                "trades": int(res.metrics["trades"]),
                "pf": res.metrics["profit_factor"],
                "mdd": res.metrics["max_drawdown_pct"],
                "liq": int(res.metrics["liquidations"]),  # slot liqs (info)
                "account_liq": bool(res.metrics.get("account_liq", 0.0) >= 0.5) or final <= 1.0,
                "symbol": "PORT5",
            }
            for s in PORTFOLIO_SYMBOLS:
                row[f"trades_{s}"] = int(res.trades_by_symbol.get(s, 0))
                row[f"liq_{s}"] = int(res.liq_by_symbol.get(s, 0))
            rows.append(row)
        cur += step
        if max_windows and len(rows) >= max_windows:
            break

    tab = pd.DataFrame(rows)
    if tab.empty:
        summary = dict(
            n_windows=0,
            n_hit=0,
            hit_rate=0.0,
            median_peak_mult=0.0,
            mean_peak_mult=0.0,
            max_peak_mult=0.0,
            min_peak_mult=0.0,
            median_final_mult=0.0,
            pct_survived=0.0,
            n_account_liq=0,
            n_mdd_ok=0,
            pct_mdd_le_50=0.0,
            worst_mdd=0.0,
        )
    else:
        summary = {
            "n_windows": int(len(tab)),
            "n_hit": int(tab["hit_10000x"].sum()),
            "hit_rate": float(tab["hit_10000x"].mean()),
            "median_peak_mult": float(tab["mult_peak"].median()),
            "mean_peak_mult": float(tab["mult_peak"].mean()),
            "max_peak_mult": float(tab["mult_peak"].max()),
            "min_peak_mult": float(tab["mult_peak"].min()),
            "median_final_mult": float(tab["mult_final"].median()),
            "pct_survived": float((tab["final"] > 1.0).mean()),
            "n_account_liq": int(tab["account_liq"].sum()),
            "pct_account_liq": float(tab["account_liq"].mean()),
            "n_mdd_ok": int((tab["mdd"] >= -50.0).sum()),
            "pct_mdd_le_50": float((tab["mdd"] >= -50.0).mean()),
            "worst_mdd": float(tab["mdd"].min()),
            "median_mdd": float(tab["mdd"].median()),
            "best_window": tab.loc[tab["mult_peak"].idxmax(), ["start", "end", "mult_peak"]].to_dict(),
            "total_slot_liq": int(tab["liq"].sum()),
            "total_trades": int(tab["trades"].sum()),
        }
    return {"summary": summary, "windows": tab}


def main():
    args = parse_args()
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    for s in symbols:
        if s not in STRATEGY_BUILDERS:
            raise SystemExit(f"unknown symbol/strategy: {s}")

    eval_frames, signal_frames = load_portfolio_frames(
        Path(args.data_root), symbols, start=args.start, end=args.end
    )
    signals = build_all_signals(signal_frames)
    # clip signals to eval range (warmup bars already baked into indicator state)
    if args.start:
        cut = pd.Timestamp(args.start, tz="UTC")
        signals = {s: sig[sig.index >= cut].copy() for s, sig in signals.items()}
    frames = eval_frames
    cfg = PortfolioConfig(
        initial_capital=args.capital,
        target_equity=args.capital * args.target_mult,
        leverage=args.leverage,
        fee_rate=args.fee,
        slippage=args.slippage,
    )
    print(
        f"[cfg] PORT5 capital={args.capital} lev={args.leverage} "
        f"slot_frac={cfg.slot_frac} fee={args.fee} slip={args.slippage}"
    )
    out = evaluate_portfolio_windows(
        frames,
        signals,
        cfg,
        args.window_days,
        args.step_days,
        args.target_mult,
        args.max_windows,
    )
    s, tab = out["summary"], out["windows"]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if not tab.empty:
        tab.to_csv(out_dir / f"{args.tag}_windows.csv", index=False)
    payload = {
        "tag": args.tag,
        "symbol": "PORT5",
        "symbols": symbols,
        "leverage": args.leverage,
        "window_days": args.window_days,
        "step_days": args.step_days,
        "target_mult": args.target_mult,
        "slot_frac": cfg.slot_frac,
        "summary": s,
    }
    path = out_dir / f"{args.tag}_window_summary.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print("\n========== PORTFOLIO WINDOW RESULT ==========")
    print(f"windows={s['n_windows']}  hits_10000x={s['n_hit']}  hit_rate={s.get('hit_rate', 0)*100:.2f}%")
    print(
        f"peak_mult median={s.get('median_peak_mult', 0):.3f} "
        f"min={s.get('min_peak_mult', 0):.3f} max={s.get('max_peak_mult', 0):.3f}"
    )
    print(f"survived={s.get('pct_survived', 0)*100:.1f}%  account_liq={s.get('n_account_liq', 0)}  slot_liq={s.get('total_slot_liq', s.get('total_liq', 0))}  best={s.get('best_window')}")
    print(
        f"mdd_le_50={s.get('n_mdd_ok', 0)}/{s.get('n_windows', 0)}  "
        f"worst_mdd={s.get('worst_mdd', 0):.1f}%  median_mdd={s.get('median_mdd', 0):.1f}%"
    )
    print(f"[saved] {path}")


if __name__ == "__main__":
    main()
