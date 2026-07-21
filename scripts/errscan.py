#!/usr/bin/env python3
"""errscan: mine session logs for RUNTIME error & health signals per plugin/skill.

Companion to skill-curator's usage mining (curator.py build_usage): that tool
mines the SAME session logs for USAGE; this one mines them for FAILURES, which
no tool does today. Defensively scans line-delimited JSONL transcripts under
~/.claude/projects/ (Claude Code) and ~/.codex/sessions/ (Codex) and aggregates
failure signals so a plugin author sees what is actually breaking:
  hook_missing : "Hook script appears to be missing" / hook path not found
  hook_block   : PreToolUse/PostToolUse/Stop hook blocked/denied/non-zero exit
  tool_error   : tool_use result is_error / non-zero exec / exception
  skill_error  : a skill invoked then erroring, or "skill not found"

Each signal is attributed to a plugin and/or skill when the line allows it (a
Skill `"skill"` field, a skills/<name>/ path, an mcp plugin tool name, or a
plugin path under a plugins dir); the rest go to an "unattributed" bucket keyed
by category. Incremental mtime+size cache (like build_usage) means re-runs only
scan changed files. Sample snippets are hard-truncated (<=200 chars) and common
API-key shapes redacted, since logs can contain secrets.

stdlib only. Subcommands: (default report), selftest.
"""
import argparse
import json
import os
import re
import sys
import time

CACHE_DEFAULT = "~/.codex/cache/errscan-cache.json"
SAMPLE_MAX = 200

# Only JSON-parse lines that may carry a relevant signal or map entry; the vast
# majority of transcript lines (reasoning, token counts, plain prose) are skipped
# cheaply. Keeps a first (uncached) scan of GB-scale logs bounded.
HINT_RE = re.compile(
    rb"tool_use|tool_result|function_call|is_error|exec_command_end"
    rb'|"skill"|Hook script|call_id|hookEventName')

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")

# --- attribution regexes ----------------------------------------------------
# plugin dir: the path component immediately before a known plugin subdir, after
# a literal 'plugins/' (optionally a 'cache/' and/or a marketplace level).
PLUGIN_PATH_RE = re.compile(
    r"plugins/(?:cache/)?(?:[\w.@+-]+/)*?([\w.@+-]+)/"
    r"(?:skills|hooks|commands|agents|\.claude-plugin|\.codex-plugin)/")
SKILL_PATH_RE = re.compile(r"skills/([\w-]+)/(?:SKILL\.md|scripts|references)")
SKILL_FIELD_RE = re.compile(r'"skill"\s*:\s*"([\w :./-]{2,80})"')
# mcp tool naming: mcp__plugin_<plugin>_<server>__<tool>  or  mcp__<server>__<tool>
MCP_PLUGIN_RE = re.compile(r"^mcp__plugin_([\w-]+?)_[\w-]+__")

# --- error text signals (applied only to OUTCOME text, never prose) ---------
HOOK_MISSING_RE = re.compile(
    r"[Hh]ook script appears to be missing"
    r"|[Hh]ook\b[^\n]{0,40}\b(?:is missing|not found|does not exist)")
HOOK_BLOCK_RE = re.compile(
    r"(?:PreToolUse|PostToolUse|Stop|SubagentStop|UserPromptSubmit)[^\n]{0,40}"
    r"hook[^\n]{0,60}(?:blocked|denied|failed|non-zero|exit code)"
    r"|hook[^\n]{0,40}(?:blocked|denied) (?:the|this) (?:tool|operation|call)")
SKILL_ERR_RE = re.compile(
    r"[Ss]kill[^\n]{0,30}(?:not found|does not exist|unknown skill|failed to load)"
    r"|[Nn]o such skill")
EXIT_NONZERO_RE = re.compile(
    r"[Ee]xit code (?!0\b)\d+"
    r"|command not found|No such file or directory"
    r"|Traceback \(most recent call last\)")

# --- secret redaction (applied to every emitted sample) ---------------------
SECRET_RES = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{12,}"),
    # OpenAI (sk-...), Stripe (sk_live_.../pk_test_...): hyphen OR underscore
    re.compile(r"\b(?:sk|rk|pk)[-_][A-Za-z0-9][A-Za-z0-9_-]{15,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{12,}"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{16,}"),
    re.compile(r"\b[A-Fa-f0-9]{40,}\b"),           # long hex blob
    re.compile(r"\b[A-Za-z0-9+/]{50,}={0,2}"),     # long base64 blob
]


def redact(text):
    for rx in SECRET_RES:
        text = rx.sub("[REDACTED]", text)
    return text


def sample_of(text):
    """One-line, secret-redacted, hard-truncated representative snippet."""
    s = re.sub(r"\s+", " ", str(text)).strip()
    s = redact(s)
    if len(s) > SAMPLE_MAX:
        s = s[:SAMPLE_MAX] + "…"
    return s


def date_from(obj, fallback):
    ts = obj.get("timestamp") or (obj.get("payload") or {}).get("timestamp")
    if isinstance(ts, str):
        m = DATE_RE.search(ts)
        if m:
            return m.group(1)
    return fallback


def norm_skill(raw):
    """'plugin-improver:plugin-audit' -> ('plugin-improver', 'plugin-audit')."""
    raw = str(raw).strip()
    if ":" in raw:
        plug, skill = raw.rsplit(":", 1)
        plug = plug.strip() or None
    else:
        plug, skill = None, raw
    skill = skill.strip().lower().replace(" ", "-")
    return plug, (skill or None)


def attribute(text, linked):
    """Return (plugin, skill) best-effort from linked tool_use + outcome text."""
    plugin = linked.get("plugin")
    skill = linked.get("skill")
    if not (plugin and skill):
        m = SKILL_FIELD_RE.search(text)
        if m:
            p, s = norm_skill(m.group(1))
            plugin = plugin or p
            skill = skill or s
    if not skill:
        m = SKILL_PATH_RE.search(text)
        if m:
            skill = m.group(1)
    if not plugin:
        m = PLUGIN_PATH_RE.search(text)
        if m:
            plugin = m.group(1)
    return plugin, skill


def categorize(text, is_error, linked_tool):
    """Classify outcome text into a category, or None if it is not a failure."""
    if HOOK_MISSING_RE.search(text):
        return "hook_missing"
    if HOOK_BLOCK_RE.search(text):
        return "hook_block"
    if SKILL_ERR_RE.search(text):
        return "skill_error"
    if is_error and linked_tool == "Skill":
        return "skill_error"
    if is_error or EXIT_NONZERO_RE.search(text):
        return "tool_error"
    return None


def _emit(sigs, cat, plugin, skill, date, text):
    sigs.append({"cat": cat, "plugin": plugin, "skill": skill,
                 "date": date, "sample": sample_of(text)})


# --- per-record scanning ----------------------------------------------------

def _content_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for it in content:
            if isinstance(it, dict):
                parts.append(it.get("text") or it.get("content") or "")
            else:
                parts.append(str(it))
        return " ".join(str(p) for p in parts)
    if isinstance(content, dict):
        return content.get("text") or content.get("content") or json.dumps(content)
    return "" if content is None else str(content)


def scan_claude_record(obj, toolmap, fallback_date, sigs):
    msg = obj.get("message")
    if not isinstance(msg, dict):
        return
    date = date_from(obj, fallback_date)
    content = msg.get("content")
    if not isinstance(content, list):
        return
    for it in content:
        if not isinstance(it, dict):
            continue
        t = it.get("type")
        if t == "tool_use":
            name = str(it.get("name") or "")
            rec = {"tool": name, "skill": None, "plugin": None}
            if name == "Skill":
                p, s = norm_skill((it.get("input") or {}).get("skill", ""))
                rec["skill"], rec["plugin"] = s, p
            else:
                m = MCP_PLUGIN_RE.match(name)
                if m:
                    rec["plugin"] = m.group(1)
            if it.get("id"):
                toolmap[it["id"]] = rec
        elif t == "tool_result":
            is_err = bool(it.get("is_error"))
            text = _content_text(it.get("content"))
            linked = toolmap.get(it.get("tool_use_id"), {})
            cat = categorize(text, is_err, linked.get("tool"))
            if not cat:
                continue
            plugin, skill = attribute(text, linked)
            _emit(sigs, cat, plugin, skill, date, text or linked.get("tool") or cat)


def scan_codex_record(obj, toolmap, fallback_date, sigs):
    pl = obj.get("payload") if isinstance(obj.get("payload"), dict) else obj
    ptype = pl.get("type")
    date = date_from(obj, fallback_date)
    if ptype in ("function_call", "custom_tool_call", "local_shell_call"):
        cid = pl.get("call_id") or pl.get("id")
        name = str(pl.get("name") or "")
        rec = {"tool": name, "skill": None, "plugin": None}
        m = MCP_PLUGIN_RE.match(name)
        if m:
            rec["plugin"] = m.group(1)
        if cid:
            toolmap[cid] = rec
    elif ptype in ("function_call_output", "custom_tool_call_output"):
        out = pl.get("output")
        is_err = False
        if isinstance(out, dict):
            meta = out.get("metadata") or {}
            code = meta.get("exit_code")
            is_err = isinstance(code, int) and code != 0
            text = _content_text(out.get("output") if "output" in out else out)
        else:
            text = _content_text(out)
        linked = toolmap.get(pl.get("call_id"), {})
        cat = categorize(text, is_err, linked.get("tool"))
        if cat:
            plugin, skill = attribute(text, linked)
            _emit(sigs, cat, plugin, skill, date, text or cat)
    elif ptype == "exec_command_end":
        # Codex shell completions arrive as a sibling event_msg (NOT
        # function_call_output); this record carries the real exit code + stderr.
        code = pl.get("exit_code")
        is_err = isinstance(code, int) and code != 0
        text = _content_text(pl.get("stderr") or pl.get("aggregated_output")
                             or pl.get("formatted_output") or pl.get("stdout"))
        linked = toolmap.get(pl.get("call_id"), {})
        cat = categorize(text, is_err, linked.get("tool"))
        if cat:
            plugin, skill = attribute(text, linked)
            _emit(sigs, cat, plugin, skill, date, text or cat)
    elif ptype in ("error", "stream_error"):
        text = _content_text(pl.get("message") or pl)
        _emit(sigs, "tool_error", *attribute(text, {}), date, text)


def scan_file(path, ecosystem, fallback_date):
    """Return a list of raw signal dicts from one JSONL transcript. Never raises."""
    sigs, toolmap = [], {}
    try:
        f = open(path, "rb")
    except OSError:
        return sigs
    with f:
        for raw in f:
            if not HINT_RE.search(raw):
                continue
            try:
                obj = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(obj, dict):
                continue
            try:
                if ecosystem == "codex":
                    scan_codex_record(obj, toolmap, fallback_date, sigs)
                else:
                    scan_claude_record(obj, toolmap, fallback_date, sigs)
            except Exception:  # one weird record must not kill the file
                continue
    return sigs


def collapse(sigs):
    """Collapse a file's signals to one entry per (kind,target,cat): count + newest sample."""
    grouped = {}
    for s in sigs:
        if s["skill"]:
            kind, target = "skill", s["skill"]
        elif s["plugin"]:
            kind, target = "plugin", s["plugin"]
        else:
            kind, target = "unattributed", s["cat"]
        key = (kind, target, s["cat"], s["plugin"] or "")
        g = grouped.get(key)
        if g is None:
            grouped[key] = {"kind": kind, "target": target,
                            "plugin": s["plugin"], "skill": s["skill"],
                            "cat": s["cat"], "count": 1,
                            "date": s["date"], "sample": s["sample"]}
        else:
            g["count"] += 1
            if (s["date"] or "") >= (g["date"] or ""):
                g["date"], g["sample"] = s["date"], s["sample"]
            g["plugin"] = g["plugin"] or s["plugin"]
    return list(grouped.values())


# --- incremental cache + aggregation ----------------------------------------

def build_cache(roots, cache_path, rebuild=False):
    """roots: list of (dir, ecosystem). Returns (all_entries, stats)."""
    cache_path = os.path.expanduser(cache_path)
    old = {}
    if not rebuild and os.path.isfile(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                old = json.load(f).get("files", {})
        except (OSError, ValueError):
            old = {}
    files, scanned = {}, 0
    for root, eco in roots:
        root = os.path.expanduser(root)
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, names in os.walk(root):
            dirnames[:] = [d for d in dirnames if d != ".git"]
            for nm in names:
                if not nm.endswith(".jsonl"):
                    continue
                p = os.path.join(dirpath, nm)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                prev = old.get(p)
                if prev and prev.get("mtime") == st.st_mtime and \
                        prev.get("size") == st.st_size:
                    files[p] = prev
                    continue
                dm = DATE_RE.search(nm)
                fdate = dm.group(1) if dm else time.strftime(
                    "%Y-%m-%d", time.localtime(st.st_mtime))
                files[p] = {"mtime": st.st_mtime, "size": st.st_size, "eco": eco,
                            "entries": collapse(scan_file(p, eco, fdate))}
                scanned += 1
    try:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "files": files}, f)
    except OSError as e:
        print(f"warning: cache not written: {e}", file=sys.stderr)
    entries = []
    for rec in files.values():
        entries.extend(rec.get("entries", []))
    return entries, {"files": len(files), "scanned": scanned}


def aggregate(entries, plugin_filter=None):
    groups, unattributed = {}, {}
    for e in entries:
        if e["kind"] == "unattributed":
            u = unattributed.setdefault(e["cat"], {"count": 0, "date": None,
                                                   "sample": e["sample"]})
            u["count"] += e["count"]
            if (e["date"] or "") >= (u["date"] or ""):
                u["date"], u["sample"] = e["date"], e["sample"]
            continue
        if plugin_filter and plugin_filter not in (
                e["target"], e.get("plugin"), e.get("skill")):
            continue
        # key on (kind, plugin, name) so same-named skills in different plugins
        # never merge (and their owning plugin is never mis-locked)
        plug = e.get("plugin") or ""
        key = (e["kind"], plug, e["target"])
        display = (f"{plug}:{e['target']}" if e["kind"] == "skill" and plug
                   else e["target"])
        g = groups.get(key)
        if g is None:
            g = groups[key] = {"kind": e["kind"], "target": display,
                               "name": e["target"], "plugin": e.get("plugin"),
                               "cats": {}, "count": 0, "last_seen": None,
                               "sample": e["sample"]}
        g["cats"][e["cat"]] = g["cats"].get(e["cat"], 0) + e["count"]
        g["count"] += e["count"]
        if (e["date"] or "") >= (g["last_seen"] or ""):
            g["last_seen"], g["sample"] = e["date"], e["sample"]
    out = sorted(groups.values(),
                 key=lambda g: (-g["count"], g["kind"], g["target"]))
    unatt = None
    if not plugin_filter:
        unatt = {c: unattributed[c] for c in sorted(unattributed)}
    return out, unatt


# --- rendering --------------------------------------------------------------

def render_text(groups, unatt, stats):
    L = [f"errscan: {sum(g['count'] for g in groups)} attributed signal(s) "
         f"across {len(groups)} plugin/skill target(s); "
         f"{stats['files']} log files ({stats['scanned']} scanned)"]
    if not groups and not unatt:
        return "no error signals found"
    if groups:
        L.append("")
        L.append(f"{'TARGET':32} {'KIND':6} {'COUNT':>5}  {'LAST':10}  CATEGORIES")
        for g in groups:
            cats = ",".join(f"{k}:{v}" for k, v in sorted(g["cats"].items()))
            L.append(f"{g['target'][:32]:32} {g['kind']:6} {g['count']:>5}  "
                     f"{g['last_seen'] or '?':10}  {cats}")
            L.append(f"    e.g. {g['sample']}")
    if unatt:
        total = sum(u["count"] for u in unatt.values())
        L.append("")
        L.append(f"unattributed ({total}):")
        for cat, u in unatt.items():
            L.append(f"  {cat}: {u['count']} (last {u['date'] or '?'}) — {u['sample']}")
    return "\n".join(L)


def render_md(groups, unatt, stats):
    L = ["# errscan — runtime error & health report", "",
         f"- {sum(g['count'] for g in groups)} attributed signal(s), "
         f"{len(groups)} target(s)",
         f"- scanned {stats['scanned']} of {stats['files']} cached log file(s)", ""]
    if not groups and not unatt:
        L.append("No error signals found.")
        return "\n".join(L)
    if groups:
        L.append("## By plugin/skill")
        L.append("")
        L.append("| target | kind | count | last seen | categories |")
        L.append("|---|---|---|---|---|")
        for g in groups:
            cats = ", ".join(f"{k}: {v}" for k, v in sorted(g["cats"].items()))
            L.append(f"| `{g['target']}` | {g['kind']} | {g['count']} | "
                     f"{g['last_seen'] or '?'} | {cats} |")
        L.append("")
        L.append("### Representative samples")
        L.append("")
        for g in groups:
            L.append(f"- **{g['target']}** — {g['sample']}")
        L.append("")
    if unatt:
        L.append("## Unattributed (by category)")
        L.append("")
        for cat, u in unatt.items():
            L.append(f"- **{cat}**: {u['count']} (last {u['date'] or '?'}) — "
                     f"{u['sample']}")
    return "\n".join(L)


def to_json(groups, unatt, stats):
    return json.dumps({"stats": stats, "targets": groups,
                       "unattributed": unatt or {}}, indent=2)


# --- selftest ---------------------------------------------------------------

def selftest():
    import tempfile
    ok = True

    def check(cond, msg):
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + msg)
        ok = ok and cond

    tmp = tempfile.mkdtemp(prefix="errscan-selftest-")
    claude_dir = os.path.join(tmp, "claude", "projects", "-proj")
    codex_dir = os.path.join(tmp, "codex", "sessions", "2026", "07", "20")
    os.makedirs(claude_dir)
    os.makedirs(codex_dir)
    cache = os.path.join(tmp, "cache.json")

    # Claude Code transcript: a Skill invocation that errors, a hook-missing
    # tool_result attributed by plugin path, a plain tool error, and a secret.
    claude_lines = [
        {"type": "assistant", "timestamp": "2026-07-20T10:00:00Z",
         "message": {"role": "assistant", "content": [
             {"type": "tool_use", "id": "t1", "name": "Skill",
              "input": {"skill": "myplugin:broken-skill"}}]}},
        {"type": "user", "timestamp": "2026-07-20T10:00:01Z",
         "message": {"role": "user", "content": [
             {"type": "tool_result", "tool_use_id": "t1", "is_error": True,
              "content": "Skill failed to load: broken-skill token sk-ABCDEF0123456789ABCDEF"}]}},
        {"type": "user", "timestamp": "2026-07-19T09:00:00Z",
         "message": {"role": "user", "content": [
             {"type": "tool_result", "tool_use_id": "t9", "is_error": True,
              "content": "PreToolUse:Bash hook blocked the tool: /Users/x/.claude/plugins/mkt/harness-self-improvement/hooks/guard.py exit code 2"}]}},
        {"type": "user", "timestamp": "2026-07-18T09:00:00Z",
         "message": {"role": "user", "content": [
             {"type": "tool_result", "tool_use_id": "t8", "is_error": True,
              "content": "Exit code 1\nls: nope: No such file or directory"}]}},
    ]
    with open(os.path.join(claude_dir, "s.jsonl"), "w", encoding="utf-8") as f:
        for o in claude_lines:
            f.write(json.dumps(o) + "\n")
        f.write("{ this is not valid json\n")  # malformed line must not crash

    # Codex session: a function_call_output with a hook-missing message, plus a
    # non-zero exec_command_end (the sibling event that carries shell exit codes).
    codex_lines = [
        {"type": "response_item", "timestamp": "2026-07-20T11:00:00Z",
         "payload": {"type": "function_call", "call_id": "c1", "name": "shell"}},
        {"type": "response_item", "timestamp": "2026-07-20T11:00:01Z",
         "payload": {"type": "function_call_output", "call_id": "c1",
                     "output": "Hook script appears to be missing: "
                               "~/.codex/plugins/harness-self-improvement/hooks/x.sh"}},
        {"type": "event_msg", "timestamp": "2026-07-20T11:05:00Z",
         "payload": {"type": "exec_command_end", "call_id": "c2", "exit_code": 1,
                     "stderr": "sed: ~/.agents/skills/etsyhero/SKILL.md: "
                               "No such file or directory", "stdout": ""}},
    ]
    with open(os.path.join(codex_dir, "r.jsonl"), "w", encoding="utf-8") as f:
        for o in codex_lines:
            f.write(json.dumps(o) + "\n")

    roots = [(os.path.join(tmp, "claude", "projects"), "claude"),
             (os.path.join(tmp, "codex", "sessions"), "codex")]
    entries, stats = build_cache(roots, cache, rebuild=True)
    groups, unatt = aggregate(entries)
    by_name = {g["name"]: g for g in groups}

    check(stats["scanned"] == 2, "scanned exactly 2 files")
    check("broken-skill" in by_name, "skill attribution (broken-skill)")
    check(by_name.get("broken-skill", {}).get("target") == "myplugin:broken-skill",
          "skill target qualified by owning plugin")
    check(by_name.get("broken-skill", {}).get("cats", {}).get("skill_error") == 1,
          "broken-skill -> skill_error x1")
    check("harness-self-improvement" in by_name,
          "plugin attribution from hook path")
    hsi = by_name.get("harness-self-improvement", {}).get("cats", {})
    check(hsi.get("hook_block") == 1, "harness-self-improvement -> hook_block x1")
    check(hsi.get("hook_missing") == 1,
          "harness-self-improvement -> hook_missing x1 (codex)")
    check("etsyhero" in by_name and
          by_name["etsyhero"]["cats"].get("tool_error") == 1,
          "exec_command_end non-zero exit -> etsyhero tool_error x1")
    check(unatt.get("tool_error", {}).get("count") == 1,
          "unattributed tool_error x1 (bare exit-1)")
    # secret redaction: the raw sk-... token must never appear in any sample
    blob = json.dumps(groups) + json.dumps(unatt)
    check("sk-ABCDEF0123456789ABCDEF" not in blob and "[REDACTED]" in blob,
          "secret token redacted in emitted sample")
    # incremental cache: a second pass scans 0 files but yields identical result
    entries2, stats2 = build_cache(roots, cache, rebuild=False)
    g2, _ = aggregate(entries2)
    check(stats2["scanned"] == 0, "second pass uses cache (0 scanned)")
    check(len(g2) == len(groups), "cached aggregation matches fresh")
    # --plugin filter
    fg, fu = aggregate(entries, plugin_filter="myplugin")
    check(any(g["name"] == "broken-skill" for g in fg) and fu is None,
          "--plugin filter matches by owning plugin")

    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


# --- cli --------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Mine session logs for runtime error/health signals per plugin/skill.")
    ap.add_argument("subcommand", nargs="?", default="report",
                    choices=["report", "selftest"],
                    help="report (default) scans logs; selftest runs deterministic checks")
    ap.add_argument("--plugin", metavar="NAME",
                    help="filter to one plugin or skill name")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    ap.add_argument("--md", action="store_true", help="emit Markdown")
    ap.add_argument("--claude-root", default="~/.claude",
                    help="Claude Code root (contains projects/); default ~/.claude")
    ap.add_argument("--codex-root", default="~/.codex",
                    help="Codex root (contains sessions/); default ~/.codex")
    ap.add_argument("--cache", default=CACHE_DEFAULT,
                    help=f"state cache path (default {CACHE_DEFAULT})")
    ap.add_argument("--rebuild", action="store_true",
                    help="ignore the cache and rescan every file")
    args = ap.parse_args(argv)

    if args.subcommand == "selftest":
        return selftest()

    roots = [(os.path.join(os.path.expanduser(args.claude_root), "projects"), "claude"),
             (os.path.join(os.path.expanduser(args.codex_root), "sessions"), "codex")]
    entries, stats = build_cache(roots, args.cache, rebuild=args.rebuild)
    groups, unatt = aggregate(entries, plugin_filter=args.plugin)

    if args.json:
        print(to_json(groups, unatt, stats))
    elif args.md:
        print(render_md(groups, unatt, stats))
    else:
        print(render_text(groups, unatt, stats))
    return 0


if __name__ == "__main__":
    sys.exit(main())
