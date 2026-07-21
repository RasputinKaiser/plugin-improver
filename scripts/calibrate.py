#!/usr/bin/env python3
"""Saturation meter — is the audit score spread wide, or has it re-saturated?

Stdlib only. Imports score.py and portfolio.py as modules.
  python3 scripts/calibrate.py                       # inventory spread (human)
  python3 scripts/calibrate.py ~/plugins/*           # explicit plugin roots
  python3 scripts/calibrate.py --json | --md         # structured output
  python3 scripts/calibrate.py --check               # exit 1 if re-saturated
  python3 scripts/calibrate.py --check --max-maxout-frac 0.6 --min-stdev 5
  python3 scripts/calibrate.py selftest              # hermetic fixtures

Scores a set of plugin SOURCE roots (default: the same local inventory
portfolio.py sweeps; NEVER read-only cache/ installs) and reports the SCORE
DISTRIBUTION so saturation is visible: overall stats + histogram + band split,
and the per-dimension MAX-OUT RATE (the key saturation signal — % of plugins
where a dimension hits its rubric ceiling). `--check` is a CI guardrail against
a future change re-saturating the audit: it fails if any single dimension maxes
out for too large a fraction of plugins, or the overall spread collapses.

Relies only on score.py's stable schema: total.auto / total.max and, per
dimension, dimensions[k].auto / dimensions[k].max.
"""
import json
import os
import statistics
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import score  # noqa: E402  (lives beside this file)
import portfolio  # noqa: E402  (reuse source discovery)

# Frozen quality bands (0–100 scale). Reported as a distribution; the audit's
# deterministic `auto` floor is what we band here.
BANDS = [
    ("Exceptional", 92),
    ("Strong", 82),
    ("Solid", 68),
    ("Needs work", 50),
    ("Poor", 0),
]
DEFAULT_MAX_MAXOUT_FRAC = 0.60
DEFAULT_MIN_STDEV = 5.0


def band_of(v):
    for name, lo in BANDS:
        if v >= lo:
            return name
    return BANDS[-1][0]


# ---------- discovery ----------

def resolve_roots(args):
    """Turn CLI args into concrete plugin SOURCE roots.

    No args -> the local inventory portfolio.py sweeps. Explicit args: each is a
    plugin root if it looks like one, else treated as a parent dir to enumerate
    (so both `~/plugins/*` and `~/plugins` work). Never yields cache/ installs.
    """
    if not args:
        srcs = portfolio.enumerate_sources(portfolio.DEFAULT_SOURCE_ROOTS)
    else:
        srcs = []
        for a in args:
            p = Path(os.path.expanduser(a))
            if not p.is_dir():
                continue
            if portfolio.is_plugin_root(p):
                srcs.append(p)
            else:
                srcs.extend(portfolio.enumerate_sources([str(p)]))
    seen, out = set(), []
    for p in srcs:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            out.append(p)
    return out


def collect(roots):
    """Score each root. Returns (rows, skipped) — a plugin that fails to score
    (raises, or yields a degenerate max==0) is skipped and noted, not fatal."""
    rows, skipped = [], []
    for r in roots:
        try:
            res = score.score(r)
        except Exception as e:  # pragma: no cover - defensive
            skipped.append({"path": str(r), "error": str(e)})
            continue
        if res.get("total", {}).get("max", 0) <= 0:
            skipped.append({"path": str(r), "error": "total max is 0 (nothing scorable)"})
            continue
        rows.append({
            "name": portfolio.plugin_name(Path(r)),
            "path": str(Path(r).resolve()),
            "auto": res["total"]["auto"],
            "max": res["total"]["max"],
            "dimensions": {k: {"auto": v["auto"], "max": v["max"]}
                           for k, v in res["dimensions"].items()},
        })
    return rows, skipped


# ---------- analysis ----------

def histogram(scores, width=10):
    """Counts in [0,10), [10,20), … [90,100]. Top bin is inclusive of 100."""
    bins = [0] * 10
    for s in scores:
        idx = int(s // width)
        idx = 0 if idx < 0 else (9 if idx > 9 else idx)
        bins[idx] += 1
    return bins


def analyze(rows):
    scores = [r["auto"] for r in rows]
    n = len(scores)
    if n == 0:
        stats = {"n": 0, "min": None, "max": None, "mean": None,
                 "median": None, "stdev": None}
    else:
        stdev = round(statistics.stdev(scores), 2) if n >= 2 else 0.0
        stats = {
            "n": n,
            "min": round(min(scores), 1),
            "max": round(max(scores), 1),
            "mean": round(statistics.mean(scores), 2),
            "median": round(statistics.median(scores), 2),
            "stdev": stdev,
        }
    # Per-dimension max-out (saturation) rate. Only dimensions with a positive
    # ceiling can saturate; a crashed dimension (max==0) is excluded.
    maxout = {}
    for key, _fn in score.DIMENSIONS:
        maxed = considered = 0
        for r in rows:
            d = r["dimensions"].get(key)
            if not d or d["max"] <= 0:
                continue
            considered += 1
            if abs(d["auto"] - d["max"]) < 1e-9:
                maxed += 1
        frac = (maxed / considered) if considered else 0.0
        maxout[key] = {"maxed": maxed, "considered": considered, "frac": round(frac, 3)}
    bands = {name: 0 for name, _ in BANDS}
    for s in scores:
        bands[band_of(s)] += 1
    return {
        "stats": stats,
        "maxout": maxout,
        "bands": bands,
        "histogram": histogram(scores),
    }


def check(analysis, max_maxout_frac=DEFAULT_MAX_MAXOUT_FRAC, min_stdev=DEFAULT_MIN_STDEV):
    """Return a list of guardrail failures (empty == healthy spread)."""
    failures = []
    for key, m in analysis["maxout"].items():
        if m["considered"] > 0 and m["frac"] > max_maxout_frac:
            failures.append(
                f"dimension '{key}' maxes out for {m['frac'] * 100:.0f}% of "
                f"{m['considered']} plugins (> {max_maxout_frac * 100:.0f}% threshold)")
    st = analysis["stats"]
    if st["n"] is not None and st["n"] >= 2 and st["stdev"] < min_stdev:
        failures.append(
            f"total-score stdev {st['stdev']} < floor {min_stdev} (spread collapsed)")
    return failures


# ---------- rendering ----------

def _bar(count, total, width=30):
    if total <= 0:
        return ""
    return "#" * max(1, round(width * count / total)) if count else ""


def render_table(rows, skipped, analysis, failures, thresholds):
    st = analysis["stats"]
    L = [f"calibrate — {st['n']} plugin(s) scored" +
         (f", {len(skipped)} skipped" if skipped else "")]
    if st["n"] == 0:
        L.append("(no plugin sources found — nothing to calibrate)")
        return "\n".join(L)
    L += [
        "",
        f"  min {st['min']}  max {st['max']}  mean {st['mean']}  "
        f"median {st['median']}  stdev {st['stdev']}",
        "",
        "score histogram (auto floor, 0–100):",
    ]
    bins = analysis["histogram"]
    for i, c in enumerate(bins):
        lo = i * 10
        hi = 100 if i == 9 else lo + 9
        L.append(f"  {lo:>3}-{hi:<3} {c:>3} {_bar(c, st['n'])}")
    L += ["", "band distribution:"]
    for name, _ in BANDS:
        c = analysis["bands"][name]
        L.append(f"  {name:<12} {c:>3} {_bar(c, st['n'])}")
    L += ["", "per-dimension max-out (saturation) rate:"]
    for key, m in analysis["maxout"].items():
        pct = f"{m['frac'] * 100:.0f}%"
        L.append(f"  {key:<20} {m['maxed']:>2}/{m['considered']:<2} {pct:>4} "
                 f"{_bar(m['maxed'], max(m['considered'], 1), 20)}")
    if skipped:
        L += ["", "skipped:"]
        for s in skipped:
            L.append(f"  {s['path']}: {s['error']}")
    L += ["", (f"CHECK: FAIL (max-maxout-frac {thresholds[0]}, min-stdev {thresholds[1]})"
               if failures else "CHECK: PASS")]
    for f in failures:
        L.append(f"  - {f}")
    return "\n".join(L)


def render_md(rows, skipped, analysis, failures, thresholds):
    st = analysis["stats"]
    L = [f"# Calibration — {st['n']} plugin(s) scored"]
    if st["n"] == 0:
        L.append("\n_No plugin sources found._")
        return "\n".join(L)
    L += [
        "",
        f"| N | Min | Max | Mean | Median | Stdev |",
        "|---:|---:|---:|---:|---:|---:|",
        f"| {st['n']} | {st['min']} | {st['max']} | {st['mean']} | "
        f"{st['median']} | {st['stdev']} |",
        "",
        "## Band distribution",
        "",
        "| Band | Count |",
        "|---|---:|",
    ]
    for name, _ in BANDS:
        L.append(f"| {name} | {analysis['bands'][name]} |")
    L += ["", "## Per-dimension max-out (saturation) rate", "",
          "| Dimension | Maxed | Considered | Rate |", "|---|---:|---:|---:|"]
    for key, m in analysis["maxout"].items():
        L.append(f"| {key} | {m['maxed']} | {m['considered']} | {m['frac'] * 100:.0f}% |")
    if skipped:
        L += ["", "## Skipped", ""]
        for s in skipped:
            L.append(f"- `{s['path']}` — {s['error']}")
    L += ["", f"## Check — {'FAIL' if failures else 'PASS'}",
          f"_thresholds: max-maxout-frac {thresholds[0]}, min-stdev {thresholds[1]}_", ""]
    for f in failures:
        L.append(f"- {f}")
    if not failures:
        L.append("_healthy spread_")
    return "\n".join(L)


# ---------- selftest ----------

def _add_hooks(base):
    (base / "hooks").mkdir(parents=True, exist_ok=True)
    (base / "hooks" / "hooks.json").write_text(json.dumps({
        "PreToolUse": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/x.py"}]}]
    }), encoding="utf-8")


def _break_manifest(base):
    # name drift + version drift -> parity and validity penalties (< 15).
    (base / ".codex-plugin" / "plugin.json").write_text(json.dumps({
        "name": "good-plug", "version": "2.0.0",
        "description": "drifted", "author": {"name": "RasputinKaiser"},
        "skills": "./skills/"}), encoding="utf-8")


def _healthy_fixtures(td):
    """5 plugins whose manifest/hooks saturation each stays <= 40%, with a wide
    total-score spread. Only manifest_integrity and hooks_health can saturate
    (all other dimensions' auto ceilings sit below their max)."""
    roots = []
    # f1: perfect manifest (max), no hooks (hooks max) — the top scorer.
    p = td / "f1"; score._make_good_plugin(p); roots.append(p)
    # f2: perfect manifest (max), hooks present -> hooks NOT max.
    p = td / "f2"; score._make_good_plugin(p); _add_hooks(p); roots.append(p)
    # f3: broken manifest, hooks present -> neither maxes.
    p = td / "f3"; score._make_good_plugin(p); _break_manifest(p); _add_hooks(p); roots.append(p)
    # f4: weak plugin, hooks present -> neither maxes.
    p = td / "f4"; score._make_broken_plugin(p); _add_hooks(p); roots.append(p)
    # f5: weak plugin, no hooks -> hooks maxes.
    p = td / "f5"; score._make_broken_plugin(p); roots.append(p)
    return roots


def selftest():
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)

        # --- healthy spread: --check must PASS ---
        roots = _healthy_fixtures(td)
        rows, skipped = collect(roots)
        an = analyze(rows)
        st = an["stats"]
        checks = [
            ("scores all 5 fixtures", st["n"] == 5),
            ("no fixture skipped", skipped == []),
            ("stats ordered min<=median<=max", st["min"] <= st["median"] <= st["max"]),
            ("spread is wide (stdev >= 5)", st["stdev"] >= 5.0),
            ("manifest max-out <= 60%", an["maxout"]["manifest_integrity"]["frac"] <= 0.60),
            ("hooks max-out <= 60%", an["maxout"]["hooks_health"]["frac"] <= 0.60),
            ("skill_quality never maxes (0%)", an["maxout"]["skill_quality"]["frac"] == 0.0),
            ("bands sum to N", sum(an["bands"].values()) == st["n"]),
            ("histogram sums to N", sum(an["histogram"]) == st["n"]),
        ]
        for label, ok in checks:
            if not ok:
                failures.append(f"healthy: {label} (stats={st}, maxout="
                                f"{ {k: v['frac'] for k, v in an['maxout'].items()} })")
        healthy_fail = check(an)
        if healthy_fail:
            failures.append(f"healthy spread should PASS --check, got: {healthy_fail}")

        # --- degenerate all-max spread: --check must FAIL ---
        dgen = []
        for i in range(3):
            p = td / f"dgen{i}"
            score._make_good_plugin(p)  # identical: no hooks + perfect manifest
            dgen.append(p)
        drows, _ = collect(dgen)
        dan = analyze(drows)
        dcheck = check(dan)
        dchecks = [
            ("degenerate stdev == 0", dan["stats"]["stdev"] == 0.0),
            ("degenerate manifest maxes 100%", dan["maxout"]["manifest_integrity"]["frac"] == 1.0),
            ("degenerate hooks maxes 100%", dan["maxout"]["hooks_health"]["frac"] == 1.0),
            ("degenerate --check FAILS", len(dcheck) > 0),
            ("failure names a cause", any("maxes out" in f or "stdev" in f for f in dcheck)),
        ]
        for label, ok in dchecks:
            if not ok:
                failures.append(f"degenerate: {label} (maxout="
                                f"{ {k: v['frac'] for k, v in dan['maxout'].items()} }, "
                                f"check={dcheck})")

        # rendering must not crash on either shape
        try:
            render_table(rows, skipped, an, healthy_fail, (0.6, 5.0))
            render_md(rows, skipped, an, healthy_fail, (0.6, 5.0))
            render_table([], [], analyze([]), [], (0.6, 5.0))
        except Exception as e:  # pragma: no cover
            failures.append(f"rendering crashed: {e}")

    if failures:
        print("SELFTEST FAILED:")
        for f in failures:
            print("  - " + f)
        return 1
    print("calibrate.py selftest: OK")
    return 0


# ---------- cli ----------

def main(argv):
    args = argv[1:]
    if args and args[0] == "selftest":
        return selftest()
    as_json = "--json" in args
    as_md = "--md" in args
    do_check = "--check" in args
    max_maxout_frac = DEFAULT_MAX_MAXOUT_FRAC
    min_stdev = DEFAULT_MIN_STDEV
    positional = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--max-maxout-frac", "--min-stdev"):
            if i + 1 >= len(args):
                print(f"error: {a} requires a value", file=sys.stderr)
                return 2
            try:
                val = float(args[i + 1])
            except ValueError:
                print(f"error: {a} value {args[i + 1]!r} is not a number", file=sys.stderr)
                return 2
            if a == "--max-maxout-frac":
                max_maxout_frac = val
            else:
                min_stdev = val
            i += 2
            continue
        if a in ("-h", "--help"):
            print(__doc__)
            return 0
        if a.startswith("-"):
            i += 1
            continue
        positional.append(a)
        i += 1

    roots = resolve_roots(positional)
    rows, skipped = collect(roots)
    analysis = analyze(rows)
    failures = check(analysis, max_maxout_frac, min_stdev)
    thresholds = (max_maxout_frac, min_stdev)

    if as_json:
        print(json.dumps({
            "count": analysis["stats"]["n"],
            "stats": analysis["stats"],
            "bands": analysis["bands"],
            "histogram": analysis["histogram"],
            "maxout": analysis["maxout"],
            "check": {"thresholds": {"max_maxout_frac": max_maxout_frac,
                                     "min_stdev": min_stdev},
                      "failures": failures, "ok": not failures},
            "skipped": skipped,
            "rows": rows,
        }, indent=2))
    elif as_md:
        print(render_md(rows, skipped, analysis, failures, thresholds))
    else:
        print(render_table(rows, skipped, analysis, failures, thresholds))

    if do_check and failures:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
