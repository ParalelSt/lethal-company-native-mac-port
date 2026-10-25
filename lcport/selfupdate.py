"""Launcher self-update: compare the installed kit version with the latest GitHub release and replace the kit files."""
import os, re, io, zipfile, shutil, tempfile
from . import config
from .util import http_json, download, log

def latest(strict=False):
    """The newest release, or None (offline, or no release yet). strict: let the network error through instead."""
    try:
        r = http_json(f"https://api.github.com/repos/{config.REPO}/releases/latest")
    except Exception:
        if strict: raise
        return None
    tag = r.get("tag_name", "").lstrip("v"); asset = next((a for a in r.get("assets", []) if a["name"].endswith(".zip")), None)
    return {"version": tag, "notes": r.get("body", ""), "url": asset["browser_download_url"] if asset else None} if tag else None

def vtuple(v): return tuple(int(x) for x in re.findall(r"\d+", v)[:3])

def available():
    from . import __version__
    l = latest()
    if l and l["url"] and vtuple(l["version"]) > vtuple(__version__): return l
    return None

def apply(rel):
    """Download the release zip and replace the kit's own files (prebuilt, lcport, unity, launcher app, docs)."""
    z = zipfile.ZipFile(download(rel["url"], f"launcher-{rel['version']}.zip", force=True))
    tmp = tempfile.mkdtemp(prefix="lcport-update"); z.extractall(tmp)
    # the zip holds one top-level folder
    root = os.path.join(tmp, os.listdir(tmp)[0]) if len(os.listdir(tmp)) == 1 else tmp
    for name in os.listdir(root):
        src = os.path.join(root, name); dst = os.path.join(config.KIT, name)
        if os.path.isdir(src):
            shutil.rmtree(dst, ignore_errors=True); shutil.copytree(src, dst, symlinks=True)
        else: shutil.copy2(src, dst)
    shutil.rmtree(tmp, ignore_errors=True)
    log(f"launcher updated to {rel['version']}")
