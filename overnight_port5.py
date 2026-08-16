"""PORT5 research loop: eval → diagnose → 1 source mutation → eval → keep/revert.

Usage:
  python -u overnight_port5.py --sets 80 --start-tag 1194 --out-dir reports/iter/port5_agent
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TRACKED = [
    ROOT / "portfolio_engine.py",
    ROOT / "strategies" / "btc_trend.py",
    ROOT / "strategies" / "eth_breakout.py",
    ROOT / "strategies" / "bnb_structure.py",
    ROOT / "strategies" / "sol_momentum.py",
    ROOT / "strategies" / "xrp_meanrev.py",
    ROOT / "strategies" / "regime.py",
]


from overnight_mutations import Mutation, mutations



def safe_copy(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    if src.resolve() == dst.resolve():
        return
    for attempt in range(5):
        try:
            shutil.copy2(src, dst)
            return
        except PermissionError:
            time.sleep(0.4 * (attempt + 1))
    dst.write_bytes(src.read_bytes())


def snapshot(dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for f in TRACKED:
        if f.exists():
            shutil.copy2(f, dst / f.name)


def restore(src: Path) -> None:
    for f in TRACKED:
        bak = src / f.name
        if bak.exists():
            shutil.copy2(bak, f)


def apply_mutation(mut: Mutation) -> bool:
    path = ROOT / mut.file
    text = path.read_text(encoding="utf-8")
    if mut.old not in text:
        return False
    if text.count(mut.old) != 1:
        return False
    path.write_text(text.replace(mut.old, mut.new, 1), encoding="utf-8")
    return True


def run_eval(tag: str, out_dir: Path) -> dict:
    cmd = [
        sys.executable,
        "-u",
        str(ROOT / "eval_portfolio_windows.py"),
        "--capital",
        "100",
        "--tag",
        tag,
        "--out-dir",
        str(out_dir),
    ]
    log = out_dir / f"{tag}_log.txt"
    with log.open("w", encoding="utf-8") as fh:
        proc = subprocess.run(cmd, cwd=str(ROOT), stdout=fh, stderr=subprocess.STDOUT, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"eval failed tag={tag} code={proc.returncode}; see {log}")
    summary_path = out_dir / f"{tag}_window_summary.json"
    return json.loads(summary_path.read_text(encoding="utf-8"))["summary"]


def decide(before: dict, after: dict) -> str:
    """Keep order: hits → median → min → n_account_liq must not rise."""
    bh, ah = int(before["n_hit"]), int(after["n_hit"])
    bmed, amed = float(before["median_peak_mult"]), float(after["median_peak_mult"])
    bmin, amin = float(before["min_peak_mult"]), float(after["min_peak_mult"])
    bal, aal = int(before.get("n_account_liq", 0)), int(after.get("n_account_liq", 0))

    if aal > bal:
        return "REVERT"
    if ah < bh:
        return "REVERT"
    if ah > bh:
        return "KEEP"
    # hits flat: clearly higher median or min, without median collapse
    if amed > bmed and aal <= bal:
        return "KEEP"
    if amin > bmin and amed >= bmed * 0.995 and aal <= bal:
        return "KEEP"
    return "REVERT"


def pick_mutation(
    pool: list[Mutation],
    tried: set[str],
    failed_axis_streak: dict[str, int],
) -> Mutation | None:
    # rotate symbol-regime first; block axes that failed 5+ in a row
    # Summer weak-window focus: SOL side first (P3280 signal), then BNB/SOL bear
    prefer = [
        "sol_side",
        "bnb_side",
        "bnb_bear",
        "sol_bear",
        "bnb_bull",
        "sol_bull",
        "eth_side",
        "eth_bear",
        "eth_bull",
        "btc_side",
        "btc_bear",
        "btc_bull",
        "xrp_side",
        "xrp_bear",
        "xrp_bull",
        "regime",
        "engine",
    ]
    blocked = {a for a, n in failed_axis_streak.items() if n >= 5}
    for axis in prefer:
        if axis in blocked:
            continue
        for mut in pool:
            if mut.mid in tried:
                continue
            if mut.axis != axis:
                continue
            return mut
    for mut in pool:
        if mut.mid not in tried:
            return mut
    return None


def weak_windows_note(out_dir: Path, tag_before: str) -> str:
    csv_path = out_dir / f"{tag_before}_windows.csv"
    if not csv_path.exists():
        return "weak=n/a"
    import csv

    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    ranked = sorted(rows, key=lambda r: float(r["mult_peak"]))
    parts = [f"{r['start'][:10]}={float(r['mult_peak']):.2f}" for r in ranked[:5]]
    near = sorted(rows, key=lambda r: -float(r["mult_peak"]))
    near_miss = [f"{r['start'][:10]}={float(r['mult_peak']):.0f}" for r in near if not (r.get("hit_10000x") in ("True", "true", "1")) ][:3]
    return "weak=[" + ", ".join(parts) + "] near=[" + ", ".join(near_miss) + "]"


def write_diagnose(path: Path, tag: str, before: dict, mut: Mutation, weak: str) -> None:
    path.write_text(
        "\n".join(
            [
                f"{tag} BEFORE",
                "=" * 40,
                f"hits={before.get('n_hit')}/59 med={float(before.get('median_peak_mult')):.4f} "
                f"min={float(before.get('min_peak_mult')):.4f} max={float(before.get('max_peak_mult', 0)):.1f}",
                f"account_liq={before.get('n_account_liq')} slot_liq={before.get('total_slot_liq')} "
                f"surv={float(before.get('pct_survived', 0)):.3f}",
                f"{weak}",
                "",
                "FAILURE MODE / HYPOTHESIS:",
                f"[{mut.axis}] {mut.hypothesis}",
                f"ONE CHANGE: {mut.mid} -> {mut.file}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def append_decision(path: Path, decision: str, before: dict, after: dict) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(
            f"{decision}: hits {before.get('n_hit')}→{after.get('n_hit')} "
            f"med {float(before.get('median_peak_mult')):.2f}→{float(after.get('median_peak_mult')):.2f} "
            f"min {float(before.get('min_peak_mult')):.3f}→{float(after.get('min_peak_mult')):.3f} "
            f"acc_liq {before.get('n_account_liq')}→{after.get('n_account_liq')}\n"
        )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", type=int, default=0, help="Exact number of sets to run (0 = use --hours)")
    ap.add_argument("--hours", type=float, default=12.0)
    ap.add_argument("--out-dir", default="reports/iter/port5_agent")
    ap.add_argument("--start-tag", type=int, default=1194)
    ap.add_argument("--state", default="reports/iter/port5_agent/overnight_state.json")
    ap.add_argument("--fresh-tried", action="store_true", help="Ignore prior tried mutations")
    args = ap.parse_args()

    out_dir = ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    state_path = ROOT / args.state
    champ_dir = out_dir / "_champion_snap"

    deadline = time.time() + args.hours * 3600
    target_sets = args.sets if args.sets > 0 else 10**9
    pool = mutations()
    set_n = args.start_tag
    tried: set[str] = set()
    failed_axis_streak: dict[str, int] = {}
    history: list[dict] = []

    if state_path.exists() and not args.fresh_tried:
        st = json.loads(state_path.read_text(encoding="utf-8"))
        # only resume set number if continuing same campaign; user asked fresh 80 from 1194
        if int(st.get("next_set", 0)) >= set_n:
            set_n = int(st.get("next_set", set_n))
        tried = set(st.get("tried", []))
        failed_axis_streak = dict(st.get("failed_axis_streak", {}))
        history = list(st.get("history", []))

    if args.fresh_tried:
        tried.clear()
        failed_axis_streak.clear()

    print(
        f"[overnight] sets_target={target_sets if args.sets else 'hours'} "
        f"start=P{set_n} mutations={len(pool)} hours_cap={args.hours}",
        flush=True,
    )

    snapshot(champ_dir)

    before_tag = f"P{set_n}_before"
    print(f"[overnight] baseline eval {before_tag}", flush=True)
    before = run_eval(before_tag, out_dir)
    print(
        f"[overnight] baseline hits={before['n_hit']} med={before['median_peak_mult']:.2f} "
        f"min={before['min_peak_mult']:.3f} acc_liq={before.get('n_account_liq')}",
        flush=True,
    )

    sets_this_run = 0
    while sets_this_run < target_sets and time.time() < deadline:
        stop = out_dir / "OVERNIGHT_STOP"
        if stop.exists():
            print("[overnight] STOP file detected; exiting", flush=True)
            break

        if int(before.get("n_hit", 0)) >= int(before.get("n_windows", 59)) and int(
            before.get("n_account_liq", 1)
        ) == 0:
            print("[overnight] DONE all windows hit_10000x and wipe=0", flush=True)
            break

        mut = pick_mutation(pool, tried, failed_axis_streak)
        if mut is None:
            print("[overnight] pool exhausted; clearing tried", flush=True)
            tried.clear()
            failed_axis_streak.clear()
            mut = pick_mutation(pool, tried, failed_axis_streak)
            if mut is None:
                print("[overnight] no mutations available", flush=True)
                break

        tag = f"P{set_n}"
        diagnose = out_dir / f"{tag}_diagnose.txt"
        weak = weak_windows_note(out_dir, before_tag)
        write_diagnose(diagnose, f"{tag} BEFORE", before, mut, weak)

        safe_copy(out_dir / f"{before_tag}_windows.csv", out_dir / f"{tag}_before_windows.csv")
        safe_copy(
            out_dir / f"{before_tag}_window_summary.json",
            out_dir / f"{tag}_before_window_summary.json",
        )

        restore(champ_dir)
        ok = apply_mutation(mut)
        if not ok:
            print(f"[overnight] skip {mut.mid}: pattern not found / not unique", flush=True)
            tried.add(mut.mid)
            restore(champ_dir)
            continue

        after_tag = f"{tag}_after"
        print(f"[overnight] {tag} apply {mut.mid} ({mut.axis}) → eval", flush=True)
        try:
            after = run_eval(after_tag, out_dir)
        except Exception as e:
            print(f"[overnight] {tag} eval error: {e}; REVERT", flush=True)
            restore(champ_dir)
            tried.add(mut.mid)
            failed_axis_streak[mut.axis] = failed_axis_streak.get(mut.axis, 0) + 1
            set_n += 1
            sets_this_run += 1
            before_tag = f"P{set_n}_before"
            before = run_eval(before_tag, out_dir)
            continue

        decision = decide(before, after)
        append_decision(diagnose, decision, before, after)
        print(
            f"[overnight] {tag} {decision} hits {before['n_hit']}→{after['n_hit']} "
            f"med {before['median_peak_mult']:.1f}→{after['median_peak_mult']:.1f} "
            f"min {before['min_peak_mult']:.2f}→{after['min_peak_mult']:.2f} "
            f"acc_liq {before.get('n_account_liq')}→{after.get('n_account_liq')}",
            flush=True,
        )

        tried.add(mut.mid)
        history.append(
            {
                "tag": tag,
                "mutation": mut.mid,
                "axis": mut.axis,
                "decision": decision,
                "before": {
                    k: before.get(k)
                    for k in ("n_hit", "median_peak_mult", "min_peak_mult", "n_account_liq")
                },
                "after": {
                    k: after.get(k)
                    for k in ("n_hit", "median_peak_mult", "min_peak_mult", "n_account_liq")
                },
            }
        )
        sets_this_run += 1

        if decision == "KEEP":
            snapshot(champ_dir)
            failed_axis_streak[mut.axis] = 0
            before = after
            set_n += 1
            before_tag = f"P{set_n}_before"
            safe_copy(out_dir / f"{after_tag}_windows.csv", out_dir / f"{before_tag}_windows.csv")
            safe_copy(
                out_dir / f"{after_tag}_window_summary.json",
                out_dir / f"{before_tag}_window_summary.json",
            )
        else:
            restore(champ_dir)
            failed_axis_streak[mut.axis] = failed_axis_streak.get(mut.axis, 0) + 1
            set_n += 1
            before_tag = f"P{set_n}_before"
            safe_copy(out_dir / f"{tag}_before_windows.csv", out_dir / f"{before_tag}_windows.csv")
            safe_copy(
                out_dir / f"{tag}_before_window_summary.json",
                out_dir / f"{before_tag}_window_summary.json",
            )

        session = {
            "overnight": True,
            "next_set": set_n,
            "sets_this_run": sets_this_run,
            "tried": sorted(tried),
            "failed_axis_streak": failed_axis_streak,
            "history": history[-300:],
            "summary": before,
            "remaining_sec": max(0, deadline - time.time()),
        }
        keeps = [h for h in history if h["decision"] == "KEEP"]
        if keeps:
            session["champion_tag"] = keeps[-1]["tag"]
            session["champion_after"] = keeps[-1]["after"]
        else:
            session["champion_tag"] = "P1188_baseline"
            session["champion_after"] = {
                k: before.get(k)
                for k in ("n_hit", "median_peak_mult", "min_peak_mult", "n_account_liq")
            }
        state_path.write_text(
            json.dumps(session, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
        )
        (out_dir / "session.json").write_text(
            json.dumps(session, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
        )
        print(
            f"[overnight] progress {sets_this_run}/{target_sets if args.sets else '?'} "
            f"next=P{set_n} keeps={sum(1 for h in history if h['decision']=='KEEP')}",
            flush=True,
        )

    print("[overnight] finished", flush=True)
    print(
        json.dumps(
            {
                "sets_this_run": sets_this_run,
                "keeps": sum(1 for h in history if h["decision"] == "KEEP"),
                "summary": before,
            },
            indent=2,
            default=str,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
