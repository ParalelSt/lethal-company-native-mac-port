"""Locate the Unity editor and run the batch-mode steps (import, shader/material fixes, video transcode, build)."""
import os, re, glob
from . import config
from .util import run, log, Step

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

def full_build(editor_app, proj, out_app):
    with Step("Unity: import project and resolve packages (first import takes a while)"):
        batch(editor_app, proj, "unity-import")
    with Step("Unity: point materials at package shaders"):
        batch(editor_app, proj, "unity-fixshaders", "FixPackageShaders.Run")
    with Step("Unity: validate HDRP materials"):
        batch(editor_app, proj, "unity-validate", "ValidateHdrpMaterials.Run")
    with Step("Unity: enable video transcoding"):
        batch(editor_app, proj, "unity-transcode", "TranscodeVideos.Run")
    with Step("Unity: build the macOS app (compiles every shader for Metal; 30-60 min)"):
        batch(editor_app, proj, "unity-build", "BuildMac.Build", build_path=out_app)
    return out_app
