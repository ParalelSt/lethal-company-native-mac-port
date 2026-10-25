"""Command line + simple dialog-driven menu. Commands: setup, build <game folder>, play, play-modded [profile], mods ..., check-update, self-update, version, menu"""
import os, sys, subprocess, time, shutil, glob, json
from . import config

def bootstrap():
    """Re-exec inside the kit's venv (created on first run) so UnityPy/pefile/dnfile are available."""
    venv_py = os.path.join(config.SUPPORT, "venv", "bin", "python")
    if os.path.realpath(sys.prefix) == os.path.realpath(os.path.join(config.SUPPORT, "venv")):
        try: import dnfile, UnityPy, pefile, PIL, vdf  # noqa
        except ImportError:
            subprocess.run([venv_py, "-m", "pip", "install", "-q", "--disable-pip-version-check", "UnityPy", "pefile", "pillow", "vdf", "dnfile"], check=True)
        return
    if not os.path.exists(venv_py):
        print("First run: preparing the Python environment (one time)...", flush=True)
        os.makedirs(config.SUPPORT, exist_ok=True)
        subprocess.run([sys.executable, "-m", "venv", os.path.join(config.SUPPORT, "venv")], check=True)
        subprocess.run([venv_py, "-m", "pip", "install", "-q", "--disable-pip-version-check", "UnityPy", "pefile", "pillow", "vdf", "dnfile"], check=True)
    os.execv(venv_py, [venv_py, "-m", "lcport"] + sys.argv[1:])

def validate_game_dir(d):
    d = d.rstrip("/")
    exe = os.path.join(d, "Lethal Company.exe"); data = os.path.join(d, "Lethal Company_Data", "Managed", "Assembly-CSharp.dll")
    if not (os.path.exists(exe) and os.path.exists(data)):
        raise SystemExit(f"'{d}' is not a Lethal Company install folder (expected 'Lethal Company.exe' and 'Lethal Company_Data'). "
                         "Copy the folder from a PC: Steam > Lethal Company > Manage > Browse local files.")
    return d

def cmd_setup(args):
    from . import deps, unity
    from .util import log
    log("checking requirements...")
    missing = deps.check_tools()
    for m in missing: log("  missing: " + m)
    if not os.path.exists(config.UNITY_HUB): log("  missing: Unity Hub (https://unity.com/download) - install it and sign in once")
    log("ok" if not missing else "fix the items above, then run again")

def cmd_build(args):
    from . import deps, unity, rip, project, thirdparty, install, steam
    from .util import log, Step, read_state, write_state, md5
    game = validate_game_dir(args[0] if args else (ask_game_dir() or ""))
    os.makedirs(config.WORK, exist_ok=True)
    with Step("Steam ownership check"):
        if not steam.ensure_running(): raise SystemExit("Steam is not running. Start Steam and sign in, then try again.")
        owns = steam.owns_game(thirdparty.natives())
        if owns is None: raise SystemExit("Could not talk to Steam. Make sure you are signed in.")
        if not owns: raise SystemExit("The signed-in Steam account does not own Lethal Company. This port only works with a purchased copy.")
    ver = unity.game_unity_version(game); log(f"    game Unity version: {ver}")
    with Step(f"Unity {ver}"):
        app = unity.editor_for(ver)
        if not app:
            log("    not installed; installing through Unity Hub (sign in to the Hub if it asks)")
            deps.install_unity(ver); app = unity.editor_for(ver)
            if not app: raise SystemExit(f"Unity {ver} is still missing. Open Unity Hub, sign in, install Unity {ver} (Apple silicon), then rerun.")
    with Step("extract assets from your game copy (AssetRipper)"):
        proj = rip.export(game, os.path.join(config.WORK, "rip"))
    marker = os.path.join(config.WORK, "rip", ".assembled")
    if not os.path.exists(marker):
        project.assemble(proj, game, app, thirdparty.natives()); open(marker, "w").write("ok")
    else: log("==> project already assembled, skipping")
    out_app = os.path.join(config.WORK, "build", f"{config.APP_NAME}.app")
    unity.full_build(app, proj, out_app, game)
    install.install_app(out_app, game); install.install_modded_launcher()
    with Step("record game shaders for the mod audit"):
        record_game_shaders()
    st = read_state(); st["game_dir"] = game; st["unity"] = ver; st["assembly_md5"] = md5(os.path.join(game, "Lethal Company_Data", "Managed", "Assembly-CSharp.dll")); st["built"] = time.strftime("%Y-%m-%d %H:%M"); write_state(st)
    try:
        from . import check_update; check_update.check(accept=True)
    except Exception: pass
    log(f"\nDone. '{config.APP_NAME}' is in your Applications folder (Spotlight: Lethal Company). Keep Steam running when you play.")

def record_game_shaders():
    import UnityPy
    data = os.path.join(config.APP_DST, "Contents", "Resources", "Data"); names = set()
    for f in os.listdir(data):
        if not (f.startswith(("level", "sharedassets", "globalgamemanagers", "resources")) and not f.endswith((".resS", ".resource"))): continue
        try:
            for o in UnityPy.load(os.path.join(data, f)).objects:
                if o.type.name == "Shader":
                    try: names.add(o.read().m_ParsedForm.m_Name)
                    except Exception: pass
        except Exception: pass
    json.dump(sorted(names), open(os.path.join(config.WORK, "game-shaders.json"), "w"))

def cmd_play(args, modded=False):
    from . import steam, thirdparty
    if not os.path.exists(config.APP_DST): raise SystemExit("Lethal Company is not built yet. Run: build <game folder>")
    steam.ensure_running()
    env = {}; extra = []
    if modded:
        from .mods import profile_dir
        bep = profile_dir(args[0] if args else "Default")
        env = {"DOORSTOP_ENABLED": "1", "DOORSTOP_TARGET_ASSEMBLY": os.path.join(bep, "core", "BepInEx.Preloader.dll"),
               "DOORSTOP_IGNORE_DISABLED_ENV": "0", "DYLD_INSERT_LIBRARIES": os.path.join(thirdparty.bepinex(), "libdoorstop.dylib")}
    p = steam.launch(config.APP_DST, extra, env, logfile=os.path.join(config.WORK, "player-modded.log" if modded else "player.log"))
    p.wait()

def ask_game_dir():
    from .util import ask_folder
    return ask_folder("Select your Lethal Company folder (from Steam on a PC: Lethal Company > Manage > Browse local files)")

def cmd_menu(args):
    from .util import dialog
    from . import __version__, selfupdate
    upd = selfupdate.available()
    if upd:
        notes = upd["notes"].strip().replace('"', "'")[:500]
        if dialog(f"Launcher {upd['version']} is available (you have {__version__}).\n\n{notes}", buttons=("Later", "Update"), default="Update") == "Update":
            selfupdate.apply(upd); print("Updated. Please reopen the launcher."); return
    while True:
        built = os.path.exists(config.APP_DST)
        choice = dialog(f"Lethal Company native macOS port  (launcher {__version__})", buttons=("Mods", "Build / Update", "Play") if built else ("Quit", "Build / Update"), default="Play" if built else "Build / Update")
        if choice == "Play": cmd_play([]); continue
        if choice == "Build / Update":
            d = ask_game_dir()
            if d: cmd_build([d])
            continue
        if choice == "Mods":
            c = dialog("Mods: use the modded launcher in Applications, or the command line:\n  lcport mods import <profile> <code>\n  lcport mods audit <profile>", buttons=("Play modded", "Back"), default="Back")
            if c == "Play modded": cmd_play(["Default"], modded=True)
            continue
        return

def main():
    bootstrap()
    a = sys.argv[1:]
    cmd = a[0] if a else "menu"
    try:
        if cmd == "setup": cmd_setup(a[1:])
        elif cmd == "build": cmd_build(a[1:])
        elif cmd == "play": cmd_play(a[1:])
        elif cmd == "play-modded": cmd_play(a[1:], modded=True)
        elif cmd == "mods":
            from . import mods; mods.main(a[1:])
        elif cmd == "version":
            from . import __version__; print(__version__)
        elif cmd == "self-update":
            from . import selfupdate
            u = selfupdate.available(); print("already up to date" if not u else "updating...") ; u and selfupdate.apply(u)
        elif cmd == "check-update":
            from . import check_update; sys.exit(check_update.check(notify="--notify" in a, accept="--accept" in a))
        elif cmd == "menu": cmd_menu(a[1:])
        else: print(__doc__)
    except KeyboardInterrupt: pass
    except (SystemExit, RuntimeError) as e:
        if str(e): print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)
