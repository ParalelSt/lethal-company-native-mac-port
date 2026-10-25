"""Run AssetRipper headless against the game folder and export a Unity project (DLL export mode)."""
import os, time, urllib.request, urllib.parse, subprocess, shutil
from . import config
from .util import log, Step
from .thirdparty import assetripper

PORT = 8097
def _post(path, data):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=urllib.parse.urlencode(data).encode(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=7200) as r: return r.status
    except urllib.error.HTTPError as e: return e.code

def export(game_dir, out_dir):
    exe = assetripper()
    if os.path.isdir(os.path.join(out_dir, "ExportedProject", "Assets")):
        log("    rip already present, skipping"); return os.path.join(out_dir, "ExportedProject")
    # start clean but keep Unity's Library (shader cache) from a previous build: it makes rebuilds much faster
    proj = os.path.join(out_dir, "ExportedProject"); lib = os.path.join(proj, "Library"); keep = os.path.join(out_dir, "..", "Library.keep")
    if os.path.isdir(lib): shutil.move(lib, keep)
    shutil.rmtree(out_dir, ignore_errors=True); os.makedirs(proj, exist_ok=True)
    if os.path.isdir(keep): shutil.move(keep, lib)
    p = subprocess.Popen([exe, "--headless", "--port", str(PORT), "--log-path", os.path.join(config.WORK, "assetripper.log")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try: urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=2); break
            except Exception: time.sleep(1)
        # Hybrid: game code is decompiled to C# (Unity only binds scene data to scripts it compiles itself);
        # the original assemblies are swapped back into the built app afterwards so mods see identical IL
        _post("/Settings/Update", {"ScriptExportMode": "Hybrid", "ScriptContentLevel": "Level2",
                                   "ShaderExportMode": "Dummy", "BundledAssetsExportMode": "DirectExport", "TextExportMode": "Parse",
                                   "AudioExportFormat": "Default", "ImageExportFormat": "Png", "LightmapTextureExportFormat": "Yaml",
                                   "SpriteExportMode": "Yaml", "ScriptLanguageVersion": "AutoSafe"})
        page = urllib.request.urlopen(f"http://127.0.0.1:{PORT}/Settings/Edit", timeout=30).read().decode()
        if 'value="Hybrid" selected' not in page:
            raise RuntimeError("could not switch AssetRipper to Hybrid script export mode")
        log("    loading game folder"); _post("/LoadFolder", {"Path": game_dir})
        log("    exporting Unity project"); _post("/Export/UnityProject", {"Path": out_dir})
    finally:
        p.terminate()
    proj = os.path.join(out_dir, "ExportedProject")
    if not os.path.isdir(os.path.join(proj, "Assets")): raise RuntimeError("AssetRipper export failed, see work/assetripper.log")
    return proj
