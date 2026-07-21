#!/usr/bin/env python3
"""Diagnostic linter / self-test for dual-harness (Claude Code + Codex) plugins.

Stdlib only.
  python3 scripts/validate.py [--json]          # validate this repo (self-test)
  python3 scripts/validate.py <plugin-dir>      # validate another plugin
Exit 0 if no `error`-severity finding, 1 otherwise. (`warn`/`info` never fail.)

The check registry (CHECKS) is a list of (name, fn) pairs — add a check by
appending one. Each fn takes the target plugin root Path and returns a Collector
(see below) carrying human-readable notes plus structured findings.

--------------------------------------------------------------------------------
Findings & error codes
--------------------------------------------------------------------------------
Every distinct problem carries a stable code `PI-<letter><3 digits>`. The letter
namespaces the check so codes never collide as checks evolve:

    M  manifests / marketplace       I  Codex per-skill interface (openai.yaml)
    S  skill frontmatter             C  Claude Code commands
    B  skill body budget             P  cross-harness parity
    R  reference integrity           A  manifest asset paths
    H  hook health                   J  .mcp.json shape
    D  dead / empty files            Z  validator-internal (crash guard)

Each finding has a severity:
    error  blocks — counts toward exit 1 (things that failed before this rewrite)
    warn   advisory — does NOT fail the run (e.g. body > 600 words)
    info   neutral note that is still worth surfacing in the flat feed

and a one-line `fix` hint. A check "passes" (results[].ok == True) when it emits
no `error`-severity finding; the run exits 1 iff any check has an error.

--------------------------------------------------------------------------------
JSON shape (--json)
--------------------------------------------------------------------------------
Backward-compatible top-level keys are preserved verbatim: `target`, `results`
(list of {name, ok, messages}), `passed`, `total`, `summary`. A NEW flat
`findings` array is added: {code, severity, check, path, message, fix}. Existing
keys are never removed or renamed — sibling scripts may consume them.
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
# Relative reference tokens in a skill body: references/x.md, ../a/b.md, scripts/z.py.
# The lookbehind requires a path boundary so mid-path fragments of an absolute/home
# path (e.g. ~/.codex/.../scripts/plugin-eval.js) are NOT treated as repo links.
REF_TOKEN = re.compile(r"(?<![\w/~.-])(?:\.\./[\w./-]+|references/[\w./-]+|scripts/[\w./-]+|assets/[\w./-]+)\.\w+")
ASSET_EXT = re.compile(r"\.(svg|png|jpe?g|webp|ico|gif)$", re.I)
FENCE = re.compile(r"```.*?```", re.S)  # fenced code blocks hold illustrative templates
# A hook command references a script by its file suffix; used to locate + resolve it.
SCRIPT_TOKEN = re.compile(r"[\w./${}~-]+\.(?:py|sh|js|ts|rb|mjs|cjs)\b")
PLUGIN_ROOT_VAR = re.compile(r"\$\{(?:CLAUDE_)?PLUGIN_(?:ROOT|DATA)\}")

# ---------- small helpers ----------


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def strip_fences(text):
    """Drop ``` fenced code blocks — their paths are examples, not real links."""
    return FENCE.sub("", text)


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


class Collector:
    """Accumulates readable notes + structured findings for one check.

    `note()` records a neutral pass/detail line (human output only). `finding()`
    records a structured diagnostic AND a matching, code-prefixed human line, so
    the table and the `--json` feed never drift apart. A check is `ok` when it has
    emitted no `error`-severity finding.
    """

    def __init__(self):
        self.messages = []
        self.findings = []

    def note(self, msg):
        self.messages.append(msg)
        return self

    def finding(self, code, severity, message, fix, path=""):
        line = f"{code} [{severity}] {message}"
        if fix:
            line += f"  (fix: {fix})"
        self.messages.append(line)
        self.findings.append({
            "code": code,
            "severity": severity,
            "path": path,
            "message": message,
            "fix": fix,
        })
        return self

    @property
    def ok(self):
        return not any(f["severity"] == "error" for f in self.findings)


# ---------- checks ----------


def check_manifests(root):
    c = Collector()
    claude_p = root / ".claude-plugin" / "plugin.json"
    codex_p = root / ".codex-plugin" / "plugin.json"
    market_p = root / ".claude-plugin" / "marketplace.json"
    parsed = {}
    for label, p in (("claude", claude_p), ("codex", codex_p)):
        rel = str(p.relative_to(root))
        if not p.is_file():
            c.finding("PI-M001", "error", f"missing {rel}",
                      f"create {rel} with name/version/description", rel)
            continue
        try:
            parsed[label] = load_json(p)
            c.note(f"parsed {rel}")
        except Exception as e:
            c.finding("PI-M002", "error", f"invalid JSON {rel}: {e}",
                      "fix the JSON syntax so the manifest parses", rel)
    if "claude" in parsed and "codex" in parsed:
        cm, xm = parsed["claude"], parsed["codex"]
        cn, xn = cm.get("name"), xm.get("name")
        if cn != xn:
            c.finding("PI-M003", "error", f"name mismatch: claude={cn!r} codex={xn!r}",
                      "make `name` identical in both plugin.json manifests")
        elif not (cn and KEBAB.match(cn)):
            c.finding("PI-M004", "error", f"name not kebab-case: {cn!r}",
                      "rename to lowercase-hyphenated (e.g. my-plugin)")
        else:
            c.note(f"name agrees & kebab-case: {cn}")
        for lbl, m in (("claude", cm), ("codex", xm)):
            if not SEMVER.match(m.get("version", "")):
                c.finding("PI-M005", "error", f"{lbl} version not semver: {m.get('version')!r}",
                          "use MAJOR.MINOR.PATCH (e.g. 1.2.0)")
        cv, xv = base_version(cm.get("version", "")), base_version(xm.get("version", ""))
        if cv != xv:
            c.finding("PI-M006", "error", f"version mismatch: claude={cv} codex={xv}",
                      "bump both manifests to the same version (ignoring any +build suffix)")
        else:
            c.note(f"version agrees: {cv}")
    if not market_p.is_file():
        rel = str(market_p.relative_to(root))
        c.finding("PI-M007", "error", f"missing {rel}",
                  "add a marketplace.json listing this plugin under plugins[]", rel)
    else:
        try:
            mkt = load_json(market_p)
            name = parsed.get("codex", {}).get("name") or parsed.get("claude", {}).get("name")
            entries = mkt.get("plugins", []) if isinstance(mkt, dict) else []
            listed = {e.get("name") for e in entries if isinstance(e, dict)}
            if name and name in listed:
                c.note(f"marketplace lists {name}")
            else:
                c.finding("PI-M008", "error",
                          f"marketplace plugins[] does not list {name!r} (found {sorted(listed)})",
                          f"add an entry with name={name!r} to marketplace.json plugins[]",
                          ".claude-plugin/marketplace.json")
        except Exception as e:
            c.finding("PI-M009", "error", f"invalid marketplace JSON: {e}",
                      "fix the JSON syntax in marketplace.json",
                      ".claude-plugin/marketplace.json")
    return c


def check_frontmatter(root):
    c = Collector()
    dirs = iter_skill_dirs(root)
    if not dirs:
        c.finding("PI-S006", "error", "no skills found under skills/",
                  "add at least one skills/<name>/SKILL.md", "skills/")
        return c
    for d in dirs:
        fm, _ = split_frontmatter((d / "SKILL.md").read_text(encoding="utf-8"))
        rel = f"skills/{d.name}/SKILL.md"
        if fm is None:
            c.finding("PI-S001", "error", f"{d.name}: no YAML frontmatter",
                      "add a --- ... --- block with name and description at the top", rel)
            continue
        name = fm.get("name")
        if name != d.name:
            c.finding("PI-S002", "error", f"{d.name}: name {name!r} != dir",
                      f"set frontmatter name to {d.name!r} to match the directory", rel)
        elif not KEBAB.match(name):
            c.finding("PI-S003", "error", f"{d.name}: name not kebab-case",
                      "use lowercase-hyphenated name", rel)
        desc = fm.get("description", "")
        if not desc:
            c.finding("PI-S004", "error", f"{d.name}: missing description",
                      "add a description stating what it does and when to use it", rel)
        elif len(desc) > 400:
            c.finding("PI-S005", "error", f"{d.name}: description {len(desc)} chars > 400",
                      "tighten the description to <=400 chars; push detail to references/", rel)
        else:
            c.note(f"{d.name}: ok ({len(desc)} char desc)")
    return c


def check_body_budget(root):
    c = Collector()
    for d in iter_skill_dirs(root):
        _, body = split_frontmatter((d / "SKILL.md").read_text(encoding="utf-8"))
        rel = f"skills/{d.name}/SKILL.md"
        words = len(body.split())
        if words > 1500:
            c.finding("PI-B001", "error", f"{d.name}: {words} words > 1500 (hard fail)",
                      "split the body; move detail to references/ (progressive disclosure)", rel)
        elif words > 600:
            c.finding("PI-B002", "warn", f"{d.name}: {words} words > 600",
                      "trim toward <=600 words; move detail to references/", rel)
        else:
            c.note(f"{d.name}: {words} words")
    return c


def check_reference_integrity(root):
    c = Collector()
    total = 0
    # Scan SKILL.md bodies AND their references/*.md files. Fenced code blocks are
    # stripped first — the paths inside them are illustrative templates, not links.
    for d in iter_skill_dirs(root):
        md_files = [d / "SKILL.md"] + sorted((d / "references").glob("*.md")) \
            if (d / "references").is_dir() else [d / "SKILL.md"]
        for f in md_files:
            text = strip_fences(f.read_text(encoding="utf-8"))
            for tok in sorted(set(REF_TOKEN.findall(text))):
                total += 1
                # Resolve relative to the file's own dir, the skill dir, or repo root.
                if not ((f.parent / tok).exists() or (d / tok).exists() or (root / tok).exists()):
                    c.finding("PI-R001", "error", f"{d.name}/{f.name}: broken link {tok}",
                              "fix the path or create the missing file",
                              f"skills/{d.name}/{f.name}")
    c.note(f"{total} relative links checked (prose only)")
    return c


def check_openai_interface(root):
    c = Collector()
    for d in iter_skill_dirs(root):
        y = d / "agents" / "openai.yaml"
        rel = f"skills/{d.name}/agents/openai.yaml"
        if not y.is_file():
            c.finding("PI-I001", "error", f"{d.name}: missing agents/openai.yaml",
                      "add agents/openai.yaml with interface + display_name (Codex-only surface)", rel)
            continue
        text = y.read_text(encoding="utf-8")
        keys = {ln.split(":", 1)[0].strip() for ln in text.splitlines() if ":" in ln}
        missing = [k for k in ("interface", "display_name") if k not in keys]
        if missing:
            c.finding("PI-I002", "error", f"{d.name}: openai.yaml missing {', '.join(missing)}",
                      f"add the {', '.join(missing)} key(s) to openai.yaml", rel)
        else:
            c.note(f"{d.name}: openai.yaml ok")
    return c


def check_commands(root):
    """Claude Code slash-command surface (optional; the Codex analogue is $skill).
    If commands/ exists, every file must be well-formed. For plugin-improver itself,
    require one command per skill so the two harnesses reach explicit-invocation parity."""
    c = Collector()
    cmd_dir = root / "commands"
    if not cmd_dir.is_dir():
        c.note("no commands/ (Claude Code explicit-invocation surface absent — optional)")
        return c
    cmds = sorted(cmd_dir.glob("*.md"))
    for cmd in cmds:
        fm, _ = split_frontmatter(cmd.read_text(encoding="utf-8"))
        rel = f"commands/{cmd.name}"
        if not fm or not fm.get("description"):
            c.finding("PI-C001", "error", f"commands/{cmd.name}: missing frontmatter description",
                      "add a --- frontmatter block with a description key", rel)
        else:
            c.note(f"commands/{cmd.name}: ok")
    if root.resolve() == REPO.resolve():
        have = {cmd.stem for cmd in cmds}
        for name in EXPECTED_SKILLS:
            if name not in have:
                c.finding("PI-C002", "error", f"no command for skill: {name}",
                          f"add commands/{name}.md so both harnesses reach invocation parity")
    return c


def check_parity(root):
    c = Collector()
    dirs = iter_skill_dirs(root)
    if not dirs:
        c.finding("PI-P003", "error", "no skills found under skills/",
                  "add at least one skills/<name>/SKILL.md", "skills/")
        return c
    # The fixed 7-skill roster is only meaningful for plugin-improver itself.
    if root.resolve() == REPO.resolve():
        present = {d.name for d in dirs}
        for name in EXPECTED_SKILLS:
            if name not in present:
                c.finding("PI-P001", "error", f"missing required skill: {name}",
                          f"restore skills/{name}/ — it is part of this plugin's roster")
    for d in dirs:
        has_skill = (d / "SKILL.md").is_file()
        has_yaml = (d / "agents" / "openai.yaml").is_file()
        gaps = [f for f, present in (("SKILL.md", has_skill), ("openai.yaml", has_yaml)) if not present]
        if gaps:
            c.finding("PI-P002", "error", f"{d.name}: missing {', '.join(gaps)}",
                      "add the missing file so the skill is discoverable on both harnesses",
                      f"skills/{d.name}")
        else:
            c.note(f"{d.name}: discoverable on both harnesses")
    return c


def check_assets(root):
    c = Collector()
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
                    c.note(f"asset ok: {s}")
                else:
                    c.finding("PI-A001", "error", f"missing asset: {s} (from {m.name})",
                              "add the asset file or fix the path in the manifest", s)
    if not found:
        c.note("no asset paths referenced by manifests")
    return c


def _load_hook_configs(root):
    """Return list of (source_label, parsed_config, parse_error). Hooks may live in
    hooks/hooks.json or be pointed at / inlined by either manifest's `hooks` key."""
    configs = []
    hooks_json = root / "hooks" / "hooks.json"
    if hooks_json.is_file():
        try:
            configs.append(("hooks/hooks.json", load_json(hooks_json), None))
        except Exception as e:
            configs.append(("hooks/hooks.json", None, str(e)))
    for man in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json"):
        p = root / man
        if not p.is_file():
            continue
        try:
            data = load_json(p)
        except Exception:
            continue
        hooks = data.get("hooks")
        if hooks is None:
            continue
        if isinstance(hooks, str):
            hp = (root / hooks.lstrip("./")).resolve()
            if hp == hooks_json.resolve():
                continue  # already loaded above
            if hp.is_file():
                try:
                    configs.append((f"{man}:hooks->{hooks}", load_json(hp), None))
                except Exception as e:
                    configs.append((f"{man}:hooks->{hooks}", None, str(e)))
            else:
                configs.append((f"{man}:hooks->{hooks}", None, "path does not exist"))
        elif isinstance(hooks, (dict, list)):
            configs.append((f"{man}:hooks (inline)", hooks, None))
    return configs


def check_hooks(root):
    """If the plugin declares hooks, every referenced script must exist, be
    executable, and be addressed via ${CLAUDE_PLUGIN_ROOT}/${PLUGIN_ROOT} rather
    than an absolute or bare-relative path. No hooks => pass."""
    c = Collector()
    configs = _load_hook_configs(root)
    if not configs:
        c.note("no hooks declared (nothing to check)")
        return c
    commands = []  # (source, command_str)
    for source, cfg, err in configs:
        if err is not None:
            c.finding("PI-H004", "error", f"{source}: invalid hooks JSON: {err}",
                      "fix the JSON syntax or the hooks path", source)
            continue
        # Collect every {"type":"command","command":...} string, wherever nested.
        def collect(obj):
            if isinstance(obj, dict):
                if isinstance(obj.get("command"), str):
                    commands.append((source, obj["command"]))
                for v in obj.values():
                    collect(v)
            elif isinstance(obj, list):
                for v in obj:
                    collect(v)
        collect(cfg)
    checked = 0
    for source, cmd in commands:
        for tok in SCRIPT_TOKEN.findall(cmd):
            checked += 1
            uses_var = bool(PLUGIN_ROOT_VAR.search(tok))
            is_abs = tok.startswith("/") or tok.startswith("~")
            if not uses_var and (is_abs or "/" in tok.strip("${}")):
                c.finding("PI-H003", "error",
                          f"{source}: hook command path not portable: {tok}",
                          "reference the script via ${CLAUDE_PLUGIN_ROOT}/... (Codex also accepts ${PLUGIN_ROOT})",
                          source)
            # Resolve the script path to check existence + executable bit.
            resolved = PLUGIN_ROOT_VAR.sub(str(root), tok)
            if resolved.startswith("${"):  # some other unresolved var — skip fs checks
                continue
            sp = Path(resolved)
            if not sp.is_absolute():
                sp = (root / resolved.lstrip("./")).resolve()
            if not sp.is_file():
                c.finding("PI-H001", "error", f"{source}: hook script not found: {tok}",
                          "create the script or fix the path in the hook command", source)
            elif not (sp.stat().st_mode & 0o111):
                c.finding("PI-H002", "error", f"{source}: hook script not executable: {tok}",
                          f"chmod +x {sp.relative_to(root) if root in sp.parents else sp}", source)
    c.note(f"{len(commands)} hook command(s), {checked} script path(s) checked")
    return c


def check_mcp(root):
    """If .mcp.json is present it must parse and be a direct server map or wrapped
    as {mcp_servers: {...}} / {mcpServers: {...}}. Absent => pass."""
    c = Collector()
    p = root / ".mcp.json"
    if not p.is_file():
        c.note("no .mcp.json (nothing to check)")
        return c
    try:
        data = load_json(p)
    except Exception as e:
        c.finding("PI-J001", "error", f".mcp.json invalid JSON: {e}",
                  "fix the JSON syntax", ".mcp.json")
        return c
    if not isinstance(data, dict):
        c.finding("PI-J002", "error", ".mcp.json is not an object",
                  "use a server map or {mcp_servers: {...}}", ".mcp.json")
        return c
    wrapper = None
    for key in ("mcp_servers", "mcpServers"):
        if key in data:
            wrapper = key
            break
    servers = data[wrapper] if wrapper else data
    if not isinstance(servers, dict):
        loc = f"{wrapper}" if wrapper else "top level"
        c.finding("PI-J002", "error", f".mcp.json {loc} is not a server map",
                  "map each server name to its config object", ".mcp.json")
    else:
        shape = f"{{{wrapper}: {{...}}}}" if wrapper else "direct server map"
        c.note(f".mcp.json ok ({shape}, {len(servers)} server(s))")
    return c


def check_dead_files(root):
    """Flag zero-byte or whitespace-only files under skills/ (advisory)."""
    c = Collector()
    sk = root / "skills"
    if not sk.is_dir():
        c.note("no skills/ directory")
        return c
    keep = {".gitkeep", ".keep"}
    flagged = 0
    scanned = 0
    for f in sorted(sk.rglob("*")):
        if not f.is_file() or f.name in keep:
            continue
        scanned += 1
        try:
            empty = f.stat().st_size == 0 or not f.read_text(encoding="utf-8", errors="ignore").strip()
        except OSError:
            continue
        if empty:
            flagged += 1
            c.finding("PI-D001", "warn", f"empty file under skills/: {f.relative_to(root)}",
                      "remove the file or give it content", str(f.relative_to(root)))
    if not flagged:
        c.note(f"no empty files under skills/ ({scanned} files scanned)")
    return c


CHECKS = [
    ("Manifests parse & agree", check_manifests),
    ("Skill frontmatter", check_frontmatter),
    ("Body budget", check_body_budget),
    ("Reference integrity", check_reference_integrity),
    ("Codex per-skill interface", check_openai_interface),
    ("Claude Code commands", check_commands),
    ("Parity", check_parity),
    ("Assets", check_assets),
    ("Hook health", check_hooks),
    (".mcp.json shape", check_mcp),
    ("Dead / empty files", check_dead_files),
]


def run(target):
    """Return (results, findings). results preserves the legacy per-check shape;
    findings is the flat cross-check diagnostic feed."""
    results = []
    findings = []
    for name, fn in CHECKS:
        try:
            c = fn(target)
            ok, messages, check_findings = c.ok, c.messages, c.findings
        except Exception as e:
            ok = False
            msg = f"check crashed: {e}"
            messages = [f"PI-Z001 [error] {msg}"]
            check_findings = [{
                "code": "PI-Z001", "severity": "error", "path": "",
                "message": msg, "fix": "file a bug against validate.py",
            }]
        for f in check_findings:
            f["check"] = name
            findings.append(f)
        results.append({"name": name, "ok": ok, "messages": messages})
    return results, findings


def main():
    args = sys.argv[1:]
    as_json = "--json" in args
    positional = [a for a in args if not a.startswith("-")]
    target = Path(positional[0]).resolve() if positional else REPO
    if not (target / "skills").is_dir() and not (target / ".codex-plugin").is_dir() \
            and not (target / ".claude-plugin").is_dir():
        print(f"error: {target} does not look like a plugin root "
              f"(no skills/, .codex-plugin/, or .claude-plugin/)", file=sys.stderr)
        return 2
    results, findings = run(target)
    passed = sum(1 for r in results if r["ok"])
    total = len(results)
    n_err = sum(1 for f in findings if f["severity"] == "error")
    n_warn = sum(1 for f in findings if f["severity"] == "warn")
    if as_json:
        summary = f"PASS {passed}/{total}" if passed == total else f"FAIL: {total - passed}"
        print(json.dumps({
            "target": str(target),
            "results": results,
            "passed": passed,
            "total": total,
            "summary": summary,
            "findings": findings,
        }, indent=2))
    else:
        if target != REPO:
            print(f"target: {target}\n")
        for r in results:
            print(f"[{'PASS' if r['ok'] else 'FAIL'}] {r['name']}")
            for m in r["messages"]:
                print(f"       - {m}")
        print()
        tail = f" ({n_warn} warn)" if n_warn else ""
        if passed == total:
            print(f"PASS {passed}/{total}{tail}")
        else:
            print(f"FAIL: {n_err} error finding(s) across {total - passed} check(s) "
                  f"({passed}/{total} checks passed){tail}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
