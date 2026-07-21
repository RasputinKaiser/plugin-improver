#!/usr/bin/env python3
"""Deterministic machine sub-score for the plugin health rubric.

Stdlib only.
  python3 scripts/score.py <plugin-root>              # human table
  python3 scripts/score.py <plugin-root> --json       # structured object
  python3 scripts/score.py <plugin-root> --md         # markdown
  python3 scripts/score.py <plugin-root> --min N       # exit 1 if effective total < N
  python3 scripts/score.py <plugin-root> --min-baseline PATH  # exit 1 on regression
  python3 scripts/score.py selftest                    # deterministic fixtures

Scores the OBJECTIVE parts of the 100-pt rubric in
skills/plugin-audit/references/scoring-rubric.md. For each dimension it emits
{auto, max, ceiling, applicable, needs_judgment}: `auto` = machine-verifiable
points earned, `max` = the dimension's nominal rubric ceiling (unchanged),
`ceiling` = the machine-achievable slice of that max (auto can never exceed it),
`applicable` = whether the dimension applies to this plugin at all.

Calibration (2026 recalibration — de-saturate + discriminate):
  * No free points. Every dimension awards graduated credit; validity earns the
    MIDDLE of a sub-point, not its max.
  * N/A -> redistribute. A dimension that genuinely does not apply (no hooks, no
    skills) is DROPPED — excluded from both numerator and denominator — so its
    weight spreads proportionally across the applicable dimensions. No dimension
    ever hands out a free maximum for being absent.
  * The effective total renormalizes the earned auto against the achievable auto
    ceiling of the *applicable* dimensions, scaled to 100, so totals stay
    comparable across plugins with different applicable sets. A perfect plugin
    can reach 100; a mature-but-improvable one lands in the 70s-80s.
  * Grade bands (on the effective total):
        92-100 Exceptional | 82-91 Strong | 68-81 Solid |
        50-67 Needs work   | <50 Poor

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
# NOT-clause with a genuine redirect to an alternative/sibling — merely containing
# the token "not" earns nothing; the description must point somewhere else.
NOT_ALT = re.compile(
    r"\binstead of\b|"                                # "instead of X"
    r"\brather than\b|"                               # "rather than X"
    r"\buse\s+[`'\"]?[\w-]+[`'\"]?\s+instead\b|"      # "use Y instead"
    r"\bnot for\b[^.]{0,80}?\buse\b|"                 # "not for X ... use Y"
    r"\bnot\b[^.]{0,80}?[\(;,—-]\s*use\b|"       # "not X, use Y" / "not X (use Y)"
    r"\bdon'?t use\b[^.]{0,60}?\buse\b|"              # "don't use ... use Y"
    r"\bdo not use\b[^.]{0,60}?\buse\b",
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

# Imperative verbs an agent-instruction body tends to open lines with.
IMPERATIVE_VERBS = {
    "run", "read", "write", "create", "add", "use", "check", "verify", "edit",
    "open", "load", "call", "score", "compute", "parse", "return", "emit",
    "report", "list", "find", "set", "print", "build", "install", "fix", "avoid",
    "ensure", "do", "make", "keep", "note", "pass", "save", "delete", "remove",
    "update", "generate", "apply", "follow", "start", "stop", "copy", "move",
    "rename", "replace", "insert", "append", "split", "join", "merge", "fetch",
    "send", "click", "type", "select", "choose", "pick", "review", "audit",
    "scan", "test", "validate", "confirm", "ask", "reject", "accept", "skip",
    "include", "exclude", "define", "declare", "assert", "raise", "catch",
    "handle", "render", "draw", "show", "hide", "enable", "disable", "count",
    "sum", "map", "filter", "sort", "group", "trim", "strip", "format",
    "normalize", "extract", "collect", "gather", "record", "log", "track",
    "measure", "rank", "weight", "prefer", "treat", "name", "label", "mark",
    "flag", "gate", "guard", "wrap", "identify", "determine", "decide",
    "compare", "match", "search", "grep", "cd", "echo", "cat", "give", "grade",
    "reason", "walk", "iterate", "loop", "collapse", "expand", "inspect",
}

# Failure-handling signals in a body.
FAILURE_KEYWORDS = [
    "if missing", "if it fails", "if fails", "fallback", "falls back", "fall back",
    "error", "ambiguous", "absent", "does not exist", "doesn't exist", "cannot",
    "can't", "unavailable", "invalid", "retry", "when missing", "if absent",
    "if unavailable", "if the file", "if no ", "not found", "fails", "failure",
    "timeout", "times out", "crash", "exit 1", "unreadable", "when in doubt",
    "if unclear", "edge case", "missing", "otherwise", "when none", "if empty",
]

# Machine-achievable ceilings per dimension (sum of auto sub-point weights).
CEILINGS = {
    "manifest_integrity": 15.0,
    "skill_quality": 18.0,
    "trigger_precision": 13.0,
    "context_economy": 14.0,
    "hooks_health": 5.0,
    "distribution": 8.0,
}

GRADE_BANDS = [
    (92.0, "Exceptional"),
    (82.0, "Strong"),
    (68.0, "Solid"),
    (50.0, "Needs work"),
    (0.0, "Poor"),
]


def grade_for(effective):
    for floor, label in GRADE_BANDS:
        if effective >= floor:
            return label
    return "Poor"


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


def budget_fraction(used, budget):
    """Utilization gradient: full credit at <=50% of budget, linear decay to 0 at
    >=100%. A body/description that hugs the budget scores far below a lean one."""
    if budget <= 0:
        return 0.0
    u = used / budget
    return clamp(2.0 * (1.0 - u), 0.0, 1.0)


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


# ---------- skill-quality proxies ----------

def _first_word(line):
    s = re.sub(r"^[#>*\-\d.\)\(`\s]+", "", line.strip())
    m = re.match(r"[A-Za-z']+", s)
    return m.group(0).lower() if m else ""


def skill_quality_components(body):
    """Return (imperative<=8, actionable<=5, failure<=5) machine proxies for one
    skill body. Averaged across skills upstream."""
    lines = [l for l in body.splitlines() if l.strip()]
    if not lines:
        return (0.0, 0.0, 0.0)

    # imperative body (8): verb-first density + step markers + verb-first heading.
    firsts = [_first_word(l) for l in lines]
    verb_lines = sum(1 for w in firsts if w in IMPERATIVE_VERBS)
    density = verb_lines / len(lines)
    imp = 5.0 * clamp(density / 0.35, 0.0, 1.0)
    has_steps = bool(re.search(r"(?m)^\s*\d+[.)]\s", body)) or bool(re.search(r"\bstep\s*\d", body, re.I))
    imp += 2.0 if has_steps else 0.0
    heading_verb = any(_first_word(l) in IMPERATIVE_VERBS
                       for l in lines if l.lstrip().startswith("#"))
    imp += 1.0 if heading_verb else 0.0
    imp = clamp(imp, 0.0, 8.0)

    # actionable specifics (5): code fences + inline code + file paths.
    spec = 0.0
    fences = body.count("```")
    spec += 2.0 if fences >= 2 else (1.0 if fences == 1 else 0.0)
    inline = len(re.findall(r"`[^`\n]+`", body))
    spec += 1.5 * clamp(inline / 3.0, 0.0, 1.0)
    # A real path reference — a known extension, a ./ ~/ ../ prefix, or a slash
    # inside inline code. Deliberately NOT a bare `word/word` (excludes prose like
    # "and/or", "read/write", "pass/fail").
    pathlike = bool(re.search(r"[\w./-]+\.(py|md|json|sh|js|ts|txt|ya?ml|toml)\b", body)) \
        or bool(re.search(r"(?:\.\.?/|~/)[\w./-]+", body)) \
        or bool(re.search(r"`[^`\n]*/[^`\n]*`", body))
    spec += 1.5 if pathlike else 0.0
    spec = clamp(spec, 0.0, 5.0)

    # failure handling (5): distinct failure-signal keywords.
    low = body.lower()
    fh_hits = sum(1 for kw in FAILURE_KEYWORDS if kw in low)
    fail = 5.0 * clamp(fh_hits / 3.0, 0.0, 1.0)

    return (imp, spec, fail)


# ---------- dimension scorers ----------

def score_manifest(root):
    m = manifests(root)
    judgment, auto = [], 0.0
    claude, codex = m.get("claude"), m.get("codex")
    present = {k: v for k, v in m.items() if v is not None}
    files_present = len(m)
    corrupt = any(v is None for v in m.values())

    # 4pt — validity, graduated: kebab name (2), semver version (1.5), description (0.5).
    if present and not corrupt:
        names = {v.get("name") for v in present.values()}
        name_ok = all(n and KEBAB.match(n) for n in names)
        vers_ok = all(SEMVER.match(v.get("version", "") or "") for v in present.values())
        desc_ok = all((v.get("description") or "").strip() for v in present.values())
        auto += 2.0 * name_ok + 1.5 * vers_ok + 0.5 * desc_ok
    judgment.append("description accuracy (part of the 4pt validity sub-point) is judgment")

    # 4pt — cross-harness parity: identical name (2) + agreeing version (2).
    if files_present == 2 and claude and codex:
        same_name = claude.get("name") == codex.get("name")
        same_ver = base_version(claude.get("version", "")) == base_version(codex.get("version", ""))
        auto += 2.0 * same_name + 2.0 * same_ver
    elif files_present == 1 and len(present) == 1:
        auto += 4.0  # single-harness plugin earns full parity credit for its one manifest
    else:
        judgment.append("cross-harness parity unverifiable (a manifest missing or failed to parse)")

    # 3pt — component pointers ./-prefixed, in-root, resolvable (proportional).
    ptr_keys = ("skills", "hooks", "mcpServers", "apps")
    ptr_vals = []
    for v in present.values():
        for k in ptr_keys:
            if k in v and isinstance(v[k], str):
                ptr_vals.append(v[k])
    if ptr_vals:
        good = sum(1 for p in ptr_vals
                   if p.startswith("./") and not p.startswith("../")
                   and (root / p.lstrip("./")).exists())
        auto += 3.0 * good / len(ptr_vals)
    else:
        auto += 3.0  # no string pointers to get wrong

    # 2pt — layout: each manifest dir holds only plugin.json / marketplace.json (proportional).
    mdirs = [root / d for d in (".claude-plugin", ".codex-plugin") if (root / d).is_dir()]
    if mdirs:
        clean = 0
        for d in mdirs:
            stray = [f.name for f in d.iterdir()
                     if f.name not in ("plugin.json", "marketplace.json")]
            if stray:
                judgment.append(f"{d.name}/ holds stray files: {stray}")
            else:
                clean += 1
        auto += 2.0 * clean / len(mdirs)
    else:
        auto += 2.0

    # 2pt — publisher metadata: author present (mechanical core).
    has_author = any(v.get("author") for v in present.values())
    auto += 2.0 if has_author else 0.0
    judgment.append("publisher-metadata appropriateness to distribution level (2pt) is judgment")

    return {"auto": round(auto, 1), "max": 15, "ceiling": CEILINGS["manifest_integrity"],
            "applicable": True, "needs_judgment": judgment}


def score_skill_quality(root):
    skills = load_skills(root)
    if not skills:
        return {"auto": 0.0, "max": 25, "ceiling": 0.0, "applicable": False,
                "needs_judgment": ["no skills — dimension N/A, weight redistributed"]}
    imp = spec = fail = 0.0
    weak = []
    for s in skills:
        i, sp, fh = skill_quality_components(s["body"])
        imp += i
        spec += sp
        fail += fh
        if (i + sp + fh) < 6.0:
            weak.append(s["name"])
    n = len(skills)
    auto = imp / n + spec / n + fail / n  # each component averaged, ceiling 8+5+5=18
    judgment = [
        "one-job-per-skill / no two skills same job — judgment",
        "imperative-body proxy scored (~8): verb-first density, step markers, verb headings",
        "actionable-specifics proxy scored (~5): file paths, backticked commands, code fences",
        "failure-handling proxy scored (~5): missing/fails/fallback/error/ambiguous/absent signals",
        "remaining ~7pt (genuine one-job separation & instruction depth) is judgment residue",
    ]
    if weak:
        judgment.append(f"skills scoring low on machine proxies (read the body): {weak}")
    return {"auto": round(auto, 1), "max": 25, "ceiling": CEILINGS["skill_quality"],
            "applicable": True, "needs_judgment": judgment}


def score_trigger(root):
    skills = load_skills(root)
    if not skills:
        return {"auto": 0.0, "max": 20, "ceiling": 0.0, "applicable": False,
                "needs_judgment": ["no skills — dimension N/A, weight redistributed"]}
    judgment, auto = [], 0.0
    n = len(skills)

    # 3pt (of 7) — description within budget AND carries a when/trigger signal or quoted phrase.
    good_when = sum(1 for s in skills
                    if s["description"] and len(s["description"]) <= 400
                    and (WHEN_SIGNAL.search(s["description"]) or quoted_phrases(s["description"])))
    auto += 3.0 * good_when / n
    judgment.append("what+when completeness & trigger-phrase quality (remaining 4pt) is judgment")

    # 5pt — negative scope: NOT-clause that redirects to an alternative/sibling.
    has_alt = sum(1 for s in skills if NOT_ALT.search(s["description"]))
    auto += 5.0 * has_alt / n
    if has_alt < n:
        judgment.append(f"{n - has_alt}/{n} skills lack a redirecting NOT-clause (\"not for X, use Y\")")

    # 5pt — no trigger collisions (light sibling collision count).
    count, notes = collision_count(skills)
    auto += clamp(5.0 - count, 0.0, 5.0)
    if count:
        judgment.extend(notes)

    judgment.append("risky-skill guarding (allow_implicit_invocation / negative scope, 3pt) is judgment")
    return {"auto": round(auto, 1), "max": 20, "ceiling": CEILINGS["trigger_precision"],
            "applicable": True, "needs_judgment": judgment}


def score_context(root):
    skills = load_skills(root)
    if not skills:
        return {"auto": 0.0, "max": 20, "ceiling": 0.0, "applicable": False,
                "needs_judgment": ["no skills — dimension N/A, weight redistributed"]}
    judgment, auto = [], 0.0
    n = len(skills)

    # 8pt — body utilization gradient (600-word budget; lean scores far above near-budget).
    body_frac = sum(budget_fraction(len(s["body"].split()), 600) for s in skills) / n
    auto += 8.0 * body_frac
    over = [f"{s['name']}={len(s['body'].split())}w" for s in skills if len(s["body"].split()) > 600]
    if over:
        judgment.append(f"bodies over the 600-word budget: {over}")
    judgment.append("progressive disclosure (detail pushed to references/) is judgment")

    # 6pt — no duplicated content across skills — judgment.
    judgment.append("no duplicated content across skills (6pt) is judgment")

    # 4pt — description utilization gradient (400-char budget).
    desc_frac = sum(budget_fraction(len(s["description"]), 400) for s in skills) / n
    auto += 4.0 * desc_frac
    d_over = [f"{s['name']}={len(s['description'])}c" for s in skills if len(s["description"]) > 400]
    if d_over:
        judgment.append(f"descriptions over the 400-char budget: {d_over}")

    # 2pt — no dead weight: empty files / empty reference dirs.
    dead = []
    for s in skills:
        for f in s["dir"].rglob("*"):
            if f.is_file() and f.stat().st_size == 0:
                dead.append(str(f.relative_to(root)))
        refs = s["dir"] / "references"
        if refs.is_dir() and not any(refs.iterdir()):
            dead.append(str(refs.relative_to(root)) + "/ (empty)")
    auto += 2.0 if not dead else 0.0
    if dead:
        judgment.append(f"dead/empty files: {dead}")
    return {"auto": round(auto, 1), "max": 20, "ceiling": CEILINGS["context_economy"],
            "applicable": True, "needs_judgment": judgment}


def score_hooks(root):
    judgment = []
    hj = root / "hooks" / "hooks.json"
    if not hj.is_file():
        return {"auto": 0.0, "max": 10, "ceiling": 0.0, "applicable": False,
                "needs_judgment": ["no hooks present — dimension N/A, weight redistributed"]}
    auto = 0.0
    try:
        data = load_json(hj)
    except Exception as e:
        return {"auto": 0.0, "max": 10, "ceiling": CEILINGS["hooks_health"], "applicable": True,
                "needs_judgment": [f"hooks.json invalid JSON: {e}"]}
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
    auto += 3.0 if shape_ok else 0.0
    if not shape_ok:
        judgment.append("hooks.json shape is not event -> matcher group -> handlers")
    # 2pt — paths use ${CLAUDE_PLUGIN_ROOT} or ${PLUGIN_ROOT}.
    strings = list(walk_strings(data))
    cmds = [s for s in strings if "/" in s and (".py" in s or ".sh" in s or ".js" in s)]
    paths_ok = all(("${CLAUDE_PLUGIN_ROOT}" in s or "${PLUGIN_ROOT}" in s) for s in cmds) if cmds else True
    auto += 2.0 if paths_ok else 0.0
    if not paths_ok:
        judgment.append("some hook paths do not use ${CLAUDE_PLUGIN_ROOT}/${PLUGIN_ROOT}")
    judgment.append("per-event contract correctness & harness-limit respect (5pt) is judgment")
    return {"auto": round(auto, 1), "max": 10, "ceiling": CEILINGS["hooks_health"],
            "applicable": True, "needs_judgment": judgment}


def score_distribution(root):
    judgment, auto = [], 0.0
    # 3pt — README covers what / skills / install (graduated by signals present).
    readme = None
    for cand in ("README.md", "readme.md", "Readme.md"):
        if (root / cand).is_file():
            readme = (root / cand).read_text(encoding="utf-8").lower()
            break
    if readme:
        sig = ("install" in readme) + ("skill" in readme) + bool(re.search(r"^#", readme, re.M))
        auto += 3.0 * clamp(sig, 0, 3) / 3
        judgment.append("README completeness (does it truly cover all sections) is judgment")
    else:
        judgment.append("no README found")

    # 3pt — version discipline: changelog or ledger exists.
    has_log = any((root / f).is_file() for f in ("CHANGELOG.md", "LEDGER.md", "CHANGES.md"))
    auto += 3.0 if has_log else 0.0
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
    auto += 2.0 if listed else 0.0
    if not listed:
        judgment.append("Claude Code marketplace.json does not list this plugin")
    judgment.append("Codex marketplace registration (user-global) unverifiable from plugin root (2pt)")
    return {"auto": round(auto, 1), "max": 10, "ceiling": CEILINGS["distribution"],
            "applicable": True, "needs_judgment": judgment}


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
            d = fn(root)
        except Exception as e:
            d = {"auto": 0.0, "max": 0, "ceiling": 0.0, "applicable": False,
                 "needs_judgment": [f"scorer crashed: {e}"]}
        d.setdefault("applicable", True)
        d.setdefault("ceiling", d.get("max", 0))
        dims[key] = d

    applicable = {k: v for k, v in dims.items()
                  if v.get("applicable", True) and v.get("ceiling", 0) > 0}
    sum_ceiling = sum(v["ceiling"] for v in applicable.values())
    sum_auto = sum(v["auto"] for v in applicable.values())
    effective = round(100.0 * sum_auto / sum_ceiling, 1) if sum_ceiling else 0.0
    return {
        "target": str(root),
        "dimensions": dims,
        "grade": grade_for(effective),
        # total.auto = effective score out of 100 (N/A dims dropped & redistributed).
        # total.effective mirrors it; total.max stays 100 for cross-plugin comparability.
        "total": {"auto": effective, "max": 100, "effective": effective},
    }


# ---------- rendering ----------

def render_table(result):
    lines = [f"target: {result['target']}", ""]
    lines.append(f"{'dimension':<20} {'auto':>6} {'max':>5}  applicable")
    lines.append("-" * 46)
    for key, d in result["dimensions"].items():
        app = "yes" if d.get("applicable", True) and d.get("ceiling", 0) > 0 else "N/A (dropped)"
        lines.append(f"{key:<20} {d['auto']:>6} {d['max']:>5}  {app}")
    t = result["total"]
    lines.append("-" * 46)
    lines.append(f"{'EFFECTIVE / 100':<20} {t['auto']:>6} {t['max']:>5}  grade: {result['grade']}")
    lines.append("")
    lines.append("needs judgment (score on top of the deterministic floor):")
    for key, d in result["dimensions"].items():
        for note in d["needs_judgment"]:
            lines.append(f"  [{key}] {note}")
    return "\n".join(lines)


def render_md(result):
    lines = [f"# Deterministic score — `{result['target']}`", "",
             f"**Effective: {result['total']['auto']}/100 — {result['grade']}**", "",
             "| Dimension | Auto | Max | Applicable |", "|---|---:|---:|:--|"]
    for key, d in result["dimensions"].items():
        app = "yes" if d.get("applicable", True) and d.get("ceiling", 0) > 0 else "N/A — dropped"
        lines.append(f"| {key} | {d['auto']} | {d['max']} | {app} |")
    t = result["total"]
    lines.append(f"| **Effective / 100** | **{t['auto']}** | **{t['max']}** | {result['grade']} |")
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


_RICH_BODY = (
    "## Read the manifest\n"
    "1. Read the manifest at `.claude-plugin/plugin.json` and parse it.\n"
    "2. Run `python3 scripts/score.py .` to compute the floor.\n"
    "3. Verify the `--json` output matches the expected format.\n"
    "4. Report the effective total and grade.\n\n"
    "If the manifest is missing, emit an error and stop. If the command fails or the\n"
    "input is ambiguous, fall back to a manual pass and note it. When in doubt, skip.\n"
)


def _lean_body():
    return _RICH_BODY  # ~55 words, well under budget


def _near_budget_body():
    # ~590 words of imperative-ish prose, just under the 600-word body budget.
    sentence = "Run the next step and verify the file exists before you continue. "
    return _RICH_BODY + "\n" + (sentence * 75)


def _make_plugin(base, *, dual=True, skills=None, hooks=False, readme=True,
                 changelog=True, marketplace=True, author=True, name="demo-plugin",
                 codex_name=None, codex_ver="1.0.0+codex.1", ver="1.0.0"):
    man = {"name": name, "version": ver, "description": "A demo plugin.", "skills": "./skills/"}
    if author:
        man["author"] = {"name": "RasputinKaiser"}
    _write(base, ".claude-plugin/plugin.json", json.dumps(man))
    if dual:
        cman = dict(man)
        cman["name"] = codex_name or name
        cman["version"] = codex_ver
        _write(base, ".codex-plugin/plugin.json", json.dumps(cman))
    if marketplace:
        _write(base, ".claude-plugin/marketplace.json", json.dumps({
            "name": name, "plugins": [{"name": name, "source": ".", "category": "dev"}]}))
    if readme:
        _write(base, "README.md",
               "# demo\n## What it does\nthings\n## Skills\nlist\n## Install\nsteps here\n")
    if changelog:
        _write(base, "CHANGELOG.md", "# Changelog\n- 1.0.0 initial\n")
    if hooks:
        _write(base, "hooks/hooks.json", json.dumps({
            "PreToolUse": [{"matcher": "Bash",
                            "hooks": [{"type": "command",
                                       "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/guard.py"}]}]}))
        _write(base, "hooks/guard.py", "print('ok')\n")
    for rel, desc, body in (skills or []):
        _write(base, rel, f"---\nname: {rel.split('/')[1]}\ndescription: {desc}\n---\n{body}")


def _excellent(base):
    skills = [
        ("skills/alpha/SKILL.md",
         "Convert widgets to gadgets. Use when the user asks to transmute a widget "
         "into a gadget. Not for gadget deletion (use the beta skill instead).",
         _lean_body()),
        ("skills/beta/SKILL.md",
         "Render invoices to a printable PDF. Use when the user wants a printed bill "
         "or receipt. Not for spreadsheet export, rather than a ledger dump.",
         _lean_body()),
    ]
    _make_plugin(base, dual=True, skills=skills, hooks=True, name="excellent-plugin")


def _solid(base):
    # mature-but-improvable: rich lean bodies, but one skill lacks a redirecting
    # NOT-clause, no changelog, no hooks. Should land Solid/Strong (68-91).
    skills = [
        ("skills/alpha/SKILL.md",
         "Convert widgets to gadgets. Use when the user asks to transmute a widget. "
         "Not for gadget deletion (use the beta skill instead).",
         _lean_body()),
        ("skills/beta/SKILL.md",
         "Render invoices to a printable PDF. Use when the user wants a printed bill.",
         _lean_body()),
    ]
    _make_plugin(base, dual=True, skills=skills, hooks=False, changelog=False,
                 name="solid-plugin")


def _fair(base):
    # thin bodies, near-budget on one, weak triggers, no marketplace/changelog.
    skills = [
        ("skills/alpha/SKILL.md",
         "Manage the widget gadget thing for the user in various situations.",
         "Do the alpha job.\nStep one then step two.\n"),
        ("skills/beta/SKILL.md",
         "Handle beta stuff when needed by the operator somehow.",
         _near_budget_body()),
    ]
    _make_plugin(base, dual=True, skills=skills, hooks=False, readme=True,
                 changelog=False, marketplace=False, name="fair-plugin")


def _poor(base):
    # name mismatch, version drift, over-budget colliding descriptions, empty file,
    # no NOT-clauses, no marketplace listing, no changelog, thin bodies.
    _write(base, ".claude-plugin/plugin.json", json.dumps({
        "name": "poor-plugin", "version": "1.0.0", "description": "x"}))
    _write(base, ".codex-plugin/plugin.json", json.dumps({
        "name": "por-plugin", "version": "2.0.0", "description": ""}))
    _write(base, ".claude-plugin/marketplace.json", json.dumps({"plugins": []}))
    long_desc = "manage the widget gadget thing " * 20  # > 400 chars, no when/not signal
    _write(base, "skills/alpha/SKILL.md", f"---\nname: alpha\ndescription: {long_desc}\n---\nbody\n")
    _write(base, "skills/beta/SKILL.md", f"---\nname: beta\ndescription: {long_desc}\n---\nbody\n")
    _write(base, "skills/alpha/references/empty.md", "")


def selftest():
    failures = []
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)

        exc = base / "excellent"; _excellent(exc); re_ = score(exc)
        sol = base / "solid"; _solid(sol); rs = score(sol)
        fai = base / "fair"; _fair(fai); rf = score(fai)
        poo = base / "poor"; _poor(poo); rp = score(poo)

        ed, sd, fd, pd_ = (r["dimensions"] for r in (re_, rs, rf, rp))
        et, st, ft, pt = (r["total"]["auto"] for r in (re_, rs, rf, rp))

        checks = [
            # --- band membership of effective totals ---
            (f"excellent in Exceptional (>=92), got {et}", et >= 92),
            (f"solid in Solid/Strong band [68,91], got {st}", 68 <= st <= 91),
            (f"fair in Needs-work band [50,67], got {ft}", 50 <= ft <= 67),
            (f"poor in Poor band (<50), got {pt}", pt < 50),
            ("monotonic ordering poor<fair<solid<excellent",
             pt < ft < st < et),
            # --- de-saturation invariants ---
            ("(a) hooks NOT auto-max when absent — dropped/redistributed in solid",
             sd["hooks_health"]["applicable"] is False and sd["hooks_health"]["auto"] == 0),
            ("(a2) hooks applicable & graduated when present in excellent",
             ed["hooks_health"]["applicable"] is True and ed["hooks_health"]["auto"] == 5),
            ("(b) skill_quality auto > 0 for a good plugin",
             ed["skill_quality"]["auto"] > 0 and sd["skill_quality"]["auto"] > 0),
            ("(b2) skill_quality auto reaches ~16 for excellent (rich imperative body)",
             ed["skill_quality"]["auto"] >= 16),
            ("(d) demanding-but-not-impossible: excellent is 92+ yet NOT a trivial 100",
             92 <= et < 100),
            # --- schema freeze ---
            ("total.max == 100", re_["total"]["max"] == 100),
            ("total.effective mirrors total.auto", re_["total"]["effective"] == et),
            ("grade computed from the band table", re_["grade"] == "Exceptional"),
            ("dimension keys unchanged",
             list(ed.keys()) == [k for k, _ in DIMENSIONS]),
            ("nominal maxes preserved 15/25/20/20/10/10",
             [ed[k]["max"] for k, _ in DIMENSIONS] == [15, 25, 20, 20, 10, 10]),
        ]
        for label, ok in checks:
            if not ok:
                failures.append(label)

        # --- (c) context strictly higher for lean vs near-budget body ---
        lean = base / "ctx_lean"
        _make_plugin(lean, dual=False, name="lean-plugin",
                     skills=[("skills/a/SKILL.md", "Do a. Use when a is needed. Not for b (use c).",
                              _lean_body())])
        near = base / "ctx_near"
        _make_plugin(near, dual=False, name="near-plugin",
                     skills=[("skills/a/SKILL.md", "Do a. Use when a is needed. Not for b (use c).",
                              _near_budget_body())])
        lc = score(lean)["dimensions"]["context_economy"]["auto"]
        nc = score(near)["dimensions"]["context_economy"]["auto"]
        if not (lc > nc):
            failures.append(f"(c) lean context {lc} not > near-budget context {nc}")

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
        print(f"\nGATE FAIL: effective total {total_auto} < --min {min_n}", file=sys.stderr)
        rc = 1
    if baseline is not None:
        try:
            prev = load_json(baseline)
            prev_total = prev.get("total", {}) if isinstance(prev, dict) else {}
            prev_auto = prev_total.get("auto", prev.get("auto")) \
                if isinstance(prev, dict) else None
            # `total.auto` switched to the renormalized effective scale; a baseline
            # captured before that (no `effective` key) is not comparable.
            if isinstance(prev_total, dict) and prev_auto is not None \
                    and "effective" not in prev_total:
                print(f"\nwarning: baseline {baseline} predates effective-scoring; "
                      "scales differ, skipping regression gate", file=sys.stderr)
            elif prev_auto is None:
                print(f"\nwarning: baseline {baseline} has no total.auto; skipping regression gate",
                      file=sys.stderr)
            elif total_auto < prev_auto:
                print(f"\nGATE FAIL: effective total {total_auto} < baseline {prev_auto} ({baseline})",
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
