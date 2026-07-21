#!/usr/bin/env python3
"""skill-curator v3: deterministic skill+plugin inventory scanner, economist, and ledger.

Detects skill sprawl across every trigger surface:
  - flat skills roots (~/.codex/skills, ~/.claude/skills)
  - installed plugin caches (each plugin's skills/ occupy trigger surface too)
  - duplicate surfaces: the same skill name shipped in 2+ places
    (classified shared-symlink / identical-copies / diverged-copies)
  - name families, near-duplicate descriptions, dead dirs, unresolved symlinks
  - trigger collisions with noise controls (boilerplate stoplist, bigram
    requirement, quoted-phrase matches) reported as CLUSTERS, not O(n^2) pairs
  - context economics: trigger tokens (paid every session) vs invoke tokens,
    cost ranked against mined usage from BOTH ecosystems' session logs
      codex:  skills/<name>/SKILL.md refs in ~/.codex/sessions
      claude: Skill-tool calls + SKILL.md refs in ~/.claude/projects
  - a curation ledger: findings get stable fingerprints; decisions
    (accept/reject/snooze) persist so runs surface only what's new
  - plugin-level sprawl (v3): local plugin SOURCES (~/.codex/plugins/<name>)
    vs installed cache copies — source<->cache version drift, the same plugin
    installed from 2+ marketplaces, and stale extra cached versions

plugin-eval integration (openai-curated plugin):
  - emit-metric-pack: manifest so `plugin-eval analyze --metric-pack` merges
    inventory-wide findings into any single-skill evaluation
  - probes: routing probes + benchmark scenarios + a routing sheet, so trigger
    confusion is measured behaviorally; probes-grade builds the confusion matrix

stdlib only. Subcommands: report, check, decide, decisions, archive, restore,
probes, probes-grade, emit-metric-pack, metric-pack-emit, selftest.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time

# --- lexical machinery ------------------------------------------------------

STOP = {
    # v1 stoplist
    "the", "and", "for", "use", "when", "this", "that", "with", "not",
    "skill", "skills", "user", "users", "also", "any", "all", "are",
    "you", "your", "can", "will", "into", "from", "such", "via", "etc",
    "trigger", "triggers", "asks", "wants", "like", "even", "only",
    # v2: skill-description boilerplate that carried zero routing signal
    # (observed: docx<->pdf "colliding" on files/whenever/create)
    "whenever", "asked", "asking", "mention", "mentions", "mentioned",
    "request", "requests", "requested", "requires", "needs", "need",
    "file", "files", "create", "creating", "created", "creates",
    "edit", "editing", "edits", "work", "working", "works",
    "task", "tasks", "says", "say", "saying", "covers", "cover",
    "including", "includes", "include", "involved", "involving",
    "existing", "new", "make", "makes", "making", "made",
    "one", "two", "way", "ways", "thing", "things", "them", "their",
    "its", "get", "gets", "using", "used", "uses", "see", "should",
    "would", "could", "may", "might", "must", "have", "has", "had",
    "been", "being", "then", "than", "these", "those", "some", "more",
    "most", "very", "just", "out", "off", "own", "does", "els",
    "primary", "input", "output", "wan", "there", "where", "which",
    "what", "who", "how", "why", "each", "per", "both", "either",
    "instead", "rather", "directly", "want", "help", "helps",
}
NAME_STOP = {"to", "the", "a", "an", "of", "core", "cli", "use", "learned", "my"}
WORD_RE = re.compile(r"[a-z]{3,}")
PHRASE_RE = re.compile(r"['‘’\"]([^'‘’\"]{8,70})['‘’\"]")
CHARS_PER_TOKEN = 4.0
PRUNE_DIRS = {
    ".git", "node_modules", "__pycache__", "fixtures", "tests", "test",
    ".plugin-eval", ".claude", ".codex", ".archive", "worktrees",
    ".worktrees", "dist", "build", ".venv", "venv",
}


def word_list(text):
    return WORD_RE.findall(text.lower())


def tokens(text):
    return {t for t in word_list(text) if t not in STOP}


def bigrams(text):
    ws = word_list(text)
    return {(a, b) for a, b in zip(ws, ws[1:])
            if a not in STOP and b not in STOP}


def phrases(text):
    return {p.strip().lower() for p in PHRASE_RE.findall(text)
            if len(WORD_RE.findall(p)) >= 2}


def name_tokens(name):
    return [t for t in re.split(r"[^a-z0-9]+", name.lower())
            if t and t not in NAME_STOP]


def est_tokens(chars):
    return int(round(chars / CHARS_PER_TOKEN))


def fingerprint(kind, key):
    h = hashlib.sha1((kind + "|" + key).encode("utf-8")).hexdigest()[:10]
    return f"{kind[:4]}-{h}"


# --- frontmatter ------------------------------------------------------------

FOLD_MARKERS = {">", ">-", ">+", "|", "|-", "|+"}


def parse_frontmatter(path):
    """Tolerant YAML-lite: top-level scalar keys, folded/literal blocks OK."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return {}
    m = re.match(r"\A---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return {}
    fields, key = {}, None
    for line in m.group(1).splitlines():
        km = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if km:
            key = km.group(1)
            val = km.group(2).strip()
            if val in FOLD_MARKERS:
                val = ""  # folded/literal block: value comes from continuations
            fields[key] = val.strip("\"'")
        elif key and line.startswith((" ", "\t")):
            fields[key] = (fields[key] + " " + line.strip().strip("\"'")).strip()
    return fields


# --- scanning ---------------------------------------------------------------

def _skill_record(name, path, surface, kind="dir", link_target=None):
    info = {
        "name": name, "path": path, "surface": surface, "kind": kind,
        "link_target": link_target, "resolved": os.path.isdir(path),
        "realpath": os.path.realpath(path) if os.path.exists(path) else path,
        "has_skill_md": False, "description": "", "desc_chars": 0,
        "body_chars": 0, "body_sha": None,
    }
    smd = os.path.join(path, "SKILL.md")
    if os.path.isfile(smd):
        info["has_skill_md"] = True
        fm = parse_frontmatter(smd)
        info["description"] = fm.get("description", "")
        info["desc_chars"] = len(info["description"])
        try:
            with open(smd, "rb") as f:
                body = f.read()
            info["body_chars"] = len(body)
            info["body_sha"] = hashlib.sha1(body).hexdigest()[:12]
        except OSError:
            pass
    return info


def scan_root(root):
    skills, root = [], os.path.expanduser(root)
    try:
        entries = sorted(os.listdir(root))
    except OSError as e:
        print(f"warning: cannot list {root}: {e}", file=sys.stderr)
        return skills
    for name in entries:
        if name.startswith("."):
            continue
        path = os.path.join(root, name)
        is_link = os.path.islink(path)
        if not is_link and not os.path.isdir(path):
            continue
        rec = _skill_record(
            name, path, f"root:{root}",
            "symlink" if is_link else "dir",
            os.readlink(path) if is_link else None)
        skills.append(rec)
    return skills


VERSIONISH_RE = re.compile(r"^(\d+[\w.+-]*|[0-9a-f]{6,40}|unknown|latest)$")


def scan_plugin_cache(cache_root):
    """Find <plugin>/skills/<skill>/SKILL.md under a plugin cache tree.

    Tolerates layouts with or without marketplace/version path levels.
    Multiple cached versions of one plugin: newest skills/ dir wins.
    """
    cache_root = os.path.expanduser(cache_root)
    found = {}  # (marketplace, plugin) -> (mtime, [records])
    if not os.path.isdir(cache_root):
        return []
    for dirpath, dirnames, _files in os.walk(cache_root):
        dirnames[:] = [d for d in dirnames if d not in PRUNE_DIRS]
        rel = os.path.relpath(dirpath, cache_root)
        if rel.count(os.sep) > 4:
            dirnames[:] = []
            continue
        if os.path.basename(dirpath) != "skills":
            continue
        dirnames[:] = []  # don't descend further via walk; we handle it
        plugin_dir = os.path.dirname(dirpath)
        plugin = os.path.basename(plugin_dir)
        hops = 0
        while (VERSIONISH_RE.match(plugin) and hops < 2 and
               os.path.dirname(plugin_dir) != cache_root and
               os.path.basename(os.path.dirname(plugin_dir))):
            plugin_dir = os.path.dirname(plugin_dir)
            plugin = os.path.basename(plugin_dir)
            hops += 1
        parts = rel.split(os.sep)
        marketplace = parts[0] if len(parts) > 1 else os.path.basename(cache_root)
        try:
            mtime = os.stat(dirpath).st_mtime
        except OSError:
            mtime = 0
        recs = []
        try:
            entries = sorted(os.listdir(dirpath))
        except OSError:
            continue
        for name in entries:
            spath = os.path.join(dirpath, name)
            if name.startswith(".") or not os.path.isdir(spath):
                continue
            if not os.path.isfile(os.path.join(spath, "SKILL.md")):
                continue
            recs.append(_skill_record(
                name, spath, f"plugin:{plugin}@{marketplace}", "plugin"))
        key = (marketplace, plugin)
        if recs and (key not in found or mtime > found[key][0]):
            found[key] = (mtime, recs)
    out = []
    for _mtime, recs in sorted(found.values(), key=lambda kv: kv[1][0]["surface"]):
        out.extend(recs)
    return out


def dedupe_mirrors(skills):
    """Drop plugin records from '<mkt>-remote' mirror caches.

    A remote mirror cache is not a live trigger surface: the installed copy
    (non-remote marketplace) is what loads. Mirrors are dropped entirely;
    where a mirror's body diverges from the installed copy (stale mirror) or
    a mirror has no installed sibling (remote-only, not installed), that is
    reported as an info note instead of a scored finding.
    """
    def mkt_of(s):
        return s["surface"].rsplit("@", 1)[1] if "@" in s["surface"] else None

    def plug_of(s):
        return s["surface"].split(":", 1)[1].rsplit("@", 1)[0]

    installed = {}  # (plugin@mkt, skill name) -> body_sha
    for s in skills:
        mkt = mkt_of(s)
        if s["kind"] == "plugin" and mkt and not mkt.endswith("-remote"):
            installed[(plug_of(s) + "@" + mkt, s["name"])] = s["body_sha"]
    kept, notes = [], {}
    for s in skills:
        mkt = mkt_of(s)
        if s["kind"] == "plugin" and mkt and mkt.endswith("-remote"):
            base = mkt[:-len("-remote")]
            key = plug_of(s) + "@" + base
            if (key, s["name"]) not in installed:
                notes.setdefault(key, set()).add("remote-only (not installed)")
            elif installed[(key, s["name"])] != s["body_sha"]:
                notes.setdefault(key, set()).add(
                    f"mirror diverges: {s['name']}")
            continue  # mirror records never count as surface
        kept.append(s)
    mirror_notes = [{"plugin": k, "notes": sorted(v)}
                    for k, v in sorted(notes.items())]
    return kept, mirror_notes


def gather_skills(roots, plugin_caches):
    skills = []
    for r in roots:
        skills.extend(scan_root(r))
    for c in plugin_caches:
        skills.extend(scan_plugin_cache(c))
    skills, mirror_notes = dedupe_mirrors(skills)
    gather_skills.last_mirror_notes = mirror_notes
    return skills


# --- plugin-level scanning (v3) ---------------------------------------------

PLUGIN_MANIFEST_DIRS = (".codex-plugin", ".claude-plugin")


def read_plugin_manifest(plugin_dir):
    """Return the plugin.json dict from .codex-plugin/ or .claude-plugin/, or None."""
    for mdir in PLUGIN_MANIFEST_DIRS:
        mpath = os.path.join(plugin_dir, mdir, "plugin.json")
        if os.path.isfile(mpath):
            try:
                with open(mpath, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
            except (OSError, ValueError):
                continue
    return None


def base_version(v):
    """Comparable core of a version string: strip build metadata and one 'v'."""
    v = re.sub(r"^[vV](?=\d)", "", str(v or "").strip())
    return v.split("+", 1)[0]


def scan_plugin_sources(source_root):
    """Find local plugin SOURCE trees: <root>/<plugin>/.{codex,claude}-plugin/plugin.json.

    Skips 'cache' (installed copies, scanned separately) and dot dirs.
    """
    out, root = [], os.path.expanduser(source_root)
    if not os.path.isdir(root):
        return out
    try:
        entries = sorted(os.listdir(root))
    except OSError:
        return out
    for name in entries:
        if name.startswith(".") or name == "cache":
            continue
        pdir = os.path.join(root, name)
        if not os.path.isdir(pdir):
            continue
        man = read_plugin_manifest(pdir)
        if man is not None:
            out.append({"name": str(man.get("name") or name), "path": pdir,
                        "version": str(man.get("version", ""))})
    return out


def scan_cache_plugins(cache_root):
    """Map installed plugins in a cache: (marketplace, plugin) -> version info.

    Expects <cache>/<marketplace>/<plugin>/<version>/ . A marketplace-less
    layout (<cache>/<plugin>/<version> where the version dir holds a manifest
    or skills/) is detected and keyed under the cache dir's own name. A plugin
    dir with no version-ish children records the version from its plugin.json.
    """
    found = {}
    root = os.path.expanduser(cache_root)
    if not os.path.isdir(root):
        return found
    root_label = os.path.basename(root.rstrip(os.sep)) or root

    def record(mkt, plug, pdir):
        versions, newest, newest_mtime = [], None, -1.0
        try:
            subs = sorted(os.listdir(pdir))
        except OSError:
            return
        for sub in subs:
            vdir = os.path.join(pdir, sub)
            if sub.startswith(".") or not os.path.isdir(vdir):
                continue
            if not VERSIONISH_RE.match(sub):
                continue
            versions.append(sub)
            try:
                mtime = os.stat(vdir).st_mtime
            except OSError:
                mtime = 0.0
            if mtime > newest_mtime:
                newest, newest_mtime = sub, mtime
        if not versions:
            man = read_plugin_manifest(pdir)
            if man is None:
                return
            v = str(man.get("version", "")) or "unknown"
            versions, newest, newest_mtime = [v], v, 0.0
        found[(mkt, plug)] = {"versions": sorted(versions), "newest": newest,
                              "newest_mtime": newest_mtime, "path": pdir}

    def looks_like_plugin(pdir):
        """True if pdir's version-ish children hold a manifest or skills/."""
        try:
            subs = sorted(os.listdir(pdir))
        except OSError:
            return False
        for sub in subs:
            vdir = os.path.join(pdir, sub)
            if sub.startswith(".") or not os.path.isdir(vdir):
                continue
            if VERSIONISH_RE.match(sub) and (
                    read_plugin_manifest(vdir) is not None or
                    os.path.isdir(os.path.join(vdir, "skills"))):
                return True
        return False

    try:
        mkts = sorted(os.listdir(root))
    except OSError:
        return found
    for mkt in mkts:
        mdir = os.path.join(root, mkt)
        if mkt.startswith(".") or not os.path.isdir(mdir):
            continue
        if looks_like_plugin(mdir):
            record(root_label, mkt, mdir)  # marketplace-less layout
            continue
        try:
            plugs = sorted(os.listdir(mdir))
        except OSError:
            continue
        for plug in plugs:
            pdir = os.path.join(mdir, plug)
            if plug.startswith(".") or not os.path.isdir(pdir):
                continue
            record(mkt, plug, pdir)
    return found


def merge_cache_maps(maps):
    """Merge per-root cache maps; same (mkt, plugin) in 2 roots unions versions."""
    out = {}
    for m in maps:
        for k, info in m.items():
            if k in out:
                versions = sorted(set(out[k]["versions"]) | set(info["versions"]))
                if info.get("newest_mtime", 0) >= out[k].get("newest_mtime", 0):
                    out[k] = dict(info)
                out[k]["versions"] = versions
            else:
                out[k] = dict(info)
    return out


def analyze_plugins(findings, sources, cache_map):
    """Add plugin-level findings: version drift, duplicate installs, stale caches."""
    drift, dups, stale = [], [], []
    by_name = {}
    for (mkt, plug), info in sorted(cache_map.items()):
        if mkt.endswith("-remote"):
            continue  # mirrors are not live install surfaces
        by_name.setdefault(plug, []).append((mkt, info))
    for plug, entries in sorted(by_name.items()):
        mkts = sorted({m for m, _ in entries})
        if len(mkts) > 1:
            # fp keyed on name only: adding a 3rd marketplace must not
            # resurface a rejected/snoozed decision as a "new" finding
            dups.append({"fp": fingerprint("pdup", plug),
                         "name": plug, "marketplaces": mkts})
        for mkt, info in entries:
            if len(info["versions"]) > 1:
                old = [v for v in info["versions"] if v != info["newest"]]
                stale.append({"fp": fingerprint("pstale", plug + "@" + mkt),
                              "name": plug, "marketplace": mkt,
                              "active": info["newest"], "stale_versions": old})
    src_by_name = {}
    for src in sorted(sources, key=lambda s: (s["name"], s["path"])):
        src_by_name.setdefault(src["name"], []).append(src)
    for name, group in sorted(src_by_name.items()):
        svs = []
        for s in group:
            bv = base_version(s["version"])
            if bv and bv not in ("unknown", "latest") and bv not in svs:
                svs.append(bv)
        if not svs:
            continue  # no meaningful source version -> no drift signal
        extra = "" if len(group) == 1 else f" (+{len(group) - 1} more copies)"
        for mkt, info in by_name.get(name, []):
            cv = base_version(info["newest"])
            if cv and cv not in ("unknown", "latest") and cv not in svs:
                drift.append({
                    "fp": fingerprint("pdrf", name + "@" + mkt),
                    "name": name, "marketplace": mkt,
                    "source_version": "/".join(svs),
                    "cache_version": info["newest"],
                    "source_path": group[0]["path"] + extra,
                    "note": "source and installed cache disagree; refresh the "
                            "install (or commit the source) so one truth wins"})
    findings["plugin_version_drift"] = drift
    findings["duplicate_plugins"] = dups
    findings["stale_plugin_caches"] = stale
    findings["plugin_source_count"] = len(sources)
    findings["plugin_install_count"] = len(by_name)


# --- analysis ---------------------------------------------------------------

def _edge_terms(rec):
    t = set(rec["shared_terms"])
    for bg in rec["shared_bigrams"]:
        t.update(bg.split())
    return t


def build_clusters(pair_recs):
    """Agglomerate collision pairs into topic clusters.

    NOT transitive union-find: an edge joins a cluster only if it overlaps a
    member AND shares >=2 terms with the cluster's term CORE (the intersection
    of its edges' terms). This keeps a skill that collides with two unrelated
    topics from chaining them into one mega-blob.
    """
    def strength(r):
        return (10 * len(r["shared_phrases"]) + 3 * len(r["shared_bigrams"])
                + len(r["shared_terms"]))

    clusters = []
    for rec in sorted(pair_recs, key=lambda r: (-strength(r), r["pair"])):
        members, terms = set(rec["pair"]), _edge_terms(rec)
        placed = False
        for c in clusters:
            if (members & c["members"]) and len(c["core"] & terms) >= 2:
                c["members"] |= members
                newcore = c["core"] & terms
                if len(newcore) >= 2:
                    c["core"] = newcore
                c["phrases"].update(rec["shared_phrases"])
                c["edges"] += 1
                placed = True
                break
        if not placed:
            clusters.append({"members": members, "core": terms,
                             "phrases": set(rec["shared_phrases"]), "edges": 1})
    return clusters


def analyze(skills, jaccard_min=0.55, family_min=3, desc_warn=1500):
    findings = {
        "families": [], "duplicate_surfaces": [], "near_dupes": [],
        "collision_clusters": [], "collision_pairs": [],
        "dead": [], "unresolved_links": [], "long_descriptions": [],
        "skill_count": len(skills),
        "surface_count": len({s["surface"] for s in skills}),
        "context_cost_chars": sum(s["desc_chars"] for s in skills),
        "context_cost_tokens": est_tokens(sum(s["desc_chars"] for s in skills)),
    }
    for s in skills:
        if s["kind"] == "symlink" and not s["resolved"]:
            findings["unresolved_links"].append(
                {"fp": fingerprint("link", s["name"]), "name": s["name"],
                 "target": s["link_target"],
                 "note": "target not visible from here; verify before treating as dead"})
        elif not s["has_skill_md"]:
            findings["dead"].append(
                {"fp": fingerprint("dead", s["name"]), "name": s["name"],
                 "path": s["path"]})
        if s["desc_chars"] > desc_warn:
            findings["long_descriptions"].append(
                {"fp": fingerprint("long", s["name"]), "name": s["name"],
                 "desc_chars": s["desc_chars"],
                 "est_tokens": est_tokens(s["desc_chars"])})

    # duplicate surfaces: same skill name in 2+ places
    by_name = {}
    for s in skills:
        by_name.setdefault(s["name"], []).append(s)
    for name, group in sorted(by_name.items()):
        if len(group) < 2:
            continue
        realpaths = {g["realpath"] for g in group}
        shas = {g["body_sha"] for g in group if g["body_sha"]}
        if len(realpaths) == 1:
            klass = "shared"  # symlinked single body; deliberate economy
        elif len(shas) <= 1:
            klass = "identical-copies"
        else:
            klass = "diverged-copies"
        findings["duplicate_surfaces"].append({
            "fp": fingerprint("dup", name + "|" +
                              "|".join(sorted(g["surface"] for g in group))),
            "name": name, "class": klass,
            "surfaces": sorted(g["surface"] for g in group),
            "wasted_trigger_tokens": (0 if klass == "shared" else
                                      est_tokens(sum(g["desc_chars"] for g in group[1:]))),
        })

    # name families on unique names
    tok_map = {}
    for n in sorted(by_name):
        for t in set(name_tokens(n)):
            tok_map.setdefault(t, []).append(n)
    for t, members in sorted(tok_map.items()):
        if len(members) >= family_min:
            findings["families"].append(
                {"fp": fingerprint("fam", t), "token": t,
                 "members": sorted(members)})

    # description similarity + collisions on unique names w/ descriptions
    described = []
    seen_names = set()
    for s in skills:
        if s["description"] and s["name"] not in seen_names:
            described.append(s)
            seen_names.add(s["name"])
    n = len(described)
    tsets = {s["name"]: tokens(s["description"]) for s in described}
    bsets = {s["name"]: bigrams(s["description"]) for s in described}
    psets = {s["name"]: phrases(s["description"]) for s in described}
    df = {}
    for ts in tsets.values():
        for t in ts:
            df[t] = df.get(t, 0) + 1
    # loose on purpose: a term in k descriptions is still discriminative for
    # those k skills (they compete for it); precision comes from the bigram /
    # phrase gates, and boilerplate is already stoplisted
    distinctive_max = max(3, min(24, int(n * 0.25))) if n else 0
    for i in range(n):
        for j in range(i + 1, n):
            a, b = described[i]["name"], described[j]["name"]
            ta, tb = tsets[a], tsets[b]
            if not ta or not tb:
                continue
            jac = len(ta & tb) / len(ta | tb)
            same_body = (described[i]["body_sha"] and
                         described[i]["body_sha"] == described[j]["body_sha"])
            if jac >= jaccard_min or same_body:
                findings["near_dupes"].append(
                    {"fp": fingerprint("dupe", a + "|" + b),
                     "pair": [a, b], "jaccard": round(jac, 3),
                     "identical_body": bool(same_body)})
                continue
            shared_distinctive = sorted(
                t for t in ta & tb if df.get(t, 0) <= distinctive_max)
            shared_bi = bsets[a] & bsets[b]
            shared_ph = sorted(psets[a] & psets[b])
            collides = (shared_ph or
                        (len(shared_distinctive) >= 3 and shared_bi) or
                        len(shared_distinctive) >= 6)
            if collides:
                rec = {"pair": [a, b],
                       "shared_terms": shared_distinctive[:10],
                       "shared_bigrams": sorted(
                           " ".join(x) for x in shared_bi)[:6],
                       "shared_phrases": shared_ph[:4]}
                findings["collision_pairs"].append(rec)
    for c in build_clusters(findings["collision_pairs"]):
        members = sorted(c["members"])
        core = sorted(c["core"])
        findings["collision_clusters"].append({
            "fp": fingerprint("coll", "|".join(members) + "#" + "|".join(core)),
            "members": members, "shared_terms": core[:8],
            "shared_phrases": sorted(c["phrases"])[:4],
            "phrase_backed": bool(c["phrases"])})
    findings["collision_clusters"].sort(
        key=lambda c: (-len(c["members"]), c["members"]))
    return findings


# --- economics --------------------------------------------------------------

def apply_economics(findings, skills):
    per_surface, table = {}, []
    seen = set()
    for s in skills:
        per_surface[s["surface"]] = per_surface.get(s["surface"], 0) + \
            est_tokens(s["desc_chars"])
        if s["name"] in seen:
            continue
        seen.add(s["name"])
        if s["has_skill_md"]:
            table.append({"name": s["name"], "surface": s["surface"],
                          "trigger_tokens": est_tokens(s["desc_chars"]),
                          "invoke_tokens": est_tokens(s["body_chars"])})
    table.sort(key=lambda r: -r["trigger_tokens"])
    findings["economics"] = {
        "note": "tokens ~= chars/4 (estimate); trigger tokens are paid in "
                "EVERY session on that surface, invoke tokens only when used",
        "total_trigger_tokens": sum(r["trigger_tokens"] for r in table),
        "per_surface_trigger_tokens": dict(sorted(per_surface.items())),
        "heaviest": table[:15],
    }


# --- usage mining -----------------------------------------------------------

SKILL_MD_RE = re.compile(rb"skills/([A-Za-z0-9_-]+)/SKILL\.md")
SKILL_TOOL_RE = re.compile(rb'"skill"\s*:\s*"([A-Za-z0-9 _:./-]{2,80})"')
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
CHUNK, KEEP = 1 << 23, 128


def normalize_skill_name(raw):
    raw = raw.strip().split(":")[-1].strip()  # plugin:skill -> skill
    return raw.lower().replace(" ", "-")


def scan_usage_file(path, patterns):
    counts = {}
    try:
        with open(path, "rb") as f:
            buf = b""
            while True:
                chunk = f.read(CHUNK)
                buf += chunk
                limit = len(buf) if not chunk else max(0, len(buf) - KEEP)
                for pat in patterns:
                    for m in pat.finditer(buf, 0, limit):
                        name = normalize_skill_name(
                            m.group(1).decode("utf-8", "replace"))
                        if name:
                            counts[name] = counts.get(name, 0) + 1
                if not chunk:
                    break
                buf = buf[limit:]
    except OSError:
        pass
    return counts


def build_usage(sessions_dir, cache_path, patterns, rebuild=False):
    """Incremental scan of <sessions_dir>/**.jsonl cached by mtime+size."""
    old = {}
    if not rebuild and os.path.isfile(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                old = json.load(f).get("files", {})
        except (OSError, ValueError):
            old = {}
    files, scanned = {}, 0
    if os.path.isdir(sessions_dir):
        for dirpath, dirnames, names in os.walk(sessions_dir):
            dirnames[:] = [d for d in dirnames if d not in (".git",)]
            for nm in names:
                if not nm.endswith(".jsonl"):
                    continue
                p = os.path.join(dirpath, nm)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                key = os.path.relpath(p, sessions_dir)
                prev = old.get(key)
                if prev and prev.get("mtime") == st.st_mtime and \
                        prev.get("size") == st.st_size:
                    files[key] = prev
                    continue
                dm = DATE_RE.search(nm)
                date = dm.group(1) if dm else time.strftime(
                    "%Y-%m-%d", time.localtime(st.st_mtime))
                files[key] = {"mtime": st.st_mtime, "size": st.st_size,
                              "date": date,
                              "counts": scan_usage_file(p, patterns)}
                scanned += 1
    agg = {}
    for rec in files.values():
        for name, c in rec["counts"].items():
            a = agg.setdefault(name, {"refs": 0, "sessions": 0,
                                      "last_seen": None})
            a["refs"] += c
            a["sessions"] += 1
            d = rec.get("date")
            if d and (a["last_seen"] is None or d > a["last_seen"]):
                a["last_seen"] = d
    try:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({"files": files}, f)
    except OSError as e:
        print(f"warning: usage cache not written: {e}", file=sys.stderr)
    return agg, scanned, len(files)


def merge_usage(per_ecosystem):
    merged = {}
    for eco, agg in per_ecosystem.items():
        for name, u in agg.items():
            m = merged.setdefault(name, {"refs": 0, "sessions": 0,
                                         "last_seen": None, "by": {}})
            m["refs"] += u["refs"]
            m["sessions"] += u["sessions"]
            m["by"][eco] = u["refs"]
            if u["last_seen"] and (m["last_seen"] is None or
                                   u["last_seen"] > m["last_seen"]):
                m["last_seen"] = u["last_seen"]
    return merged


def apply_usage(findings, skills, usage, grace_days=14):
    now = time.time()
    table, never, seen = {}, [], set()
    for s in skills:
        if s["name"] in seen:
            continue
        seen.add(s["name"])
        u = usage.get(s["name"])
        if u:
            table[s["name"]] = u
        else:
            try:
                mtime = os.lstat(s["path"]).st_mtime
            except OSError:
                mtime = 0
            if now - mtime < grace_days * 86400:
                continue  # too new to judge fairly
            never.append(s["name"])
    findings["usage"] = table
    findings["never_used"] = sorted(set(never))
    trig = {r["name"]: r["trigger_tokens"]
            for r in findings.get("economics", {}).get("heaviest", [])}
    all_trig = {s["name"]: est_tokens(s["desc_chars"]) for s in skills}
    findings["prune_candidates"] = sorted(
        ({"fp": fingerprint("nuse", n), "name": n,
          "trigger_tokens": all_trig.get(n, trig.get(n, 0))}
         for n in findings["never_used"]),
        key=lambda r: -r["trigger_tokens"])
    findings["usage_note"] = (
        "signal = SKILL.md path refs (codex+claude logs) and Skill-tool calls "
        "(claude logs); context-only triggering is not captured, so never_used "
        "means 'no recorded reference', not proof of zero use")


# --- ledger + diff ----------------------------------------------------------

FINDING_SECTIONS = ["duplicate_surfaces", "families", "near_dupes",
                    "collision_clusters", "dead", "unresolved_links",
                    "long_descriptions", "prune_candidates",
                    "plugin_version_drift", "duplicate_plugins",
                    "stale_plugin_caches"]


def ledger_path(state_dir):
    return os.path.join(state_dir, "skill-curator-ledger.json")


def snapshot_path(state_dir):
    return os.path.join(state_dir, "skill-curator-last.json")


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)


def active_decision(ledger, fp, now=None):
    d = ledger.get("decisions", {}).get(fp)
    if not d:
        return None
    if d.get("decision") == "snoozed" and (now or time.time()) > d.get("until", 0):
        return None  # snooze expired
    return d


def apply_ledger(findings, ledger, show_all=False):
    """Annotate findings with decisions; filter rejected/snoozed unless --all."""
    now = time.time()
    hidden = 0
    for section in FINDING_SECTIONS:
        items = findings.get(section)
        if items is None:
            continue
        kept = []
        for item in items:
            d = active_decision(ledger, item.get("fp", ""), now)
            if d:
                item["decision"] = d["decision"]
                if d.get("note"):
                    item["decision_note"] = d["note"]
            if d and d["decision"] in ("rejected", "snoozed") and not show_all:
                hidden += 1
                continue
            kept.append(item)
        findings[section] = kept
    findings["hidden_by_ledger"] = hidden


def compute_diff(findings, state_dir, write=True):
    current = {}
    for section in FINDING_SECTIONS:
        for item in findings.get(section) or []:
            if item.get("fp"):
                current[item["fp"]] = section
    prev = load_json(snapshot_path(state_dir), {}).get("fps", {})
    new = sorted(fp for fp in current if fp not in prev)
    resolved = sorted(fp for fp in prev if fp not in current)
    findings["diff"] = {"new": new, "resolved": resolved,
                        "new_count": len(new), "resolved_count": len(resolved),
                        "prev_run": load_json(snapshot_path(state_dir), {}).get("date")}
    if write:
        save_json(snapshot_path(state_dir),
                  {"date": time.strftime("%Y-%m-%d %H:%M"), "fps": current})


# --- scoring + report -------------------------------------------------------

def score(findings):
    pts = 100.0
    for d in findings.get("duplicate_surfaces", []):
        pts -= {"diverged-copies": 8, "identical-copies": 5,
                "shared": 0}.get(d["class"], 4)
    for c in findings.get("collision_clusters", []):
        pts -= 5 if c.get("phrase_backed") else 3
    pts -= 4 * len(findings.get("near_dupes", []))
    pts -= 2 * len(findings.get("dead", []))
    pts -= 1 * len(findings.get("long_descriptions", []))
    pts -= min(10.0, 0.5 * len(findings.get("prune_candidates",
                                            findings.get("never_used", []))))
    pts -= 4 * len(findings.get("plugin_version_drift", []))
    pts -= 3 * len(findings.get("duplicate_plugins", []))
    pts -= min(5.0, 1 * len(findings.get("stale_plugin_caches", [])))
    pts = max(0.0, pts)
    grade = ("A" if pts >= 90 else "B" if pts >= 80 else
             "C" if pts >= 70 else "D" if pts >= 60 else "F")
    return int(round(pts)), grade


def top_actions(findings):
    acts = []
    for d in findings.get("duplicate_surfaces", []):
        if d["class"] == "shared":
            continue
        acts.append({
            "save_tokens": d["wasted_trigger_tokens"],
            "action": f"dedupe '{d['name']}' ({d['class']}: "
                      f"{', '.join(d['surfaces'])})", "fp": d["fp"]})
    for p in findings.get("prune_candidates", []):
        acts.append({"save_tokens": p["trigger_tokens"],
                     "action": f"archive never-used '{p['name']}' "
                               f"(-{p['trigger_tokens']} trigger tokens/session)",
                     "fp": p["fp"]})
    for l in findings.get("long_descriptions", []):
        acts.append({"save_tokens": max(0, l["est_tokens"] - 200),
                     "action": f"trim description of '{l['name']}' "
                               f"({l['est_tokens']} tokens)", "fp": l["fp"]})
    for c in findings.get("collision_clusters", []):
        acts.append({"save_tokens": 40 * len(c["members"]),
                     "action": "sharpen triggers in cluster "
                               f"[{', '.join(c['members'])}] "
                               f"(shared: {', '.join(c['shared_terms'][:4])})"
                               + (" PHRASE OVERLAP" if c["phrase_backed"] else ""),
                     "fp": c["fp"]})
    acts.sort(key=lambda a: -a["save_tokens"])
    acts = acts[:5]
    # version drift is a correctness bug, not a token cost: always leads
    for d in reversed(findings.get("plugin_version_drift", [])):
        acts.insert(0, {"save_tokens": 0, "fp": d["fp"],
                        "action": f"refresh install of '{d['name']}'@"
                                  f"{d['marketplace']} (source "
                                  f"{d['source_version']} vs cache "
                                  f"{d['cache_version']} — DRIFT)"})
    return acts[:6]


def render_md(findings):
    pts, grade = score(findings)
    L = ["# Skill Curator report", ""]
    L.append(f"- health: **{grade} ({pts}/100)**")
    L.append(f"- skills: {findings['skill_count']} across "
             f"{findings['surface_count']} surfaces")
    if findings.get("plugin_source_count") or findings.get("plugin_install_count"):
        L.append(f"- plugins: {findings.get('plugin_source_count', 0)} local "
                 f"sources, {findings.get('plugin_install_count', 0)} installed")
    L.append(f"- trigger-token tax: ~{findings['context_cost_tokens']} tokens "
             f"({findings['context_cost_chars']} chars) loaded per session")
    diff = findings.get("diff")
    if diff:
        L.append(f"- since last run ({diff.get('prev_run') or 'never'}): "
                 f"{diff['new_count']} new, {diff['resolved_count']} resolved")
    if findings.get("hidden_by_ledger"):
        L.append(f"- ledger: {findings['hidden_by_ledger']} finding(s) hidden "
                 "(rejected/snoozed); --all to show")
    L.append("")
    acts = top_actions(findings)
    if acts:
        L.append("## Do these first")
        L.append("")
        for a in acts:
            L.append(f"- [{a['fp']}] {a['action']} (~{a['save_tokens']} tok)")
        L.append("")
    new_set = set((findings.get("diff") or {}).get("new", []))

    def line(item, text):
        mark = " **NEW**" if item.get("fp") in new_set else ""
        dec = f" [{item['decision']}]" if item.get("decision") else ""
        return f"- [{item.get('fp', '?')}]{mark}{dec} {text}"

    sec = [
        ("duplicate_surfaces", "Duplicate surfaces (same skill, 2+ places)",
         lambda i: line(i, f"`{i['name']}` — {i['class']}: "
                           f"{'; '.join(i['surfaces'])}"
                           + (f" (wasting ~{i['wasted_trigger_tokens']} tok)"
                              if i["wasted_trigger_tokens"] else ""))),
        ("collision_clusters", "Trigger-collision clusters",
         lambda i: line(i, f"{', '.join(i['members'])} — shared: "
                           f"{', '.join(i['shared_terms'][:6])}"
                           + (f"; PHRASES: {'; '.join(i['shared_phrases'])}"
                              if i["shared_phrases"] else ""))),
        ("near_dupes", "Near-duplicate descriptions",
         lambda i: line(i, f"{i['pair'][0]} ~ {i['pair'][1]} "
                           f"(jaccard {i['jaccard']}"
                           + (", identical body" if i.get("identical_body")
                              else "") + ")")),
        ("families", "Name families (verify split is deliberate)",
         lambda i: line(i, f"{i['token']}-*: {', '.join(i['members'])}")),
        ("dead", "Dead skills (no SKILL.md)",
         lambda i: line(i, f"`{i['name']}` at {i['path']}")),
        ("unresolved_links", "Unresolved symlinks (verify, don't assume)",
         lambda i: line(i, f"`{i['name']}` -> {i['target']}")),
        ("long_descriptions", "Heavy descriptions (>1500 chars)",
         lambda i: line(i, f"`{i['name']}`: {i['desc_chars']} chars "
                           f"(~{i['est_tokens']} tok in EVERY session)")),
        ("plugin_version_drift", "Plugin version drift (source vs installed cache)",
         lambda i: line(i, f"`{i['name']}`@{i['marketplace']}: source "
                           f"{i['source_version']} vs cache {i['cache_version']}"
                           f" ({i['source_path']})")),
        ("duplicate_plugins", "Plugins installed from 2+ marketplaces",
         lambda i: line(i, f"`{i['name']}`: {', '.join(i['marketplaces'])}")),
        ("stale_plugin_caches", "Stale cached plugin versions (newest wins)",
         lambda i: line(i, f"`{i['name']}`@{i['marketplace']}: active "
                           f"{i['active']}, stale: "
                           f"{', '.join(i['stale_versions'])}")),
    ]
    for key, title, fmt in sec:
        items = findings.get(key) or []
        L.append(f"## {title} ({len(items)})")
        L.append("")
        for item in items:
            L.append(fmt(item))
        L.append("")
    eco = findings.get("economics")
    if eco:
        L.append("## Economics")
        L.append("")
        L.append(f"> {eco['note']}")
        L.append("")
        for surf, tok in eco["per_surface_trigger_tokens"].items():
            L.append(f"- {surf}: ~{tok} trigger tokens")
        L.append("")
        L.append("Heaviest descriptions:")
        L.append("")
        for r in eco["heaviest"][:10]:
            L.append(f"- {r['name']}: {r['trigger_tokens']} trigger / "
                     f"{r['invoke_tokens']} invoke tokens")
        L.append("")
    if "usage" in findings:
        prunes = findings.get("prune_candidates", [])
        L.append(f"## Usage (prune candidates: {len(prunes)})")
        L.append("")
        L.append(f"> {findings['usage_note']}")
        L.append("")
        for p in prunes[:20]:
            L.append(f"- [{p['fp']}] never used: {p['name']} "
                     f"(~{p['trigger_tokens']} tok/session)")
        top = sorted(findings["usage"].items(), key=lambda kv: -kv[1]["refs"])[:10]
        if top:
            L.append("")
            L.append("Most used:")
            L.append("")
            for name, u in top:
                by = ", ".join(f"{k}:{v}" for k, v in sorted(u["by"].items()))
                L.append(f"- {name}: {u['refs']} refs / {u['sessions']} sessions "
                         f"({by}), last seen {u['last_seen']}")
        L.append("")
    conf = findings.get("routing_confusion")
    if conf:
        L.append("## Routing confusion (from probes-grade)")
        L.append("")
        L.append(f"- graded {conf['probes']} probes on {conf['date']}: "
                 f"accuracy {conf['accuracy']}")
        for m in conf.get("worst", [])[:8]:
            L.append(f"- '{m['expected']}' probes routed to "
                     f"'{m['selected']}' x{m['count']}")
        L.append("")
    mirrors = findings.get("mirror_caches")
    if mirrors:
        L.append(f"## Mirror caches (info only, excluded from scan) ({len(mirrors)})")
        L.append("")
        for m in mirrors:
            L.append(f"- {m['plugin']}: {'; '.join(m['notes'][:4])}")
        L.append("")
    return "\n".join(L)


# --- pipeline helpers -------------------------------------------------------

def default_roots(args):
    roots = args.root or [r for r in ("~/.codex/skills", "~/.claude/skills")
                          if os.path.isdir(os.path.expanduser(r))]
    caches = args.plugin_cache
    if caches is None and not getattr(args, "no_plugins", False):
        caches = [c for c in ("~/.claude/plugins/cache", "~/.codex/plugins/cache")
                  if os.path.isdir(os.path.expanduser(c))]
    return [os.path.expanduser(r) for r in (roots or [])], \
           [os.path.expanduser(c) for c in (caches or [])]


def default_plugin_sources(args):
    if getattr(args, "no_plugins", False):
        return []
    srcs = getattr(args, "plugin_source", None)
    if srcs is None:
        srcs = [s for s in ("~/.codex/plugins", "~/.claude/plugins")
                if os.path.isdir(os.path.expanduser(s))]
    return [os.path.expanduser(s) for s in srcs]


def state_dir_of(args):
    sd = getattr(args, "state_dir", None) or os.path.join(
        os.path.expanduser(getattr(args, "codex_root", "~/.codex")), "cache")
    os.makedirs(sd, exist_ok=True)
    return sd


def run_usage(args, skills, findings):
    if not getattr(args, "usage", False):
        return
    sd = state_dir_of(args)
    croot = os.path.expanduser(args.codex_root)
    claude_root = os.path.expanduser(getattr(args, "claude_root", "~/.claude"))
    per, total_scanned = {}, []
    eco_specs = [
        ("codex", os.path.join(croot, "sessions"),
         os.path.join(croot, "cache", "skill-curator-usage.json"),
         [SKILL_MD_RE]),
        ("claude", os.path.join(claude_root, "projects"),
         os.path.join(sd, "skill-curator-usage-claude.json"),
         [SKILL_MD_RE, SKILL_TOOL_RE]),
    ]
    for eco, sess, cache, pats in eco_specs:
        if not os.path.isdir(sess):
            continue
        agg, scanned, nfiles = build_usage(
            sess, cache, pats, rebuild=getattr(args, "rebuild_usage", False))
        per[eco] = agg
        total_scanned.append(f"{eco}: {nfiles} files, {scanned} (re)scanned")
    apply_usage(findings, skills, merge_usage(per), grace_days=args.grace_days)
    print("usage: " + "; ".join(total_scanned or ["no session dirs found"]),
          file=sys.stderr)


def build_all(args, with_ledger=True, write_snapshot=True):
    roots, caches = default_roots(args)
    skills = gather_skills(roots, caches)
    findings = analyze(skills)
    findings["mirror_caches"] = getattr(gather_skills, "last_mirror_notes", [])
    apply_economics(findings, skills)
    run_usage(args, skills, findings)
    sources = []
    for sroot in default_plugin_sources(args):
        sources.extend(scan_plugin_sources(sroot))
    cache_map = merge_cache_maps(scan_cache_plugins(c) for c in caches)
    analyze_plugins(findings, sources, cache_map)
    sd = state_dir_of(args)
    conf = load_json(os.path.join(sd, "skill-curator-confusion.json"), None)
    if conf:
        findings["routing_confusion"] = conf
    if with_ledger:
        apply_ledger(findings, load_json(ledger_path(sd), {}),
                     show_all=getattr(args, "all", False))
        compute_diff(findings, sd, write=write_snapshot)
    return skills, findings


# --- commands ---------------------------------------------------------------

def cmd_report(args):
    _skills, findings = build_all(args)
    if args.json:
        print(json.dumps(findings, indent=2, ensure_ascii=False))
    else:
        print(render_md(findings))
    if args.md:
        with open(args.md, "w", encoding="utf-8") as f:
            f.write(render_md(findings) + "\n")
        print(f"\nreport written: {args.md}", file=sys.stderr)
    return 0


def cmd_check(args):
    _skills, findings = build_all(args, write_snapshot=False)
    failures = []
    for spec in args.expect_used or []:
        name, _, num = spec.partition(":")
        want = int(num or 1)
        got = findings.get("usage", {}).get(name, {}).get("refs", 0)
        if got < want:
            failures.append(f"usage {name!r}: wanted >={want} refs, got {got}")
    for spec in args.expect_family or []:
        tok, _, num = spec.partition(":")
        want = int(num or 2)
        got = next((f for f in findings["families"] if f["token"] == tok), None)
        if not got or len(got["members"]) < want:
            failures.append(f"family {tok!r}: wanted >={want}, got "
                            f"{len(got['members']) if got else 0}")
    if args.min_near_dupes and len(findings["near_dupes"]) < args.min_near_dupes:
        failures.append(f"near_dupes: wanted >={args.min_near_dupes}, "
                        f"got {len(findings['near_dupes'])}")
    if args.min_dead and len(findings["dead"]) < args.min_dead:
        failures.append(f"dead: wanted >={args.min_dead}, got {len(findings['dead'])}")
    if args.max_trigger_tokens and \
            findings["context_cost_tokens"] > args.max_trigger_tokens:
        failures.append(f"trigger tokens {findings['context_cost_tokens']} "
                        f"> budget {args.max_trigger_tokens}")
    if args.max_new_findings is not None and \
            findings.get("diff", {}).get("new_count", 0) > args.max_new_findings:
        failures.append(f"new findings {findings['diff']['new_count']} "
                        f"> allowed {args.max_new_findings}")
    for f in failures:
        print(f"CHECK FAIL: {f}")
    if not failures:
        print("CHECK OK")
    return 1 if failures else 0


def cmd_decide(args):
    sd = state_dir_of(args)
    ledger = load_json(ledger_path(sd), {})
    decisions = ledger.setdefault("decisions", {})
    if args.reject:
        decision = "rejected"
    elif args.accept:
        decision = "accepted"
    elif args.snooze_days is not None:
        decision = "snoozed"
    else:
        print("pick one of --accept / --reject / --snooze-days N", file=sys.stderr)
        return 2
    for fp in args.fingerprint:
        rec = {"decision": decision, "note": args.note or "",
               "date": time.strftime("%Y-%m-%d")}
        if decision == "snoozed":
            rec["until"] = time.time() + args.snooze_days * 86400
        decisions[fp] = rec
        print(f"{fp}: {decision}" + (f" until +{args.snooze_days}d"
                                     if decision == "snoozed" else ""))
    save_json(ledger_path(sd), ledger)
    return 0


def cmd_decisions(args):
    sd = state_dir_of(args)
    ledger = load_json(ledger_path(sd), {})
    decs = ledger.get("decisions", {})
    if not decs:
        print("no decisions recorded")
        return 0
    for fp, d in sorted(decs.items()):
        extra = ""
        if d["decision"] == "snoozed":
            left = (d.get("until", 0) - time.time()) / 86400
            extra = f" ({'expired' if left < 0 else f'{left:.0f}d left'})"
        note = f" — {d['note']}" if d.get("note") else ""
        print(f"{fp}: {d['decision']}{extra} [{d.get('date', '?')}]{note}")
    return 0


def cmd_archive(args):
    roots, _ = default_roots(args)
    target = None
    for r in roots:
        p = os.path.join(r, args.name)
        if os.path.islink(p) or os.path.isdir(p):
            target, root = p, r
            break
    if not target:
        print(f"'{args.name}' not found in roots {roots} "
              "(plugin skills can't be archived here — disable the plugin "
              "in its app instead)", file=sys.stderr)
        return 1
    day = time.strftime("%Y%m%d")
    dest_dir = os.path.join(root, ".archive", day)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, args.name)
    if os.path.exists(dest) or os.path.islink(dest):
        print(f"refusing: {dest} already exists", file=sys.stderr)
        return 1
    was_link = os.path.islink(target)
    link_target = os.readlink(target) if was_link else None
    shutil.move(target, dest)
    manifest = {
        "name": args.name, "archived_at": time.strftime("%Y-%m-%d %H:%M"),
        "from": target, "reason": args.reason or "", "fp": args.fp or "",
        "was_symlink": was_link, "link_target": link_target,
        "restore": f"python3 curator.py restore {args.name} --root {root}",
    }
    mpath = (os.path.join(dest, "curator-archive-manifest.json")
             if not was_link else dest + ".manifest.json")
    save_json(mpath, manifest)
    print(f"archived {target} -> {dest}")
    if was_link:
        print(f"note: archived the SYMLINK only; target untouched: {link_target}")
    return 0


def cmd_restore(args):
    roots, _ = default_roots(args)
    candidates = []
    for r in roots:
        adir = os.path.join(r, ".archive")
        if not os.path.isdir(adir):
            continue
        for day in sorted(os.listdir(adir), reverse=True):
            p = os.path.join(adir, day, args.name)
            if os.path.islink(p) or os.path.exists(p):
                candidates.append((day, r, p))
    if not candidates:
        print(f"no archived copy of '{args.name}' found", file=sys.stderr)
        return 1
    _day, root, src = candidates[0]
    dest = os.path.join(root, args.name)
    if os.path.exists(dest) or os.path.islink(dest):
        print(f"refusing: {dest} already exists", file=sys.stderr)
        return 1
    man_inner = os.path.join(src, "curator-archive-manifest.json")
    if os.path.isfile(man_inner):
        try:
            os.remove(man_inner)
        except OSError:
            pass
    shutil.move(src, dest)
    side = src + ".manifest.json"
    if os.path.isfile(side):
        try:
            os.remove(side)
        except OSError:
            pass
    print(f"restored {dest}")
    return 0


# --- probes / routing evals -------------------------------------------------

def stable_order(names):
    return sorted(names, key=lambda n: hashlib.sha1(n.encode()).hexdigest())


def cmd_probes(args):
    roots, caches = default_roots(args)
    skills = gather_skills(roots, caches)
    only = set(args.only or [])
    seen, described = set(), []
    for s in skills:
        if s["description"] and s["name"] not in seen and \
                (not only or s["name"] in only):
            described.append(s)
            seen.add(s["name"])
    out_dir = args.out_dir
    os.makedirs(out_dir, exist_ok=True)
    probe_list, need_authoring = [], []
    for s in described:
        phs = sorted(phrases(s["description"]))
        if not phs:
            need_authoring.append(s["name"])
        for i, ph in enumerate(phs[:args.max_per_skill]):
            probe_list.append({"id": f"{s['name']}:{i}", "skill": s["name"],
                               "text": ph, "kind": "phrase"})
    probes = {
        "note": "phrase probes are lifted verbatim from each description's "
                "quoted triggers; ADD PARAPHRASE + NEAR-MISS PROBES by hand "
                "or with a model before trusting accuracy numbers",
        "results_format": "JSONL lines: {\"probe_id\": ..., \"selected\": "
                          "\"<skill-name the router picked>\"}",
        "needs_authoring": sorted(need_authoring),
        "probes": probe_list,
    }
    save_json(os.path.join(out_dir, "probes.json"), probes)
    scen = [{"title": f"route:{p['id']}",
             "purpose": f"Routing probe for {p['skill']}",
             "userInput": p["text"],
             "successChecklist": [
                 f"The {p['skill']} skill is the one that should handle this",
                 "No other installed skill is a better match",
             ]} for p in probe_list]
    save_json(os.path.join(out_dir, "benchmark-scenarios.json"), scen)
    sheet = ["# Routing sheet", "",
             "You are a skill router. For each probe (see probes.json), pick "
             "the ONE skill below whose description best matches. Answer as "
             "JSONL: {\"probe_id\": ..., \"selected\": ...}. Do not favor "
             "list position.", ""]
    for s in stable_order([d["name"] for d in described]):
        desc = next(d["description"] for d in described if d["name"] == s)
        sheet.append(f"- **{s}**: {desc}")
    with open(os.path.join(out_dir, "routing-sheet.md"), "w",
              encoding="utf-8") as f:
        f.write("\n".join(sheet) + "\n")
    print(f"{len(probe_list)} probes for {len(described)} skills -> {out_dir}/"
          f"{{probes.json, benchmark-scenarios.json, routing-sheet.md}}")
    if need_authoring:
        print(f"{len(need_authoring)} skills have no quoted trigger phrases "
              f"(need authored probes): {', '.join(sorted(need_authoring)[:8])}"
              + (" ..." if len(need_authoring) > 8 else ""))
    return 0


def cmd_probes_grade(args):
    probes = load_json(args.probes, {})
    expected = {p["id"]: p["skill"] for p in probes.get("probes", [])}
    results = []
    try:
        with open(args.results, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    results.append(json.loads(line))
    except (OSError, ValueError) as e:
        print(f"cannot read results: {e}", file=sys.stderr)
        return 1
    per_skill, misroutes, hits, graded = {}, {}, 0, 0
    for r in results:
        pid = r.get("probe_id")
        if pid not in expected:
            continue
        graded += 1
        exp = expected[pid]
        sel = normalize_skill_name(str(r.get("selected", "")))
        st = per_skill.setdefault(exp, {"probes": 0, "hits": 0})
        st["probes"] += 1
        if sel == exp:
            st["hits"] += 1
            hits += 1
        else:
            key = (exp, sel)
            misroutes[key] = misroutes.get(key, 0) + 1
    if not graded:
        print("no gradeable results (probe_id mismatch?)", file=sys.stderr)
        return 1
    worst = sorted(({"expected": e, "selected": s, "count": c}
                    for (e, s), c in misroutes.items()),
                   key=lambda m: -m["count"])
    conf = {"date": time.strftime("%Y-%m-%d"), "probes": graded,
            "accuracy": round(hits / graded, 3),
            "per_skill": {k: {"probes": v["probes"], "hits": v["hits"]}
                          for k, v in sorted(per_skill.items())},
            "worst": worst[:20]}
    sd = state_dir_of(args)
    save_json(os.path.join(sd, "skill-curator-confusion.json"), conf)
    print(f"accuracy {conf['accuracy']} over {graded} probes")
    for m in worst[:10]:
        print(f"  MISROUTE {m['expected']} -> {m['selected']} x{m['count']}")
    print(f"confusion snapshot saved; next `report` will include it")
    return 0


# --- plugin-eval metric pack ------------------------------------------------

def cmd_emit_metric_pack(args):
    out = os.path.abspath(os.path.expanduser(args.dir))
    os.makedirs(out, exist_ok=True)
    cmd = ["python3", os.path.abspath(__file__), "metric-pack-emit"]
    roots, caches = default_roots(args)
    for r in roots:
        cmd += ["--root", r]
    for c in caches:
        cmd += ["--plugin-cache", c]
    if getattr(args, "state_dir", None):
        cmd += ["--state-dir", args.state_dir]
    manifest = {"name": "skill-curator-inventory", "version": "2.0.0",
                "supportedTargetKinds": ["skill", "plugin"],
                "command": cmd}
    save_json(os.path.join(out, "manifest.json"), manifest)
    print(f"metric pack written: {out}/manifest.json")
    print("use: plugin-eval analyze <skill-or-plugin> --metric-pack "
          f"{out}/manifest.json")
    return 0


def band(value, good, moderate):
    return "good" if value <= good else "moderate" if value <= moderate else "heavy"


def cmd_metric_pack_emit(args):
    target = os.environ.get("PLUGIN_EVAL_TARGET") or \
        (args.extra[0] if args.extra else None)
    kind = os.environ.get("PLUGIN_EVAL_TARGET_KIND") or \
        (args.extra[1] if len(args.extra) > 1 else "skill")
    if not target:
        print(json.dumps({"checks": [], "metrics": [], "artifacts": [],
                          "error": "no PLUGIN_EVAL_TARGET"}))
        return 1
    treal = os.path.realpath(os.path.expanduser(target))
    if treal.endswith("SKILL.md"):
        treal = os.path.dirname(treal)
    roots, caches = default_roots(args)
    skills = gather_skills(roots, caches)
    findings = analyze(skills)
    apply_economics(findings, skills)
    names = set()
    if kind == "plugin":
        for s in skills:
            if s["realpath"].startswith(treal + os.sep) or s["realpath"] == treal:
                names.add(s["name"])
        if not names:
            for s in scan_plugin_cache(treal):
                names.add(s["name"])
    else:
        for s in skills:
            if s["realpath"] == treal:
                names.add(s["name"])
        if not names:
            names.add(os.path.basename(treal))
    checks, metrics = [], []
    for d in findings["duplicate_surfaces"]:
        if d["name"] in names and d["class"] != "shared":
            checks.append({
                "id": f"curator-dup-{d['name']}", "category": "inventory",
                "severity": "error" if d["class"] == "diverged-copies" else "warning",
                "status": "fail" if d["class"] == "diverged-copies" else "warn",
                "message": f"'{d['name']}' exists on multiple surfaces "
                           f"({d['class']})",
                "evidence": d["surfaces"],
                "remediation": ["keep one canonical copy; archive or symlink "
                                "the rest (curator.py archive)"]})
    for c in findings["collision_clusters"]:
        overlap = names & set(c["members"])
        if overlap:
            checks.append({
                "id": f"curator-collision-{c['fp']}", "category": "inventory",
                "severity": "warning", "status": "warn",
                "message": "trigger collision with: " + ", ".join(
                    sorted(set(c["members"]) - names) or c["members"]),
                "evidence": [f"shared terms: {', '.join(c['shared_terms'])}"] +
                            ([f"shared phrases: {'; '.join(c['shared_phrases'])}"]
                             if c["shared_phrases"] else []),
                "remediation": ["sharpen the description's distinctive "
                                "triggers; verify with curator.py probes"]})
    for nd in findings["near_dupes"]:
        if names & set(nd["pair"]):
            checks.append({
                "id": f"curator-neardupe-{nd['fp']}", "category": "inventory",
                "severity": "warning", "status": "warn",
                "message": f"near-duplicate description: {nd['pair'][0]} ~ "
                           f"{nd['pair'][1]} (jaccard {nd['jaccard']})",
                "evidence": [], "remediation": ["consider merging"]})
    if not checks:
        checks.append({"id": "curator-inventory-clean", "category": "inventory",
                       "severity": "info", "status": "pass",
                       "message": "no inventory-level findings for this target",
                       "evidence": [], "remediation": []})
    tks = [est_tokens(s["desc_chars"]) for s in skills if s["name"] in names]
    if tks:
        tt = sum(tks)
        metrics.append({"id": "curator-trigger-tokens", "category": "inventory",
                        "value": tt, "unit": "tokens",
                        "band": band(tt, 100, 250)})
    metrics.append({"id": "curator-inventory-trigger-tokens",
                    "category": "inventory",
                    "value": findings["context_cost_tokens"], "unit": "tokens",
                    "band": band(findings["context_cost_tokens"], 2500, 6000)})
    print(json.dumps({"checks": checks, "metrics": metrics, "artifacts": []},
                     indent=1))
    return 0


# --- selftest ---------------------------------------------------------------

def cmd_selftest(_args):
    fails, total = [], [0]

    def expect(cond, label):
        total[0] += 1
        print(("PASS " if cond else "FAIL ") + label)
        if not cond:
            fails.append(label)

    with tempfile.TemporaryDirectory() as croot:
        td = os.path.join(croot, "skills")
        td2 = os.path.join(croot, "skills2")
        os.makedirs(td)
        os.makedirs(td2)

        def mk(root, name, desc=None, body_extra=""):
            d = os.path.join(root, name)
            os.makedirs(d, exist_ok=True)
            if desc is not None:
                with open(os.path.join(d, "SKILL.md"), "w") as f:
                    f.write(f"---\nname: {name}\ndescription: {desc}\n---\n"
                            f"# {name}\n{body_extra}")

        mk(td, "alpha-render", "Render alpha compositions into layered frame stacks quickly.")
        mk(td, "alpha-render-media", "Encode media assets for alpha pipelines with ffmpeg presets.")
        mk(td, "alpha-render-motion", "Motion curves and easing helpers for alpha timeline work.")
        dupe = ("Create polished marketing videos from a product webpage, "
                "screenshots, and brand colors using automated scene templates.")
        mk(td, "video-maker-one", dupe)
        mk(td, "video-maker-two", dupe + " Includes caption styling.")
        mk(td, "solo", "Summarize psychiatric intake interviews into structured clinical notes.")
        mk(td, "dead-skill")
        os.symlink(os.path.join(td, "nonexistent"), os.path.join(td, "ghost"))
        # boilerplate-only overlap must NOT collide
        mk(td, "word-writer", "Use this to create, edit, and work with document deliverables whenever the user mentions them.")
        mk(td, "sheet-writer", "Use this to create, edit, and work with spreadsheet deliverables whenever the user mentions them.")
        # real collision cluster (distinctive terms + bigrams)
        mk(td, "swift-anim-audit", "Audit SwiftUI animation performance and motion smoothness for Swift views when animations feel janky.")
        mk(td, "swift-anim-polish", "Polish SwiftUI animation performance with motion tuning for Swift views when animations stutter.")
        mk(td, "swift-anim-review", "Review SwiftUI animation performance and motion jank across Swift views before release.")
        # phrase-backed collision
        mk(td, "jank-fixer", "Fix rendering issues. Use when the user says 'fix the jank' or reports dropped frames.")
        mk(td, "frame-doctor", "Diagnose frame pacing. Trigger on 'fix the jank' complaints about scrolling.")
        # bridge member with two unrelated topics must NOT chain clusters
        mk(td, "net-scan", "Scan wifi network topology and router firmware vulnerabilities across home networks.")
        mk(td, "net-fix", "Repair wifi network topology and router firmware faults; separately calibrate oven thermostat sensors in kitchens.")
        mk(td, "oven-fix", "Calibrate oven thermostat sensors and balance kitchens heating coils safely.")
        # duplicate surfaces: diverged copy of solo in second root
        mk(td2, "solo", "Summarize psychiatric intake interviews into structured clinical notes.", body_extra="DIVERGED\n")
        # shared symlink surface
        os.symlink(os.path.join(td, "alpha-render"), os.path.join(td2, "alpha-render"))
        # folded YAML description
        d = os.path.join(td, "folded")
        os.makedirs(d)
        with open(os.path.join(d, "SKILL.md"), "w") as f:
            f.write("---\nname: folded\ndescription: >-\n  Folded scalar "
                    "narrative about telescopes\n  and star charts.\n---\n# folded\n")
        # plugin cache with a fixtures dir that must be pruned
        pc = os.path.join(croot, "plugcache")
        pskill = os.path.join(pc, "mkt", "coolplug", "1.2.0", "skills", "coolskill")
        os.makedirs(pskill)
        with open(os.path.join(pskill, "SKILL.md"), "w") as f:
            f.write("---\nname: coolskill\ndescription: Orchestrate satellite "
                    "imagery mosaics for cartography.\n---\n# coolskill\n")
        fx = os.path.join(pc, "mkt", "coolplug", "1.2.0", "fixtures", "skills", "fakeskill")
        os.makedirs(fx)
        with open(os.path.join(fx, "SKILL.md"), "w") as f:
            f.write("---\nname: fakeskill\ndescription: fixture noise\n---\n")
        # remote mirror cache: identical copy + diverged copy + remote-only plugin
        for name, desc, extra in (
                ("coolskill", "Orchestrate satellite imagery mosaics for cartography.", ""),):
            rm = os.path.join(pc, "mkt-remote", "coolplug", "1.2.0", "skills", name)
            os.makedirs(rm)
            with open(os.path.join(rm, "SKILL.md"), "w") as f:
                f.write(f"---\nname: {name}\ndescription: {desc}\n---\n# {name}\n{extra}")
        rm2 = os.path.join(pc, "mkt-remote", "coolplug", "1.2.0", "skills", "coolskill2")
        os.makedirs(rm2)
        with open(os.path.join(rm2, "SKILL.md"), "w") as f:
            f.write("---\nname: coolskill2\ndescription: Divergent mirror copy of tides.\n---\nDIFFERENT\n")
        cs2 = os.path.join(pc, "mkt", "coolplug", "1.2.0", "skills", "coolskill2")
        os.makedirs(cs2)
        with open(os.path.join(cs2, "SKILL.md"), "w") as f:
            f.write("---\nname: coolskill2\ndescription: Divergent mirror copy of tides.\n---\nORIGINAL\n")
        ro = os.path.join(pc, "mkt-remote", "remoteonly", "9.9.9-abcdef123456", "skills", "ghost-skill")
        os.makedirs(ro)
        with open(os.path.join(ro, "SKILL.md"), "w") as f:
            f.write("---\nname: ghost-skill\ndescription: Remote-only phantom entry.\n---\n")

        skills = gather_skills([td, td2], [pc])
        mirror_notes = gather_skills.last_mirror_notes
        f = analyze(skills)
        apply_economics(f, skills)

        fam = next((x for x in f["families"] if x["token"] == "alpha"), None)
        expect(fam is not None and len(fam["members"]) == 3, "family: alpha x3 detected")
        nd = [set(p["pair"]) for p in f["near_dupes"]]
        expect({"video-maker-one", "video-maker-two"} in nd, "near-dupe pair detected")
        expect(any(d_["name"] == "dead-skill" for d_ in f["dead"]), "dead skill detected")
        expect(all(d_["name"] != "solo" for d_ in f["dead"]), "no false dead finding")
        expect(any(u["name"] == "ghost" for u in f["unresolved_links"]),
               "unresolved symlink classified (not dead)")
        expect(f["context_cost_tokens"] > 0, "token cost computed")
        cp = {frozenset(p["pair"]) for p in f["collision_pairs"]}
        expect(frozenset(("word-writer", "sheet-writer")) not in cp,
               "boilerplate-only overlap suppressed")
        expect(any({"swift-anim-audit", "swift-anim-polish"} <= set(c["members"])
                   for c in f["collision_clusters"]),
               "true collision detected and clustered")
        expect(any(set(c["members"]) >= {"swift-anim-audit", "swift-anim-polish",
                                         "swift-anim-review"}
                   for c in f["collision_clusters"]),
               "3-member cluster formed from pairwise edges")
        expect(any(c["phrase_backed"] and
                   {"jank-fixer", "frame-doctor"} <= set(c["members"])
                   for c in f["collision_clusters"]),
               "quoted-phrase collision detected")
        expect(not any({"net-scan", "oven-fix"} <= set(c["members"])
                       for c in f["collision_clusters"]),
               "bridge member does not chain unrelated topics into one blob")
        expect(any({"net-scan", "net-fix"} <= set(c["members"])
                   for c in f["collision_clusters"]) and
               any({"net-fix", "oven-fix"} <= set(c["members"])
                   for c in f["collision_clusters"]),
               "both topic clusters survive around the bridge member")
        folded_rec = next(s for s in skills if s["name"] == "folded")
        expect(folded_rec["description"].startswith("Folded scalar"),
               "folded YAML description parsed without marker")
        dups = {d_["name"]: d_ for d_ in f["duplicate_surfaces"]}
        expect(dups.get("solo", {}).get("class") == "diverged-copies",
               "diverged duplicate surface detected")
        expect(dups.get("alpha-render", {}).get("class") == "shared",
               "symlink-shared surface classified as shared")
        expect(any(s["name"] == "coolskill" and s["surface"] ==
                   "plugin:coolplug@mkt" for s in skills),
               "plugin cache skill discovered with surface label")
        expect(all(s["name"] != "fakeskill" for s in skills),
               "fixtures dir pruned from plugin scan")
        surfaces = {s["surface"] for s in skills}
        expect(not any("-remote" in x for x in surfaces),
               "mirror cache records dropped from surfaces")
        expect(sum(1 for s in skills if s["name"] == "coolskill") == 1,
               "mirror copy not double-counted")
        note_map = {m["plugin"]: m["notes"] for m in mirror_notes}
        expect(any("mirror diverges: coolskill2" in n
                   for n in note_map.get("coolplug@mkt", [])),
               "diverged mirror noted, not scored")
        expect(any("remote-only" in n
                   for n in note_map.get("remoteonly@mkt", [])),
               "remote-only plugin noted as not installed")
        expect(all(s["name"] != "ghost-skill" for s in skills),
               "remote-only plugin skills excluded from surface")
        expect(any(s["name"] == "coolskill2" and "/mkt/" in s["path"]
                   for s in skills),
               "installed copy of diverged-mirror skill kept")
        expect(f["economics"]["total_trigger_tokens"] > 0 and
               "plugin:coolplug@mkt" in f["economics"]["per_surface_trigger_tokens"],
               "economics per-surface totals computed")

        # fingerprint stability
        f2 = analyze(gather_skills([td, td2], [pc]))
        fp1 = sorted(c["fp"] for c in f["collision_clusters"])
        fp2 = sorted(c["fp"] for c in f2["collision_clusters"])
        expect(fp1 == fp2, "fingerprints stable across runs")

        # --- usage: codex pattern + claude Skill-tool pattern ---
        sdir = os.path.join(croot, "sessions", "2026", "01", "01")
        os.makedirs(sdir)
        with open(os.path.join(sdir, "rollout-2026-01-01T10-00-00-abc.jsonl"), "w") as fh:
            fh.write(json.dumps({"type": "response_item",
                                 "text": "Read skills/alpha-render/SKILL.md ok"}) + "\n")
            fh.write(json.dumps({"type": "response_item",
                                 "text": "again skills/alpha-render/SKILL.md"}) + "\n")
        cdir = os.path.join(croot, "claude", "projects", "p1")
        os.makedirs(cdir)
        with open(os.path.join(cdir, "0aa2-uuid.jsonl"), "w") as fh:
            fh.write(json.dumps({"name": "Skill",
                                 "input": {"skill": "coolplug:coolskill"}}) + "\n")

        agg, scanned, nfiles = build_usage(
            os.path.join(croot, "sessions"),
            os.path.join(croot, "cache", "u-codex.json"), [SKILL_MD_RE])
        expect(scanned == 1 and nfiles == 1, "first usage pass scans the file")
        a = agg.get("alpha-render", {})
        expect(a.get("refs") == 2 and a.get("last_seen") == "2026-01-01",
               "refs counted and last_seen dated from filename")
        agg2, scanned2, _ = build_usage(
            os.path.join(croot, "sessions"),
            os.path.join(croot, "cache", "u-codex.json"), [SKILL_MD_RE])
        expect(scanned2 == 0 and agg2 == agg, "second pass served from cache")
        cagg, _, _ = build_usage(
            os.path.join(croot, "claude", "projects"),
            os.path.join(croot, "cache", "u-claude.json"),
            [SKILL_MD_RE, SKILL_TOOL_RE])
        expect(cagg.get("coolskill", {}).get("refs", 0) >= 1,
               "claude Skill-tool call counted, plugin: prefix normalized")

        merged = merge_usage({"codex": agg, "claude": cagg})
        apply_usage(f, skills, merged, grace_days=0)
        expect("alpha-render" not in f["never_used"] and "solo" in f["never_used"],
               "never_used excludes used, includes unused (grace=0)")
        expect(f["never_used"].count("solo") == 1,
               "never_used deduped across surfaces")
        apply_usage(f, skills, merged, grace_days=30)
        expect(f["never_used"] == [], "grace period shields fresh skills")
        apply_usage(f, skills, merged, grace_days=0)
        pr = f["prune_candidates"]
        expect(pr and all(pr[i]["trigger_tokens"] >= pr[i + 1]["trigger_tokens"]
                          for i in range(len(pr) - 1)),
               "prune candidates ranked by trigger cost")

        # --- ledger + diff ---
        sd = os.path.join(croot, "state")
        cluster_fp = f["collision_clusters"][0]["fp"]
        ledger = {"decisions": {cluster_fp: {"decision": "rejected",
                                             "date": "2026-01-01"}}}
        save_json(ledger_path(sd), ledger)
        apply_ledger(f, ledger)
        expect(all(c["fp"] != cluster_fp for c in f["collision_clusters"]),
               "rejected finding hidden from report")
        expect(f["hidden_by_ledger"] >= 1, "hidden count surfaces in report")
        snoozed = {"decisions": {cluster_fp: {"decision": "snoozed",
                                              "until": time.time() - 5}}}
        f3 = analyze(skills)
        apply_ledger(f3, snoozed)
        expect(any(c["fp"] == cluster_fp for c in f3["collision_clusters"]),
               "expired snooze resurfaces the finding")
        f4 = analyze(skills)
        compute_diff(f4, sd)
        expect(f4["diff"]["new_count"] > 0, "first snapshot: all findings new")
        f5 = analyze(skills)
        compute_diff(f5, sd)
        expect(f5["diff"]["new_count"] == 0 and f5["diff"]["resolved_count"] == 0,
               "second snapshot: no drift")
        mk(td, "brand-new", "Detect meteor shower peaks for astro planning sessions tonight.")
        f6 = analyze(gather_skills([td, td2], [pc]))
        compute_diff(f6, sd)
        expect(f6["diff"]["resolved_count"] == 0, "adding a skill resolves nothing")
        _pts, grade = score(f6)
        expect(grade in "ABCDF", "score yields a letter grade")
        expect(render_md(f6).startswith("# Skill Curator report"),
               "markdown report renders")

        # --- archive / restore ---
        ns = argparse.Namespace(root=[td, td2], plugin_cache=[], name="solo",
                                reason="test", fp="", no_plugins=True)
        rc = cmd_archive(ns)
        arch = os.path.join(td, ".archive", time.strftime("%Y%m%d"), "solo")
        expect(rc == 0 and os.path.isdir(arch) and
               os.path.isfile(os.path.join(arch, "curator-archive-manifest.json")),
               "archive moves dir and writes manifest")
        expect(not os.path.exists(os.path.join(td, "solo")),
               "archived skill gone from root")
        rc = cmd_restore(ns)
        expect(rc == 0 and os.path.isdir(os.path.join(td, "solo")) and
               not os.path.exists(arch), "restore round-trips")

        # --- probes + grade ---
        pd = os.path.join(croot, "probes-out")
        ns2 = argparse.Namespace(root=[td], plugin_cache=[], no_plugins=True,
                                 only=["jank-fixer", "frame-doctor"],
                                 out_dir=pd, max_per_skill=4)
        cmd_probes(ns2)
        probes = load_json(os.path.join(pd, "probes.json"), {})
        expect(any(p["text"] == "fix the jank" for p in probes["probes"]),
               "quoted phrase became a probe")
        expect(os.path.isfile(os.path.join(pd, "benchmark-scenarios.json")) and
               os.path.isfile(os.path.join(pd, "routing-sheet.md")),
               "benchmark scenarios + routing sheet emitted")
        res = os.path.join(croot, "results.jsonl")
        with open(res, "w") as fh:
            for p in probes["probes"]:
                sel = p["skill"] if p["skill"] == "jank-fixer" else "wrong-skill"
                fh.write(json.dumps({"probe_id": p["id"], "selected": sel}) + "\n")
        ns3 = argparse.Namespace(probes=os.path.join(pd, "probes.json"),
                                 results=res, state_dir=sd, codex_root=croot)
        rc = cmd_probes_grade(ns3)
        conf = load_json(os.path.join(sd, "skill-curator-confusion.json"), {})
        expect(rc == 0 and 0 < conf.get("accuracy", 0) < 1 and
               any(m["expected"] == "frame-doctor" for m in conf["worst"]),
               "confusion matrix graded and saved")

        # --- metric pack emit ---
        os.environ["PLUGIN_EVAL_TARGET"] = os.path.join(td2, "solo")
        os.environ["PLUGIN_EVAL_TARGET_KIND"] = "skill"
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        ns4 = argparse.Namespace(root=[td, td2], plugin_cache=[pc],
                                 no_plugins=False, extra=[])
        with redirect_stdout(buf):
            rc = cmd_metric_pack_emit(ns4)
        os.environ.pop("PLUGIN_EVAL_TARGET")
        os.environ.pop("PLUGIN_EVAL_TARGET_KIND")
        try:
            pack = json.loads(buf.getvalue())
        except ValueError:
            pack = {}
        expect(rc == 0 and any(c["id"].startswith("curator-dup-solo")
                               for c in pack.get("checks", [])),
               "metric pack emits duplicate-surface check for target")
        expect(all(k in c for c in pack.get("checks", [])
                   for k in ("id", "category", "severity", "status", "message")),
               "metric pack checks match plugin-eval contract fields")
        expect(any(m["id"] == "curator-inventory-trigger-tokens" and
                   m["band"] in ("good", "moderate", "heavy")
                   for m in pack.get("metrics", [])),
               "metric pack metrics carry good/moderate/heavy bands")

        # --- check gate ---
        ns5 = argparse.Namespace(root=[td, td2], plugin_cache=[pc],
                                 no_plugins=False, usage=False,
                                 codex_root=croot, claude_root=croot,
                                 state_dir=sd, all=False, grace_days=14,
                                 rebuild_usage=False, expect_used=None,
                                 expect_family=None, min_near_dupes=0,
                                 min_dead=0, max_trigger_tokens=1,
                                 max_new_findings=None, plugin_source=[])
        expect(cmd_check(ns5) == 1, "check fails when trigger budget exceeded")

        # --- plugin-level findings (v3) ---
        psrc = os.path.join(croot, "plugsrc")
        for pname, ver in (("driftplug", "1.4.0+build.20260101"),
                           ("steadyplug", "2.0.0"),
                           ("uninstalled", "0.1.0")):
            mdir = os.path.join(psrc, pname, ".codex-plugin")
            os.makedirs(mdir)
            with open(os.path.join(mdir, "plugin.json"), "w") as fh:
                json.dump({"name": pname, "version": ver}, fh)
        os.makedirs(os.path.join(psrc, "cache", "x", ".codex-plugin"),
                    exist_ok=True)  # cache/ subdir must be skipped as a source
        pcache = os.path.join(croot, "plugcache2")
        for mkt, pname, vers in (("mktA", "driftplug", ["1.2.0", "1.4.0"]),
                                 ("mktA", "steadyplug", ["2.0.0"]),
                                 ("mktB", "steadyplug", ["1.9.0"]),
                                 ("mktA-remote", "driftplug", ["0.1.0"])):
            for v in vers:
                os.makedirs(os.path.join(pcache, mkt, pname, v), exist_ok=True)
        # make 1.2.0 the NEWEST mtime for driftplug: active install is stale
        now_t = time.time()
        os.utime(os.path.join(pcache, "mktA", "driftplug", "1.4.0"),
                 (now_t - 9000, now_t - 9000))
        os.utime(os.path.join(pcache, "mktA", "driftplug", "1.2.0"),
                 (now_t, now_t))
        srcs = scan_plugin_sources(psrc)
        expect(sorted(s["name"] for s in srcs) ==
               ["driftplug", "steadyplug", "uninstalled"],
               "plugin sources discovered, cache/ dir skipped")
        cmap = scan_cache_plugins(pcache)
        expect(cmap[("mktA", "driftplug")]["newest"] == "1.2.0" and
               cmap[("mktA", "driftplug")]["versions"] == ["1.2.0", "1.4.0"],
               "cache versions listed, newest picked by mtime")
        fp_ = {}
        analyze_plugins(fp_, srcs, cmap)
        dr = {(d["name"], d["marketplace"]): d
              for d in fp_["plugin_version_drift"]}
        dp = dr.get(("driftplug", "mktA"))
        expect(dp is not None and dp["cache_version"] == "1.2.0"
               and dp["source_version"].startswith("1.4.0"),
               "source<->cache version drift detected (build metadata ignored)")
        expect(("steadyplug", "mktA") not in dr,
               "no false drift when base versions match")
        expect(("steadyplug", "mktB") in dr,
               "same plugin drifting in a SECOND marketplace still flagged")
        expect(not any(d["marketplace"] == "mktA-remote"
                       for d in fp_["plugin_version_drift"]),
               "remote mirror caches excluded from drift")
        pd_ = {d["name"] for d in fp_["duplicate_plugins"]}
        expect(pd_ == {"steadyplug"},
               "plugin installed from 2+ marketplaces flagged")
        st_ = {(s["name"], s["marketplace"]): s
               for s in fp_["stale_plugin_caches"]}
        expect(("driftplug", "mktA") in st_ and
               st_[("driftplug", "mktA")]["stale_versions"] == ["1.4.0"],
               "stale cached versions reported against the active one")
        expect(all(x.get("fp") for sec in ("plugin_version_drift",
                                           "duplicate_plugins",
                                           "stale_plugin_caches")
                   for x in fp_[sec]),
               "plugin findings carry ledger fingerprints")
        pts_before = score({"plugin_version_drift": [], "duplicate_plugins": [],
                            "stale_plugin_caches": []})[0]
        pts_after = score(fp_)[0]
        expect(pts_after < pts_before, "plugin findings lower the health score")
        fp_.update({"skill_count": 0, "surface_count": 0,
                    "context_cost_chars": 0, "context_cost_tokens": 0})
        md = render_md(fp_)
        expect("Plugin version drift" in md and "driftplug" in md and
               "DRIFT" in md.split("## ")[1],
               "drift renders and leads the Do-these-first list")
        # review fixes (2026-07-20 adversarial pass)
        psrc2 = os.path.join(croot, "plugsrc2")
        for pname, ver in (("driftplug", "1.4.0"), ("phantom", "unknown")):
            mdir = os.path.join(psrc2, pname, ".codex-plugin")
            os.makedirs(mdir)
            with open(os.path.join(mdir, "plugin.json"), "w") as fh:
                json.dump({"name": pname, "version": ver}, fh)
        fp2_ = {}
        analyze_plugins(fp2_, srcs + scan_plugin_sources(psrc2), cmap)
        d_mktA = [d for d in fp2_["plugin_version_drift"]
                  if (d["name"], d["marketplace"]) == ("driftplug", "mktA")]
        expect(len(d_mktA) == 1 and "+1 more copies" in d_mktA[0]["source_path"],
               "same-name source in 2 roots dedupes to one drift finding")
        expect(all(d["name"] != "phantom" for d in fp2_["plugin_version_drift"]),
               "source version 'unknown' emits no drift noise")
        nomkt = os.path.join(croot, "plugcache-nomkt")
        for pname in ("alphaplug", "betaplug"):
            vdir = os.path.join(nomkt, pname, "1.2.0", ".codex-plugin")
            os.makedirs(vdir)
            with open(os.path.join(vdir, "plugin.json"), "w") as fh:
                json.dump({"name": pname, "version": "1.2.0"}, fh)
        cm2 = scan_cache_plugins(nomkt)
        expect(set(cm2) == {("plugcache-nomkt", "alphaplug"),
                            ("plugcache-nomkt", "betaplug")},
               "marketplace-less cache layout keyed as plugins, not versions")
        fp3_ = {}
        analyze_plugins(fp3_, [], cm2)
        expect(fp3_["duplicate_plugins"] == [],
               "no false duplicate_plugins from marketplace-less layout")
        merged_cm = merge_cache_maps([
            {("m", "p"): {"versions": ["1.0.0"], "newest": "1.0.0",
                          "newest_mtime": 5.0, "path": "/a"}},
            {("m", "p"): {"versions": ["2.0.0"], "newest": "2.0.0",
                          "newest_mtime": 9.0, "path": "/b"}}])
        expect(merged_cm[("m", "p")]["versions"] == ["1.0.0", "2.0.0"] and
               merged_cm[("m", "p")]["newest"] == "2.0.0",
               "cache maps from 2 roots merge instead of clobbering")
        dupA, dupB = {}, {}
        analyze_plugins(dupA, [], {("m1", "dp"): {"versions": ["1.0"], "newest": "1.0",
                                                  "newest_mtime": 0, "path": "/x"},
                                   ("m2", "dp"): {"versions": ["1.0"], "newest": "1.0",
                                                  "newest_mtime": 0, "path": "/y"}})
        analyze_plugins(dupB, [], {("m1", "dp"): {"versions": ["1.0"], "newest": "1.0",
                                                  "newest_mtime": 0, "path": "/x"},
                                   ("m2", "dp"): {"versions": ["1.0"], "newest": "1.0",
                                                  "newest_mtime": 0, "path": "/y"},
                                   ("m3", "dp"): {"versions": ["1.0"], "newest": "1.0",
                                                  "newest_mtime": 0, "path": "/z"}})
        expect(dupA["duplicate_plugins"][0]["fp"] ==
               dupB["duplicate_plugins"][0]["fp"],
               "duplicate_plugins fp stable when a 3rd marketplace appears")
        expect(base_version("v1.2.3+meta") == "1.2.3" and
               base_version("Version2") == "Version2",
               "base_version strips one leading v before digits only")

    print(f"\nselftest: {total[0] - len(fails)}/{total[0]} passed")
    return 1 if fails else 0


# --- main -------------------------------------------------------------------

def add_common(sp, usage=True):
    sp.add_argument("--root", action="append", default=None,
                    help="skills root (repeatable; default: ~/.codex/skills "
                         "+ ~/.claude/skills that exist)")
    sp.add_argument("--plugin-cache", action="append", default=None,
                    help="plugin cache root (repeatable; default: "
                         "~/.claude/plugins/cache + ~/.codex/plugins/cache)")
    sp.add_argument("--no-plugins", action="store_true",
                    help="skip plugin cache + plugin source scanning")
    sp.add_argument("--plugin-source", action="append", default=None,
                    help="local plugin SOURCE root (repeatable; default: "
                         "~/.codex/plugins + ~/.claude/plugins, minus cache/)")
    sp.add_argument("--state-dir", default=None,
                    help="ledger/snapshot dir (default <codex-root>/cache)")
    if usage:
        sp.add_argument("--usage", action="store_true",
                        help="mine session logs for per-skill usage signals")
        sp.add_argument("--codex-root", default="~/.codex")
        sp.add_argument("--claude-root", default="~/.claude")
        sp.add_argument("--rebuild-usage", action="store_true")
        sp.add_argument("--grace-days", type=int, default=14)
    else:
        sp.add_argument("--codex-root", default="~/.codex")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    rp = sub.add_parser("report", help="scan all surfaces and print findings")
    add_common(rp)
    rp.add_argument("--json", action="store_true")
    rp.add_argument("--md", help="also write markdown report to this path")
    rp.add_argument("--all", action="store_true",
                    help="include rejected/snoozed findings")
    rp.set_defaults(fn=cmd_report)

    cp = sub.add_parser("check", help="assert findings (for CI/scheduled runs)")
    add_common(cp)
    cp.add_argument("--all", action="store_true")
    cp.add_argument("--expect-family", action="append")
    cp.add_argument("--min-near-dupes", type=int, default=0)
    cp.add_argument("--min-dead", type=int, default=0)
    cp.add_argument("--expect-used", action="append")
    cp.add_argument("--max-trigger-tokens", type=int, default=0,
                    help="fail if inventory trigger tokens exceed this budget")
    cp.add_argument("--max-new-findings", type=int, default=None,
                    help="fail if more than N findings are new since last run")
    cp.set_defaults(fn=cmd_check)

    dp = sub.add_parser("decide", help="record accept/reject/snooze for findings")
    dp.add_argument("fingerprint", nargs="+")
    dp.add_argument("--accept", action="store_true")
    dp.add_argument("--reject", action="store_true")
    dp.add_argument("--snooze-days", type=float, default=None)
    dp.add_argument("--note", default="")
    dp.add_argument("--state-dir", default=None)
    dp.add_argument("--codex-root", default="~/.codex")
    dp.set_defaults(fn=cmd_decide)

    lp = sub.add_parser("decisions", help="list recorded decisions")
    lp.add_argument("--state-dir", default=None)
    lp.add_argument("--codex-root", default="~/.codex")
    lp.set_defaults(fn=cmd_decisions)

    ap = sub.add_parser("archive", help="archive a skill (never delete)")
    ap.add_argument("name")
    ap.add_argument("--reason", default="")
    ap.add_argument("--fp", default="")
    add_common(ap, usage=False)
    ap.set_defaults(fn=cmd_archive)

    rsp = sub.add_parser("restore", help="restore an archived skill")
    rsp.add_argument("name")
    add_common(rsp, usage=False)
    rsp.set_defaults(fn=cmd_restore)

    pp = sub.add_parser("probes", help="emit routing probes + plugin-eval "
                                       "benchmark scenarios + routing sheet")
    add_common(pp, usage=False)
    pp.add_argument("--only", action="append",
                    help="limit to these skills (repeatable)")
    pp.add_argument("--out-dir", default="./curator-probes")
    pp.add_argument("--max-per-skill", type=int, default=6)
    pp.set_defaults(fn=cmd_probes)

    gp = sub.add_parser("probes-grade", help="grade routing results into a "
                                             "confusion matrix")
    gp.add_argument("--probes", required=True)
    gp.add_argument("--results", required=True)
    gp.add_argument("--state-dir", default=None)
    gp.add_argument("--codex-root", default="~/.codex")
    gp.set_defaults(fn=cmd_probes_grade)

    ep = sub.add_parser("emit-metric-pack",
                        help="write a plugin-eval metric pack manifest")
    ep.add_argument("--dir", default="./curator-metric-pack")
    add_common(ep, usage=False)
    ep.set_defaults(fn=cmd_emit_metric_pack)

    mp = sub.add_parser("metric-pack-emit",
                        help="internal: called by plugin-eval analyze")
    add_common(mp, usage=False)
    mp.add_argument("extra", nargs="*")
    mp.set_defaults(fn=cmd_metric_pack_emit)

    st = sub.add_parser("selftest", help="fixture-based regression test")
    st.set_defaults(fn=cmd_selftest)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
