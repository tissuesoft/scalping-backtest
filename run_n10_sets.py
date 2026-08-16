"""Run 5 PORT5 sets targeting 2023 summer weak windows (P3358 champ).

Usage: python -u run_n10_sets.py --start-tag 3361
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
OUT = ROOT / "reports" / "iter" / "port5_agent"
TRACKED = [
    ROOT / "portfolio_engine.py",
    ROOT / "strategies" / "btc_trend.py",
    ROOT / "strategies" / "eth_breakout.py",
    ROOT / "strategies" / "bnb_structure.py",
    ROOT / "strategies" / "sol_momentum.py",
    ROOT / "strategies" / "xrp_meanrev.py",
    ROOT / "strategies" / "regime.py",
]


@dataclass
class Mut:
    mid: str
    axis: str
    hyp: str
    file: str
    old: str
    new: str


def pool() -> list[Mut]:
    """5 independent edits: lift 2023-08 (~654x) without cutting hits37."""
    return [
        Mut(
            "s5_sol_side_stoch_18_82",
            "sol_side",
            "SOL side 19/81→18/82 — deepen extremes (soft 19/81 already helped summer)",
            "strategies/sol_momentum.py",
            "raw_long = (k < 19) & (k > d) & (k.shift(1) <= d.shift(1)) & (k > k.shift(1)) & vol_ok & a.notna()\n"
            "    raw_short = (k > 81) & (k < d) & (k.shift(1) >= d.shift(1)) & (k < k.shift(1)) & vol_ok & a.notna()",
            "raw_long = (k < 18) & (k > d) & (k.shift(1) <= d.shift(1)) & (k > k.shift(1)) & vol_ok & a.notna()\n"
            "    raw_short = (k > 82) & (k < d) & (k.shift(1) >= d.shift(1)) & (k < k.shift(1)) & vol_ok & a.notna()",
        ),
        Mut(
            "s5_sol_side_cd_80_55",
            "sol_side",
            "SOL side CD 70/50→80/55 — less stacked SOL fade churn",
            "strategies/sol_momentum.py",
            "apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 70, 50)",
            "apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 80, 55)",
        ),
        Mut(
            "s5_bnb_side_rsi_20_80",
            "bnb_side",
            "BNB side RSI 22/78→20/80 — deeper fade extremes",
            "strategies/bnb_structure.py",
            'raw_long = touch_low & (r < 22) & (r > r.shift(1)) & (df["close"] > df["open"]) & (df["close"] > vw) & vol_ok & a.notna()\n'
            '    raw_short = touch_hi & (r > 78) & (r < r.shift(1)) & (df["close"] < df["open"]) & (df["close"] < vw) & vol_ok & a.notna()',
            'raw_long = touch_low & (r < 20) & (r > r.shift(1)) & (df["close"] > df["open"]) & (df["close"] > vw) & vol_ok & a.notna()\n'
            '    raw_short = touch_hi & (r > 80) & (r < r.shift(1)) & (df["close"] < df["open"]) & (df["close"] < vw) & vol_ok & a.notna()',
        ),
        Mut(
            "s5_bnb_side_cd_220_140",
            "bnb_side",
            "BNB side CD 200/130→220/140 — less stacked summer fades",
            "strategies/bnb_structure.py",
            "apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 200, 130)",
            "apply_cooldown(raw_long.fillna(False), raw_short.fillna(False), 220, 140)",
        ),
        Mut(
            "s5_bnb_bear_rsi_floor_20",
            "bnb_bear",
            "BNB bear RSI floor 18→20 — skip oversold dump traps in summer",
            "strategies/bnb_structure.py",
            "& (r < 42) & (r > 18) & (df[\"close\"] < mid) & (df[\"close\"] < vw) & vol_ok & body_ok & a.notna()",
            "& (r < 42) & (r > 20) & (df[\"close\"] < mid) & (df[\"close\"] < vw) & vol_ok & body_ok & a.notna()",
        ),
    ]


def safe_copy(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    if src.resolve() == dst.resolve():
        return
    for attempt in range(8):
        try:
            shutil.copy2(src, dst)
            return
        except PermissionError:
            time.sleep(0.3 * (attempt + 1))
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


def apply_mut(mut: Mut) -> bool:
    path = ROOT / mut.file
    text = path.read_text(encoding="utf-8")
    if text.count(mut.old) != 1:
        return False
    path.write_text(text.replace(mut.old, mut.new, 1), encoding="utf-8")
    return True


def run_eval(tag: str) -> dict:
    cmd = [
        sys.executable,
        "-u",
        str(ROOT / "eval_portfolio_windows.py"),
        "--capital",
        "100",
        "--tag",
        tag,
        "--out-dir",
        str(OUT),
    ]
    log = OUT / f"{tag}_log.txt"
    with log.open("w", encoding="utf-8") as fh:
        proc = subprocess.run(cmd, cwd=str(ROOT), stdout=fh, stderr=subprocess.STDOUT, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"eval failed {tag} code={proc.returncode}")
    return json.loads((OUT / f"{tag}_window_summary.json").read_text(encoding="utf-8"))["summary"]


def decide(before: dict, after: dict) -> str:
    bh, ah = int(before["n_hit"]), int(after["n_hit"])
    bmed, amed = float(before["median_peak_mult"]), float(after["median_peak_mult"])
    bmin, amin = float(before["min_peak_mult"]), float(after["min_peak_mult"])
    bal, aal = int(before.get("n_account_liq", 0)), int(after.get("n_account_liq", 0))
    if aal > bal or ah < bh:
        return "REVERT"
    if ah > bh:
        return "KEEP"
    if amed > bmed:
        return "KEEP"
    if amin > bmin and amed >= bmed * 0.995:
        return "KEEP"
    return "REVERT"


def summer_note(csv_path: Path) -> str:
    if not csv_path.exists():
        return "summer=n/a"
    import csv

    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    parts = []
    for key in ("2023-06-25", "2023-07-25", "2023-08-24"):
        for r in rows:
            if r["start"].startswith(key):
                parts.append(f"{key[5:]}={float(r['mult_peak']):.1f}")
    return "summer=[" + ", ".join(parts) + "]"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-tag", type=int, default=3361)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    champ = OUT / "_champion_snap"
    snapshot(champ)

    muts = pool()
    bad = []
    for mut in muts:
        restore(champ)
        if not apply_mut(mut):
            bad.append(mut.mid)
    restore(champ)
    if bad:
        print("[s5] FATAL pattern fail:", bad, flush=True)
        sys.exit(1)
    print(f"[s5] {len(muts)} mutations OK; start=P{args.start_tag}", flush=True)

    set_n = args.start_tag
    before_tag = f"P{set_n}_before"
    print(f"[s5] baseline {before_tag}", flush=True)
    before = run_eval(before_tag)
    print(
        f"[s5] baseline hits={before['n_hit']} med={before['median_peak_mult']:.2f} "
        f"min={before['min_peak_mult']:.3f} acc={before.get('n_account_liq')}",
        flush=True,
    )

    history = []
    for mut in muts:
        tag = f"P{set_n}"
        diag = OUT / f"{tag}_diagnose.txt"
        weak = summer_note(OUT / f"{before_tag}_windows.csv")
        diag.write_text(
            "\n".join(
                [
                    f"{tag} BEFORE (champ P3358 — hits37 med11859 min654)",
                    f"hits={before['n_hit']} med={before['median_peak_mult']:.4f} "
                    f"min={before['min_peak_mult']:.4f} acc_liq={before.get('n_account_liq')}",
                    f"TARGET: lift 2023-08 (~654x) via BNB/SOL side+bear entry | {weak}",
                    "",
                    f"[{mut.axis}] {mut.hyp}",
                    f"ONE CHANGE: {mut.mid} -> {mut.file}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        safe_copy(OUT / f"{before_tag}_windows.csv", OUT / f"{tag}_before_windows.csv")
        safe_copy(
            OUT / f"{before_tag}_window_summary.json",
            OUT / f"{tag}_before_window_summary.json",
        )

        restore(champ)
        if not apply_mut(mut):
            print(f"[s5] skip {mut.mid} (pattern stale after KEEP)", flush=True)
            # still advance tag so we complete 5 attempts from remaining muts
            set_n += 1
            continue

        after_tag = f"{tag}_after"
        print(f"[s5] {tag} {mut.mid} → eval", flush=True)
        after = run_eval(after_tag)
        decision = decide(before, after)
        with diag.open("a", encoding="utf-8") as fh:
            fh.write(
                f"{decision}: hits {before['n_hit']}→{after['n_hit']} "
                f"med {before['median_peak_mult']:.2f}→{after['median_peak_mult']:.2f} "
                f"min {before['min_peak_mult']:.3f}→{after['min_peak_mult']:.3f} "
                f"acc_liq {before.get('n_account_liq')}→{after.get('n_account_liq')}\n"
            )
            fh.write(summer_note(OUT / f"{after_tag}_windows.csv") + "\n")
        print(
            f"[s5] {tag} {decision} hits {before['n_hit']}→{after['n_hit']} "
            f"med {before['median_peak_mult']:.1f}→{after['median_peak_mult']:.1f} "
            f"min {before['min_peak_mult']:.2f}→{after['min_peak_mult']:.2f}",
            flush=True,
        )
        history.append({"tag": tag, "mut": mut.mid, "decision": decision})

        if decision == "KEEP":
            snapshot(champ)
            before = after
            set_n += 1
            before_tag = f"P{set_n}_before"
            safe_copy(OUT / f"{after_tag}_windows.csv", OUT / f"{before_tag}_windows.csv")
            safe_copy(
                OUT / f"{after_tag}_window_summary.json",
                OUT / f"{before_tag}_window_summary.json",
            )
        else:
            restore(champ)
            set_n += 1
            before_tag = f"P{set_n}_before"
            safe_copy(OUT / f"{tag}_before_windows.csv", OUT / f"{before_tag}_windows.csv")
            safe_copy(
                OUT / f"{tag}_before_window_summary.json",
                OUT / f"{before_tag}_window_summary.json",
            )

    keeps = [h for h in history if h["decision"] == "KEEP"]
    print("[s5] finished", flush=True)
    print(
        json.dumps(
            {
                "sets": len(history),
                "keeps": keeps,
                "final": {
                    "n_hit": before["n_hit"],
                    "median": before["median_peak_mult"],
                    "min": before["min_peak_mult"],
                    "acc_liq": before.get("n_account_liq"),
                },
            },
            indent=2,
            default=str,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
