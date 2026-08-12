#!/usr/bin/env python3
"""11h autonomous loop: eval -> diagnose -> one code edit -> eval -> keep/revert.

Runs until reports/iter/v11h_agent/end_epoch.txt. Writes Bxxx_diagnose.txt each set.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "reports" / "iter" / "v11h_agent"
STRAT = ROOT / "strategies" / "momentum_breakout.py"
ENG = ROOT / "compound_engine.py"
PARAMS = ROOT / "reports" / "iter" / "champion_params.json"
END_EPOCH = OUT / "end_epoch.txt"
DECISIONS = OUT / "decisions.jsonl"
LOG = OUT / "loop_run.log"


@dataclass
class Metrics:
    hits: int
    n: int
    median: float
    min_peak: float
    max_peak: float
    ge2: int
    liq: int
    liqw: int
    dead: int
    wipe: int
    surv: float
    med_trades: float


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_eval(tag: str) -> Metrics:
    cmd = [
        sys.executable, "-u", str(ROOT / "eval_windows.py"),
        "--symbol", "BTCUSDT", "--capital", "100",
        "--params-json", str(PARAMS),
        "--tag", tag, "--out-dir", str(OUT),
    ]
    subprocess.run(cmd, cwd=str(ROOT), check=True)
    s = json.loads((OUT / f"{tag}_window_summary.json").read_text(encoding="utf-8"))["summary"]
    tab = pd.read_csv(OUT / f"{tag}_windows.csv")
    return Metrics(
        hits=int(s["n_hit"]),
        n=int(s["n_windows"]),
        median=float(s["median_peak_mult"]),
        min_peak=float(tab["mult_peak"].min()),
        max_peak=float(s["max_peak_mult"]),
        ge2=int((tab["mult_peak"] >= 2).sum()),
        liq=int(tab["liq"].sum()),
        liqw=int((tab["liq"] > 0).sum()),
        dead=int((tab["mult_peak"] <= 1.01).sum()),
        wipe=int((tab["final"] <= 1).sum()),
        surv=float(s["pct_survived"]),
        med_trades=float(tab["trades"].median()),
    )


def write_diagnose(sid: str, m: Metrics, hypothesis: str, edit: str) -> None:
    text = f"""{sid} BEFORE DIAGNOSE
GOAL: all windows 10000x, liq=0, fees+slippage ON.
Keep: hits > median > min > ge2; liq increase = REVERT; max-only NOT keep.

METRICS hits={m.hits}/{m.n} med={m.median:.4f} min={m.min_peak:.4f} max={m.max_peak:.4f}
ge2={m.ge2} liq={m.liq} liq_windows={m.liqw} dead={m.dead} wipe={m.wipe} surv={m.surv*100:.1f}%
med_trades={m.med_trades:.1f}

FAILURE MODE
"""
    if m.liqw > 0:
        text += f"- {m.liqw} windows with liquidations (total {m.liq}).\n"
    if m.dead >= 10:
        text += f"- {m.dead} dead windows peak~1.\n"
    if m.hits < m.n:
        text += f"- only {m.hits} hit(s); need all-window 10000x.\n"
    text += f"\nHYPOTHESIS: {hypothesis}\nEDIT: {edit}\n"
    (OUT / f"{sid}_diagnose.txt").write_text(text, encoding="utf-8")


def better(after: Metrics, before: Metrics) -> tuple[bool, str]:
    if after.liq > before.liq or after.liqw > before.liqw:
        return False, "liq worse"
    if after.hits > before.hits:
        return True, "hits up"
    if after.median > before.median + 1e-12:
        return True, "median up"
    if after.min_peak > before.min_peak + 1e-12:
        return True, "min up"
    if after.ge2 > before.ge2:
        return True, "ge2 up"
    if after.liq < before.liq and after.median >= before.median - 1e-9:
        return True, "liq down med ok"
    return False, "no primary improve"


def _read_eng() -> str:
    return ENG.read_text(encoding="utf-8")


def _read_strat() -> str:
    return STRAT.read_text(encoding="utf-8")


def _write_eng(t: str) -> None:
    ENG.write_text(t, encoding="utf-8")


def _write_strat(t: str) -> None:
    STRAT.write_text(t, encoding="utf-8")


def edit_later_scale(delta: float) -> str:
    t = _read_eng()
    m = re.search(r"(\s+)close_frac = ([0-9.]+)  # (?:KEEP B|AUTO)", t)
    if not m:
        m = re.search(r"else:\s*\n\s+close_frac = ([0-9.]+)", t)
        if not m:
            raise RuntimeError("later close_frac not found")
        indent = "                        "
        cur = float(m.group(1))
    else:
        indent = m.group(1)
        cur = float(m.group(2))
    new = max(0.01, min(0.05, round(cur + delta, 4)))
    t2 = re.sub(
        r"(\s+)close_frac = [0-9.]+  # (?:KEEP B\d+|AUTO later).*",
        rf"\g<1>close_frac = {new}  # AUTO later",
        t,
        count=1,
    )
    if t2 == t:
        t2 = re.sub(
            r"else:\s*\n\s+close_frac = [0-9.]+.*",
            f"else:\n{indent}close_frac = {new}  # AUTO later",
            t,
            count=1,
        )
    _write_eng(t2)
    return f"later_scale {cur}->{new}"


def edit_trail_mult(factor: float) -> str:
    t = _read_eng()
    m = re.search(r"tr = tr \* ([0-9.eE+-]+)", t)
    if not m:
        raise RuntimeError("trail mult not found")
    cur = float(m.group(1))
    new = cur * factor
    t2 = re.sub(r"tr = tr \* [0-9.eE+-]+.*", f"tr = tr * {new}  # AUTO trail", t, count=1)
    _write_eng(t2)
    return f"trail_mult {cur}->{new}"


def edit_cooldown_cap(delta: int) -> str:
    t = _read_strat()
    m = re.search(r"cooldown = min\(int\(p\[\"cooldown_bars\"\]\), (\d+)\)", t)
    if not m:
        raise RuntimeError("cooldown cap not found")
    cur = int(m.group(1))
    new = max(60, min(360, cur + delta))
    t2 = re.sub(
        r"cooldown = min\(int\(p\[\"cooldown_bars\"\]\), \d+\).*",
        f"cooldown = min(int(p[\"cooldown_bars\"]), {new})  # AUTO cooldown",
        t,
        count=1,
    )
    _write_strat(t2)
    return f"cooldown_cap {cur}->{new}"


def edit_slope_diff(delta: int) -> str:
    t = _read_strat()
    m = re.search(r"ema_slope = ema_ht\.diff\((\d+)\)", t)
    if not m:
        raise RuntimeError("slope diff not found")
    cur = int(m.group(1))
    new = max(60, min(300, cur + delta))
    t2 = re.sub(
        r"ema_slope = ema_ht\.diff\(\d+\).*",
        f"ema_slope = ema_ht.diff({new})  # AUTO slope",
        t,
        count=1,
    )
    _write_strat(t2)
    return f"slope_diff {cur}->{new}"


def edit_risk_cap(delta: float) -> str:
    t = _read_eng()
    m = re.search(r"risk_cap_pct: float = ([0-9.]+)", t)
    if not m:
        raise RuntimeError("risk_cap not found")
    cur = float(m.group(1))
    new = max(0.0015, min(0.005, round(cur + delta, 5)))
    t2 = re.sub(r"risk_cap_pct: float = [0-9.]+.*", f"risk_cap_pct: float = {new}  # AUTO risk", t, count=1)
    _write_eng(t2)
    return f"risk_cap {cur}->{new}"


def edit_win_size_mult(delta: float) -> str:
    t = _read_eng()
    m = re.search(r"win_size_mult: float = ([0-9.]+)", t)
    if not m:
        raise RuntimeError("win_size_mult not found")
    cur = float(m.group(1))
    new = max(1.0, min(3.0, round(cur + delta, 3)))
    t2 = re.sub(r"win_size_mult: float = [0-9.]+.*", f"win_size_mult: float = {new}  # AUTO wsm", t, count=1)
    _write_eng(t2)
    return f"win_size_mult {cur}->{new}"


def edit_lev_cap(delta: float) -> str:
    t = _read_eng()
    m = re.search(r"lev_cap = equity \* cfg\.leverage \* size_mult \* ([0-9.]+) \* boost", t)
    if not m:
        raise RuntimeError("lev_cap not found")
    cur = float(m.group(1))
    new = max(1.0, min(2.0, round(cur + delta, 3)))
    t2 = re.sub(
        r"lev_cap = equity \* cfg\.leverage \* size_mult \* [0-9.]+ \* boost.*",
        f"lev_cap = equity * cfg.leverage * size_mult * {new} * boost  # AUTO lev",
        t,
        count=1,
    )
    _write_eng(t2)
    return f"lev_cap {cur}->{new}"


def edit_reentry_cap(val: int) -> str:
    t = _read_strat()
    if "reentry = min(" in t:
        t2 = re.sub(r"reentry = min\([^)]+\).*", f"reentry = min(int(p.get(\"reentry_bars\", 180) or 180), {val})  # AUTO", t, count=1)
    else:
        t2 = t.replace(
            "reentry = int(p.get(\"reentry_bars\", 180) or 180)",
            f"reentry = min(int(p.get(\"reentry_bars\", 180) or 180), {val})  # AUTO",
            1,
        )
    _write_strat(t2)
    return f"reentry_cap {val}"


def next_set_id() -> int:
    n = 0
    if DECISIONS.exists():
        for line in DECISIONS.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            sid = str(row.get("set", ""))
            if sid.startswith("B"):
                n = max(n, int(sid[1:]))
    return n + 1


def choose_edit(m: Metrics, idx: int) -> tuple[str, str, callable]:
    pool: list[tuple[str, str, callable]] = []
    if m.liqw >= 10:
        pool += [
            ("fewer liq via longer cooldown", "cd+10", lambda: edit_cooldown_cap(10)),
            ("fewer liq via smaller win_size_mult", "wsm-0.03", lambda: edit_win_size_mult(-0.03)),
            ("fewer liq via lower lev_cap", "lev-0.05", lambda: edit_lev_cap(-0.05)),
            ("fewer reentry during cooldown", "reentry120", lambda: edit_reentry_cap(120)),
        ]
    pool += [
        ("lift med via smaller later scale-out", "later-0.001", lambda: edit_later_scale(-0.001)),
        ("tighter post-scale trail", "trail*0.5", lambda: edit_trail_mult(0.5)),
        ("smoother HTF slope +5", "slope+5", lambda: edit_slope_diff(5)),
        ("smoother HTF slope -5", "slope-5", lambda: edit_slope_diff(-5)),
        ("risk_cap -0.00005", "risk-", lambda: edit_risk_cap(-0.00005)),
        ("risk_cap +0.00005", "risk+", lambda: edit_risk_cap(0.00005)),
        ("cooldown -5 more entries", "cd-5", lambda: edit_cooldown_cap(-5)),
        ("later scale +0.001 revert explore", "later+0.001", lambda: edit_later_scale(0.001)),
    ]
    hyp, name, fn = pool[idx % len(pool)]
    return hyp, name, fn


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    end_at = float(END_EPOCH.read_text(encoding="utf-8").strip())
    log(f"11h loop start until {datetime.fromtimestamp(end_at)}")
    keeps = reverts = 0

    while time.time() < end_at:
        n = next_set_id()
        sid = f"B{n:03d}"
        tag_b, tag_a = f"{sid}_before", f"{sid}_after"
        bak_s, bak_e = OUT / f"{sid}_bak_strat.py", OUT / f"{sid}_bak_engine.py"
        shutil.copy2(STRAT, bak_s)
        shutil.copy2(ENG, bak_e)

        # before = current champion on disk
        log(f"===== {sid} BEFORE eval =====")
        before = run_eval(tag_b)
        hyp, edit_name, apply_fn = choose_edit(before, n)
        write_diagnose(sid, before, hyp, edit_name)

        try:
            applied = apply_fn()
        except Exception as e:
            log(f"{sid} edit-fail: {e}")
            shutil.copy2(bak_s, STRAT)
            shutil.copy2(bak_e, ENG)
            row = {"set": sid, "decision": "REVERT", "edit": edit_name, "reason": f"edit_failed:{e}"}
            with DECISIONS.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            reverts += 1
            continue

        log(f"{sid} edit applied: {applied}")
        log(f"===== {sid} AFTER eval =====")
        after = run_eval(tag_a)
        ok, reason = better(after, before)

        if not ok:
            shutil.copy2(bak_s, STRAT)
            shutil.copy2(bak_e, ENG)
            decision = "REVERT"
            reverts += 1
        else:
            decision = "KEEP"
            keeps += 1

        row = {
            "set": sid,
            "decision": decision,
            "edit": applied,
            "edit_name": edit_name,
            "reason": reason,
            "before": {"hits": before.hits, "med": before.median, "ge2": before.ge2, "liq": before.liq, "liqw": before.liqw},
            "after": {"hits": after.hits, "med": after.median, "ge2": after.ge2, "liq": after.liq, "liqw": after.liqw},
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        with DECISIONS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        log(f"{sid} {decision} ({reason}) keeps={keeps} reverts={reverts} med {before.median:.4f}->{after.median:.4f} liq {before.liq}->{after.liq}")

    log(f"DONE keeps={keeps} reverts={reverts}")


if __name__ == "__main__":
    main()
