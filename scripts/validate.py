#!/usr/bin/env python3
"""Validator / self-test for the plugin-improver dual-harness plugin.

Stdlib only. Run from the repo root:  python3 scripts/validate.py [--json]
Exit 0 if every check passes, 1 if any check fails.

The check registry (CHECKS) is a list of (name, fn) pairs — add a check by
appending one. Each fn takes the repo root Path and returns (ok, messages).
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# The full skill roster this plugin ships once the rebuild is integrated.
EXPECTED_SKILLS = [
    "plugin-audit",
    "plugin-hooks",
    "plugin-improve",
    "plugin-tune-triggers",
    "skill-curator",
    "plugin-scaffold",
    "plugin-release",
]

KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)*$")
# Relative reference tokens in a skill body: references/x.md, ../a/b.md, scripts/z.py
REF_TOKEN = re.compile(r"(?:\.\./[\w./-]+|references/[\w./-]+|scripts/[\w./-]+|assets/[\w./-]+)\.\w+")
ASSET_EXT = re.compile(r"\.(svg|png|jpe?g|webp|ico|gif)$", re.I)


# ---------- small helpers ----------

def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def base_version(v):
    """Semver base, dropping any +build metadata (Codex appends +codex.<ts>)."""
    return str(v).split("+", 1)[0]


def split_frontmatter(text):
    """Return (frontmatter_dict, body_str) for a SKILL.md. Tiny hand parser."""
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


def walk_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_strings(v)


# ---------- checks ----------

def check_manifests(root):
    ok, msgs = True, []
    claude_p = root / ".claude-plugin" / "plugin.json"
    codex_p = root / ".codex-plugin" / "plugin.json"
    market_p = root / ".claude-plugin" / "marketplace.json"
    parsed = {}
    for label, p in (("claude", claude_p), ("codex", codex_p)):
        if not p.is_file():
            ok = False
            msgs.append(f"missing {p.relative_to(root)}")
            continue
        try:
            parsed[label] = load_json(p)
            msgs.append(f"parsed {p.relative_to(root)}")
        except Exception as e:
            ok = False
            msgs.append(f"invalid JSON {p.relative_to(root)}: {e}")
    if "claude" in parsed and "codex" in parsed:
        c, x = parsed["claude"], parsed["codex"]
        cn, xn = c.get("name"), x.get("name")
        if cn != xn:
            ok = False
            msgs.append(f"name mismatch: claude={cn!r} codex={xn!r}")
        elif not (cn and KEBAB.match(cn)):
            ok = False
            msgs.append(f"name not kebab-case: {cn!r}")
        else:
            msgs.append(f"name agrees & kebab-case: {cn}")
        for lbl, m in (("claude", c), ("codex", x)):
            if not SEMVER.match(m.get("version", "")):
                ok = False
                msgs.append(f"{lbl} version not semver: {m.get('version')!r}")
        cv, xv = base_version(c.get("version", "")), base_version(x.get("version", ""))
        if cv != xv:
            ok = False
            msgs.append(f"version mismatch: claude={cv} codex={xv}")
        else:
            msgs.append(f"version agrees: {cv}")
    if not market_p.is_file():
        ok = False
        msgs.append(f"missing {market_p.relative_to(root)}")
    else:
        try:
            mkt = load_json(market_p)
            name = parsed.get("codex", {}).get("name") or "plugin-improver"
            if name in "".join(walk_strings(mkt)):
                msgs.append(f"marketplace references {name}")
            else:
                ok = False
                msgs.append(f"marketplace does not reference {name}")
        except Exception as e:
            ok = False
            msgs.append(f"invalid marketplace JSON: {e}")
    return ok, msgs


def check_frontmatter(root):
    ok, msgs = True, []
    dirs = iter_skill_dirs(root)
    if not dirs:
        return False, ["no skills found under skills/"]
    for d in dirs:
        fm, _ = split_frontmatter((d / "SKILL.md").read_text(encoding="utf-8"))
        if fm is None:
            ok = False
            msgs.append(f"{d.name}: no YAML frontmatter")
            continue
        name = fm.get("name")
        if name != d.name:
            ok = False
            msgs.append(f"{d.name}: name {name!r} != dir")
        elif not KEBAB.match(name):
            ok = False
            msgs.append(f"{d.name}: name not kebab-case")
        desc = fm.get("description", "")
        if not desc:
            ok = False
            msgs.append(f"{d.name}: missing description")
        elif len(desc) > 400:
            ok = False
            msgs.append(f"{d.name}: description {len(desc)} chars > 400")
        else:
            msgs.append(f"{d.name}: ok ({len(desc)} char desc)")
    return ok, msgs


def check_body_budget(root):
    ok, msgs = True, []
    for d in iter_skill_dirs(root):
        _, body = split_frontmatter((d / "SKILL.md").read_text(encoding="utf-8"))
        words = len(body.split())
        if words > 1500:
            ok = False
            msgs.append(f"{d.name}: {words} words > 1500 (hard fail)")
        elif words > 600:
            msgs.append(f"{d.name}: {words} words > 600 (warn)")
        else:
            msgs.append(f"{d.name}: {words} words")
    return ok, msgs


def check_reference_integrity(root):
    ok, msgs = True, []
    total = 0
    for d in iter_skill_dirs(root):
        text = (d / "SKILL.md").read_text(encoding="utf-8")
        for tok in sorted(set(REF_TOKEN.findall(text))):
            total += 1
            # A link resolves if it exists relative to the skill dir (references/,
            # ../other-skill/...) OR relative to the repo root (scripts/validate.py).
            if not ((d / tok).exists() or (root / tok).exists()):
                ok = False
                msgs.append(f"{d.name}: broken link {tok}")
    msgs.append(f"{total} relative links checked")
    return ok, msgs


def check_openai_interface(root):
    ok, msgs = True, []
    for d in iter_skill_dirs(root):
        y = d / "agents" / "openai.yaml"
        if not y.is_file():
            ok = False
            msgs.append(f"{d.name}: missing agents/openai.yaml")
            continue
        text = y.read_text(encoding="utf-8")
        keys = {ln.split(":", 1)[0].strip() for ln in text.splitlines() if ":" in ln}
        missing = [k for k in ("interface", "display_name") if k not in keys]
        if missing:
            ok = False
            msgs.append(f"{d.name}: openai.yaml missing {', '.join(missing)}")
        else:
            msgs.append(f"{d.name}: openai.yaml ok")
    return ok, msgs


def check_parity(root):
    ok, msgs = True, []
    present = {d.name for d in iter_skill_dirs(root)}
    for name in EXPECTED_SKILLS:
        if name not in present:
            ok = False
            msgs.append(f"missing required skill: {name}")
    for d in iter_skill_dirs(root):
        has_skill = (d / "SKILL.md").is_file()
        has_yaml = (d / "agents" / "openai.yaml").is_file()
        gaps = [f for f, present in (("SKILL.md", has_skill), ("openai.yaml", has_yaml)) if not present]
        if gaps:
            ok = False
            msgs.append(f"{d.name}: missing {', '.join(gaps)}")
        else:
            msgs.append(f"{d.name}: discoverable on both harnesses")
    return ok, msgs


def check_assets(root):
    ok, msgs = True, []
    manifests = [root / ".claude-plugin" / "plugin.json", root / ".codex-plugin" / "plugin.json"]
    found = False
    for m in manifests:
        if not m.is_file():
            continue
        try:
            data = load_json(m)
        except Exception:
            continue
        for s in walk_strings(data):
            if ASSET_EXT.search(s):
                found = True
                target = (root / s.lstrip("./")).resolve() if not s.startswith("/") else Path(s)
                if target.exists():
                    msgs.append(f"asset ok: {s}")
                else:
                    ok = False
                    msgs.append(f"missing asset: {s} (from {m.name})")
    if not found:
        msgs.append("no asset paths referenced by manifests")
    return ok, msgs


CHECKS = [
    ("Manifests parse & agree", check_manifests),
    ("Skill frontmatter", check_frontmatter),
    ("Body budget", check_body_budget),
    ("Reference integrity", check_reference_integrity),
    ("Codex per-skill interface", check_openai_interface),
    ("Parity", check_parity),
    ("Assets", check_assets),
]


def run():
    results = []
    for name, fn in CHECKS:
        try:
            ok, msgs = fn(REPO)
        except Exception as e:
            ok, msgs = False, [f"check crashed: {e}"]
        results.append({"name": name, "ok": ok, "messages": msgs})
    return results


def main():
    as_json = "--json" in sys.argv[1:]
    results = run()
    passed = sum(1 for r in results if r["ok"])
    total = len(results)
    if as_json:
        summary = f"PASS {passed}/{total}" if passed == total else f"FAIL: {total - passed}"
        print(json.dumps({"results": results, "passed": passed, "total": total,
                          "summary": summary}, indent=2))
    else:
        for r in results:
            print(f"[{'PASS' if r['ok'] else 'FAIL'}] {r['name']}")
            for m in r["messages"]:
                print(f"       - {m}")
        print()
        if passed == total:
            print(f"PASS {passed}/{total}")
        else:
            print(f"FAIL: {total - passed} ({passed}/{total} checks passed)")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
