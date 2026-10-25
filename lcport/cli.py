"""Command line + simple dialog-driven menu. Commands: setup, build <game folder>, play, play-modded [profile], mods ..., check-update, check-unity (one JSON line: Unity Hub, sign-in, editor), self-update, steam-shortcut [--remove] (alias add-to-steam), version, net-fix (restore the original network prefab hashes in the installed app, needed to join Windows hosts), net-verify (check those hashes), menu"""
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
    from . import deps
    from .util import log, progress_steps, done
    log("checking requirements...")
    missing = deps.check_tools()
    for m in missing: log("  missing: " + m)
    if missing: raise SystemExit("Fix the items above, then run setup again.")
    ver = unity_version()
    with progress_steps(UNITY_STEPS): ensure_unity(ver)
    done(f"Unity {ver} is ready")

UNITY_STEPS = 4   # top-level Steps in ensure_unity
BUILD_STEPS = 17  # top-level Steps in cmd_build: Steam check, ensure_unity's 4, extract, assemble, unity.full_build's 7, 2 installs, the shader record

def unity_version():
    """The game's Unity version: the one the last build recorded, else the version this port targets."""
    from .util import read_state
    return read_state().get("unity") or config.UNITY_VERSION

def ensure_unity(ver):
    """Python packages, Unity Hub, the Unity sign-in, then the editor (UNITY_STEPS top-level Steps). Returns the editor app."""
    from . import deps, unity
    from .util import log, Step
    with Step("Python packages", status="Checking the Python packages"):
        deps.ensure_venv()
    with Step("Unity Hub", status="Checking Unity Hub"):
        hub = deps.hub_path()
        if not hub:
            log("    not installed; installing it from Unity's official download")
            hub = deps.install_hub()
        log(f"    {hub}")
    with Step("Unity sign-in", status="Checking the Unity sign-in"):
        deps.ensure_unity_signed_in()
    with Step(f"Unity {ver}", status=f"Checking Unity {ver}"):
        app = unity.editor_for(ver)
        if not app:
            log("    not installed; installing through Unity Hub")
            deps.install_unity(ver); app = unity.editor_for(ver)
            if not app: raise SystemExit(f"Unity {ver} is still missing. Open Unity Hub, sign in, install Unity {ver} (Apple silicon), then rerun.")
    return app

def unity_report():
    """For the launcher's status grid: {"hub": app path or None, "signed_in": bool, "editor": Unity.app path or None}."""
    from . import deps, unity
    return {"hub": deps.hub_path(), "signed_in": deps.unity_signed_in(), "editor": unity.editor_for(unity_version())}

def cmd_build(args):
    from .util import progress_steps, done
    game = validate_game_dir(args[0] if args else (ask_game_dir() or ""))
    with progress_steps(BUILD_STEPS): _build(game)
    done("Build finished. Lethal Company is in your Applications folder")

def _build(game):
    from . import deps, unity, rip, project, thirdparty, install, steam
    from .util import log, Step, read_state, write_state, md5
    os.makedirs(config.WORK, exist_ok=True)
    with Step("Steam ownership check", status="Checking that Steam owns the game"):
        if not steam.ensure_running(): raise SystemExit("Steam is not running. Start Steam and sign in, then try again.")
        owns = steam.owns_game(thirdparty.natives())
        if owns is None: raise SystemExit("Could not talk to Steam. Make sure you are signed in.")
        if not owns: raise SystemExit("The signed-in Steam account does not own Lethal Company. This port only works with a purchased copy.")
    ver = unity.game_unity_version(game); log(f"    game Unity version: {ver}")
    app = ensure_unity(ver)
    with Step("extract assets from your game copy (AssetRipper)", status="Extracting your game files"):
        proj = rip.export(game, os.path.join(config.WORK, "rip"))
    marker = os.path.join(config.WORK, "rip", ".assembled")
    with Step("assemble the Unity project", status="Swapping the Windows-only parts"):
        if not os.path.exists(marker):
            project.assemble(proj, game, app, thirdparty.natives()); open(marker, "w").write("ok")
        else: log("    project already assembled, skipping")
    out_app = os.path.join(config.WORK, "build", f"{config.APP_NAME}.app")
    unity.full_build(app, proj, out_app, game)
    install.install_app(out_app, game); install.install_modded_launcher()
    with Step("record game shaders for the mod audit", status="Recording game shaders for the mod check"):
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
    from .util import read_state, write_state, status, done
    status("Launching...")
    steam.ensure_running()
    env = {}; extra = []
    if modded:
        from .mods import profile_dir
        st = read_state()
        # no profile given: use the profile last chosen in the launcher (the modded bundle's native launcher does the same)
        pname = args[0] if args else st.get("modded_profile", "Default")
        if st.get("modded_profile") != pname: st["modded_profile"] = pname; write_state(st)
        bep = profile_dir(pname)
        try: n = len([f for f in os.listdir(os.path.join(bep, "plugins")) if f != "MacShaderFix" and not f.startswith(".")])
        except OSError: n = 0
        print(f"Launching Lethal Company with profile {pname} ({n} mods)", flush=True)
        env = {"DOORSTOP_ENABLED": "1", "DOORSTOP_TARGET_ASSEMBLY": os.path.join(bep, "core", "BepInEx.Preloader.dll"),
               "DOORSTOP_IGNORE_DISABLED_ENV": "0", "DYLD_INSERT_LIBRARIES": os.path.join(thirdparty.bepinex(), "libdoorstop.dylib")}
    if not modded: print("Launching Lethal Company (vanilla)", flush=True)
    logfile = os.path.join(config.WORK, "player-modded.log" if modded else "player.log")
    p = steam.launch(config.APP_DST, extra, env, logfile=logfile, shortcut_app=config.MODDED_DST if modded else None)
    if p is None:
        print(f"Launched through Steam (overlay by Steam). Game log: {logfile}", flush=True)
        done("Launched through Steam"); return
    print(f"Game running (pid {p.pid}), log: {logfile}", flush=True)
    status("Game running")
    code = p.wait()
    print(f"Game closed (exit {code})", flush=True)
    done("Game closed")

VANILLA_SHORTCUT = "Lethal Company"
MODDED_SHORTCUT = "Lethal Company (Modded)"

def cmd_steam_shortcut(args):
    """Register the native app (and the modded launcher) as non-Steam games so Steam starts them and draws its overlay."""
    from . import steam, steam_shortcuts as sc, install
    from .util import read_state, write_state
    acct = steam.current_account_id()
    if not acct: raise SystemExit("Could not tell which Steam account is signed in on this Mac. Sign in to Steam once, then try again.")
    path = steam.shortcuts_path(acct)
    entries = sc.load(path)
    st = read_state()
    if "--remove" in args:
        kept = sc.remove(sc.remove(entries, VANILLA_SHORTCUT), MODDED_SHORTCUT)
        if len(kept) != len(entries): sc.save(path, kept)
        st.pop("steam_shortcuts", None); write_state(st)
        print(f"Removed {len(entries) - len(kept)} Lethal Company shortcut(s) from Steam.")
        print("Restart Steam once so it picks up the change.")
        print("##done Removed from Steam. Restart Steam once to see it", flush=True)
        return
    if not os.path.exists(config.APP_DST): raise SystemExit("Lethal Company is not built yet. Run: build <game folder>")
    now = int(time.time()); recs = {}
    def add(key, name, app, launch_options=""):
        exe = steam.app_executable(app); icns = os.path.join(app, "Contents", "Resources", "PlayerIcon.icns")
        e = sc.upsert(entries, name, exe, os.path.dirname(exe), icon=icns if os.path.exists(icns) else "", launch_options=launch_options)
        recs[key] = {"appid": e["appid"], "rungameid": sc.rungameid(e["appid"]), "exe": exe, "added": now}
    vlog = os.path.join(config.WORK, "player.log")
    add("vanilla", VANILLA_SHORTCUT, config.APP_DST, launch_options=f'-logFile "{vlog}"')
    if os.path.exists(config.MODDED_DST):
        if install.fix_modded_launcher(): print(f"Updated the launcher in {config.MODDED_DST} (it now starts the game itself, so Steam's overlay reaches it).")
        add("modded", MODDED_SHORTCUT, config.MODDED_DST)
    else:
        entries[:] = sc.remove(entries, MODDED_SHORTCUT)
        print(f"{config.MODDED_DST} is missing, so only the vanilla shortcut was added (run build to create it).")
    sc.save(path, entries)
    st["steam_shortcuts"] = recs; write_state(st)
    for key, name in (("vanilla", VANILLA_SHORTCUT), ("modded", MODDED_SHORTCUT)):
        if key in recs: print(f"{name}: steam://rungameid/{recs[key]['rungameid']}")
    print("Restart Steam once so it picks up the new shortcuts.")
    print("##done Added to Steam. Restart Steam once to see it", flush=True)

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
            if "--json" in a:  # for the launcher's status grid: {"current", "latest", "available", "state": ok | none (no release yet) | offline}
                from . import __version__
                import urllib.error
                try: l = selfupdate.latest(strict=True); state = "ok" if l else "none"
                except urllib.error.HTTPError as e: l = None; state = "none" if e.code == 404 else "offline"
                except Exception: l = None; state = "offline"
                print(json.dumps({"current": __version__, "latest": l and l["version"], "state": state,
                                  "available": bool(l and l["url"] and selfupdate.vtuple(l["version"]) > selfupdate.vtuple(__version__))})); return
            u = selfupdate.available(); print("already up to date" if not u else "updating...") ; u and selfupdate.apply(u)
        elif cmd == "check-unity": print(json.dumps(unity_report()))
        elif cmd == "check-update":
            from . import check_update; sys.exit(check_update.check(notify="--notify" in a, accept="--accept" in a))
        elif cmd in ("steam-shortcut", "add-to-steam"): cmd_steam_shortcut(a[1:])
        elif cmd == "net-fix": from . import net_hashes; net_hashes.main(["fix", str(config.APP_DST)] + a[1:])
        elif cmd == "net-verify": from . import net_hashes; net_hashes.main(["verify", str(config.APP_DST)] + a[1:])
        elif cmd == "menu": cmd_menu(a[1:])
        else: print(__doc__)
    except KeyboardInterrupt: pass
    except (SystemExit, RuntimeError) as e:
        if isinstance(e, SystemExit) and (e.code is None or isinstance(e.code, int)): raise  # sys.exit(n): keep its exit code
        if str(e):
            print(f"\nERROR: {e}", file=sys.stderr)
            print("##fail " + str(e).strip().splitlines()[0], flush=True)  # the launcher's status line shows this
        sys.exit(1)
