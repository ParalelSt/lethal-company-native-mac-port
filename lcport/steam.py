"""Steam client helpers: make sure Steam runs, verify the signed-in account owns the game, launch the app."""
import os, time, subprocess, ctypes
from . import config
from .util import log

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

def launch(app, extra_args=(), env=None, logfile=None):
    from .install import reset_window_state
    reset_window_state()
    exe = os.path.join(app, "Contents", "MacOS", config.APP_NAME)
    args = [exe] + (["-logFile", logfile] if logfile else []) + list(extra_args)
    e = dict(os.environ); e.update(env or {})
    return subprocess.Popen(args, env=e, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
