"""Launcher self-update: compare the installed kit version with the latest GitHub release and replace the kit files."""
import os, re, shutil, subprocess, tempfile
from . import config
from .util import http_json, download, log

APP_NAME = "Lethal Company Port.app"

def latest(strict=False):
    """The newest release, or None (offline, or no release yet). strict: let the network error through instead.
    The asset is the zipped launcher app (name ending in -app.zip) when the release has one, else any .zip."""
    try:
        r = http_json(f"https://api.github.com/repos/{config.REPO}/releases/latest")
    except Exception:
        if strict: raise
        return None
    tag = r.get("tag_name", "").lstrip("v"); assets = [a for a in r.get("assets", []) if a["name"].endswith(".zip")]
    asset = next((a for a in assets if a["name"].endswith("-app.zip")), assets[0] if assets else None)
    return {"version": tag, "notes": r.get("body", ""), "url": asset["browser_download_url"] if asset else None} if tag else None

def vtuple(v): return tuple(int(x) for x in re.findall(r"\d+", v)[:3])

def available():
    from . import __version__
    l = latest()
    if l and l["url"] and vtuple(l["version"]) > vtuple(__version__): return l
    return None

def _copy_over(src_dir, dst_dir):
    """Replace every top-level entry of dst_dir that src_dir has (folders as a whole, files one by one)."""
    for name in os.listdir(src_dir):
        src = os.path.join(src_dir, name); dst = os.path.join(dst_dir, name)
        if os.path.isdir(src) and not os.path.islink(src):
            shutil.rmtree(dst, ignore_errors=True); shutil.copytree(src, dst, symlinks=True)
        else: shutil.copy2(src, dst, follow_symlinks=False)

def _replace_file(src, dst):
    """Swap in a new file under a fresh inode (a running executable must not be rewritten in place)."""
    tmp = dst + ".new"; shutil.copy2(src, tmp); os.replace(tmp, dst)

def apply(rel):
    """Download the release zip and replace the kit's own files (lcport, prebuilt, unity, docs). The zip is either the
    zipped launcher app (kit in Contents/Resources/kit) or an older source zip (one folder holding the kit). When the kit
    lives inside an app bundle, the app's launcher binary and Info.plist are updated too and the bundle is re-signed."""
    archive = download(rel["url"], f"launcher-{rel['version']}.zip", force=True)
    tmp = tempfile.mkdtemp(prefix="lcport-update")
    try:
        subprocess.run(["ditto", "-x", "-k", archive, tmp], check=True)  # keeps exec bits and symlinks, unlike zipfile
        entries = [e for e in os.listdir(tmp) if e != "__MACOSX"]
        root = os.path.join(tmp, entries[0]) if len(entries) == 1 else tmp
        new_app = root if root.endswith(".app") else None
        src_kit = os.path.join(new_app, config.EMBEDDED_KIT) if new_app else root
        if not os.path.isfile(os.path.join(src_kit, "lcport", "__init__.py")): raise RuntimeError("the downloaded release does not contain the kit")
        _copy_over(src_kit, config.KIT)
        app = config.bundle_app()
        if app:
            if new_app:
                exe = os.path.join("Contents", "MacOS", "Lethal Company Port")
                if os.path.isfile(os.path.join(new_app, exe)): _replace_file(os.path.join(new_app, exe), os.path.join(app, exe))
                plist = os.path.join("Contents", "Info.plist")
                if os.path.isfile(os.path.join(new_app, plist)): _replace_file(os.path.join(new_app, plist), os.path.join(app, plist))
            resign(app)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    log(f"launcher updated to {rel['version']}")

def resign(app):
    """The update changed files inside the signed bundle: sign it again (ad hoc) and drop quarantine so macOS keeps opening it."""
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", app], check=True, capture_output=True)
    subprocess.run(["xattr", "-dr", "com.apple.quarantine", app], check=False, capture_output=True)
