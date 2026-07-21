#!/usr/bin/env python3
"""Per-plugin token / context-budget report for dual-harness plugins.

Stdlib only. All token counts are ESTIMATES (~chars/4) — never exact.

  python3 scripts/tokens.py [<plugin-root>]        # human table (default: .)
  python3 scripts/tokens.py <root> --json          # machine-readable
  python3 scripts/tokens.py <root> --md            # markdown
  python3 scripts/tokens.py <root> --save-baseline # write tokens-baseline.json
  python3 scripts/tokens.py <root> --max-trigger-tokens N   # gate (exit 1 if over)
  python3 scripts/tokens.py selftest               # deterministic self-check

Two token classes a plugin author cares about:
  * TRIGGER tokens — a skill's `description`. Loaded into EVERY session's
    metadata whether or not the skill is used: the per-session "session tax".
  * INVOKE tokens — a skill's SKILL.md body. Loaded only when the skill fires.

Budgets come from skills/plugin-audit/references/scoring-rubric.md:
  description <=400 chars (hard flag >600); body <=600 words (hard flag >1500).

The frontmatter parser mirrors scripts/validate.py's split_frontmatter style
but this script is fully self-contained (no sibling imports).
"""
import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# curator.py's convention: ~4 chars per token (an estimate, not exact).
CHARS_PER_TOKEN = 4.0

# Budgets from the scoring rubric. (chars for descriptions, words for bodies.)
DESC_BUDGET, DESC_HARD = 400, 600      # trigger text
BODY_BUDGET, BODY_HARD = 600, 1500     # invoke text

BASELINE_REL = Path(".plugin-improver") / "tokens-baseline.json"


# ---------- estimation & parsing (self-contained) ----------

def est_tokens(chars):
    """Estimate tokens from a character count (~chars/4). ESTIMATE only."""
    return int(round(chars / CHARS_PER_TOKEN))


def split_frontmatter(text):
    """Return (frontmatter_dict, body_str) for a SKILL.md. Tiny hand parser
    matching validate.py: top-level `key: value` scalars only."""
    if not text.startswith("---"):
        return None, text
    lines = text.splitlines()
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None, text
    fm = {}
    for line in lines[1:end]:
        if ":" in line and not line.startswith((" ", "\t", "#")):
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip().strip('"').strip("'")
    body = "\n".join(lines[end + 1:])
    return fm, body


def iter_skill_dirs(root):
    sk = root / "skills"
    if not sk.is_dir():
        return []
    return sorted(p for p in sk.iterdir() if p.is_dir() and (p / "SKILL.md").is_file())


def _status(value, soft, hard):
    """error if over the hard flag, warn if over the soft budget, else ok."""
    if value > hard:
        return "error"
    if value > soft:
        return "warn"
    return "ok"


# ---------- analysis ----------

def analyze_skill(skill_dir):
    fm, body = split_frontmatter((skill_dir / "SKILL.md").read_text(encoding="utf-8"))
    fm = fm or {}
    desc = fm.get("description", "") or ""
    desc_chars = len(desc)
    body_words = len(body.split())
    body_chars = len(body)
    return {
        "name": skill_dir.name,
        "desc_chars": desc_chars,
        "trigger_tokens": est_tokens(desc_chars),
        "desc_headroom_chars": DESC_BUDGET - desc_chars,
        "desc_status": _status(desc_chars, DESC_BUDGET, DESC_HARD),
        "body_words": body_words,
        "body_chars": body_chars,
        "invoke_tokens": est_tokens(body_chars),
        "body_headroom_words": BODY_BUDGET - body_words,
        "body_status": _status(body_words, BODY_BUDGET, BODY_HARD),
    }


def analyze_plugin(root):
    skills = [analyze_skill(d) for d in iter_skill_dirs(root)]
    session_tax = sum(s["trigger_tokens"] for s in skills)
    total_invoke = sum(s["invoke_tokens"] for s in skills)
    return {
        "root": str(root),
        "skill_count": len(skills),
        "session_tax_tokens": session_tax,
        "total_invoke_tokens": total_invoke,
        "skills": skills,
        "heaviest_descriptions": sorted(
            skills, key=lambda s: (-s["trigger_tokens"], s["name"]))[:5],
        "heaviest_bodies": sorted(
            skills, key=lambda s: (-s["invoke_tokens"], s["name"]))[:5],
        "flags": [
            {"skill": s["name"], "kind": kind, "severity": s[f"{kind}_status"]}
            for s in skills for kind in ("desc", "body")
            if s[f"{kind}_status"] != "ok"
        ],
    }


# ---------- baseline ----------

def baseline_path(root):
    return root / BASELINE_REL


def load_baseline(root):
    p = baseline_path(root)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_baseline(root, report):
    p = baseline_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "saved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "session_tax_tokens": report["session_tax_tokens"],
        "total_invoke_tokens": report["total_invoke_tokens"],
        "skills": {s["name"]: {"trigger_tokens": s["trigger_tokens"],
                               "invoke_tokens": s["invoke_tokens"]}
                   for s in report["skills"]},
    }
    p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return p


def diff_baseline(report, baseline):
    """Compute +/- deltas of the report against a saved baseline."""
    if not baseline:
        return None
    old_skills = baseline.get("skills", {})
    now = {s["name"] for s in report["skills"]}
    then = set(old_skills)
    per_skill = []
    for s in report["skills"]:
        old = old_skills.get(s["name"])
        if old is None:
            continue
        per_skill.append({
            "name": s["name"],
            "trigger_delta": s["trigger_tokens"] - old.get("trigger_tokens", 0),
            "invoke_delta": s["invoke_tokens"] - old.get("invoke_tokens", 0),
        })
    return {
        "saved_at": baseline.get("saved_at"),
        "session_tax_delta": report["session_tax_tokens"]
        - baseline.get("session_tax_tokens", 0),
        "total_invoke_delta": report["total_invoke_tokens"]
        - baseline.get("total_invoke_tokens", 0),
        "added_skills": sorted(now - then),
        "removed_skills": sorted(then - now),
        "per_skill": [d for d in per_skill
                      if d["trigger_delta"] or d["invoke_delta"]],
    }


# ---------- rendering ----------

def _sign(n):
    return f"+{n}" if n > 0 else str(n)


def render_human(report, delta):
    L = []
    L.append(f"Session tax: {report['session_tax_tokens']} trigger tokens "
             f"(estimate ~chars/4) — paid every session, all skills")
    L.append(f"Total invoke tokens: {report['total_invoke_tokens']} "
             f"(estimate; only the invoked skill's body loads)")
    L.append(f"Skills: {report['skill_count']}   Budgets: desc <=400 chars "
             f"(flag >600), body <=600 words (flag >1500)")
    L.append("")
    L.append(f"{'skill':22} {'desc¢':>6} {'trig~':>6} {'hd¢':>6} "
             f"{'body w':>7} {'inv~':>6} {'hd w':>6}  flags")
    L.append("-" * 78)
    for s in report["skills"]:
        flags = []
        if s["desc_status"] != "ok":
            flags.append(f"desc:{s['desc_status']}")
        if s["body_status"] != "ok":
            flags.append(f"body:{s['body_status']}")
        L.append(f"{s['name'][:22]:22} {s['desc_chars']:>6} "
                 f"{s['trigger_tokens']:>6} {s['desc_headroom_chars']:>6} "
                 f"{s['body_words']:>7} {s['invoke_tokens']:>6} "
                 f"{s['body_headroom_words']:>6}  {' '.join(flags)}")
    L.append("")
    if report["skills"]:
        top_t = report["heaviest_descriptions"][0]
        top_b = report["heaviest_bodies"][0]
        L.append(f"Heaviest description: {top_t['name']} "
                 f"({top_t['trigger_tokens']} trig tokens)")
        L.append(f"Heaviest body: {top_b['name']} "
                 f"({top_b['invoke_tokens']} invoke tokens)")
    if report["flags"]:
        L.append("")
        L.append("Over-budget:")
        for f in report["flags"]:
            L.append(f"  [{f['severity'].upper()}] {f['skill']} ({f['kind']})")
    if delta:
        L.append("")
        L.append(f"Since baseline ({delta['saved_at']}):")
        L.append(f"  session tax {_sign(delta['session_tax_delta'])} tokens, "
                 f"invoke {_sign(delta['total_invoke_delta'])} tokens")
        for d in delta["per_skill"]:
            L.append(f"    {d['name']}: trig {_sign(d['trigger_delta'])}, "
                     f"inv {_sign(d['invoke_delta'])}")
        for n in delta["added_skills"]:
            L.append(f"    + new skill: {n}")
        for n in delta["removed_skills"]:
            L.append(f"    - removed skill: {n}")
    return "\n".join(L)


def render_md(report, delta):
    L = [f"# Token budget — {Path(report['root']).name}", ""]
    L.append(f"**Session tax: {report['session_tax_tokens']} trigger tokens** "
             f"(estimate ~chars/4, paid every session).  "
             f"Total invoke tokens: {report['total_invoke_tokens']}.")
    L.append("")
    L.append("| skill | desc chars | trigger~ | desc headroom | body words "
             "| invoke~ | body headroom | flags |")
    L.append("|---|--:|--:|--:|--:|--:|--:|---|")
    for s in report["skills"]:
        flags = ", ".join(
            f"{k}:{s[k + '_status']}" for k in ("desc", "body")
            if s[k + "_status"] != "ok") or "-"
        L.append(f"| {s['name']} | {s['desc_chars']} | {s['trigger_tokens']} "
                 f"| {s['desc_headroom_chars']} | {s['body_words']} "
                 f"| {s['invoke_tokens']} | {s['body_headroom_words']} "
                 f"| {flags} |")
    if delta:
        L.append("")
        L.append(f"_Since baseline ({delta['saved_at']}): session tax "
                 f"{_sign(delta['session_tax_delta'])}, invoke "
                 f"{_sign(delta['total_invoke_delta'])} tokens._")
    return "\n".join(L)


# ---------- selftest ----------

def _write_skill(root, name, desc, body):
    d = root / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {desc}\n---\n\n{body}\n",
        encoding="utf-8")


def selftest():
    failures = []

    def check(cond, label):
        if not cond:
            failures.append(label)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # Lean plugin: desc exactly 40 chars, body exactly 100 words.
        _write_skill(root, "lean", "a" * 40, " ".join(["w"] * 100))
        rep = analyze_plugin(root)
        lean = rep["skills"][0]
        check(lean["desc_chars"] == 40, "lean desc_chars==40")
        check(lean["trigger_tokens"] == 10, "lean trigger==10 (40/4)")
        check(lean["body_words"] == 100, "lean body_words==100")
        check(lean["desc_status"] == "ok", "lean desc ok")
        check(lean["body_status"] == "ok", "lean body ok")
        check(lean["desc_headroom_chars"] == 360, "lean desc headroom 360")
        check(lean["body_headroom_words"] == 500, "lean body headroom 500")
        check(rep["session_tax_tokens"] == 10, "lean session tax==10")

        # Bloated plugin: desc 800 chars (>600 hard), body 2000 words (>1500).
        broot = Path(tmp) / "bloat"
        _write_skill(broot, "bloat", "b" * 800, " ".join(["w"] * 2000))
        brep = analyze_plugin(broot)
        bl = brep["skills"][0]
        check(bl["trigger_tokens"] == 200, "bloat trigger==200 (800/4)")
        check(bl["desc_status"] == "error", "bloat desc error (>600)")
        check(bl["body_status"] == "error", "bloat body error (>1500 words)")
        check(bl["desc_headroom_chars"] == -400, "bloat desc headroom -400")
        check(len(brep["flags"]) == 2, "bloat has 2 flags")

        # Warn tier: desc 500 chars (>400,<=600), body 900 words (>600,<=1500).
        wroot = Path(tmp) / "warn"
        _write_skill(wroot, "warn", "c" * 500, " ".join(["w"] * 900))
        wrep = analyze_plugin(wroot)
        wl = wrep["skills"][0]
        check(wl["desc_status"] == "warn", "warn desc warn")
        check(wl["body_status"] == "warn", "warn body warn")

        # Baseline round-trip + delta.
        check(load_baseline(root) is None, "no baseline initially")
        save_baseline(root, rep)
        check(baseline_path(root).is_file(), "baseline written")
        check(diff_baseline(rep, load_baseline(root))["session_tax_delta"] == 0,
              "delta zero right after save")
        # Grow the description by 40 chars -> +10 trigger tokens.
        _write_skill(root, "lean", "a" * 80, " ".join(["w"] * 100))
        _write_skill(root, "added", "a" * 20, "body")
        rep2 = analyze_plugin(root)
        delta = diff_baseline(rep2, load_baseline(root))
        check(delta["session_tax_delta"] == 15,
              f"delta +15 (lean +10, added +5), got {delta['session_tax_delta']}")
        check(delta["added_skills"] == ["added"], "added skill detected")
        check(any(d["name"] == "lean" and d["trigger_delta"] == 10
                  for d in delta["per_skill"]), "lean per-skill delta +10")

        # Empty plugin (no skills) must not crash.
        eroot = Path(tmp) / "empty"
        (eroot / "skills").mkdir(parents=True)
        erep = analyze_plugin(eroot)
        check(erep["session_tax_tokens"] == 0, "empty session tax 0")
        render_human(erep, None)  # must not raise

    if failures:
        print("SELFTEST FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("SELFTEST PASS (all token/flag/baseline assertions hold)")
    return 0


# ---------- cli ----------

def build_parser():
    p = argparse.ArgumentParser(
        description="Per-plugin token / context-budget report (estimates ~chars/4). "
                    "Use `selftest` as the target to run the self-check.")
    p.add_argument("target", nargs="?", default=".",
                   help="plugin root (default: current dir), or 'selftest'")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--md", action="store_true", help="markdown output")
    p.add_argument("--save-baseline", action="store_true",
                   help="write <root>/.plugin-improver/tokens-baseline.json")
    p.add_argument("--max-trigger-tokens", type=int, metavar="N",
                   help="exit 1 if total session tax exceeds N")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.target == "selftest":
        return selftest()

    root = Path(args.target).resolve()
    if not (root / "skills").is_dir():
        print(f"error: {root} has no skills/ — not a plugin root", file=sys.stderr)
        return 2

    report = analyze_plugin(root)
    baseline = load_baseline(root)
    delta = diff_baseline(report, baseline)

    if args.save_baseline:
        written = save_baseline(root, report)
        if not (args.json or args.md):
            print(f"baseline saved: {written}")

    if args.json:
        print(json.dumps({"report": report, "baseline_delta": delta,
                          "estimate_note": "token counts are estimates (~chars/4)"},
                         indent=2))
    elif args.md:
        print(render_md(report, delta))
    else:
        print(render_human(report, delta))

    if args.max_trigger_tokens is not None \
            and report["session_tax_tokens"] > args.max_trigger_tokens:
        print(f"\nGATE FAIL: session tax {report['session_tax_tokens']} "
              f"> --max-trigger-tokens {args.max_trigger_tokens}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
