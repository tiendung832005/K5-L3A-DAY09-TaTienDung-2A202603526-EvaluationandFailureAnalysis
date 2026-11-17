"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item
from lab9.graders import GRADERS


def _check_ratchet(spec: dict, base_spec: dict) -> list[str]:
    problems: list[str] = []
    if spec.get("eval_set_version") != base_spec.get("eval_set_version"):
        return problems

    base_metrics = {m["id"]: m for m in base_spec.get("metrics", [])}
    cur_metrics = {m["id"]: m for m in spec.get("metrics", [])}

    for mid, bm in base_metrics.items():
        if mid not in cur_metrics:
            problems.append(f"ratchet: metric {mid!r} removed from spec")
            continue
        cm = cur_metrics[mid]
        if bm.get("blocking") and not cm.get("blocking"):
            problems.append(f"ratchet: blocking metric {mid!r} became non-blocking")
        bth = bm.get("threshold") or {}
        cth = cm.get("threshold") or {}
        if "min" in bth:
            if "min" not in cth or float(cth["min"]) < float(bth["min"]) - 1e-12:
                problems.append(f"ratchet: {mid} min lowered ({cth.get('min')} < {bth['min']})")
        if "max" in bth:
            if "max" not in cth or float(cth["max"]) > float(bth["max"]) + 1e-12:
                problems.append(f"ratchet: {mid} max raised ({cth.get('max')} > {bth['max']})")
        if "max_increase" in bth:
            if "max_increase" not in cth or float(cth["max_increase"]) > float(bth["max_increase"]) + 1e-12:
                problems.append(f"ratchet: {mid} max_increase raised")
        if bth.get("no_significant_drop") and not cth.get("no_significant_drop"):
            problems.append(f"ratchet: {mid} dropped no_significant_drop")

    base_slices = {(s["name"], s["metric"]): s for s in base_spec.get("slices", [])}
    cur_slices = {(s["name"], s["metric"]): s for s in spec.get("slices", [])}
    for key, bs in base_slices.items():
        if key not in cur_slices:
            problems.append(f"ratchet: slice {key[0]}/{key[1]} removed from spec")
            continue
        cs = cur_slices[key]
        if bs.get("blocking") and not cs.get("blocking"):
            problems.append(f"ratchet: blocking slice {key[0]}/{key[1]} became non-blocking")
        if "min" in bs:
            if "min" not in cs or float(cs["min"]) < float(bs["min"]) - 1e-12:
                problems.append(f"ratchet: slice {key[0]}/{key[1]} min lowered")
        if bs.get("no_significant_drop") and not cs.get("no_significant_drop"):
            problems.append(f"ratchet: slice {key[0]}/{key[1]} dropped no_significant_drop")

    return problems


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate."""
    problems: list[str] = []

    # 1. NaN / inf / None in pr["metrics"]
    for k, v in (pr.get("metrics") or {}).items():
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            problems.append(f"metric {k!r} is NaN or inf")

    # 2. Evaluator failures must be empty
    if pr.get("evaluator_failures"):
        problems.append(f"evaluator_failures non-empty ({len(pr['evaluator_failures'])})")

    # 3. Row count vs manifest items x seeds & duplicate (item_id, seed)
    pr_rows = pr.get("rows") or []
    base_rows = base.get("rows") or []
    manifest = pr.get("manifest") or {}
    expected_rows = int(manifest.get("items") or 0) * len(manifest.get("seeds") or [])
    if expected_rows and len(pr_rows) != expected_rows:
        problems.append(f"row count {len(pr_rows)} != expected {expected_rows}")

    pr_pairs = [(r.get("item_id"), r.get("seed")) for r in pr_rows]
    if len(pr_pairs) != len(set(pr_pairs)):
        problems.append("duplicate (item_id, seed) rows in PR report")

    base_pairs = [(r.get("item_id"), r.get("seed")) for r in base_rows]
    if set(pr_pairs) != set(base_pairs):
        problems.append("(item_id, seed) set differs between PR and baseline")

    # 4. Missing/None metric values in any row for graded spec metrics
    graded_ids = [m["id"] for m in spec.get("metrics", []) if m["id"] in GRADERS]
    for r in pr_rows:
        for mid in graded_ids:
            if r.get(mid) is None:
                problems.append(f"row {r.get('item_id')}@{r.get('seed')} has None for {mid!r}")
                break

    # 5. Slice tag tampering between PR and baseline
    base_slices_by_item: dict[str, set[str]] = {}
    for r in base_rows:
        base_slices_by_item[r["item_id"]] = set(r.get("slices") or [])
    for r in pr_rows:
        iid = r.get("item_id")
        if iid in base_slices_by_item and set(r.get("slices") or []) != base_slices_by_item[iid]:
            problems.append(f"slice tags modified on item {iid}")
            break

    # 6. Spec ratchet check
    if base_spec is not None:
        problems.extend(_check_ratchet(spec, base_spec))

    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices") or []:
        sname = sl["name"]
        mid = sl["metric"]
        a = per_item(pr, mid, slice_name=sname)
        b = per_item(base, mid, slice_name=sname)
        keys = sorted(set(a) & set(b))
        val = round(sum(a.values()) / len(a), 4) if a else None
        verdict, note = "ok", ""
        if val is None or not keys:
            verdict = "missing"
        elif "min" in sl and val < sl["min"]:
            verdict = "fail"
        if sl.get("no_significant_drop") and val is not None and keys:
            d, lo, hi = stats.paired_bootstrap(
                [a[k] for k in keys],
                [b[k] for k in keys],
                n_resamples=bs.get("n_resamples", 1000),
                rng=bs.get("rng", 2027),
            )
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        sid = f"slice:{sname}/{mid}"
        if verdict != "ok" and sl.get("blocking", True):
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if sl.get("blocking", True) else "warn")
        th_display = json.dumps({k: v for k, v in sl.items() if k in ("min", "no_significant_drop")})
        lines.append(f"  {sid:<22} {val!s:<8} {th_display:<40} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())