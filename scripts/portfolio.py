#!/usr/bin/env python3
"""Portfolio sweep — score every local plugin SOURCE tree, rank fix-first.

Stdlib only. Imports score.py as a module.
  python3 scripts/portfolio.py                 # human leaderboard
  python3 scripts/portfolio.py --json
  python3 scripts/portfolio.py --md
  python3 scripts/portfolio.py --state-dir DIR  # where score history is persisted
  python3 scripts/portfolio.py selftest         # deterministic temp fixtures

Enumerates plugin sources under ~/.codex/plugins + ~/.claude/plugins (each dir
holding .codex-plugin/plugin.json or .claude-plugin/plugin.json), NEVER scoring
read-only cache/ installs. Ranks a "fix-first" leaderboard by low auto-score
(x usage when a usage cache is available, else just low score) and persists
per-plugin score history to a state dir so the delta since the last sweep (the
slow-rot trajectory) is visible.
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import score  # noqa: E402  (score.py lives beside this file)

DEFAULT_SOURCE_ROOTS = ["~/.codex/plugins", "~/.claude/plugins"]
DEFAULT_STATE_DIRS = ["~/.codex/cache", "~/.claude/cache"]
HISTORY_FILE = "plugin-improver-portfolio.json"


def is_plugin_root(p):
    return (p / ".codex-plugin" / "plugin.json").is_file() or \
           (p / ".claude-plugin" / "plugin.json").is_file()


def enumerate_sources(roots):
    """Yield plugin source dirs under each root, skipping cache/ and dot dirs."""
    found = []
    for root in roots:
        root = Path(os.path.expanduser(root))
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            if child.name == "cache" or child.name.startswith("."):
                continue
            if is_plugin_root(child):
                found.append(child)
    # de-dupe by resolved path (same source reachable via two roots)
    seen, out = set(), []
    for p in found:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            out.append(p)
    return out


def plugin_name(root):
    for rel in (".codex-plugin/plugin.json", ".claude-plugin/plugin.json"):
        p = root / rel
        if p.is_file():
            try:
                return json.loads(p.read_text(encoding="utf-8")).get("name") or root.name
            except Exception:
                pass
    return root.name


def load_usage(state_dir):
    """Best-effort usage lookup: {skill_name: refs} from a curator usage cache,
    if one exists in the state dir. Absent by default -> ranking by score only."""
    if not state_dir:
        return {}
    for fn in ("skill-curator-usage.json", "skill-curator-usage-claude.json"):
        p = Path(state_dir) / fn
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                agg = data.get("aggregate", data)
                if isinstance(agg, dict):
                    return {k: (v.get("refs", 0) if isinstance(v, dict) else v)
                            for k, v in agg.items()}
            except Exception:
                pass
    return {}


def plugin_usage(root, usage):
    """Sum usage refs across the plugin's skills (0 when no usage data)."""
    if not usage:
        return 0
    total = 0
    for d in score.iter_skill_dirs(root):
        total += usage.get(d.name, 0)
    return total


def load_history(state_dir):
    if not state_dir:
        return {}
    p = Path(state_dir) / HISTORY_FILE
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_history(state_dir, history):
    if not state_dir:
        return False
    try:
        Path(state_dir).mkdir(parents=True, exist_ok=True)
        (Path(state_dir) / HISTORY_FILE).write_text(
            json.dumps(history, indent=2), encoding="utf-8")
        return True
    except Exception as e:
        print(f"warning: could not persist history: {e}", file=sys.stderr)
        return False


def resolve_state_dir(explicit):
    if explicit:
        return os.path.expanduser(explicit)
    for cand in DEFAULT_STATE_DIRS:
        c = os.path.expanduser(cand)
        if os.path.isdir(c):
            return c
    return None


def sweep(roots, state_dir, persist=True):
    sources = enumerate_sources(roots)
    usage = load_usage(state_dir)
    history = load_history(state_dir)
    rows = []
    for src in sources:
        result = score.score(src)
        auto = result["total"]["auto"]
        mx = result["total"]["max"]
        name = plugin_name(src)
        key = str(src.resolve())
        u = plugin_usage(src, usage)
        prev = history.get(key, {})
        prev_auto = prev.get("auto")
        delta = round(auto - prev_auto, 1) if isinstance(prev_auto, (int, float)) else None
        gap = mx - auto
        # fix-first weight: gap x (1 + usage). Absent usage -> rank by gap alone.
        rank_weight = gap * (1 + u)
        rows.append({
            "name": name, "path": key, "auto": auto, "max": mx,
            "gap": round(gap, 1), "usage": u, "delta": delta,
            "rank_weight": round(rank_weight, 1),
            "dimensions": {k: v["auto"] for k, v in result["dimensions"].items()},
        })
    rows.sort(key=lambda r: (-r["rank_weight"], r["auto"], r["name"]))
    if persist and state_dir:
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        for r in rows:
            history[r["path"]] = {"auto": r["auto"], "name": r["name"], "at": stamp}
        save_history(state_dir, history)
    return {"count": len(rows), "state_dir": state_dir, "rows": rows}


def render_table(res):
    lines = [f"portfolio sweep — {res['count']} plugin source(s)"]
    if res["state_dir"]:
        lines.append(f"state dir: {res['state_dir']}")
    lines.append("")
    lines.append(f"{'#':>2}  {'plugin':<24} {'auto':>6} {'max':>4} {'gap':>5} {'usage':>6} {'delta':>6}")
    lines.append("-" * 60)
    for i, r in enumerate(res["rows"], 1):
        delta = "" if r["delta"] is None else f"{r['delta']:+}"
        lines.append(f"{i:>2}  {r['name'][:24]:<24} {r['auto']:>6} {r['max']:>4} "
                     f"{r['gap']:>5} {r['usage']:>6} {delta:>6}")
    if not res["rows"]:
        lines.append("(no plugin sources found)")
    lines.append("")
    lines.append("fix-first: top of the list has the largest score gap (x usage when known).")
    return "\n".join(lines)


def render_md(res):
    lines = [f"# Portfolio sweep — {res['count']} plugin source(s)"]
    if res["state_dir"]:
        lines.append(f"\nState dir: `{res['state_dir']}`")
    lines.append("\n| # | Plugin | Auto | Max | Gap | Usage | Δ since last |")
    lines.append("|---:|---|---:|---:|---:|---:|---:|")
    for i, r in enumerate(res["rows"], 1):
        delta = "" if r["delta"] is None else f"{r['delta']:+}"
        lines.append(f"| {i} | {r['name']} | {r['auto']} | {r['max']} | "
                     f"{r['gap']} | {r['usage']} | {delta} |")
    if not res["rows"]:
        lines.append("| — | (no plugin sources found) | | | | | |")
    return "\n".join(lines)


# ---------- selftest ----------

def _make_fixtures(base):
    """Two fake plugin sources + a cache/ dir that must be skipped."""
    root = base / "plugins"
    # good plugin (top scorer)
    score._excellent(root / "good-plugin")
    # weak plugin (floors the fix-first ranking)
    score._poor(root / "broken-plugin")
    # a cache dir that must NOT be scored
    score._excellent(root / "cache" / "some-mkt" / "cached-plugin" / "1.0.0")
    # a non-plugin dir that must be ignored
    (root / "not-a-plugin").mkdir(parents=True, exist_ok=True)
    (root / "not-a-plugin" / "README.md").write_text("nope", encoding="utf-8")
    return root


def selftest():
    failures = []
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        root = _make_fixtures(base)
        state = base / "state"
        state.mkdir()

        res = sweep([str(root)], str(state), persist=True)
        names = [r["name"] for r in res["rows"]]
        paths = [r["path"] for r in res["rows"]]
        checks = [
            ("finds exactly 2 sources (cache + non-plugin skipped)", res["count"] == 2),
            ("cache plugin not scored", "cached-plugin" not in names),
            ("broken ranks before good (fix-first)", paths and paths[0].endswith("broken-plugin")),
            ("history persisted", (state / HISTORY_FILE).is_file()),
            ("first sweep has no delta", all(r["delta"] is None for r in res["rows"])),
        ]
        for label, ok in checks:
            if not ok:
                failures.append(f"{label} (names={names})")

        # Second sweep should surface deltas from persisted history (0.0 here, unchanged).
        res2 = sweep([str(root)], str(state), persist=True)
        if not all(r["delta"] == 0.0 for r in res2["rows"]):
            failures.append(f"second sweep deltas not 0.0 (got {[r['delta'] for r in res2['rows']]})")

    if failures:
        print("SELFTEST FAILED:")
        for f in failures:
            print("  - " + f)
        return 1
    print("portfolio.py selftest: OK")
    return 0


# ---------- cli ----------

def main(argv):
    args = argv[1:]
    if args and args[0] == "selftest":
        return selftest()
    as_json = "--json" in args
    as_md = "--md" in args
    state_arg = None
    roots = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--state-dir":
            if i + 1 >= len(args):
                print("error: --state-dir requires a value", file=sys.stderr)
                return 2
            state_arg = args[i + 1]; i += 2; continue
        if a.startswith("-"):
            i += 1; continue
        roots.append(a); i += 1
    roots = roots or DEFAULT_SOURCE_ROOTS
    state_dir = resolve_state_dir(state_arg)
    res = sweep(roots, state_dir, persist=True)
    if as_json:
        print(json.dumps(res, indent=2))
    elif as_md:
        print(render_md(res))
    else:
        print(render_table(res))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
