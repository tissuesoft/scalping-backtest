#!/usr/bin/env python3
"""8h strict research loop: eval -> diagnose -> one code edit -> eval -> keep/revert.

Primary metrics: hits_10000x, then median/min peak (NOT max-only).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "reports" / "iter" / "v2_8h"
STRAT = ROOT / "strategies" / "momentum_breakout.py"
ENG = ROOT / "compound_engine.py"
PARAMS = ROOT / "reports" / "iter" / "champion_params.json"
HOURS = 8.0
DECISIONS = OUT / "decisions.jsonl"
STATUS = OUT / "status.json"
SUMMARY = OUT / "loop_summary.json"


@dataclass
class Metrics:
    hits: int
    n: int
    median: float
    min_peak: float
    max_peak: float
    mean: float
    surv: float
    ge2: int
    ge10: int
    dead: int
    wipe: int
    liq: int
    med_trades: float
    mean_trades: float
    zero_trade: int

    def primary_tuple(self):
        # higher is better for keep
        return (self.hits, self.median, self.min_peak, self.ge2, self.mean, self.surv)


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
        mean=float(s["mean_peak_mult"]),
        surv=float(s["pct_survived"]),
        ge2=int((tab["mult_peak"] >= 2).sum()),
        ge10=int((tab["mult_peak"] >= 10).sum()),
        dead=int((tab["mult_peak"] <= 1.01).sum()),
        wipe=int((tab["final"] <= 1).sum()),
        liq=int(tab["liq"].sum()),
        med_trades=float(tab["trades"].median()),
        mean_trades=float(tab["trades"].mean()),
        zero_trade=int((tab["trades"] == 0).sum()),
    )


def write_diagnose(set_id: int, m: Metrics, hypothesis: str, edit_name: str) -> None:
    lines = [
        f"R{set_id} BEFORE DIAGNOSE",
        "GOAL: EVERY window 10000x from $100. Keep order: hits > median/min > ge2. Max-only is NOT keep.",
        f"hits={m.hits}/{m.n} median={m.median:.4f} min={m.min_peak:.4f} max={m.max_peak:.4f} mean={m.mean:.4f}",
        f"surv={m.surv*100:.1f}% ge2={m.ge2} ge10={m.ge10} dead={m.dead} wipe={m.wipe} liq={m.liq}",
        f"zero_trade={m.zero_trade} med_trades={m.med_trades:.1f} mean_trades={m.mean_trades:.1f}",
        "",
        "FAILURE MODE",
    ]
    if m.med_trades >= 40 and m.wipe >= m.n * 0.5:
        lines.append("- Overtrading chop at high leverage: many trades then wipe before compound.")
    if m.dead >= m.n * 0.5:
        lines.append("- Majority of windows never get a meaningful peak (dead ~1.0).")
    if m.zero_trade >= 15:
        lines.append("- Too many zero-trade windows: filters may be blocking mild regimes.")
    if m.liq >= 20:
        lines.append("- Liquidations frequent: size/risk too aggressive for dual-side.")
    if m.hits == 0 and m.median <= 1.01:
        lines.append("- No path yet to all-window 10000x; need coverage + survival, not one-window max.")
    lines += ["", f"HYPOTHESIS: {hypothesis}", f"EDIT: {edit_name}"]
    (OUT / f"R{set_id}_diagnose.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def better(after: Metrics, before: Metrics) -> tuple[bool, str]:
    if after.hits > before.hits:
        return True, "hits increased"
    if after.median > before.median + 1e-12:
        return True, "median peak increased"
    if after.min_peak > before.min_peak + 1e-12:
        return True, "min peak increased"
    # coverage ladder without survival collapse
    if after.ge2 > before.ge2 and after.mean >= before.mean - 1e-9 and after.surv + 1e-12 >= before.surv:
        return True, "ge2 up with mean/surv not worse"
    if after.ge10 > before.ge10 and after.median >= before.median - 1e-12 and after.surv + 1e-12 >= before.surv:
        return True, "ge10 up with median/surv not worse"
    return False, "no improvement on hits/median/min/coverage"


# --- one coherent source edits (apply/revert via full file backup per set) ---

def edit_force_expand(val: float) -> str:
    t = STRAT.read_text(encoding="utf-8")
    # replace expand block with forced value
    import re
    t2, n = re.subn(
        r"expand_mult = float\(p\[\"atr_expand_mult\"\]\)\n"
        r"    #.*\n"
        r"    if expand_mult > 0:\n"
        r"        expand_mult = min\(expand_mult, [0-9.]+\)\n"
        r"        expand_ok = a > \(sma\(a, int\(p\[\"atr_sma_period\"\]\)\) \* expand_mult\)\n"
        r"    else:\n"
        r"        expand_ok = pd\.Series\(True, index=df\.index\)",
        f'expand_mult = float(p["atr_expand_mult"])\n'
        f"    # AUTO: force expand={val}\n"
        f"    if expand_mult > 0:\n"
        f"        expand_mult = {val}\n"
        f"        expand_ok = a > (sma(a, int(p[\"atr_sma_period\"])) * expand_mult)\n"
        f"    else:\n"
        f"        expand_ok = pd.Series(True, index=df.index)",
        t,
        count=1,
    )
    if n != 1:
        raise RuntimeError(f"expand edit failed n={n}")
    STRAT.write_text(t2, encoding="utf-8")
    return f"force_expand={val}"


def edit_cooldown(val: int) -> str:
    t = STRAT.read_text(encoding="utf-8")
    import re
    t2, n = re.subn(
        r"cooldown = int\(p\[\"cooldown_bars\"\]\)\n\s*reentry = int\(p\.get\(\"reentry_bars\".*",
        f"cooldown = {val}  # AUTO force cooldown\n    reentry = int(p.get(\"reentry_bars\", 180) or 180)",
        t,
        count=1,
    )
    if n != 1:
        # fallback simpler
        if "cooldown = int(p[\"cooldown_bars\"])" not in t:
            raise RuntimeError("cooldown pattern missing")
        t2 = t.replace(
            'cooldown = int(p["cooldown_bars"])',
            f"cooldown = {val}  # AUTO force cooldown",
            1,
        )
    STRAT.write_text(t2, encoding="utf-8")
    return f"force_cooldown={val}"


def edit_trail(val: float) -> str:
    t = STRAT.read_text(encoding="utf-8")
    if 'trail = float(p["trail_atr"])' not in t:
        raise RuntimeError("trail pattern missing")
    t = t.replace(
        'trail = float(p["trail_atr"])',
        f"trail = {val}  # AUTO force trail",
        1,
    )
    STRAT.write_text(t, encoding="utf-8")
    return f"force_trail={val}"


def edit_lookback(val: int) -> str:
    t = STRAT.read_text(encoding="utf-8")
    if 'n = int(p["lookback"])' not in t:
        raise RuntimeError("lookback pattern missing")
    t = t.replace('n = int(p["lookback"])', f"n = {val}  # AUTO force lookback", 1)
    STRAT.write_text(t, encoding="utf-8")
    return f"force_lookback={val}"


def edit_buf(val: float) -> str:
    t = STRAT.read_text(encoding="utf-8")
    if 'buf = float(p["breakout_buffer_atr"]) * a' not in t:
        raise RuntimeError("buf pattern missing")
    t = t.replace(
        'buf = float(p["breakout_buffer_atr"]) * a',
        f"buf = {val} * a  # AUTO force buffer",
        1,
    )
    STRAT.write_text(t, encoding="utf-8")
    return f"force_buf_atr={val}"


def edit_body_min(val: float) -> str:
    t = STRAT.read_text(encoding="utf-8")
    if 'body_min = float(p.get("body_min_atr", 0.0) or 0.0)' not in t:
        raise RuntimeError("body_min pattern missing")
    t = t.replace(
        'body_min = float(p.get("body_min_atr", 0.0) or 0.0)',
        f"body_min = {val}  # AUTO force body_min",
        1,
    )
    STRAT.write_text(t, encoding="utf-8")
    return f"force_body_min={val}"


def edit_min_atr(val: float) -> str:
    t = STRAT.read_text(encoding="utf-8")
    if 'vol_ok = atr_pct >= float(p["min_atr_pct"])' not in t:
        raise RuntimeError("min_atr pattern missing")
    t = t.replace(
        'vol_ok = atr_pct >= float(p["min_atr_pct"])',
        f"vol_ok = atr_pct >= {val}  # AUTO force min_atr",
        1,
    )
    STRAT.write_text(t, encoding="utf-8")
    return f"force_min_atr={val}"


def edit_reentry(val: int) -> str:
    t = STRAT.read_text(encoding="utf-8")
    import re
    t2, n = re.subn(
        r"reentry = int\(p\.get\(\"reentry_bars\", 180\) or 180\)",
        f"reentry = {val}  # AUTO force reentry",
        t,
        count=1,
    )
    if n != 1:
        raise RuntimeError(f"reentry edit failed n={n}")
    STRAT.write_text(t2, encoding="utf-8")
    return f"force_reentry={val}"


def edit_size(val: float) -> str:
    t = ENG.read_text(encoding="utf-8")
    import re
    t2, n = re.subn(
        r"pos_notional = equity \* cfg\.leverage \* size_mult \* [0-9.]+ \* boost.*",
        f"pos_notional = equity * cfg.leverage * size_mult * {val} * boost  # AUTO size",
        t,
        count=1,
    )
    if n != 1:
        raise RuntimeError(f"size edit failed n={n}")
    ENG.write_text(t2, encoding="utf-8")
    return f"base_size={val}"


def edit_risk_cap(val: float) -> str:
    t = ENG.read_text(encoding="utf-8")
    import re
    t2, n = re.subn(
        r"risk_cap_pct: float = [0-9.]+",
        f"risk_cap_pct: float = {val}  # AUTO",
        t,
        count=1,
    )
    if n != 1:
        raise RuntimeError(f"risk edit failed n={n}")
    ENG.write_text(t2, encoding="utf-8")
    return f"risk_cap={val}"


def edit_ht_rule(rule: str) -> str:
    t = STRAT.read_text(encoding="utf-8")
    if 'ema_ht = ht_ema_on_1m(df, int(p["ht_ema"]), p["ht_rule"])' not in t:
        raise RuntimeError("ht pattern missing")
    t = t.replace(
        'ema_ht = ht_ema_on_1m(df, int(p["ht_ema"]), p["ht_rule"])',
        f'ema_ht = ht_ema_on_1m(df, int(p["ht_ema"]), "{rule}")  # AUTO ht',
        1,
    )
    STRAT.write_text(t, encoding="utf-8")
    return f"force_ht_rule={rule}"


def choose_edit(m: Metrics, tried: set[str], set_id: int):
    """Diagnose-driven single edit choice. Prefer untried edits matching failure mode."""
    candidates: list[tuple[str, str, callable]] = []

    # overtrading / wipe
    if m.med_trades >= 30 or m.wipe >= 40:
        candidates += [
            ("stricter expand to cut chop", "force_expand_1.25", lambda: edit_force_expand(1.25)),
            ("stricter expand 1.30", "force_expand_1.30", lambda: edit_force_expand(1.30)),
            ("longer cooldown 480", "cooldown_480", lambda: edit_cooldown(480)),
            ("longer cooldown 720", "cooldown_720", lambda: edit_cooldown(720)),
            ("body_min 0.25 filter", "body_min_0.25", lambda: edit_body_min(0.25)),
            ("body_min 0.4 filter", "body_min_0.40", lambda: edit_body_min(0.40)),
            ("higher min_atr 0.0012", "min_atr_0.0012", lambda: edit_min_atr(0.0012)),
            ("higher min_atr 0.0015", "min_atr_0.0015", lambda: edit_min_atr(0.0015)),
            ("wider breakout buf 0.5", "buf_0.5", lambda: edit_buf(0.5)),
            ("wider breakout buf 0.6", "buf_0.6", lambda: edit_buf(0.6)),
        ]
    # too idle / dead
    if m.zero_trade >= 10 or m.dead >= 40:
        candidates += [
            ("softer expand 1.10", "force_expand_1.10", lambda: edit_force_expand(1.10)),
            ("softer expand 1.05", "force_expand_1.05", lambda: edit_force_expand(1.05)),
            ("shorter lookback 240", "lookback_240", lambda: edit_lookback(240)),
            ("shorter lookback 180", "lookback_180", lambda: edit_lookback(180)),
            ("shorter cooldown 120", "cooldown_120", lambda: edit_cooldown(120)),
            ("lower min_atr 0.0005", "min_atr_0.0005", lambda: edit_min_atr(0.0005)),
            ("tighter buf 0.2", "buf_0.2", lambda: edit_buf(0.2)),
            ("ht 4h slower filter", "ht_4h", lambda: edit_ht_rule("4h")),
            ("ht 15min faster", "ht_15min", lambda: edit_ht_rule("15min")),
        ]
    # liquidations / size
    if m.liq >= 15 or m.surv < 0.25:
        candidates += [
            ("smaller size 1.2", "size_1.2", lambda: edit_size(1.2)),
            ("smaller size 1.0", "size_1.0", lambda: edit_size(1.0)),
            ("smaller size 0.8", "size_0.8", lambda: edit_size(0.8)),
            ("tighter risk_cap 0.0025", "risk_0.0025", lambda: edit_risk_cap(0.0025)),
            ("wider risk_cap 0.0040", "risk_0.0040", lambda: edit_risk_cap(0.0040)),
        ]
    # let winners run / compound path
    candidates += [
        ("wider trail 8", "trail_8", lambda: edit_trail(8.0)),
        ("wider trail 10", "trail_10", lambda: edit_trail(10.0)),
        ("tighter trail 4", "trail_4", lambda: edit_trail(4.0)),
        ("reentry 240", "reentry_240", lambda: edit_reentry(240)),
        ("reentry 90", "reentry_90", lambda: edit_reentry(90)),
        ("reentry 0 off", "reentry_0", lambda: edit_reentry(0)),
        ("lookback 480", "lookback_480", lambda: edit_lookback(480)),
        ("size 1.8 press", "size_1.8", lambda: edit_size(1.8)),
        ("size 2.0 press", "size_2.0", lambda: edit_size(2.0)),
        ("force expand 1.20", "force_expand_1.20", lambda: edit_force_expand(1.20)),
    ]

    # rotate by set_id among matching untried
    unused = [(h, n, f) for (h, n, f) in candidates if n not in tried]
    if not unused:
        # reset tried for soft rotation but keep history in decisions
        tried.clear()
        unused = candidates
    # prefer earlier buckets; pick by set_id
    pick = unused[set_id % len(unused)]
    return pick


def metrics_dict(m: Metrics) -> dict:
    return {
        "hits": m.hits, "median": m.median, "min": m.min_peak, "max": m.max_peak,
        "mean": m.mean, "surv": m.surv, "ge2": m.ge2, "ge10": m.ge10,
        "dead": m.dead, "wipe": m.wipe, "liq": m.liq, "med_trades": m.med_trades,
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    start = time.time()
    end_at = start + HOURS * 3600
    set_id = 0
    tried: set[str] = set()
    keeps = 0
    reverts = 0

    # seed tried from prior decisions if any
    if DECISIONS.exists():
        for line in DECISIONS.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            set_id = max(set_id, int(row.get("set", 0)))
            if row.get("decision") == "REVERT" and row.get("edit_name"):
                tried.add(row["edit_name"])
            if row.get("decision") == "KEEP":
                keeps += 1
                if row.get("edit_name"):
                    tried.discard(row["edit_name"])  # allow revisit variants
            if row.get("decision") == "REVERT":
                reverts += 1

    print(f"[8h] start set_id={set_id} until {datetime.fromtimestamp(end_at).isoformat()}", flush=True)

    while time.time() < end_at:
        set_id += 1
        tag_b = f"R{set_id}_before"
        tag_a = f"R{set_id}_after"
        bak_s = OUT / f"R{set_id}_bak_strat.py"
        bak_e = OUT / f"R{set_id}_bak_engine.py"
        shutil.copy2(STRAT, bak_s)
        shutil.copy2(ENG, bak_e)

        print(f"\n===== SET {set_id} BEFORE =====", flush=True)
        before = run_eval(tag_b)

        hyp, edit_name, apply_fn = choose_edit(before, tried, set_id)
        write_diagnose(set_id, before, hyp, edit_name)
        print(f"[diag] {hyp} | edit={edit_name}", flush=True)

        try:
            applied = apply_fn()
        except Exception as e:
            print(f"[edit-fail] {e}; skip set", flush=True)
            shutil.copy2(bak_s, STRAT)
            shutil.copy2(bak_e, ENG)
            tried.add(edit_name)
            row = {
                "set": set_id, "decision": "REVERT", "edit_name": edit_name,
                "reason": f"edit_failed: {e}", "ts": datetime.now(timezone.utc).isoformat(),
            }
            with DECISIONS.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            reverts += 1
            continue

        print(f"[edit] applied {applied}", flush=True)
        print(f"===== SET {set_id} AFTER =====", flush=True)
        after = run_eval(tag_a)
        ok, reason = better(after, before)

        # max-only improvement without median/hits/ge2 => revert
        if ok and after.hits == before.hits and after.median <= before.median + 1e-12 and after.ge2 <= before.ge2:
            if after.max_peak > before.max_peak and after.min_peak <= before.min_peak + 1e-12:
                ok, reason = False, "max-only improvement rejected"

        if ok:
            decision = "KEEP"
            keeps += 1
            tried.discard(edit_name)
            print(f"[KEEP] {reason}", flush=True)
        else:
            decision = "REVERT"
            reverts += 1
            tried.add(edit_name)
            shutil.copy2(bak_s, STRAT)
            shutil.copy2(bak_e, ENG)
            print(f"[REVERT] {reason}", flush=True)

        row = {
            "set": set_id,
            "decision": decision,
            "edit_name": edit_name,
            "edit": applied,
            "hypothesis": hyp,
            "reason": reason,
            "before": metrics_dict(before),
            "after": metrics_dict(after),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        with DECISIONS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

        status = {
            "set": set_id,
            "keeps": keeps,
            "reverts": reverts,
            "elapsed_h": (time.time() - start) / 3600,
            "remaining_h": max(0.0, (end_at - time.time()) / 3600),
            "last": row,
            "champion_hint": metrics_dict(after if ok else before),
        }
        STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        SUMMARY.write_text(json.dumps({
            "hours": HOURS,
            "sets_done": set_id,
            "keeps": keeps,
            "reverts": reverts,
            "elapsed_h": (time.time() - start) / 3600,
            "goal": "every window 10000x",
            "updated": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False, indent=2), encoding="utf-8")

        if after.hits >= after.n and after.n > 0:
            print("[DONE] all windows hit 10000x", flush=True)
            break

    print(f"[8h] finished sets={set_id} keeps={keeps} reverts={reverts}", flush=True)


if __name__ == "__main__":
    main()
