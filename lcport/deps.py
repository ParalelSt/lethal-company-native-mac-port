"""Dependency detection and setup: Python venv, Unity Hub (installed from Unity's public disk image), the Unity sign-in
(licence) and the Unity editor (installed through the Hub's headless CLI)."""
import os, glob, shutil, sys, re, time, tempfile, datetime
import xml.etree.ElementTree as ET
from . import config
from .util import run, log, status, Step, http_json, download

PY_PKGS = ["UnityPy", "pefile", "pillow", "vdf", "dnfile"]

HUB_APP = "Unity Hub.app"
HUB_DMG_URL = "https://public-cdn.cloud.unity3d.com/hub/prod/UnityHubSetup.dmg"
APP_DIRS = ("/Applications", "~/Applications")  # where hub_path() looks and install_hub() copies to, in this order

# Unity licence detection (layout seen with Unity Hub 3 on macOS): signing in to the Hub activates the free Personal
# licence and writes ~/Library/Unity/licenses/UnityEntitlementLicense.xml, a signed XML whose <EntitlementGroup
# Namespace="unity_editor"> lists entitlements such as com.unity.editor / com.unity.editor.headless and carries an
# <UpdateDate> by which the Hub must refresh it (about 30 days out; a signed-in Hub refreshes it on start).
# Rule: signed in = some *.xml directly in LICENCE_DIR has a unity_editor group with an editor entitlement whose
# UpdateDate (when present) is still in the future. Older serial-based activations (Unity_lic.ulf) also count.
# The login itself lives in the Hub's encrypted accounts.db / keychain and is never read.
LICENCE_DIR = "~/Library/Unity/licenses"
LEGACY_LICENCES = ("/Library/Application Support/Unity/Unity_lic.ulf", "~/Library/Application Support/Unity/Unity_lic.ulf")
EDITOR_ENTITLEMENTS = ("com.unity.editor", "com.unity.editor.headless")
SIGNIN_STATUS = "Sign in to Unity Hub (free Personal licence), then come back here"

def venv_python():
    return os.path.join(config.SUPPORT, "venv", "bin", "python")

def ensure_venv():
    py = venv_python()
    if not os.path.exists(py):
        run([sys.executable, "-m", "venv", os.path.join(config.SUPPORT, "venv")])
    r = run([py, "-c", "import UnityPy, pefile, PIL, vdf, dnfile"], check=False, capture=True)
    if r.returncode != 0:
        run([py, "-m", "pip", "install", "-q"] + PY_PKGS)
    return py

def have(cmd): return shutil.which(cmd) is not None

def check_tools(install=False):
    missing = []
    if not have("python3"):
        missing.append("Python 3 (macOS offers it with: xcode-select --install)")
    return missing

# --- Unity Hub ---------------------------------------------------------------------------------------------------

def hub_binary(app):
    return os.path.join(app, "Contents", "MacOS", "Unity Hub")

def hub_path():
    """The installed Unity Hub.app in /Applications or ~/Applications, or None."""
    for d in APP_DIRS:
        app = os.path.join(os.path.expanduser(d), HUB_APP)
        if os.path.exists(hub_binary(app)): return app
    return None

def install_hub():
    """Download Unity's official Hub disk image, copy Unity Hub.app into /Applications (~/Applications when that is not
    writable), strip the quarantine flag so it opens without the Gatekeeper prompt. Returns the installed app's path."""
    with Step("download Unity Hub", status="Downloading Unity Hub"):
        dmg = download(HUB_DMG_URL, "UnityHubSetup.dmg", show_progress=True)
    with Step("install Unity Hub", status="Installing Unity Hub"):
        os.makedirs(config.CACHE, exist_ok=True)
        mnt = tempfile.mkdtemp(prefix="unityhub-mount-", dir=config.CACHE)
        r = run(["hdiutil", "attach", "-nobrowse", "-quiet", "-mountpoint", mnt, dmg], check=False, capture=True)
        if r.returncode != 0:
            shutil.rmtree(mnt, ignore_errors=True)
            try: os.remove(dmg)  # a broken or truncated download: fetch it again next time
            except OSError: pass
            raise RuntimeError("The Unity Hub download is not a valid disk image (hdiutil could not open it), so it was deleted. "
                               "Check the internet connection and run Build again, or install Unity Hub from https://unity.com/download")
        try:
            src = os.path.join(mnt, HUB_APP)
            if not os.path.isdir(src): raise RuntimeError(f"The Unity Hub disk image has no {HUB_APP} in it. Install Unity Hub from https://unity.com/download")
            dest_dir = os.path.expanduser(APP_DIRS[0])
            if not os.access(dest_dir, os.W_OK):
                dest_dir = os.path.expanduser(APP_DIRS[1]); os.makedirs(dest_dir, exist_ok=True)
            dst = os.path.join(dest_dir, HUB_APP)
            if os.path.exists(dst): shutil.rmtree(dst)  # a leftover without its binary (hub_path() found none)
            log(f"    copying {HUB_APP} into {dest_dir}")
            run(["ditto", src, dst])
        finally:
            run(["hdiutil", "detach", "-quiet", mnt], check=False)
            shutil.rmtree(mnt, ignore_errors=True)
        run(["xattr", "-dr", "com.apple.quarantine", dst], check=False)
    return dst

# --- Unity sign-in (licence) -------------------------------------------------------------------------------------

def _parse_date(s):
    try: return datetime.datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
    except (AttributeError, ValueError): return None

def unity_signed_in(now=None):
    """True when this Mac has an active Unity editor licence (see the rule above LICENCE_DIR)."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    for f in sorted(glob.glob(os.path.join(os.path.expanduser(LICENCE_DIR), "*.xml"))):
        try: root = ET.parse(f).getroot()
        except (ET.ParseError, OSError): continue
        for g in root.iter("EntitlementGroup"):
            if g.get("Namespace") != "unity_editor": continue
            if not any(e.get("Id") in EDITOR_ENTITLEMENTS for e in g.iter("Entitlement")): continue
            upd = _parse_date(g.findtext(".//UpdateDate") or "")
            if upd is not None and upd.tzinfo is None: upd = upd.replace(tzinfo=datetime.timezone.utc)
            if upd is None or upd > now: return True
    return any(os.path.exists(os.path.expanduser(p)) for p in LEGACY_LICENCES)

def open_hub():
    run(["open", "-a", "Unity Hub"], check=False)

def ensure_unity_signed_in(check=None, sleep=time.sleep, opener=None, timeout=15 * 60, interval=3, report_every=30):
    """Return once a Unity licence is present. Without one: open Unity Hub, ask for the sign-in and poll every
    `interval` s for up to `timeout` s, with a ##status line every `report_every` s. Raises RuntimeError on timeout."""
    check = check or unity_signed_in; opener = opener or open_hub
    if check(): log("    Unity licence present"); return True
    status(SIGNIN_STATUS)
    log("    no Unity licence on this Mac yet: opening Unity Hub. Sign in there (or create a free account); this continues by itself.")
    opener()
    waited = 0
    while waited < timeout:
        sleep(interval); waited += interval
        if check(): log("    signed in to Unity"); return True
        if waited % report_every == 0: status(f"{SIGNIN_STATUS} (waiting {waited // 60}:{waited % 60:02d})")
    raise RuntimeError(f"No Unity sign-in after {timeout // 60} minutes. Open Unity Hub, sign in with a free Unity account "
                       "(Personal licence), then run Build again.")

# --- Unity editor ------------------------------------------------------------------------------------------------

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
    hub = hub_path()
    if not hub: raise RuntimeError("Unity Hub is not installed (https://unity.com/download). Install it, sign in once, then rerun.")
    log(f"    installing Unity {version} ({cs}) via Unity Hub, this downloads ~4.5 GB")
    run([hub_binary(hub), "--", "--headless", "install", "--version", version, "--changeset", cs, "--architecture", "arm64"], check=False)
    return find_unity(version)
