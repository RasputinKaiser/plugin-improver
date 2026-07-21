#!/usr/bin/env python3
"""route_eval.py — empirical routing-evaluation loop (roadmap Phase 4).

Orchestrates a measured routing-accuracy loop around skill-curator:
generate -> route -> score -> gate.

- generate: shell out to `curator.py probes` for should-trigger probes, read
  `curator.py graph --json` for the confusable pairs G_t found, and add near-miss
  paraphrase probes per skill (prioritized by those pairs).
- route: pluggable Router. DEFAULT is manual/offline — emit a routing sheet +
  probes + a results template for a human/agent to fill a JSONL of
  {probe_id, selected}. An env-gated model router stub is documented, never run.
- score: confusion matrix + per-skill precision/recall + accuracy, computed
  inline; persisted to `.plugin-improver/routing-<date>.json`.
- gate: --min-baseline PATH / --min ACCURACY exit 1 on regression, giving
  plugin-tune-triggers / plugin-improve a numeric non-regression gate.

Stdlib only. `route_eval.py selftest` is fully offline, hermetic, deterministic.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

EPS = 1e-9
STOP = {
    "the", "and", "for", "use", "when", "with", "that", "this", "from", "into",
    "your", "you", "are", "not", "但", "a", "an", "of", "to", "in", "on", "or",
    "it", "is", "as", "by", "at", "be", "run", "using", "used", "via", "per",
    "any", "all", "its", "e.g", "eg", "etc", "also", "then", "than", "over",
}
_WORD = re.compile(r"[a-z0-9][a-z0-9.\-]*")
_QUOTED = re.compile(r'"([^"]+)"')
_SHEET_SKILL = re.compile(r"^-\s+\*\*([^*]+)\*\*\s*:", re.M)


def content_tokens(text: str) -> list[str]:
    seen, out = set(), []
    for m in _WORD.findall(text.lower()):
        t = m.strip(".-")
        if len(t) < 3 or t in STOP or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def quoted_phrases(text: str) -> list[str]:
    out, seen = [], set()
    for p in _QUOTED.findall(text):
        p = p.strip()
        if p and p.lower() not in seen:
            seen.add(p.lower())
            out.append(p)
    return out


def make_paraphrases(skill: str, desc: str, shared: set[str], n: int) -> list[str]:
    """Deterministic near-miss probe texts drawn from the skill's own words.

    These are templated on-topic stand-ins flagged needs_review — the manual
    loop lets a human or model sharpen them before the numbers are trusted."""
    toks = [t for t in content_tokens(desc) if t not in shared]
    out: list[str] = []
    if toks:
        out.append("task about: " + ", ".join(toks[:5]))
    for ph in quoted_phrases(desc):
        cand = "help me with " + ph
        if cand not in out:
            out.append(cand)
    if len(toks) > 5:
        out.append("something involving " + ", ".join(toks[5:9]))
    if not out:
        out.append("a task related to " + skill)
    return out[:n]


def default_curator() -> Path:
    return Path(__file__).resolve().parent.parent / "skills" / "skill-curator" / "scripts" / "curator.py"


def _run_curator(curator: Path, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(curator), *args],
        capture_output=True, text=True,
    )


def curator_graph_pairs(curator: Path, roots: list[str], no_plugins: bool) -> list[list[str]]:
    """Return confusable skill pairs from G_t collision clusters. []=on any failure."""
    args = ["graph", "--json"]
    for r in roots:
        args += ["--root", r]
    if no_plugins:
        args.append("--no-plugins")
    cp = _run_curator(curator, args)
    if cp.returncode != 0 or not cp.stdout.strip():
        return []
    try:
        data = json.loads(cp.stdout)
    except (ValueError, TypeError):
        return []
    if not isinstance(data, dict):
        return []
    pairs: list[list[str]] = []
    for cl in data.get("collision_clusters", []) or []:
        if not isinstance(cl, dict):
            continue
        members = sorted(str(m) for m in cl.get("members", []) or [])
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                pairs.append([members[i], members[j]])
    return pairs


def curator_probes(curator: Path, out_dir: Path, roots: list[str], no_plugins: bool,
                   only: list[str], max_per_skill: int) -> tuple[dict, str]:
    """Run `curator.py probes`; return (probes.json dict, routing-sheet.md text)."""
    args = ["probes", "--out-dir", str(out_dir), "--max-per-skill", str(max_per_skill)]
    for r in roots:
        args += ["--root", r]
    if no_plugins:
        args.append("--no-plugins")
    for o in only:
        args += ["--only", o]
    cp = _run_curator(curator, args)
    pj = out_dir / "probes.json"
    sheet = out_dir / "routing-sheet.md"
    if cp.returncode != 0 or not pj.exists():
        raise RuntimeError(
            "curator.py probes failed (rc=%s). stderr:\n%s"
            % (cp.returncode, (cp.stderr or "").strip()[:800])
        )
    try:
        with pj.open() as fh:
            probes = json.load(fh)
    except (ValueError, OSError) as e:
        raise RuntimeError("curator.py probes wrote unreadable %s: %s" % (pj, e))
    if not isinstance(probes, dict):
        raise RuntimeError("curator.py probes.json is not a JSON object (got %s)" % type(probes).__name__)
    sheet_text = sheet.read_text() if sheet.exists() else ""
    return probes, sheet_text


def sheet_labels(sheet_text: str) -> list[str]:
    return sorted(set(_SHEET_SKILL.findall(sheet_text)))


def sheet_descriptions(sheet_text: str) -> dict[str, str]:
    out = {}
    for line in sheet_text.splitlines():
        m = re.match(r"^-\s+\*\*([^*]+)\*\*\s*:\s*(.*)$", line)
        if m:
            out[m.group(1).strip()] = m.group(2).strip()
    return out


def augment_probes(base: dict, sheet_text: str, pairs: list[list[str]],
                   only: list[str], max_per_skill: int, date: str) -> dict:
    """Merge curator's phrase probes with prioritized near-miss paraphrase probes."""
    descs = sheet_descriptions(sheet_text)
    labels = sheet_labels(sheet_text) or sorted(descs)
    if only:
        labels = [s for s in labels if s in only]

    # collision partners per skill + priority order (confusable skills first)
    partners: dict[str, list[str]] = {}
    for a, b in pairs:
        partners.setdefault(a, [])
        partners.setdefault(b, [])
        if b not in partners[a]:
            partners[a].append(b)
        if a not in partners[b]:
            partners[b].append(a)
    ordered = sorted(labels, key=lambda s: (0 if s in partners else 1, s))

    probes = list(base.get("probes", []))
    for skill in ordered:
        desc = descs.get(skill, "")
        shared: set[str] = set()
        for p in partners.get(skill, []):
            shared |= set(content_tokens(descs.get(p, "")))
        for i, text in enumerate(make_paraphrases(skill, desc, shared, max_per_skill)):
            probes.append({
                "id": "%s:nm%d" % (skill, i),
                "skill": skill,
                "text": text,
                "kind": "paraphrase",
                "targets": partners.get(skill, []),
                "needs_review": True,
            })

    return {
        "note": base.get("note", ""),
        "results_format": base.get(
            "results_format",
            'JSONL lines: {"probe_id": ..., "selected": "<skill-name>"}',
        ),
        "generated": date,
        "labels": labels,
        "confusable_pairs": pairs,
        "needs_authoring": base.get("needs_authoring", []),
        "probes": probes,
    }


class ManualRouter:
    """Offline default: emit artifacts; consume a filled results JSONL if present."""

    name = "manual"

    def __init__(self, results_path: Path | None):
        self.results_path = results_path

    def route(self, probes: list[dict]) -> dict[str, str] | None:
        if not self.results_path or not self.results_path.exists():
            return None
        return load_results(self.results_path)


class ModelRouter:
    """Env-gated stub (PLUGIN_IMPROVER_ROUTER_CMD). Documented, never used in tests
    or by default. A real implementation shells out to the harness-native model
    (Codex gpt-5.6-luna @ high, or an Opus subagent) with only the routing sheet +
    one probe and parses its picked skill. Intentionally not wired to a live call."""

    name = "model"

    def route(self, probes: list[dict]) -> dict[str, str] | None:  # pragma: no cover
        raise NotImplementedError(
            "ModelRouter is a documented stub; set up a real harness-native router "
            "or use the default manual router."
        )


def load_results(path: Path) -> dict[str, str]:
    """Parse a filled routing-results JSONL. Raises RuntimeError with the line
    number on a malformed line (the file is hand-edited by design)."""
    out: dict[str, str] = {}
    with path.open() as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError as e:
                raise RuntimeError("results %s line %d is not valid JSON: %s" % (path, n, e))
            if not isinstance(rec, dict):
                raise RuntimeError("results %s line %d is not a JSON object" % (path, n))
            pid, sel = rec.get("probe_id"), rec.get("selected")
            if pid is not None and sel not in (None, ""):
                out[str(pid)] = str(sel)
    return out


def score_routing(probes: list[dict], results: dict[str, str], labels: list[str]) -> dict:
    label_set = set(labels)
    for p in probes:
        label_set.add(p["skill"])
    for sel in results.values():
        label_set.add(sel)
    per = {s: {"expected": 0, "hits": 0, "selected_as": 0} for s in label_set}
    confusion: dict[str, dict[str, int]] = {}

    total = len(probes)
    correct = unrouted = 0
    for p in probes:
        exp, sel = p["skill"], results.get(str(p["id"]))
        per[exp]["expected"] += 1
        key = "<none>"
        if sel is None:
            unrouted += 1
        else:
            key = sel
            per[sel]["selected_as"] += 1
            if sel == exp:
                correct += 1
                per[exp]["hits"] += 1
        confusion.setdefault(exp, {})
        confusion[exp][key] = confusion[exp].get(key, 0) + 1

    accuracy = correct / total if total else 0.0
    per_skill = {}
    for s in sorted(per):
        d = per[s]
        recall = (d["hits"] / d["expected"]) if d["expected"] else None
        precision = (d["hits"] / d["selected_as"]) if d["selected_as"] else None
        per_skill[s] = {
            "expected": d["expected"], "hits": d["hits"],
            "selected_as": d["selected_as"],
            "precision": precision, "recall": recall,
        }
    worst = sorted(
        (s for s in per_skill if per_skill[s]["expected"]),
        key=lambda s: (per_skill[s]["recall"] if per_skill[s]["recall"] is not None else 1.0, s),
    )[:5]
    return {
        "probes": total, "routed": total - unrouted, "unrouted": unrouted,
        "correct": correct, "accuracy": round(accuracy, 6),
        "per_skill": per_skill,
        "confusion": {k: confusion[k] for k in sorted(confusion)},
        "worst": worst,
    }


def apply_gate(report: dict, min_acc: float | None, baseline: dict | None) -> tuple[bool, list[str]]:
    acc = report["accuracy"]
    reasons: list[str] = []
    ok = True
    if min_acc is not None and acc < min_acc - EPS:
        ok = False
        reasons.append("accuracy %.4f < --min %.4f" % (acc, min_acc))
    if baseline is not None:
        base_acc = baseline.get("accuracy")
        if isinstance(base_acc, (int, float)) and acc < base_acc - EPS:
            ok = False
            reasons.append("accuracy %.4f regressed below baseline %.4f" % (acc, base_acc))
    return ok, reasons


def render_md(report: dict) -> str:
    L = ["# Routing evaluation",
         "",
         "- probes: %d (routed %d, unrouted %d)" % (report["probes"], report["routed"], report["unrouted"]),
         "- **accuracy: %.3f**" % report["accuracy"],
         "",
         "| skill | expected | hits | precision | recall |",
         "|---|---|---|---|---|"]
    for s, d in report["per_skill"].items():
        pr = "-" if d["precision"] is None else "%.2f" % d["precision"]
        rc = "-" if d["recall"] is None else "%.2f" % d["recall"]
        L.append("| %s | %d | %d | %s | %s |" % (s, d["expected"], d["hits"], pr, rc))
    if report["worst"]:
        L += ["", "Worst recall: " + ", ".join(report["worst"])]
    return "\n".join(L) + "\n"


def render_text(report: dict) -> str:
    lines = ["accuracy %.3f over %d probes (routed %d, unrouted %d)"
             % (report["accuracy"], report["probes"], report["routed"], report["unrouted"])]
    for s, d in report["per_skill"].items():
        if not d["expected"] and not d["selected_as"]:
            continue
        rc = "-" if d["recall"] is None else "%.2f" % d["recall"]
        pr = "-" if d["precision"] is None else "%.2f" % d["precision"]
        lines.append("  %-24s recall=%s precision=%s (exp %d, hits %d)"
                     % (s, rc, pr, d["expected"], d["hits"]))
    return "\n".join(lines)


def cmd_run(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        prog="route_eval.py",
        description="Empirical routing-eval loop (generate->route->score->gate). "
                    "Wraps skill-curator. Subcommand `selftest` runs offline. "
                    "Default router is manual/offline: run once to emit probes + a "
                    "routing sheet, fill routing-results.jsonl, then re-run with "
                    "--results to score and gate.",
    )
    ap.add_argument("--out-dir", default=".plugin-improver/route-eval",
                    help="artifact dir for probes + routing sheet (default: %(default)s)")
    ap.add_argument("--persist-dir", default=".plugin-improver",
                    help="where routing-<date>.json is written (default: %(default)s)")
    ap.add_argument("--only", action="append", default=[], help="limit to these skills (repeatable)")
    ap.add_argument("--root", action="append", default=[], help="skills root passthrough to curator (repeatable)")
    ap.add_argument("--no-plugins", action="store_true", help="skip plugin cache/source scanning")
    ap.add_argument("--results", help="filled routing-results JSONL to score")
    ap.add_argument("--min", dest="min_acc", type=float, help="fail if accuracy < this")
    ap.add_argument("--min-baseline", help="prior routing-<date>.json; fail if accuracy regressed")
    ap.add_argument("--date", default=time.strftime("%Y-%m-%d"), help="stamp (default: today)")
    ap.add_argument("--max-per-skill", type=int, default=2, help="near-miss probes per skill (default: %(default)s)")
    ap.add_argument("--curator", help="path to curator.py (default: sibling skill)")
    ap.add_argument("--json", action="store_true", help="print the routing report as JSON")
    ap.add_argument("--md", action="store_true", help="print the routing report as Markdown")
    args = ap.parse_args(argv)

    curator = Path(args.curator) if args.curator else default_curator()
    if not curator.exists():
        print("route_eval: curator.py not found at %s" % curator, file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. generate
    try:
        base, sheet_text = curator_probes(curator, out_dir, args.root, args.no_plugins,
                                          args.only, args.max_per_skill)
    except RuntimeError as e:
        print("route_eval: %s" % e, file=sys.stderr)
        return 2
    pairs = curator_graph_pairs(curator, args.root, args.no_plugins)
    if args.only:
        only = set(args.only)
        pairs = [p for p in pairs if p[0] in only and p[1] in only]

    aug = augment_probes(base, sheet_text, pairs, args.only, args.max_per_skill, args.date)
    (out_dir / "probes.json").write_text(json.dumps(aug, indent=1) + "\n")
    template = "\n".join(
        json.dumps({"probe_id": p["id"], "selected": ""}) for p in aug["probes"]
    ) + "\n"
    (out_dir / "routing-results.template.jsonl").write_text(template)

    labels = aug["labels"]

    # 2. route
    router = ManualRouter(Path(args.results) if args.results else None)
    try:
        results = router.route(aug["probes"])
    except RuntimeError as e:
        print("route_eval: %s" % e, file=sys.stderr)
        return 2
    if results is None:
        print("Generated %d probes for %d skills -> %s" % (len(aug["probes"]), len(labels), out_dir))
        print("Confusable pairs from G_t: %d" % len(pairs))
        print("Next: route each probe using %s/routing-sheet.md (fill "
              "routing-results.template.jsonl), then re-run with "
              "--results <filled.jsonl>." % out_dir)
        return 0

    # 3. score + persist
    report = score_routing(aug["probes"], results, labels)
    report["date"] = args.date
    report["router"] = router.name
    persist_dir = Path(args.persist_dir)
    persist_dir.mkdir(parents=True, exist_ok=True)
    persisted = persist_dir / ("routing-%s.json" % args.date)
    persisted.write_text(json.dumps(report, indent=1) + "\n")

    # 4. gate
    baseline = None
    if args.min_baseline:
        bp = Path(args.min_baseline)
        if not bp.exists():
            print("route_eval: --min-baseline %s not found" % bp, file=sys.stderr)
            return 2
        try:
            baseline = json.loads(bp.read_text())
        except ValueError as e:
            print("route_eval: baseline %s is not valid JSON: %s" % (bp, e), file=sys.stderr)
            return 2
        if not isinstance(baseline, dict):
            print("route_eval: baseline %s is not a routing report object" % bp, file=sys.stderr)
            return 2
    ok, reasons = apply_gate(report, args.min_acc, baseline)

    if args.json:
        print(json.dumps(report, indent=1))
    elif args.md:
        print(render_md(report))
    else:
        print(render_text(report))
        print("saved -> %s" % persisted)
    if not ok:
        print("GATE FAIL: " + "; ".join(reasons), file=sys.stderr)
        return 1
    if reasons == [] and (args.min_acc is not None or baseline is not None):
        print("gate ok (accuracy %.4f)" % report["accuracy"])
    return 0


def selftest() -> int:
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    labels = ["alpha", "beta"]
    probes = [
        {"id": "alpha:0", "skill": "alpha", "text": "build failure", "kind": "phrase"},
        {"id": "alpha:1", "skill": "alpha", "text": "launch app", "kind": "phrase"},
        {"id": "beta:0", "skill": "beta", "text": "edit docx", "kind": "phrase"},
        {"id": "beta:1", "skill": "beta", "text": "format a word document", "kind": "phrase"},
    ]
    # 3 correct, 1 confusion (beta:1 misrouted to alpha)
    results = {"alpha:0": "alpha", "alpha:1": "alpha", "beta:0": "beta", "beta:1": "alpha"}
    r = score_routing(probes, results, labels)
    check(abs(r["accuracy"] - 0.75) < EPS, "accuracy should be 0.75, got %s" % r["accuracy"])
    check(r["routed"] == 4 and r["unrouted"] == 0, "routed/unrouted wrong: %s" % r)
    check(abs(r["per_skill"]["alpha"]["recall"] - 1.0) < EPS, "alpha recall should be 1.0")
    check(abs(r["per_skill"]["alpha"]["precision"] - (2 / 3)) < EPS, "alpha precision should be 2/3")
    check(abs(r["per_skill"]["beta"]["recall"] - 0.5) < EPS, "beta recall should be 0.5")
    check(abs(r["per_skill"]["beta"]["precision"] - 1.0) < EPS, "beta precision should be 1.0")
    check(r["confusion"]["beta"].get("alpha") == 1, "confusion beta->alpha should be 1")
    check(r["worst"][0] == "beta", "worst recall should lead with beta")

    # unrouted probe counts against accuracy
    r2 = score_routing(probes, {"alpha:0": "alpha"}, labels)
    check(r2["unrouted"] == 3 and abs(r2["accuracy"] - 0.25) < EPS,
          "unrouted handling wrong: %s" % r2)

    # gate behavior
    ok, _ = apply_gate(r, 0.5, None)
    check(ok, "min 0.5 should pass at accuracy 0.75")
    ok, why = apply_gate(r, 0.9, None)
    check(not ok and why, "min 0.9 should fail at accuracy 0.75")
    ok, _ = apply_gate(r, None, {"accuracy": 0.70})
    check(ok, "baseline 0.70 should pass at 0.75")
    ok, why = apply_gate(r, None, {"accuracy": 0.80})
    check(not ok and why, "baseline 0.80 should fail at 0.75")
    ok, _ = apply_gate(r, None, {"accuracy": 0.75})
    check(ok, "equal-to-baseline should pass (non-strict)")
    ok, _ = apply_gate(r, None, {})  # baseline missing accuracy key
    check(ok, "baseline without accuracy should not gate-fail")

    # augment_probes: near-miss probes prioritized by confusable pairs
    sheet = ("# Routing sheet\n\n"
             "- **alpha**: Build and run iOS apps. Use for \"build failure\".\n"
             "- **beta**: Edit and format Word documents. Use for \"docx\".\n")
    base = {"note": "n", "probes": [{"id": "alpha:0", "skill": "alpha", "text": "build failure", "kind": "phrase"}]}
    aug = augment_probes(base, sheet, [["alpha", "beta"]], [], 2, "2020-01-01")
    check(aug["labels"] == ["alpha", "beta"], "labels parse wrong: %s" % aug["labels"])
    check(aug["confusable_pairs"] == [["alpha", "beta"]], "pairs wrong")
    nm = [p for p in aug["probes"] if p["kind"] == "paraphrase"]
    check(len(nm) >= 2, "should synthesize near-miss probes, got %d" % len(nm))
    check(all(p.get("needs_review") for p in nm), "near-miss probes must be flagged needs_review")
    a_nm = [p for p in nm if p["skill"] == "alpha"]
    check(a_nm and a_nm[0]["targets"] == ["beta"], "confusable target not recorded: %s" % a_nm)
    # a confusable skill must be ordered before a non-confusable one
    sheet3 = sheet + "- **gamma**: Unrelated telemetry logging helper. Use for \"metrics\".\n"
    aug3 = augment_probes({"probes": []}, sheet3, [["alpha", "beta"]], [], 1, "2020-01-01")
    order = [p["skill"] for p in aug3["probes"]]
    check(order.index("alpha") < order.index("gamma"), "confusable skills must be prioritized: %s" % order)

    # near-miss text stays on-topic and excludes the partner's distinctive tokens
    check(all("build failure" != p["text"] for p in a_nm),
          "near-miss text should differ from the verbatim phrase probe")

    # rendering does not crash
    _ = render_md(r)
    _ = render_text(r)

    # results loader ignores blank selections; raises clearly on malformed lines
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        rp = Path(td) / "res.jsonl"
        rp.write_text('{"probe_id": "alpha:0", "selected": "alpha"}\n'
                      '{"probe_id": "beta:0", "selected": ""}\n'
                      '\n')
        loaded = load_results(rp)
        check(loaded == {"alpha:0": "alpha"}, "load_results blank/empty handling: %s" % loaded)
        bad = Path(td) / "bad.jsonl"
        bad.write_text('{"probe_id": "a", "selected": "x"}\nnot json\n')
        try:
            load_results(bad)
            check(False, "load_results should raise on a malformed line")
        except RuntimeError as e:
            check("line 2" in str(e), "malformed-line error should name the line: %s" % e)

    if fails:
        print("SELFTEST FAIL (%d):" % len(fails))
        for f in fails:
            print("  - " + f)
        return 1
    print("SELFTEST PASS")
    return 0


def main(argv: list[str]) -> int:
    if argv and argv[0] == "selftest":
        return selftest()
    return cmd_run(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
