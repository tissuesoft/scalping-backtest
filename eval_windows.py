"""롤링 1~2달 창 평가."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from compound_engine import CompoundConfig, run_compound
from data_loader import load_parquet_dir
from strategies.momentum_breakout import DEFAULT_PARAMS, build_signals


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="BTCUSDT")
    p.add_argument("--data-root", default="data")
    p.add_argument("--capital", type=float, default=100.0)
    p.add_argument("--target-mult", type=float, default=10_000.0)
    p.add_argument("--leverage", type=float, default=100.0)
    p.add_argument("--fee", type=float, default=0.0004)
    p.add_argument("--slippage", type=float, default=0.0001)
    p.add_argument("--window-days", type=int, default=60)
    p.add_argument("--step-days", type=int, default=30)
    p.add_argument("--params-json", default=None)
    p.add_argument("--out-dir", default="reports/iter")
    p.add_argument("--tag", default="windows")
    p.add_argument("--max-windows", type=int, default=0)
    return p.parse_args()


def evaluate_windows(df, signals, cfg, window_days, step_days, target_mult, max_windows=0):
    target_eq = cfg.initial_capital * target_mult
    cfg = CompoundConfig(
        initial_capital=cfg.initial_capital,
        target_equity=target_eq,
        leverage=cfg.leverage,
        fee_rate=cfg.fee_rate,
        slippage=cfg.slippage,
        mmr=cfg.mmr,
        pyramid_at_r=cfg.pyramid_at_r,
        pyramid_frac=cfg.pyramid_frac,
        pyramid_be=cfg.pyramid_be,
        trail_unlock_r=cfg.trail_unlock_r,
        trail_unlock_mult=cfg.trail_unlock_mult,
    )
    start, end = df.index[0], df.index[-1]
    window, step = pd.Timedelta(days=window_days), pd.Timedelta(days=step_days)
    rows, cur = [], start
    while cur + window <= end:
        w_end = cur + window
        sl = df.loc[cur:w_end]
        sig = signals.loc[sl.index]
        if len(sl) >= 1000:
            res = run_compound(sl, sig, "win", cfg)
            peak = float(res.equity.max()) if len(res.equity) else cfg.initial_capital
            final = float(res.metrics["final_equity"])
            rows.append({
                "start": str(cur), "end": str(w_end), "bars": len(sl),
                "final": final, "peak": peak,
                "mult_final": final / cfg.initial_capital,
                "mult_peak": peak / cfg.initial_capital,
                "hit_10000x": bool(res.hit_target) or peak >= target_eq,
                "trades": int(res.metrics["trades"]),
                "pf": res.metrics["profit_factor"],
                "mdd": res.metrics["max_drawdown_pct"],
                "liq": int(res.metrics["liquidations"]),
            })
        cur += step
        if max_windows and len(rows) >= max_windows:
            break
    tab = pd.DataFrame(rows)
    if tab.empty:
        summary = dict(n_windows=0, n_hit=0, hit_rate=0.0, median_peak_mult=0.0,
                       mean_peak_mult=0.0, max_peak_mult=0.0, median_final_mult=0.0, pct_survived=0.0)
    else:
        summary = {
            "n_windows": int(len(tab)),
            "n_hit": int(tab["hit_10000x"].sum()),
            "hit_rate": float(tab["hit_10000x"].mean()),
            "median_peak_mult": float(tab["mult_peak"].median()),
            "mean_peak_mult": float(tab["mult_peak"].mean()),
            "max_peak_mult": float(tab["mult_peak"].max()),
            "median_final_mult": float(tab["mult_final"].median()),
            "pct_survived": float((tab["final"] > 1.0).mean()),
            "best_window": tab.loc[tab["mult_peak"].idxmax(), ["start", "end", "mult_peak"]].to_dict(),
        }
    return {"summary": summary, "windows": tab}


def main():
    args = parse_args()
    df = load_parquet_dir(Path(args.data_root) / args.symbol / "1m")
    print(f"[data] {args.symbol} rows={len(df):,} {df.index[0]} -> {df.index[-1]}")
    params = dict(DEFAULT_PARAMS)
    if args.params_json:
        params.update(json.loads(Path(args.params_json).read_text(encoding="utf-8")))
    leverage = float(params.pop("_leverage", args.leverage))
    base_cfg = CompoundConfig()
    _pr = params.pop("_pyramid_at_r", None)
    _pf = params.pop("_pyramid_frac", None)
    _pb = params.pop("_pyramid_be", None)
    pyramid_at_r = float(_pr) if _pr is not None else base_cfg.pyramid_at_r
    pyramid_frac = float(_pf) if _pf is not None else base_cfg.pyramid_frac
    pyramid_be = bool(_pb) if _pb is not None else base_cfg.pyramid_be
    # None → CompoundConfig 기본값 사용 (코드 기본 trail unlock 유지)
    _ur = params.pop("_trail_unlock_r", None)
    _um = params.pop("_trail_unlock_mult", None)
    trail_unlock_r = float(_ur) if _ur is not None else base_cfg.trail_unlock_r
    trail_unlock_mult = float(_um) if _um is not None else base_cfg.trail_unlock_mult
    print(f"[params] {params}")
    print(f"[cfg] lev={leverage} pyramid_r={pyramid_at_r} unlock_r={trail_unlock_r}")
    signals = build_signals(df, params)
    cfg = CompoundConfig(
        initial_capital=args.capital,
        target_equity=args.capital * args.target_mult,
        leverage=leverage,
        fee_rate=args.fee,
        slippage=args.slippage,
        pyramid_at_r=pyramid_at_r,
        pyramid_frac=pyramid_frac,
        pyramid_be=pyramid_be,
        trail_unlock_r=trail_unlock_r,
        trail_unlock_mult=trail_unlock_mult,
    )
    out = evaluate_windows(df, signals, cfg, args.window_days, args.step_days, args.target_mult, args.max_windows)
    s, tab = out["summary"], out["windows"]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if not tab.empty:
        tab.to_csv(out_dir / f"{args.tag}_windows.csv", index=False)
    payload = {
        "tag": args.tag, "symbol": args.symbol, "params": params, "leverage": leverage,
        "trail_unlock_r": trail_unlock_r, "trail_unlock_mult": trail_unlock_mult,
        "window_days": args.window_days, "step_days": args.step_days,
        "target_mult": args.target_mult, "summary": s,
    }
    path = out_dir / f"{args.tag}_window_summary.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print("\n========== WINDOW RESULT ==========")
    print(f"windows={s['n_windows']}  hits_10000x={s['n_hit']}  hit_rate={s['hit_rate']*100:.2f}%")
    print(f"peak_mult median={s['median_peak_mult']:.3f} max={s['max_peak_mult']:.3f}")
    print(f"survived={s['pct_survived']*100:.1f}%  best={s.get('best_window')}")
    print(f"[saved] {path}")


if __name__ == "__main__":
    main()
