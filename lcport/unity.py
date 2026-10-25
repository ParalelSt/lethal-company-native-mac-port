"""Locate the Unity editor and run the batch-mode steps (import, shader/material fixes, video transcode, build)."""
import os, re, glob
from . import config
from .util import run, log, Step, progress_steps

def editor_for(version):
    app = os.path.join(config.UNITY_EDITORS, version, "Unity.app")
    return app if os.path.exists(os.path.join(app, "Contents", "MacOS", "Unity")) else None

def game_unity_version(game_dir):
    data = glob.glob(os.path.join(game_dir, "*_Data", "globalgamemanagers"))
    if not data: raise RuntimeError("not a Unity game folder (no *_Data/globalgamemanagers)")
    m = re.search(rb"(20\d\d\.\d+\.\d+[a-z]\d+)", open(data[0], "rb").read(4096))
    if not m: raise RuntimeError("could not read the Unity version from the game")
    return m.group(1).decode()

def batch(editor_app, proj, logname, method=None, build_path=None, timeout=7200):
    exe = os.path.join(editor_app, "Contents", "MacOS", "Unity")
    logf = os.path.join(config.WORK, "logs", logname + ".log"); os.makedirs(os.path.dirname(logf), exist_ok=True)
    cmd = [exe, "-batchmode", "-quit", "-buildTarget", "OSXUniversal", "-projectPath", proj, "-logFile", logf]
    if method: cmd += ["-executeMethod", method]
    if build_path: cmd += ["-buildPath", build_path]
    r = run(cmd, check=False, timeout=timeout)
    text = open(logf, errors="ignore").read() if os.path.exists(logf) else ""
    errs = sorted(set(re.findall(r"error CS\d+: .*", text)))[:5]
    if errs: raise RuntimeError("Unity script compile errors:\n" + "\n".join(errs))
    if "No valid Unity Editor license" in text or "License" in text and "not activated" in text:
        raise RuntimeError("Unity has no valid licence. Open Unity Hub, sign in (free Personal licence), then rerun.")
    if build_path and "Build Finished, Result: Success" not in text:
        m = re.search(r"error: (.*)", text) or re.search(r"System\.\w+Exception: (.*)", text)
        raise RuntimeError("Unity build failed: " + (m.group(1)[:300] if m else f"see {logf}"))
    return logf

FULL_BUILD_STEPS = 5      # Unity batch steps
GAME_STEPS = 2            # extra steps when game_dir is given

def full_build(editor_app, proj, out_app, game_dir=None):
    with progress_steps(FULL_BUILD_STEPS + (GAME_STEPS if game_dir else 0)):
        _full_build(editor_app, proj, out_app, game_dir)
    return out_app

def _full_build(editor_app, proj, out_app, game_dir):
    with Step("Unity: import project and resolve packages (first import takes a while)", status="Importing the project into Unity"):
        batch(editor_app, proj, "unity-import")
    with Step("Unity: point materials at package shaders", status="Fixing material shaders"):
        batch(editor_app, proj, "unity-fixshaders", "FixPackageShaders.Run")
    with Step("Unity: validate HDRP materials", status="Checking materials"):
        batch(editor_app, proj, "unity-validate", "ValidateHdrpMaterials.Run")
    with Step("Unity: enable video transcoding", status="Preparing videos"):
        batch(editor_app, proj, "unity-transcode", "TranscodeVideos.Run")
    with Step("Unity: build the macOS app (compiles every shader for Metal; 30-60 min)", status="Compiling shaders and building the app (30-60 min)"):
        batch(editor_app, proj, "unity-build", "BuildMac.Build", build_path=out_app)
    if game_dir:
        with Step("ship the game's original assemblies (byte-identical IL for mods)", status="Adding the game's original code"):
            from . import dotnetmeta
            managed = glob.glob(os.path.join(game_dir, "*_Data", "Managed"))[0]
            dst = os.path.join(out_app, "Contents", "Resources", "Data", "Managed")
            for name in ("Assembly-CSharp.dll", "Assembly-CSharp-firstpass.dll"):
                src = os.path.join(managed, name)
                if not os.path.exists(src): continue
                n = dotnetmeta.retarget(src, os.path.join(dst, name), "Facepunch.Steamworks.Win64", "Facepunch.Steamworks.Posix")
                log(f"    {name}: original IL, {n} reference(s) retargeted")
        with Step("restore the original network prefab hashes (Windows players reject a different NetworkConfig)", status="Making online play match Windows"):
            from . import net_hashes
            net_hashes.fix_build(out_app, game_dir)
