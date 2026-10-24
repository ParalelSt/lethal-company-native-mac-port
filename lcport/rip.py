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
    shutil.rmtree(out_dir, ignore_errors=True); os.makedirs(out_dir, exist_ok=True)
    p = subprocess.Popen([exe, "--headless", "--port", str(PORT), "--log-path", os.path.join(config.WORK, "assetripper.log")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try: urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=2); break
            except Exception: time.sleep(1)
        # export game assemblies as DLLs (byte-identical IL for mods); package DLLs are replaced by real packages later
        _post("/Settings/Update", {"ScriptExportMode": "DllExportWithoutRenaming", "ScriptContentLevel": "Level2",
                                   "ShaderExportMode": "Dummy", "BundledAssetsExportMode": "DirectExport", "TextExportMode": "Parse",
                                   "AudioExportFormat": "Default", "ImageExportFormat": "Png", "LightmapTextureExportFormat": "Yaml",
                                   "SpriteExportMode": "Yaml", "ScriptLanguageVersion": "AutoSafe"})
        page = urllib.request.urlopen(f"http://127.0.0.1:{PORT}/Settings/Edit", timeout=30).read().decode()
        if 'value="DllExportWithoutRenaming" selected' not in page:
            raise RuntimeError("could not switch AssetRipper to DLL export mode")
        log("    loading game folder"); _post("/LoadFolder", {"Path": game_dir})
        log("    exporting Unity project"); _post("/Export/UnityProject", {"Path": out_dir})
    finally:
        p.terminate()
    proj = os.path.join(out_dir, "ExportedProject")
    if not os.path.isdir(os.path.join(proj, "Assets")): raise RuntimeError("AssetRipper export failed, see work/assetripper.log")
    return proj
