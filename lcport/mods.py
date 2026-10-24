"""Thunderstore mod manager for the macOS build (r2modman-compatible profile layout) with a Mac compatibility audit.

  mods profiles                      list profiles
  mods search <text>                 search Thunderstore (lethal-company)
  mods install <profile> <Author-Name>[-x.y.z] ...   install mods (+dependencies), then audit
  mods remove  <profile> <Author-Name>
  mods list    <profile>
  mods update  <profile>             update every installed mod to latest, then audit
  mods import  <profile> <code>      import an r2modman / Thunderstore profile share code, then audit
  mods audit   <profile>             classify mods: SHOULD WORK / AUTO-FIXED (MacShaderFix) / NEEDS FIXING
"""
import os, sys, json, time, io, zipfile, shutil, base64, urllib.request, re, tempfile
from . import config, dotnetmeta, thirdparty

INDEX_URL = "https://thunderstore.io/c/lethal-company/api/v1/package/"
UA = {"User-Agent": "lethal-company-mac-port/1.0"}
LOADER_FILES = {"winhttp.dll", "doorstop_config.ini", ".doorstop_version", "run_bepinex.sh", "libdoorstop_x64.so", "libdoorstop.dylib"}

def http(url, binary=False):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r: return r.read() if binary else r.read().decode()

def index():
    os.makedirs(config.CACHE, exist_ok=True); p = os.path.join(config.CACHE, "thunderstore-index.json")
    if os.path.exists(p) and time.time() - os.path.getmtime(p) < 3600: return json.load(open(p))
    print("fetching Thunderstore package index...", flush=True)
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

def download(v):
    p = os.path.join(config.CACHE, "mods", v["full_name"] + ".zip"); os.makedirs(os.path.dirname(p), exist_ok=True)
    if not os.path.exists(p):
        print(f"  downloading {v['full_name']}", flush=True); open(p, "wb").write(http(v["download_url"], binary=True))
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

def install(profile, refs, pinned=None):
    idx = by_name(index()); bep = profile_dir(profile); man = load_manifest(profile)
    queue = list(refs); done = set()
    while queue:
        ref = queue.pop(0); name, ver = split_ref(ref)
        if name in done: continue
        if name not in idx: raise SystemExit(f"unknown package {name}")
        if pinned and name in pinned: ver = pinned[name]
        v = pick_version(idx[name], ver); done.add(name); have = man.get(name)
        if have and vtuple(have) >= vtuple(v["version_number"]) and not (pinned and name in pinned):
            print(f"  {name} {have} already installed")
        else:
            print(f"installing {name} {v['version_number']}", flush=True)
            extract_mod(download(v), bep, name); man[name] = v["version_number"]
        for dep in v["dependencies"]:
            dn, _ = split_ref(dep)
            if dn not in done: queue.append(dep if not pinned else dn)
    save_manifest(profile, man); print(f"profile '{profile}': {len(man)} mods")

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
    print(f"profile code lists {len(pinned)} enabled mods")
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
        os.makedirs(config.PROFILES, exist_ok=True)
        rp = os.path.join(config.PROFILES, name_safe(profile) + "-audit.txt"); open(rp, "w").write(report); print(f"(saved to {rp})")
    return fix

def name_safe(s): return re.sub(r"[^A-Za-z0-9_.-]", "_", s)

def main(a):
    if not a or a[0] in ("-h", "--help"): print(__doc__); return
    cmd = a[0]
    if cmd == "profiles":
        os.makedirs(config.PROFILES, exist_ok=True)
        for p in sorted(os.listdir(config.PROFILES)):
            if os.path.isdir(os.path.join(config.PROFILES, p)): print(f"  {p}: {len(load_manifest(p))} mods")
    elif cmd == "search":
        q = " ".join(a[1:]).lower()
        hits = sorted([p for p in index() if q in p["full_name"].lower() or q in p["versions"][0]["description"].lower()], key=lambda p: -p["rating_score"])
        for p in hits[:25]: print(f"  {p['full_name']:45s} {p['versions'][0]['version_number']:10s} {p['rating_score']:5d}  {p['versions'][0]['description'][:60]}")
    elif cmd == "install": install(a[1], a[2:]); audit(a[1])
    elif cmd == "remove": remove(a[1], a[2])
    elif cmd == "list":
        for n, v in sorted(load_manifest(a[1]).items()): print(f"  {n} {v}")
    elif cmd == "update": install(a[1], list(load_manifest(a[1]).keys())); audit(a[1])
    elif cmd == "import": import_code(a[1], a[2]); audit(a[1])
    elif cmd == "audit": audit(a[1])
    else: print(__doc__)

if __name__ == "__main__": main(sys.argv[1:])
