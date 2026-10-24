"""Dependency detection and setup: Xcode CLT, Homebrew packages, .NET SDK, Python venv, Unity editor."""
import os, glob, shutil, sys, re
from . import config
from .util import run, log, Step, http_json

PY_PKGS = ["UnityPy", "pefile", "pillow", "vdf"]

def venv_python():
    return os.path.join(config.SUPPORT, "venv", "bin", "python")

def ensure_venv():
    py = venv_python()
    if not os.path.exists(py):
        run([sys.executable, "-m", "venv", os.path.join(config.SUPPORT, "venv")])
    r = run([py, "-c", "import UnityPy, pefile, PIL, vdf"], check=False, capture=True)
    if r.returncode != 0:
        run([py, "-m", "pip", "install", "-q"] + PY_PKGS)
    return py

def have(cmd): return shutil.which(cmd) is not None

def check_tools(install=False):
    missing = []
    if not have("python3"):
        missing.append("Python 3 (macOS offers it with: xcode-select --install)")
    return missing

def find_unity(version):
    p = os.path.join(config.UNITY_EDITORS, version, "Unity.app", "Contents", "MacOS", "Unity")
    return p if os.path.exists(p) else None

def unity_changeset(version):
    d = http_json(f"https://services.api.unity.com/unity/editor/release/v1/releases?version={version}&architecture=ARM64&platform=MAC_OS")
    for r in d.get("results", []):
        for dl in r.get("downloads", []):
            m = re.search(r"download_unity/([0-9a-f]{12})/", dl.get("url", ""))
            if m: return m.group(1)
    return None

def install_unity(version):
    cs = unity_changeset(version)
    if not cs: raise RuntimeError(f"could not find a macOS arm64 download for Unity {version}")
    if not os.path.exists(config.UNITY_HUB): raise RuntimeError("Unity Hub is not installed (https://unity.com/download). Install it, sign in once, then rerun.")
    log(f"    installing Unity {version} ({cs}) via Unity Hub, this downloads ~4.5 GB")
    run([config.UNITY_HUB, "--", "--headless", "install", "--version", version, "--changeset", cs, "--architecture", "arm64"], check=False)
    return find_unity(version)
