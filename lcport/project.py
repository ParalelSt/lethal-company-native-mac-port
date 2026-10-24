"""Turn the AssetRipper export into a buildable macOS Unity project (generic re-implementation of the hand-driven port)."""
import os, re, json, glob, shutil, zipfile, tarfile, io
from . import config, dotnetmeta, thirdparty
from .util import log, Step, md5
from . import remap_package_scripts as remap
from . import remap_shadergraph_materials as sgmat

PKG_RE = re.compile(rb"PackageCache[\\/](com\.unity\.[a-z0-9.-]+)@([0-9][0-9A-Za-z.+-]*)")
YAML_EXTS = (".unity", ".prefab", ".asset", ".controller", ".mat", ".playable", ".mixer", ".overrideController", ".anim", ".preset")
PLUGIN_META = """fileFormatVersion: 2
guid: %s
PluginImporter:
  externalObjects: {}
  serializedVersion: 2
  iconMap: {}
  executionOrder: {}
  defineConstraints: []
  isPreloaded: 0
  isOverridable: 0
  isExplicitlyReferenced: 0
  validateReferences: 0
  platformData:
  - first:
      Any: 
    second:
      enabled: 1
      settings: {}
  userData: 
  assetBundleName: 
  assetBundleVariant: 
"""

def _guid(meta): return re.search(r"guid: ([0-9a-f]{32})", open(meta).read()).group(1)

def detect_packages(plugins):
    pkgs = {}
    for dll in glob.glob(os.path.join(plugins, "*.dll")):
        n = os.path.basename(dll)
        if not n.startswith(("Unity.", "UnityEngine.")): continue
        m = PKG_RE.search(open(dll, "rb").read())
        if m: pkgs.setdefault(m.group(1).decode(), m.group(2).decode())
    return pkgs

def builtin_packages(editor_app):
    d = os.path.join(editor_app, "Contents", "Resources", "PackageManager", "BuiltInPackages")
    out = {}
    for p in glob.glob(os.path.join(d, "*", "package.json")):
        j = json.load(open(p)); out[j["name"]] = (j["version"], os.path.dirname(p))
    return out

def yaml_files(root):
    for dp, _, fs in os.walk(root):
        for f in fs:
            if f.endswith(YAML_EXTS): yield os.path.join(dp, f)

def replace_guids(proj, mapping):
    """Replace `guid: OLD` with `guid: NEW` across Assets yaml for every pair in mapping."""
    n = 0
    for p in yaml_files(os.path.join(proj, "Assets")):
        s = open(p, encoding="utf-8", errors="ignore").read(); o = s
        for a, b in mapping.items(): s = s.replace("guid: " + a + ",", "guid: " + b + ",")
        if s != o: open(p, "w", encoding="utf-8").write(s); n += 1
    return n

def shader_name(path):
    try:
        m = re.match(r'\s*Shader\s+"([^"]+)"', open(path, encoding="utf-8", errors="ignore").readline())
        return m.group(1) if m else None
    except Exception: return None

def assemble(proj, game_dir, editor_app, natives_dir):
    plugins = os.path.join(proj, "Assets", "Plugins")
    with Step("detect Unity packages from the shipped assemblies"):
        pkgs = detect_packages(plugins); builtin = builtin_packages(editor_app)
        log("    " + ", ".join(f"{k}@{v}" for k, v in sorted(pkgs.items())))
    with Step("write Packages/manifest.json"):
        deps = {}
        for name, ver in sorted(pkgs.items()):
            if name.startswith("com.unity.xr.") or name == "com.unity.profiling.core": continue  # XR unsupported on Mac; profiling comes as a dependency
            deps[name] = builtin[name][0] if name in builtin else ver
        deps["com.unity.ugui"] = builtin["com.unity.ugui"][0]
        for name, (ver, _) in builtin.items():
            if name.startswith("com.unity.modules."): deps[name] = ver
        json.dump({"dependencies": dict(sorted(deps.items()))}, open(os.path.join(proj, "Packages", "manifest.json"), "w"), indent=2)
    with Step("replace ripped package DLLs by real packages (record types for the reference remap)"):
        replaced = {}
        for dll in sorted(glob.glob(os.path.join(plugins, "*.dll"))):
            n = os.path.basename(dll)[:-4]
            if not n.startswith(("Unity.", "UnityEngine.")): continue
            replaced[n] = {"guid": _guid(dll + ".meta"), "types": dotnetmeta.types(dll)}
            os.remove(dll); os.remove(dll + ".meta")
        for extra in ("System.Runtime.CompilerServices.Unsafe.dll", "Newtonsoft.Json.dll"):
            p = os.path.join(plugins, extra)
            if os.path.exists(p) and (extra != "Newtonsoft.Json.dll" or "com.unity.services.core" in pkgs):
                os.remove(p); os.remove(p + ".meta")
        json.dump(replaced, open(os.path.join(config.WORK, "replaced_dlls.json"), "w"))
        log(f"    removed {len(replaced)} package assemblies")
    with Step("fetch package sources for script GUIDs"):
        pkgdirs = []
        for name, ver in deps.items():
            if name.startswith("com.unity.modules."): continue
            pkgdirs.append(builtin[name][1] if name in builtin else thirdparty.unity_package(name, ver))
        # dependencies that carry scripts but are not top-level (e.g. render-pipelines.core, shadergraph, hd-config)
        for name in ("com.unity.render-pipelines.core", "com.unity.shadergraph", "com.unity.render-pipelines.high-definition-config"):
            if name in builtin and builtin[name][1] not in pkgdirs: pkgdirs.append(builtin[name][1])
    with Step("remap MonoScript references to package scripts"):
        remap.run(proj, os.path.join(config.WORK, "replaced_dlls.json"), pkgdirs)
    with Step("Steamworks: Posix assembly, facade, retarget game assemblies"):
        for f in ("Facepunch.Steamworks.Win64.dll", "Facepunch.Steamworks.Win64.dll.meta", "Facepunch.Steamworks.Win32.dll", "Facepunch.Steamworks.Win32.dll.meta"):
            p = os.path.join(plugins, f)
            if os.path.exists(p): os.remove(p)
        for f in ("Facepunch.Steamworks.Posix.dll", "Facepunch.Steamworks.Posix.dll.meta"):
            shutil.copy2(os.path.join(thirdparty.PREBUILT, f), os.path.join(plugins, f))
        shutil.copy2(os.path.join(thirdparty.PREBUILT, "Facepunch.Steamworks.Win64.dll"), os.path.join(plugins, "Facepunch.Steamworks.Win64.dll"))
        open(os.path.join(plugins, "Facepunch.Steamworks.Win64.dll.meta"), "w").write(PLUGIN_META % "3f1c0d2e5b7a4c9e8d6f1a2b3c4d5e6f")
        for dll in glob.glob(os.path.join(plugins, "*.dll")):
            if dll.endswith(("Facepunch.Steamworks.Win64.dll", "Facepunch.Steamworks.Posix.dll")): continue
            if "Facepunch.Steamworks.Win64" in dotnetmeta.info(dll).get("assemblyRefs", []):
                n = dotnetmeta.retarget(dll, dll, "Facepunch.Steamworks.Win64", "Facepunch.Steamworks.Posix")
                log(f"    retargeted {os.path.basename(dll)} ({n})")
    with Step("macOS native plugins"):
        mac = os.path.join(plugins, "macOS"); os.makedirs(mac, exist_ok=True)
        for f in os.listdir(natives_dir):
            if f.endswith((".dylib", ".bundle")): shutil.copy2(os.path.join(natives_dir, f), os.path.join(mac, f))
    with Step("remove assets that collide with package-provided ones"):
        for f in ("UnityServicesProjectConfiguration.json",):
            p = os.path.join(proj, "Assets", "StreamingAssets", f)
            for q in (p, p + ".meta"):
                if os.path.exists(q): os.remove(q)
        hdrp = builtin.get("com.unity.render-pipelines.high-definition", (None, None))[1]
        if hdrp:
            guids = []
            for n in ("HDRenderPipelineRuntimeResources", "HDRenderPipelineEditorResources", "HDRenderPipelineRayTracingResources"):
                for m in glob.glob(os.path.join(hdrp, "**", n + ".cs.meta"), recursive=True): guids.append(_guid(m))
            for a in glob.glob(os.path.join(proj, "Assets", "**", "*.asset"), recursive=True):
                s = open(a, errors="ignore").read()
                if any(f"guid: {g}, type: 3" in s for g in guids):
                    os.remove(a); os.remove(a + ".meta") if os.path.exists(a + ".meta") else None; log(f"    removed {os.path.relpath(a, proj)}")
    with Step("TextMeshPro runtime shaders"):
        tmp_ver = pkgs.get("com.unity.textmeshpro")
        if tmp_ver:
            pkg = thirdparty.unity_package("com.unity.textmeshpro", tmp_ver)
            up = glob.glob(os.path.join(pkg, "Package Resources", "TMP Essential Resources.unitypackage"))
            if up:
                tmp_shaders = {}
                with tarfile.open(up[0]) as t:
                    members = {}
                    for m in t.getmembers():
                        parts = m.name.split("/")
                        if len(parts) >= 2: members.setdefault(parts[0], {})[parts[1]] = m
                    for g, d in members.items():
                        if "pathname" not in d: continue
                        path = t.extractfile(d["pathname"]).read().decode().split("\n")[0]
                        if not path.startswith("Assets/TextMesh Pro/Shaders/"): continue
                        dest = os.path.join(proj, path); os.makedirs(os.path.dirname(dest), exist_ok=True)
                        if "asset" in d: open(dest, "wb").write(t.extractfile(d["asset"]).read())
                        open(dest + ".meta", "wb").write(t.extractfile(d["asset.meta"]).read())
                        if dest.endswith(".shader"):
                            nm = shader_name(dest)
                            if nm: tmp_shaders[nm] = g
                mapping = {}
                for sh in glob.glob(os.path.join(proj, "Assets", "Shader", "*.shader")):
                    nm = shader_name(sh)
                    if nm in tmp_shaders:
                        mapping[_guid(sh + ".meta")] = tmp_shaders[nm]; os.remove(sh); os.remove(sh + ".meta")
                log(f"    remapped {len(mapping)} TMP shaders in {replace_guids(proj, mapping)} files")
    with Step("replacement shaders for unrecoverable full-screen effects"):
        for src in glob.glob(os.path.join(config.KIT, "unity", "Shaders", "*.shader")):
            nm = shader_name(src); target = None
            for sh in glob.glob(os.path.join(proj, "Assets", "Shader", "*.shader")):
                if shader_name(sh) == nm: target = sh; break
            shutil.copy2(src, target or os.path.join(proj, "Assets", "Shader", os.path.basename(src)))
            log(f"    {nm}: {'replaced' if target else 'added'}")
    with Step("materials on unrecoverable Shader Graphs -> HDRP/Lit"):
        sgmat.run(proj)
    with Step("project settings + editor tooling"):
        ps = os.path.join(proj, "ProjectSettings", "ProjectSettings.asset"); s = open(ps).read()
        s = re.sub(r"^  microphoneUsageDescription: *$", "  microphoneUsageDescription: Lethal Company uses the microphone for in-game voice chat.", s, flags=re.M)
        open(ps, "w").write(s)
        ed = os.path.join(proj, "Assets", "Editor", "PortTools"); os.makedirs(ed, exist_ok=True)
        for f in glob.glob(os.path.join(config.KIT, "unity", "Editor", "PortTools", "*.cs")): shutil.copy2(f, ed)
    return pkgs
