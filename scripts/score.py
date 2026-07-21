#!/usr/bin/env python3
"""Deterministic machine sub-score for the plugin health rubric.

Stdlib only.
  python3 scripts/score.py <plugin-root>              # human table
  python3 scripts/score.py <plugin-root> --json       # structured object
  python3 scripts/score.py <plugin-root> --md         # markdown
  python3 scripts/score.py <plugin-root> --min N       # exit 1 if total auto < N
  python3 scripts/score.py <plugin-root> --min-baseline PATH  # exit 1 on regression
  python3 scripts/score.py selftest                    # deterministic fixtures

Scores the OBJECTIVE parts of the 100-pt rubric in
skills/plugin-audit/references/scoring-rubric.md. For each dimension it emits
{auto, max, needs_judgment}: `auto` = points a machine can verify, `max` = the
dimension's rubric ceiling, `needs_judgment` = the sub-points only a human/LLM
can score. Judgment-heavy dimensions (skill quality) report auto≈0.

Self-contained: reuses the parsing patterns from scripts/validate.py but does
not import it (a sibling may be editing it).
"""
import json
import re
import sys
import tempfile
from pathlib import Path

KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)*$")
# Quoted trigger phrases in a description: 'like this', "like this", `like this`.
QUOTED = re.compile(r"'([^']{3,60})'|\"([^\"]{3,60})\"|`([^`]{3,60})`")
# NOT-clause heuristics — negative scope signals in a description.
NOT_CLAUSE = re.compile(
    r"\bnot for\b|\bnot when\b|\bdon't use\b|\bdo not use\b|\bnot to\b|"
    r"\brather than\b|\binstead of\b|\bnot\b.*\buse\b|\(not\b",
    re.I,
)
WHEN_SIGNAL = re.compile(r"\buse when\b|\buse for\b|\bwhen asked\b|\btrigger\b|\bwhen a\b|\bwhen the\b", re.I)
STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with", "is",
    "it", "its", "this", "that", "as", "at", "by", "be", "are", "when", "use",
    "used", "using", "from", "into", "your", "you", "not", "but", "if", "so",
    "each", "any", "all", "one", "two", "both", "per", "via", "across", "plugin",
    "plugins", "skill", "skills", "claude", "code", "codex", "harness",
}


# ---------- parsing helpers (self-contained) ----------

def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def base_version(v):
    return str(v).split("+", 1)[0]


def split_frontmatter(text):
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
    return fm, "\n".join(lines[end + 1:])


def iter_skill_dirs(root):
    sk = root / "skills"
    if not sk.is_dir():
        return []
    return sorted(p for p in sk.iterdir() if p.is_dir() and (p / "SKILL.md").is_file())


def walk_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_strings(v)


def content_tokens(text):
    toks = re.findall(r"[a-z0-9]+", text.lower())
    return {t for t in toks if len(t) > 2 and t not in STOPWORDS}


def quoted_phrases(text):
    out = set()
    for m in QUOTED.finditer(text):
        phrase = next(g for g in m.groups() if g is not None)
        out.add(phrase.strip().lower())
    return out


def read_skill(d):
    fm, body = split_frontmatter((d / "SKILL.md").read_text(encoding="utf-8"))
    fm = fm or {}
    return {
        "name": d.name,
        "dir": d,
        "description": fm.get("description", ""),
        "body": body,
    }


def load_skills(root):
    return [read_skill(d) for d in iter_skill_dirs(root)]


def manifests(root):
    out = {}
    for label, rel in (("claude", ".claude-plugin/plugin.json"),
                       ("codex", ".codex-plugin/plugin.json")):
        p = root / rel
        if p.is_file():
            try:
                out[label] = load_json(p)
            except Exception:
                out[label] = None
    return out


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


# ---------- collision detection (inline, stdlib) ----------

def collision_count(skills):
    """Light sibling-collision count: shared identical quoted phrases OR high
    description content-token overlap (Jaccard >= 0.5). Returns (count, notes)."""
    count, notes = 0, []
    quoted = {s["name"]: quoted_phrases(s["description"]) for s in skills}
    toks = {s["name"]: content_tokens(s["description"]) for s in skills}
    for i in range(len(skills)):
        for j in range(i + 1, len(skills)):
            a, b = skills[i]["name"], skills[j]["name"]
            shared = quoted[a] & quoted[b]
            ta, tb = toks[a], toks[b]
            jac = len(ta & tb) / len(ta | tb) if (ta | tb) else 0.0
            if shared:
                count += 1
                notes.append(f"{a}~{b}: share quoted {sorted(shared)}")
            elif jac >= 0.5:
                count += 1
                notes.append(f"{a}~{b}: description token overlap {jac:.2f}")
    return count, notes


# ---------- dimension scorers ----------

def score_manifest(root):
    m = manifests(root)
    judgment, auto = [], 0.0
    claude, codex = m.get("claude"), m.get("codex")
    present = {k: v for k, v in m.items() if v is not None}
    # m keys == manifest files that exist on disk (value None means it failed to parse).
    files_present = len(m)
    corrupt = any(v is None for v in m.values())

    # 4pt — each present manifest valid JSON, kebab name, semver version.
    if present and not corrupt:
        names = {v.get("name") for v in present.values()}
        vers_ok = all(SEMVER.match(v.get("version", "") or "") for v in present.values())
        name_ok = all(n and KEBAB.match(n) for n in names)
        auto += 4 if (name_ok and vers_ok) else (2 if (name_ok or vers_ok) else 0)
    judgment.append("description accuracy (4pt sub-point) is judgment")

    # 4pt — cross-harness parity: both manifests, identical name, agreeing version.
    if files_present == 2 and claude and codex:
        same_name = claude.get("name") == codex.get("name")
        same_ver = base_version(claude.get("version", "")) == base_version(codex.get("version", ""))
        auto += 4 if (same_name and same_ver) else (2 if (same_name or same_ver) else 0)
    elif files_present == 1 and len(present) == 1:
        auto += 4  # single-harness plugin earns full parity credit for its one manifest
    else:
        judgment.append("cross-harness parity unverifiable (a manifest missing or failed to parse)")

    # 3pt — component pointers ./-prefixed and inside root.
    ptr_keys = ("skills", "hooks", "mcpServers", "apps")
    ptr_vals = []
    for v in present.values():
        for k in ptr_keys:
            if k in v and isinstance(v[k], str):
                ptr_vals.append(v[k])
    if ptr_vals:
        good = all(p.startswith("./") and not p.startswith("../")
                   and (root / p.lstrip("./")).exists() for p in ptr_vals)
        auto += 3 if good else 0
    else:
        auto += 3  # no string pointers to get wrong
    # 2pt — layout: manifest dir holds only plugin.json / marketplace.json.
    layout_ok = True
    for mdir in (".claude-plugin", ".codex-plugin"):
        d = root / mdir
        if d.is_dir():
            stray = [f.name for f in d.iterdir()
                     if f.name not in ("plugin.json", "marketplace.json")]
            if stray:
                layout_ok = False
    auto += 2 if layout_ok else 0

    # 2pt — publisher metadata: author present (mechanical core).
    has_author = any(v.get("author") for v in present.values())
    auto += 2 if has_author else 0
    judgment.append("publisher-metadata appropriateness to distribution level (2pt) is judgment")
    return {"auto": round(auto, 1), "max": 15, "needs_judgment": judgment}


def score_context(root):
    skills = load_skills(root)
    judgment, auto = [], 0.0
    if not skills:
        return {"auto": 0.0, "max": 20, "needs_judgment": ["no skills to score"]}

    # 8pt — bodies within 600-word budget.
    within = sum(1 for s in skills if len(s["body"].split()) <= 600)
    over = [s["name"] for s in skills if len(s["body"].split()) > 600]
    auto += 8 * within / len(skills)
    if over:
        judgment.append(f"bodies over 600 words: {over}")
    judgment.append("progressive disclosure (detail pushed to references/) is judgment")

    # 6pt — no duplicated content across skills — judgment.
    judgment.append("no duplicated content across skills (6pt) is judgment")

    # 4pt — descriptions within 400-char budget.
    d_within = sum(1 for s in skills if len(s["description"]) <= 400)
    d_over = [s["name"] for s in skills if len(s["description"]) > 400]
    auto += 4 * d_within / len(skills)
    if d_over:
        judgment.append(f"descriptions over 400 chars: {d_over}")

    # 2pt — no dead weight: empty files / empty reference dirs.
    dead = []
    for s in skills:
        for f in s["dir"].rglob("*"):
            if f.is_file() and f.stat().st_size == 0:
                dead.append(str(f.relative_to(root)))
        refs = s["dir"] / "references"
        if refs.is_dir() and not any(refs.iterdir()):
            dead.append(str(refs.relative_to(root)) + "/ (empty)")
    auto += 2 if not dead else 0
    if dead:
        judgment.append(f"dead/empty files: {dead}")
    return {"auto": round(auto, 1), "max": 20, "needs_judgment": judgment}


def score_trigger(root):
    skills = load_skills(root)
    judgment, auto = [], 0.0
    if not skills:
        return {"auto": 0.0, "max": 20, "needs_judgment": ["no skills to score"]}
    n = len(skills)

    # 7pt — states what AND when, concrete trigger phrases. Mechanical proxy (3):
    # description within budget AND carries a when/trigger signal.
    good_when = sum(1 for s in skills
                    if s["description"] and len(s["description"]) <= 400
                    and (WHEN_SIGNAL.search(s["description"]) or quoted_phrases(s["description"])))
    auto += 3 * good_when / n
    judgment.append("what+when completeness & trigger-phrase quality (remaining 4pt) is judgment")

    # 5pt — negative scope: NOT-clause presence heuristic.
    has_not = sum(1 for s in skills if NOT_CLAUSE.search(s["description"]))
    auto += 5 * has_not / n
    if has_not < n:
        judgment.append(f"{n - has_not}/{n} skills lack a detectable NOT-clause")

    # 5pt — no trigger collisions (light sibling collision count).
    count, notes = collision_count(skills)
    auto += clamp(5 - count, 0, 5)
    if count:
        judgment.extend(notes)

    # 3pt — risky/niche skills guarded — judgment.
    judgment.append("risky-skill guarding (allow_implicit_invocation / negative scope, 3pt) is judgment")
    return {"auto": round(auto, 1), "max": 20, "needs_judgment": judgment}


def score_hooks(root):
    judgment = []
    hj = root / "hooks" / "hooks.json"
    if not hj.is_file():
        return {"auto": 10.0, "max": 10,
                "needs_judgment": ["no hooks present — full credit awarded"]}
    auto = 0.0
    try:
        data = load_json(hj)
    except Exception as e:
        return {"auto": 0.0, "max": 10, "needs_judgment": [f"hooks.json invalid JSON: {e}"]}
    # 3pt — valid shape: event -> matcher group -> handlers.
    shape_ok = isinstance(data, dict) and bool(data)
    if shape_ok:
        for event, groups in data.items():
            if not isinstance(groups, list):
                shape_ok = False
                break
            for g in groups:
                if not (isinstance(g, dict) and isinstance(g.get("hooks"), list)):
                    shape_ok = False
                    break
    auto += 3 if shape_ok else 0
    # 2pt — paths use ${CLAUDE_PLUGIN_ROOT} or ${PLUGIN_ROOT}.
    strings = list(walk_strings(data))
    cmds = [s for s in strings if "/" in s and (".py" in s or ".sh" in s or ".js" in s)]
    paths_ok = all(("${CLAUDE_PLUGIN_ROOT}" in s or "${PLUGIN_ROOT}" in s) for s in cmds) if cmds else True
    auto += 2 if paths_ok else 0
    if not paths_ok:
        judgment.append("some hook paths do not use ${CLAUDE_PLUGIN_ROOT}/${PLUGIN_ROOT}")
    judgment.append("per-event contract correctness & harness-limit respect (5pt) is judgment")
    return {"auto": round(auto, 1), "max": 10, "needs_judgment": judgment}


def score_distribution(root):
    judgment, auto = [], 0.0
    # 3pt — README covers what / skills / install.
    readme = None
    for cand in ("README.md", "readme.md", "Readme.md"):
        if (root / cand).is_file():
            readme = (root / cand).read_text(encoding="utf-8").lower()
            break
    if readme:
        hits = sum(kw in readme for kw in ("install", "skill", "## what"))
        # "what it does" section + skills list + install steps
        sig = ("install" in readme) + ("skill" in readme) + bool(re.search(r"^#", readme, re.M))
        auto += 3 * clamp(sig, 0, 3) / 3
        judgment.append("README completeness (does it truly cover all sections) is judgment")
    else:
        judgment.append("no README found")

    # 3pt — version discipline: changelog or ledger exists.
    has_log = any((root / f).is_file() for f in ("CHANGELOG.md", "LEDGER.md", "CHANGES.md"))
    auto += 3 if has_log else 0
    if not has_log:
        judgment.append("no CHANGELOG/LEDGER found")
    judgment.append("version-bumped-with-changes discipline is judgment")

    # 4pt — marketplace entry per targeted harness. Claude entry is in-repo (2pt auto);
    # the Codex registration lives in a user-global file, unverifiable from here.
    name = None
    for rel in (".codex-plugin/plugin.json", ".claude-plugin/plugin.json"):
        if (root / rel).is_file():
            try:
                name = load_json(root / rel).get("name")
                break
            except Exception:
                pass
    mkt = root / ".claude-plugin" / "marketplace.json"
    listed = False
    if mkt.is_file():
        try:
            data = load_json(mkt)
            entries = data.get("plugins", []) if isinstance(data, dict) else []
            listed = name in {e.get("name") for e in entries if isinstance(e, dict)}
        except Exception:
            pass
    auto += 2 if listed else 0
    if not listed:
        judgment.append("Claude Code marketplace.json does not list this plugin")
    judgment.append("Codex marketplace registration (user-global) unverifiable from plugin root (2pt)")
    return {"auto": round(auto, 1), "max": 10, "needs_judgment": judgment}


def score_skill_quality(root):
    skills = load_skills(root)
    return {"auto": 0.0, "max": 25, "needs_judgment": [
        f"one-job-per-skill / no two skills same job ({len(skills)} skills) — judgment",
        "bodies are imperative agent instructions (not docs/marketing) — judgment",
        "steps actionable: file paths, commands, exact formats — judgment",
        "failure handling: missing file / failed command / ambiguous input — judgment",
    ]}


DIMENSIONS = [
    ("manifest_integrity", score_manifest),
    ("skill_quality", score_skill_quality),
    ("trigger_precision", score_trigger),
    ("context_economy", score_context),
    ("hooks_health", score_hooks),
    ("distribution", score_distribution),
]


def score(root):
    root = Path(root).resolve()
    dims = {}
    for key, fn in DIMENSIONS:
        try:
            dims[key] = fn(root)
        except Exception as e:
            dims[key] = {"auto": 0.0, "max": 0, "needs_judgment": [f"scorer crashed: {e}"]}
    total_auto = round(sum(d["auto"] for d in dims.values()), 1)
    total_max = sum(d["max"] for d in dims.values())
    return {
        "target": str(root),
        "dimensions": dims,
        "total": {"auto": total_auto, "max": total_max},
    }


# ---------- rendering ----------

def render_table(result):
    lines = [f"target: {result['target']}", ""]
    lines.append(f"{'dimension':<20} {'auto':>6} {'max':>5}")
    lines.append("-" * 34)
    for key, d in result["dimensions"].items():
        lines.append(f"{key:<20} {d['auto']:>6} {d['max']:>5}")
    t = result["total"]
    lines.append("-" * 34)
    lines.append(f"{'TOTAL (auto)':<20} {t['auto']:>6} {t['max']:>5}")
    lines.append("")
    lines.append("needs judgment (score on top of the deterministic floor):")
    for key, d in result["dimensions"].items():
        for note in d["needs_judgment"]:
            lines.append(f"  [{key}] {note}")
    return "\n".join(lines)


def render_md(result):
    lines = [f"# Deterministic score — `{result['target']}`", "",
             "| Dimension | Auto | Max |", "|---|---:|---:|"]
    for key, d in result["dimensions"].items():
        lines.append(f"| {key} | {d['auto']} | {d['max']} |")
    t = result["total"]
    lines.append(f"| **Total (auto)** | **{t['auto']}** | **{t['max']}** |")
    lines.append("\n## Needs judgment")
    for key, d in result["dimensions"].items():
        for note in d["needs_judgment"]:
            lines.append(f"- **{key}** — {note}")
    return "\n".join(lines)


# ---------- selftest ----------

def _write(base, rel, content):
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _make_good_plugin(base):
    _write(base, ".claude-plugin/plugin.json", json.dumps({
        "name": "good-plugin", "version": "1.0.0",
        "description": "A good plugin.", "author": {"name": "RasputinKaiser"},
        "skills": "./skills/"}))
    _write(base, ".codex-plugin/plugin.json", json.dumps({
        "name": "good-plugin", "version": "1.0.0+codex.1",
        "description": "A good plugin.", "author": {"name": "RasputinKaiser"},
        "skills": "./skills/"}))
    _write(base, ".claude-plugin/marketplace.json", json.dumps({
        "name": "good-plugin", "plugins": [{"name": "good-plugin", "source": "."}]}))
    _write(base, "README.md", "# good-plugin\n## What it does\n## Skills\n## Install\nsteps here\n")
    _write(base, "CHANGELOG.md", "# Changelog\n- 1.0.0\n")
    _write(base, "skills/alpha/SKILL.md",
           "---\nname: alpha\ndescription: Convert widgets to gadgets. "
           "Use when asked to transmute a widget. Not for gadget deletion.\n---\n"
           "Do the alpha job. Step 1. Step 2.\n")
    _write(base, "skills/beta/SKILL.md",
           "---\nname: beta\ndescription: Render invoices to PDF. "
           "Use when the user wants a printable bill. Not for spreadsheets.\n---\n"
           "Do the beta job. Step 1. Step 2.\n")


def _make_broken_plugin(base):
    # version drift, name mismatch, over-budget description, empty file, no NOT-clauses,
    # colliding descriptions, no marketplace listing, no changelog.
    _write(base, ".claude-plugin/plugin.json", json.dumps({
        "name": "broken-plugin", "version": "1.0.0", "description": "x"}))
    _write(base, ".codex-plugin/plugin.json", json.dumps({
        "name": "broke-plugin", "version": "2.0.0", "description": "x"}))
    _write(base, ".claude-plugin/marketplace.json", json.dumps({"plugins": []}))
    long_desc = "manage the widget gadget thing " * 20  # > 400 chars, no when/not signal
    _write(base, "skills/alpha/SKILL.md",
           f"---\nname: alpha\ndescription: {long_desc}\n---\nbody\n")
    _write(base, "skills/beta/SKILL.md",
           f"---\nname: beta\ndescription: {long_desc}\n---\nbody\n")
    _write(base, "skills/alpha/references/empty.md", "")


def selftest():
    failures = []
    with tempfile.TemporaryDirectory() as td:
        good = Path(td) / "good"
        _make_good_plugin(good)
        r = score(good)
        dims = r["dimensions"]
        checks = [
            ("good manifest_integrity == 15", dims["manifest_integrity"]["auto"] == 15),
            ("good hooks == 10 (no hooks)", dims["hooks_health"]["auto"] == 10),
            ("good context_economy == 14 (auto ceiling)", dims["context_economy"]["auto"] == 14),
            ("good trigger no collisions (>=13)", dims["trigger_precision"]["auto"] >= 13),
            ("good distribution == 8", dims["distribution"]["auto"] == 8),
            ("good skill_quality auto == 0", dims["skill_quality"]["auto"] == 0),
            ("good total auto >= 55", r["total"]["auto"] >= 55),
            ("total max == 100", r["total"]["max"] == 100),
        ]
        for label, ok in checks:
            if not ok:
                failures.append(f"{label} (got dims={ { k:v['auto'] for k,v in dims.items()} })")

        broken = Path(td) / "broken"
        _make_broken_plugin(broken)
        rb = score(broken)
        db = rb["dimensions"]
        bchecks = [
            ("broken manifest < 15", db["manifest_integrity"]["auto"] < 15),
            ("broken parity penalized (manifest <= 9)", db["manifest_integrity"]["auto"] <= 9),
            ("broken context < 20", db["context_economy"]["auto"] < 20),
            ("broken trigger < good trigger", db["trigger_precision"]["auto"] < dims["trigger_precision"]["auto"]),
            ("broken distribution < 8", db["distribution"]["auto"] < 8),
            ("broken total < good total", rb["total"]["auto"] < r["total"]["auto"]),
        ]
        for label, ok in bchecks:
            if not ok:
                failures.append(f"{label} (got dims={ { k:v['auto'] for k,v in db.items()} })")

    if failures:
        print("SELFTEST FAILED:")
        for f in failures:
            print("  - " + f)
        return 1
    print("score.py selftest: OK")
    return 0


# ---------- cli ----------

def main(argv):
    args = argv[1:]
    if args and args[0] == "selftest":
        return selftest()
    as_json = "--json" in args
    as_md = "--md" in args
    min_n = None
    baseline = None
    positional = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--min", "--min-baseline"):
            if i + 1 >= len(args):
                print(f"error: {a} requires a value", file=sys.stderr)
                return 2
            val = args[i + 1]
            if a == "--min":
                try:
                    min_n = float(val)
                except ValueError:
                    print(f"error: --min value {val!r} is not a number", file=sys.stderr)
                    return 2
            else:
                baseline = val
            i += 2; continue
        if a.startswith("-"):
            i += 1; continue
        positional.append(a); i += 1
    target = Path(positional[0]).resolve() if positional else Path.cwd()
    if not any((target / d).exists() for d in ("skills", ".claude-plugin", ".codex-plugin")):
        print(f"error: {target} does not look like a plugin root", file=sys.stderr)
        return 2
    result = score(target)
    if as_json:
        print(json.dumps(result, indent=2))
    elif as_md:
        print(render_md(result))
    else:
        print(render_table(result))

    total_auto = result["total"]["auto"]
    rc = 0
    if min_n is not None and total_auto < min_n:
        print(f"\nGATE FAIL: total auto {total_auto} < --min {min_n}", file=sys.stderr)
        rc = 1
    if baseline is not None:
        try:
            prev = load_json(baseline)
            prev_auto = prev.get("total", {}).get("auto", prev.get("auto")) \
                if isinstance(prev, dict) else None
            if prev_auto is None:
                print(f"\nwarning: baseline {baseline} has no total.auto; skipping regression gate",
                      file=sys.stderr)
            elif total_auto < prev_auto:
                print(f"\nGATE FAIL: total auto {total_auto} < baseline {prev_auto} ({baseline})",
                      file=sys.stderr)
                rc = 1
            else:
                print(f"\nbaseline OK: {total_auto} >= {prev_auto} ({baseline})", file=sys.stderr)
        except Exception as e:
            print(f"\nwarning: baseline {baseline} unreadable ({e}); skipping regression gate",
                  file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
