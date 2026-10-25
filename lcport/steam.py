"""Steam client helpers: make sure Steam runs, verify the signed-in account owns the game, find the signed-in
account, launch the app (through a Steam shortcut when one is registered, see `steam-shortcut`)."""
import os, re, time, subprocess, ctypes, plistlib
from . import config
from .util import log, read_state

STEAM_ROOT = os.path.expanduser("~/Library/Application Support/Steam")
STEAMID64_BASE = 76561197960265728

def running(): return subprocess.run(["pgrep", "-f", "steam_osx"], capture_output=True).returncode == 0

def ensure_running(wait=60):
    if running(): return True
    subprocess.run(["open", "-a", "Steam"], check=False)
    for _ in range(wait):
        time.sleep(1)
        if running(): time.sleep(8); return True
    return False

def owns_game(shim_dir):
    """True if the Steam account signed in on this Mac owns the game. Uses the kit's libsteam_api shim via ctypes."""
    lib = os.path.join(shim_dir, "libsteam_api.dylib")
    if not os.path.exists(lib): raise RuntimeError("Steam shim missing: " + lib)
    os.environ["SteamAppId"] = str(config.APPID); os.environ["SteamGameId"] = str(config.APPID)
    s = ctypes.CDLL(lib)
    s.SteamAPI_Init.restype = ctypes.c_bool
    if not s.SteamAPI_Init(): return None  # Steam not running / not signed in
    try:
        s.SteamAPI_SteamApps_v008.restype = ctypes.c_void_p
        apps = s.SteamAPI_SteamApps_v008()
        s.SteamAPI_ISteamApps_BIsSubscribedApp.restype = ctypes.c_bool
        s.SteamAPI_ISteamApps_BIsSubscribedApp.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        return bool(s.SteamAPI_ISteamApps_BIsSubscribedApp(apps, config.APPID))
    finally:
        s.SteamAPI_Shutdown()

OVERLAY = os.path.expanduser("~/Library/Application Support/Steam/Steam.AppBundle/Steam/Contents/MacOS/gameoverlayrenderer.dylib")

# --- signed-in account -------------------------------------------------------------------------------

_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([{}])|//[^\n]*|[^\s"{}]+')

def parse_text_vdf(text):
    """Minimal text KeyValues parser (loginusers.vdf, config.vdf ...) -> nested dicts. Keys keep their case."""
    toks = []
    for m in _TOKEN.finditer(text):
        if m.group(1) is not None: toks.append(("s", re.sub(r"\\(.)", lambda x: {"n": "\n", "t": "\t"}.get(x.group(1), x.group(1)), m.group(1))))
        elif m.group(2): toks.append((m.group(2), None))
        elif not m.group(0).startswith("//"): toks.append(("s", m.group(0)))
    pos = 0
    def obj(top):
        nonlocal pos; d = {}
        while pos < len(toks):
            kind, key = toks[pos]; pos += 1
            if kind == "}":
                if top: raise ValueError("unbalanced '}' in VDF text")
                return d
            if kind != "s": raise ValueError("expected a key in VDF text")
            if pos >= len(toks): raise ValueError("key without value in VDF text")
            vk, val = toks[pos]; pos += 1
            if vk == "{": d[key] = obj(False)
            elif vk == "s": d[key] = val
            else: raise ValueError("unexpected '}' in VDF text")
        if not top: raise ValueError("unclosed '{' in VDF text")
        return d
    return obj(True)

def account_from_loginusers(text):
    """32-bit account id of the most recent user in loginusers.vdf, or None. Prefers "MostRecent" "1"; newer Steam
    clients no longer write that key, so fall back to the user with the newest "timestamp"."""
    root = parse_text_vdf(text)
    users = next((v for k, v in root.items() if k.lower() == "users" and isinstance(v, dict)), {})
    users = {sid: u for sid, u in users.items() if sid.isdigit() and int(sid) > STEAMID64_BASE and isinstance(u, dict)}
    if not users: return None
    lower = lambda u: {k.lower(): v for k, v in u.items()}
    recent = [sid for sid, u in users.items() if lower(u).get("mostrecent") == "1"]
    if not recent:
        ts = lambda sid: int(lower(users[sid]).get("timestamp", "0")) if lower(users[sid]).get("timestamp", "0").isdigit() else 0
        recent = [max(users, key=ts)]
    return int(recent[0]) - STEAMID64_BASE

def current_account_id(steam_root=None):
    """Account id (the folder name under userdata/) of the signed-in Steam user, or None if it cannot be told."""
    root = steam_root or STEAM_ROOT
    lu = os.path.join(root, "config", "loginusers.vdf")
    if os.path.exists(lu):
        try:
            with open(lu, encoding="utf-8", errors="replace") as f: acct = account_from_loginusers(f.read())
            if acct: return acct
        except ValueError: pass
    try: ids = [d for d in os.listdir(os.path.join(root, "userdata")) if d.isdigit() and int(d) != 0]
    except OSError: ids = []
    return int(ids[0]) if len(ids) == 1 else None

def shortcuts_path(account_id, steam_root=None):
    return os.path.join(steam_root or STEAM_ROOT, "userdata", str(account_id), "config", "shortcuts.vdf")

# --- launching ------------------------------------------------------------------------------------------

OVERLAY = os.path.expanduser("~/Library/Application Support/Steam/Steam.AppBundle/Steam/Contents/MacOS/gameoverlayrenderer.dylib")

def app_executable(app):
    """Path of a bundle's main executable (CFBundleExecutable, else the game's binary name)."""
    name = config.APP_NAME
    try:
        with open(os.path.join(app, "Contents", "Info.plist"), "rb") as f: name = plistlib.load(f).get("CFBundleExecutable") or name
    except Exception: pass
    return os.path.join(app, "Contents", "MacOS", name)

def shortcut_for(app):
    """The state.json record of the Steam shortcut that starts this bundle, or None."""
    exe = os.path.realpath(app_executable(app))
    for rec in (read_state().get("steam_shortcuts") or {}).values():
        if isinstance(rec, dict) and rec.get("exe") and os.path.realpath(rec["exe"]) == exe and rec.get("rungameid"): return rec
    return None

def started_at():
    """Epoch seconds when the running Steam client started, or None."""
    r = subprocess.run(["pgrep", "-x", "steam_osx"], capture_output=True, text=True)
    times = []
    for pid in r.stdout.split():
        p = subprocess.run(["ps", "-o", "lstart=", "-p", pid], capture_output=True, text=True, env=dict(os.environ, LC_ALL="C"))
        try: times.append(time.mktime(time.strptime(p.stdout.strip(), "%a %b %d %H:%M:%S %Y")))
        except ValueError: pass
    return min(times) if times else None

def launch(app, extra_args=(), env=None, logfile=None, shortcut_app=None):
    """Start the game. Returns the Popen of a direct launch, or None when Steam was asked to start it.

    shortcut_app: the bundle whose Steam shortcut stands for this launch (default: app). The modded launch runs the
    vanilla binary with BepInEx env vars, but its shortcut points at the "Lethal Company Modded" bundle."""
    from .install import reset_window_state
    reset_window_state()
    sc = shortcut_for(shortcut_app or app)
    # Two guards keep a launch that Steam itself started from going back through steam:// (which would loop):
    #  1. LC_DIRECT_LAUNCH=1: set by the modded bundle's native launcher (the Exe of the modded shortcut) and its fallback.
    #  2. SteamGameId equal to the shortcut's id: Steam sets SteamGameId/SteamAppId on what it starts from a
    #     non-Steam shortcut, so a process carrying our own shortcut id is already Steam's child.
    if sc and running() and os.environ.get("LC_DIRECT_LAUNCH") != "1" and os.environ.get("SteamGameId") not in (str(sc["appid"]), str(sc["rungameid"])):
        st = started_at()
        if st is not None and st < sc.get("added", 0):
            log("Steam was started before the shortcut was added and does not know it yet. Restart Steam once; launching directly this time.")
        elif subprocess.run(["open", f"steam://rungameid/{sc['rungameid']}"], check=False).returncode == 0:
            return None
    exe = os.path.join(app, "Contents", "MacOS", config.APP_NAME)
    args = [exe] + (["-logFile", logfile] if logfile else []) + list(extra_args)
    e = dict(os.environ); e.update(env or {})
    # Steam overlay (Shift+Tab): Steam injects this library into games it starts; do the same here
    e.setdefault("SteamAppId", str(config.APPID)); e.setdefault("SteamGameId", str(config.APPID)); e.setdefault("SteamOverlayGameId", str(config.APPID))
    if os.path.exists(OVERLAY) and os.environ.get("LC_NO_OVERLAY") != "1":
        e["DYLD_INSERT_LIBRARIES"] = OVERLAY + (":" + e["DYLD_INSERT_LIBRARIES"] if e.get("DYLD_INSERT_LIBRARIES") else "")
    return subprocess.Popen(args, env=e, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
