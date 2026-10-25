"""Thunderstore mod manager for the macOS build (r2modman-compatible profile layout) with a Mac compatibility audit.

  mods profiles                      list profiles
  mods delete-profile <name>         delete a profile and its mods (never the last one)
  mods search <text>                 search Thunderstore (lethal-company)
  mods install <profile> <Author-Name>[-x.y.z] ...   install mods (+dependencies), then audit
  mods remove  <profile> <Author-Name>
  mods list    <profile>
  mods update  <profile>             update every installed mod to latest, then audit
  mods import  <profile> <code>      import an r2modman / Thunderstore profile share code, then audit
  mods audit   <profile>             classify mods: SHOULD WORK / AUTO-FIXED (MacShaderFix) / NEEDS FIXING
  mods apply   <profile> --install <names...> --remove <names...>   batch change: removes first, then installs, then audit
  mods json-search [--installed <profile>] <text>   JSON search results for the launcher
  mods json-info <Author-Name>       JSON details (dependencies, website, versions) for one package
  mods json-installed <profile>      JSON installed mods + saved audit
"""
import os, sys, json, time, io, zipfile, shutil, base64, urllib.request, re, tempfile
from . import config, dotnetmeta, thirdparty
from .util import status as say_status, progress as say_progress, done as say_done  # launcher control lines

INDEX_URL = "https://thunderstore.io/c/lethal-company/api/v1/package/"
UA = {"User-Agent": "lethal-company-mac-port/1.0"}
LOADER_FILES = {"winhttp.dll", "doorstop_config.ini", ".doorstop_version", "run_bepinex.sh", "libdoorstop_x64.so", "libdoorstop.dylib"}

def http(url, binary=False):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r: return r.read() if binary else r.read().decode()

def index():
    os.makedirs(config.CACHE, exist_ok=True); p = os.path.join(config.CACHE, "thunderstore-index.json")
    if os.path.exists(p) and time.time() - os.path.getmtime(p) < 3600: return json.load(open(p))
    print("fetching Thunderstore package index...", file=sys.stderr, flush=True)
    data = json.loads(http(INDEX_URL)); json.dump(data, open(p, "w")); return data

def by_name(idx): return {p["full_name"]: p for p in idx}
def vtuple(v): return tuple(int(x) for x in v.split("."))
def split_ref(ref):
    m = re.match(r"^(.+?-[^-]+?)-(\d+\.\d+\.\d+)$", ref); return (m.group(1), m.group(2)) if m else (ref, None)
def pick_version(pkg, ver):
    if ver is None: return pkg["versions"][0]
    for v in pkg["versions"]:
        if v["version_number"] == ver: return v
    raise SystemExit(f"{pkg['full_name']}: version {ver} not found")

def profile_dir(name):
    d = os.path.join(config.PROFILES, name, "BepInEx")
    for sub in ("plugins", "patchers", "config", "core"): os.makedirs(os.path.join(d, sub), exist_ok=True)
    src = os.path.join(thirdparty.bepinex(), "BepInEx", "core")
    for f in os.listdir(src):
        t = os.path.join(d, "core", f)
        if not os.path.exists(t) or os.path.getmtime(t) < os.path.getmtime(os.path.join(src, f)): shutil.copy2(os.path.join(src, f), t)
    fd = os.path.join(d, "plugins", "MacShaderFix"); os.makedirs(fd, exist_ok=True)
    shutil.copy2(os.path.join(thirdparty.PREBUILT, "MacShaderFix.dll"), os.path.join(fd, "MacShaderFix.dll"))
    return d

def manifest_path(name): return os.path.join(config.PROFILES, name, "mods.json")
def load_manifest(name): return json.load(open(manifest_path(name))) if os.path.exists(manifest_path(name)) else {}
def save_manifest(name, m): json.dump(m, open(manifest_path(name), "w"), indent=1)

def download(v, span=None):
    """Fetch a mod zip into the cache in 64 KiB chunks. With a span (start_pct, end_pct) and a known Content-Length,
    emit ##progress lines moving from start to end as the bytes arrive."""
    p = os.path.join(config.CACHE, "mods", v["full_name"] + ".zip"); os.makedirs(os.path.dirname(p), exist_ok=True)
    if os.path.exists(p): return p
    print(f"  downloading {v['full_name']}", flush=True)
    req = urllib.request.Request(v["download_url"], headers=UA); tmp = p + ".part"
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        try: total = int(r.headers.get("Content-Length") or 0)
        except (TypeError, ValueError): total = 0
        got = 0
        while True:
            chunk = r.read(65536)
            if not chunk: break
            f.write(chunk); got += len(chunk)
            if span and total: say_progress(span[0] + (span[1] - span[0]) * min(1.0, got / total))
    os.replace(tmp, p)
    return p

def extract_mod(zip_path, bep, full_name):
    """r2modman layout: BepInEx/{plugins,patchers,config,core} map 1:1; anything else under plugins/<Author-Name>/."""
    dest_plugin = os.path.join(bep, "plugins", full_name); shutil.rmtree(dest_plugin, ignore_errors=True)
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            if info.is_dir(): continue
            parts = info.filename.replace("\\", "/").split("/")
            if "BepInEx" in parts:
                parts = parts[parts.index("BepInEx") + 1:]
                if not parts: continue
            low = [x.lower() for x in parts]
            if low[0] == "core" and full_name == "BepInEx-BepInExPack": continue  # the universal macOS core is used instead
            if low[0] in ("plugins", "patchers", "config", "core"):
                target = os.path.join(bep, low[0], *parts[1:]) if low[0] in ("config", "core") else os.path.join(bep, low[0], full_name, *parts[1:])
            elif low[0] in ("manifest.json", "readme.md", "changelog.md", "icon.png", "license", "license.md", "license.txt"):
                target = os.path.join(dest_plugin, parts[0])
            elif parts[-1].lower() in LOADER_FILES: continue
            else: target = os.path.join(dest_plugin, *parts)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(info) as s, open(target, "wb") as d: shutil.copyfileobj(s, d)

def install(profile, refs, pinned=None, span=(0, 90)):
    """span: the part of the launcher's progress bar (percent) this install fills, one share per package.
    The total grows when dependencies join the queue; progress is clamped so it never goes backwards."""
    idx = by_name(index()); bep = profile_dir(profile); man = load_manifest(profile)
    queue = list(refs); done = set(); high = [span[0]]
    def report(pct): high[0] = max(high[0], pct); say_progress(high[0])
    while queue:
        ref = queue.pop(0); name, ver = split_ref(ref)
        if name in done: continue
        n = len(done) + len({split_ref(r)[0] for r in queue} - done - {name}) + 1
        i = len(done); lo = span[0] + (span[1] - span[0]) * i / n; hi = span[0] + (span[1] - span[0]) * (i + 1) / n
        lo = max(lo, high[0]); hi = max(hi, lo)  # never behind what was already reported
        report(lo)
        if name not in idx: raise SystemExit(f"unknown package {name}")
        if pinned and name in pinned: ver = pinned[name]
        v = pick_version(idx[name], ver); done.add(name); have = man.get(name)
        if have and vtuple(have) >= vtuple(v["version_number"]) and not (pinned and name in pinned):
            print(f"  {name} {have} already installed")
        else:
            short = f"{name.split('-', 1)[-1]} {v['version_number']} ({i + 1} of {n})"
            print(f"installing {name} {v['version_number']}", flush=True); say_status(f"Downloading {short}")
            mid = lo + (hi - lo) * 0.85
            path = download(v, (lo, mid))
            report(mid); say_status(f"Installing {short}")
            extract_mod(path, bep, name); man[name] = v["version_number"]
        report(hi)
        for dep in v["dependencies"]:
            dn, _ = split_ref(dep)
            if dn not in done: queue.append(dep if not pinned else dn)
    save_manifest(profile, man); print(f"profile '{profile}': {len(man)} mods"); report(span[1])

def remove(profile, name):
    bep = profile_dir(profile); man = load_manifest(profile)
    for area in ("plugins", "patchers"): shutil.rmtree(os.path.join(bep, area, name), ignore_errors=True)
    man.pop(name, None); save_manifest(profile, man); print("removed", name)

def import_code(profile, code):
    raw = http(f"https://thunderstore.io/api/experimental/legacyprofile/get/{code}/")
    if not raw.startswith("#r2modman"): raise SystemExit("not a Thunderstore/r2modman profile code")
    z = zipfile.ZipFile(io.BytesIO(base64.b64decode(raw.split("\n", 1)[1])))
    r2x = z.read("export.r2x").decode()
    mods = re.findall(r"- name: (\S+)\n\s+version:\n\s+major: (\d+)\n\s+minor: (\d+)\n\s+patch: (\d+)\n\s+enabled: (\w+)", r2x)
    pinned = {n: f"{a}.{b}.{c}" for n, a, b, c, en in mods if en.lower() == "true"}
    print(f"profile code lists {len(pinned)} enabled mods"); say_status(f"importing {len(pinned)} mods")
    install(profile, [f"{n}-{v}" for n, v in pinned.items()], pinned=pinned)
    bep = profile_dir(profile)
    for info in z.infolist():
        if info.filename.startswith("config/") and not info.is_dir():
            t = os.path.join(bep, info.filename); os.makedirs(os.path.dirname(t), exist_ok=True); open(t, "wb").write(z.read(info))

# ---------------- audit ----------------
def is_unityfs(path):
    try:
        with open(path, "rb") as f: return f.read(7) == b"UnityFS"
    except Exception: return False

def scan_bundle(path):
    import UnityPy
    from UnityPy.enums import ShaderCompilerPlatform
    r = {"shaders": [], "materials": 0}
    try:
        env = UnityPy.load(path)
        for o in env.objects:
            if o.type.name == "Material": r["materials"] += 1
            elif o.type.name == "Shader":
                try:
                    sh = o.read(); plats = []
                    for p in getattr(sh, "platforms", []) or []:
                        try: plats.append(ShaderCompilerPlatform(p).name)
                        except Exception: plats.append(str(p))
                    r["shaders"].append({"name": sh.m_ParsedForm.m_Name, "platforms": plats})
                except Exception: pass
        r["d3d_only"] = [s["name"] for s in r["shaders"] if s["platforms"] and "kShaderCompPlatformMetal" not in s["platforms"]]
    except Exception as e: r["error"] = str(e)[:100]
    return r

def game_shaders():
    p = os.path.join(config.WORK, "game-shaders.json")
    return set(json.load(open(p))) if os.path.exists(p) else set()

def audit(profile, save=True):
    say_status("checking the mods for Mac compatibility")
    bep = profile_dir(profile); man = load_manifest(profile)
    managed = os.path.join(config.APP_DST, "Contents", "Resources", "Data", "Managed")
    available = {f[:-4] for f in os.listdir(managed) if f.endswith(".dll")} if os.path.isdir(managed) else set()
    available |= {f[:-4] for f in os.listdir(os.path.join(bep, "core")) if f.endswith(".dll")}
    available |= {"mscorlib", "System", "System.Core", "netstandard", "System.Xml", "System.Runtime", "System.Data", "System.Numerics", "System.IO.Compression", "System.Xml.Linq", "System.Net.Http", "Mono.Posix", "Mono.Security"}
    mods = {}
    for area in ("plugins", "patchers"):
        for name in sorted(os.listdir(os.path.join(bep, area))):
            d = os.path.join(bep, area, name)
            if not os.path.isdir(d): continue
            files = [os.path.join(dp, f) for dp, _, fs in os.walk(d) for f in fs]
            if name == "MacShaderFix" or (name not in man and not any(f.lower().endswith(".dll") for f in files)): continue
            m = mods.setdefault(name, {"dlls": [], "bundles": []})
            for f in files:
                if f.lower().endswith(".dll"): m["dlls"].append(f)
                elif is_unityfs(f): m["bundles"].append(f)
    tmp = tempfile.mkdtemp(prefix="lcaudit"); gs = game_shaders()
    infos = {f: dotnetmeta.info(f) for m in mods.values() for f in m["dlls"]}
    for d in infos.values():
        if d.get("managed") and d.get("assemblyName"): available.add(d["assemblyName"])
    def shader_note(r, label):
        d3d = sorted(set(r.get("d3d_only", [])))
        if not d3d: return None, None
        custom = [n for n in d3d if n not in gs and "FallbackError" not in n]
        if custom: return None, f"{label}: custom shaders fall back to HDRP/Lit (may look wrong): {', '.join(custom[:6])}"
        return f"{label}: standard shaders remapped at runtime", None
    ok, auto, fix = [], [], []
    for name, m in sorted(mods.items()):
        reasons, autonotes, notes = [], [], []
        for f in m["dlls"]:
            d = infos[f]; base = os.path.basename(f)
            if not d.get("managed"): reasons.append(f"Windows native library {base} ({d.get('machine')})"); continue
            missing = [a for a in d.get("assemblyRefs", []) if a not in available and not a.startswith(("UnityEngine", "Unity.", "System", "Microsoft", "MMHOOK_"))]
            if missing: notes.append(f"{base}: optional references to other mods not installed: {', '.join(missing)}")
            pinv = [x for x in d.get("moduleRefs", []) if x != "__Internal"]
            if pinv: reasons.append(f"{base} calls native code directly: {', '.join(pinv)}")
            for b in dotnetmeta.embedded_bundles(f, tmp):
                a, c = shader_note(scan_bundle(b), f"embedded bundle {os.path.basename(b).split('__', 1)[-1]}")
                if a: autonotes.append(a)
                if c: autonotes.append(c)
        for b in m["bundles"]:
            r = scan_bundle(b)
            if r.get("error"): reasons.append(f"asset bundle {os.path.basename(b)} could not be read"); continue
            a, c = shader_note(r, f"bundle {os.path.basename(b)}")
            if a: autonotes.append(a)
            if c: autonotes.append(c)
        ver = man.get(name, "?")
        if reasons: fix.append((name, ver, reasons + autonotes + notes))
        elif autonotes: auto.append((name, ver, autonotes + notes))
        else: ok.append((name, ver, notes))
    shutil.rmtree(tmp, ignore_errors=True)
    lines = [f"Mod audit for profile '{profile}' ({len(mods)} mods)", ""]
    for title, group in (("SHOULD WORK ON MAC", ok), ("AUTO-FIXED BY MacShaderFix", auto), ("NEEDS FIXING", fix)):
        lines.append(f"{title} ({len(group)}):")
        for n, v, rs in group:
            lines.append(f"  {n} {v}")
            for r in rs: lines.append(f"      - {r}")
        lines.append("")
    report = "\n".join(lines); print(report)
    if save:
        os.makedirs(os.path.join(config.PROFILES, profile), exist_ok=True)
        rp = os.path.join(config.PROFILES, profile, "audit.txt"); open(rp, "w").write(report)
        js = {}
        for grp, items in (("ok", ok), ("auto", auto), ("fix", fix)):
            for n, v, rs in items: js[n] = {"group": grp, "version": v, "notes": rs}
        json.dump(js, open(os.path.join(config.PROFILES, profile, "audit.json"), "w"), indent=1)
        print(f"(saved to {rp})")
    return fix

def name_safe(s): return re.sub(r"[^A-Za-z0-9_.-]", "_", s)

def catalog():
    """Slim copy of the Thunderstore index (only what the launcher shows), cached next to it so JSON queries skip parsing ~350 MB."""
    os.makedirs(config.CACHE, exist_ok=True)
    p = os.path.join(config.CACHE, "thunderstore-catalog.json"); src = os.path.join(config.CACHE, "thunderstore-index.json")
    if os.path.exists(p) and time.time() - os.path.getmtime(p) < 3600 and (not os.path.exists(src) or os.path.getmtime(src) <= os.path.getmtime(p)):
        try:
            with open(p) as f: return json.load(f)
        except Exception: pass
    out = []
    for pk in index():
        if pk.get("is_deprecated") or not pk.get("versions"): continue
        v = pk["versions"][0]
        out.append({"full_name": pk["full_name"], "name": pk["name"], "owner": pk["owner"], "version": v["version_number"],
                    "downloads": sum(x.get("downloads", 0) for x in pk["versions"]), "rating": pk.get("rating_score", 0),
                    "description": v.get("description", ""), "categories": pk.get("categories", []), "icon": v.get("icon", ""),
                    "website": v.get("website_url") or pk.get("website_url", ""), "dependencies": v.get("dependencies", []),
                    "date_updated": pk.get("date_updated", ""), "versions": [x["version_number"] for x in pk["versions"][:10]]})
    tmp = f"{p}.{os.getpid()}.tmp"
    with open(tmp, "w") as f: json.dump(out, f)
    os.replace(tmp, p)
    return out

SEARCH_FIELDS = ("full_name", "name", "owner", "version", "downloads", "rating", "description", "categories", "icon", "website")

def json_search(query, limit=300, only=None):
    """Packages matching query (name or description), most downloaded first. only: restrict to these full names (e.g. installed mods)."""
    q = query.lower().strip(); out = []
    for p in catalog():
        if only is not None and p["full_name"] not in only: continue
        if q and q not in p["full_name"].lower() and q not in p["description"].lower(): continue
        out.append({k: p[k] for k in SEARCH_FIELDS})
    out.sort(key=lambda x: -x["downloads"])
    return out[:limit]

def json_info(full_name):
    for p in catalog():
        if p["full_name"] == full_name:
            return {"full_name": full_name, "dependencies": p["dependencies"], "website": p["website"], "date_updated": p["date_updated"], "versions": p["versions"][:10]}
    return {"error": "unknown"}

def parse_apply(a):
    """apply <profile> --install A B --remove C D  ->  (profile, [A, B], [C, D]); either list may be empty or missing."""
    if not a or a[0].startswith("--"): raise SystemExit("usage: mods apply <profile> --install <names...> --remove <names...>")
    profile, lists, cur = a[0], {"--install": [], "--remove": []}, None
    for x in a[1:]:
        if x in lists: cur = x
        elif cur is None: raise SystemExit(f"apply: unexpected argument {x} (use --install / --remove)")
        else: lists[cur].append(x)
    return profile, lists["--install"], lists["--remove"]

def apply(profile, installs, removes):
    total = len(installs) + len(removes)
    print(f"applying {total} change(s) to profile '{profile}': {len(installs)} to install, {len(removes)} to remove", flush=True)
    cut = 90 * len(removes) / max(1, total)  # removes, then installs share the bar up to 90%; the audit fills the rest
    for i, name in enumerate(removes, 1):
        say_status(f"removing {name.split('-', 1)[-1]}"); say_progress(cut * (i - 1) / len(removes))
        print(f"[{i}/{total}] removing {name}", flush=True); remove(profile, name)
    if installs:
        print(f"[{len(removes) + 1}-{total}/{total}] installing {', '.join(installs)}", flush=True); install(profile, installs, span=(cut, 90))
    say_progress(90); audit(profile, save=True)

def delete_profile(name):
    """Remove a profile folder; refuses a missing profile, a name that escapes PROFILES, and the last remaining profile. Returns the exit code."""
    names = [p for p in (os.listdir(config.PROFILES) if os.path.isdir(config.PROFILES) else []) if os.path.isdir(os.path.join(config.PROFILES, p))]
    if not name or name in (".", "..") or "/" in name or name not in names: print(f"no such profile: {name}"); return 1
    if len(names) <= 1: print(f"cannot delete {name}: it is the only profile"); return 1
    shutil.rmtree(os.path.join(config.PROFILES, name)); print(f"deleted profile {name}"); say_done(f"Deleted profile {name}"); return 0

def main(a):
    if not a or a[0] in ("-h", "--help"): print(__doc__); return
    cmd = a[0]
    if cmd == "json-search":
        rest, only = a[1:], None
        if rest[:1] == ["--installed"]: only, rest = set(load_manifest(rest[1])), rest[2:]
        print(json.dumps(json_search(" ".join(rest), only=only))); return
    if cmd == "json-info": print(json.dumps(json_info(a[1]))); return
    if cmd == "json-installed":
        prof = a[1]; ap = os.path.join(config.PROFILES, prof, "audit.json")
        aud = json.load(open(ap)) if os.path.exists(ap) else {}
        print(json.dumps({"installed": load_manifest(prof), "audit": aud})); return
    if cmd == "profiles":
        os.makedirs(config.PROFILES, exist_ok=True)
        for p in sorted(os.listdir(config.PROFILES)):
            if os.path.isdir(os.path.join(config.PROFILES, p)): print(f"  {p}: {len(load_manifest(p))} mods")
    elif cmd == "delete-profile":
        sys.exit(delete_profile(a[1] if len(a) > 1 else ""))
    elif cmd == "search":
        q = " ".join(a[1:]).lower()
        hits = sorted([p for p in index() if q in p["full_name"].lower() or q in p["versions"][0]["description"].lower()], key=lambda p: -p["rating_score"])
        for p in hits[:25]: print(f"  {p['full_name']:45s} {p['versions'][0]['version_number']:10s} {p['rating_score']:5d}  {p['versions'][0]['description'][:60]}")
    elif cmd == "install": install(a[1], a[2:]); audit(a[1], save=True); say_done("Mods installed")
    elif cmd == "remove": say_status(f"removing {a[2].split('-', 1)[-1]}"); remove(a[1], a[2]); say_done(f"Removed {a[2].split('-', 1)[-1]}")
    elif cmd == "list":
        for n, v in sorted(load_manifest(a[1]).items()): print(f"  {n} {v}")
    elif cmd == "update": install(a[1], list(load_manifest(a[1]).keys())); audit(a[1], save=True); say_done("Mods up to date")
    elif cmd == "import": import_code(a[1], a[2]); audit(a[1], save=True); say_done("Profile imported")
    elif cmd == "apply": apply(*parse_apply(a[1:])); say_done("Changes applied")
    elif cmd == "audit": audit(a[1]); say_done("Mod check finished")
    else: print(__doc__)

if __name__ == "__main__": main(sys.argv[1:])
