"""native/modded_launcher.c, the main executable of the modded bundle: compiled with clang into a temp dir and run against a
fake bundle, support folder, BepInEx and game. The fake game is a compiled C program (a shell script would be started through
/bin/sh, which macOS protects, so DYLD_* would be stripped before it could report them). LC_LAUNCHER_TEST=1 keeps the launcher
from running `defaults` or starting Steam; HOME points into the temp dir. Steam and the real game are never started."""
import json, os, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "native", "modded_launcher.c")
CLANG = shutil.which("clang")

FAKE_GAME_C = r'''
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
extern char **environ;
int main(int argc, char **argv) {
    FILE *f = fopen(getenv("FAKE_OUT"), "w"); char cwd[4096];
    fprintf(f, "CWD=%s\n", getcwd(cwd, sizeof cwd));
    for (int i = 0; i < argc; i++) fprintf(f, "ARG=%s\n", argv[i]);
    for (char **e = environ; *e; e++) fprintf(f, "ENV=%s\n", *e);
    fclose(f); return 0;
}
'''

def write(path, data, mode=0o644):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb" if isinstance(data, bytes) else "w", encoding=None if isinstance(data, bytes) else "utf-8") as f: f.write(data)
    os.chmod(path, mode)

def clang(*args): subprocess.run([CLANG, "-O0", "-w", *args], check=True, capture_output=True)

@unittest.skipUnless(CLANG and sys.platform == "darwin", "needs clang on macOS")
class ModdedLauncherTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.mkdtemp()
        cls.launcher = os.path.join(cls.build, "launch"); cls.fake_game = os.path.join(cls.build, "fake_game")
        cls.dylib = os.path.join(cls.build, "noop.dylib")  # dyld really loads inserted libraries, so they must be real
        clang("-Wall", "-o", cls.launcher, SRC)
        write(os.path.join(cls.build, "fake_game.c"), FAKE_GAME_C); clang("-o", cls.fake_game, os.path.join(cls.build, "fake_game.c"))
        write(os.path.join(cls.build, "noop.c"), "int lc_noop_marker = 1;\n"); clang("-dynamiclib", "-o", cls.dylib, os.path.join(cls.build, "noop.c"))
    @classmethod
    def tearDownClass(cls): shutil.rmtree(cls.build, ignore_errors=True)

    def setUp(self):
        self.tmp = tempfile.mkdtemp(); t = self.tmp
        self.home = os.path.join(t, "home")
        self.support = os.path.join(t, "App Support", "LethalCompanyMac")  # spaces, like ~/Library/Application Support
        self.kit = os.path.join(t, "kit"); os.makedirs(self.kit)
        self.app = os.path.join(t, "Applications", "Lethal Company.app")
        self.bepinex = os.path.join(self.support, "work", "thirdparty", "bepinex")
        self.bundle = os.path.join(t, "Applications", "Lethal Company Modded.app")
        shutil.copy2(self.launcher, os.path.join(self.bundle_dir("MacOS"), "launch"))
        write(os.path.join(self.bundle_dir("Resources"), "launcher.json"),
              json.dumps({"kit": self.kit, "support": self.support, "app": self.app, "bepinex": self.bepinex}, indent=1))
        self.game = os.path.join(self.app, "Contents", "MacOS", "Lethal Company")
        os.makedirs(os.path.dirname(self.game)); shutil.copy2(self.fake_game, self.game)
        os.makedirs(self.bepinex); shutil.copy2(self.dylib, os.path.join(self.bepinex, "libdoorstop.dylib"))
        for prof in ("Default", "Café Run", "Audit"):
            write(os.path.join(self.support, "profiles", prof, "BepInEx", "core", "BepInEx.Preloader.dll"), b"MZ")
        # the launcher's json.dump writes non-ASCII as \u escapes; a nested key and other keys come first
        write(os.path.join(self.support, "state.json"), json.dumps({"steam_shortcuts": {"modded": {"exe": "/x"}}, "game_dir": "/g",
                                                                    "modded_profile": "Café Run"}, indent=1))
        self.saved = os.path.join(self.home, "Library", "Saved Application State", "com.ZeekerssRBLX.Lethal-Company.savedState")
        write(os.path.join(self.saved, "windows.plist"), "x")
        self.out = os.path.join(t, "game-out.txt")
    def tearDown(self): shutil.rmtree(self.tmp, ignore_errors=True)
    def bundle_dir(self, sub):
        d = os.path.join(self.bundle, "Contents", sub); os.makedirs(d, exist_ok=True); return d

    def run_launcher(self, *args, **env):
        e = {"PATH": "/usr/bin:/bin", "HOME": self.home, "LC_LAUNCHER_TEST": "1", "FAKE_OUT": self.out}
        e.update(env)
        r = subprocess.run([os.path.join(self.bundle, "Contents", "MacOS", "launch"), *args], env=e, capture_output=True, text=True, timeout=30)
        return r

    def game_saw(self):
        args, env = [], {}
        with open(self.out, encoding="utf-8") as f:
            for line in f.read().splitlines():
                k, _, v = line.partition("=")
                if k == "ARG": args.append(v)
                elif k == "ENV": n, _, val = v.partition("="); env[n] = val
                elif k == "CWD": env["<cwd>"] = v
        return args, env

    def check(self, r, profile):
        self.assertEqual(r.returncode, 0, r.stderr)
        args, env = self.game_saw()
        self.assertEqual(args[:3], [self.game, "-logFile", os.path.join(self.support, "work", "player-modded.log")])
        self.assertEqual(env["DOORSTOP_ENABLED"], "1"); self.assertEqual(env["DOORSTOP_IGNORE_DISABLED_ENV"], "0")
        self.assertEqual(env["DOORSTOP_TARGET_ASSEMBLY"], os.path.join(self.support, "profiles", profile, "BepInEx", "core", "BepInEx.Preloader.dll"))
        self.assertEqual(env["LC_DIRECT_LAUNCH"], "1")
        self.assertFalse(os.path.exists(self.saved))  # window state reset like install.reset_window_state()
        with open(os.path.join(self.support, "work", "modded-launcher.log"), encoding="utf-8") as f: self.assertIn(f"profile {profile}", f.read())
        return args, env

    def test_profile_from_state_and_args_passed_through(self):
        args, env = self.check(self.run_launcher("-screen-fullscreen", "1", "-psn_0_12345"), "Café Run")
        self.assertEqual(args[3:], ["-screen-fullscreen", "1"])  # Finder's -psn_ argument is dropped
        self.assertEqual(env["DYLD_INSERT_LIBRARIES"], os.path.join(self.bepinex, "libdoorstop.dylib"))  # no overlay installed
        for k in ("SteamAppId", "SteamGameId", "SteamOverlayGameId"): self.assertEqual(env[k], "1966720")

    def test_lc_profile_wins(self):
        self.check(self.run_launcher(LC_PROFILE="Audit"), "Audit")

    def test_default_profile_without_state(self):
        os.remove(os.path.join(self.support, "state.json"))
        self.check(self.run_launcher(), "Default")

    def test_steam_injected_overlay_is_kept(self):
        args, env = self.check(self.run_launcher(DYLD_INSERT_LIBRARIES=self.dylib), "Café Run")
        self.assertEqual(env["DYLD_INSERT_LIBRARIES"], os.path.join(self.bepinex, "libdoorstop.dylib") + ":" + self.dylib)

    def test_steam_ids_untouched(self):
        args, env = self.check(self.run_launcher(SteamGameId="12345678901234567890", SteamAppId="0"), "Café Run")
        self.assertEqual(env["SteamGameId"], "12345678901234567890"); self.assertEqual(env["SteamAppId"], "0")
        self.assertEqual(env["SteamOverlayGameId"], "1966720")

    def test_overlay_added_when_not_started_by_steam(self):
        overlay = os.path.join(self.home, "Library", "Application Support", "Steam", "Steam.AppBundle", "Steam", "Contents", "MacOS", "gameoverlayrenderer.dylib")
        os.makedirs(os.path.dirname(overlay)); shutil.copy2(self.dylib, overlay)
        doorstop = os.path.join(self.bepinex, "libdoorstop.dylib")
        self.assertEqual(self.check(self.run_launcher(), "Café Run")[1]["DYLD_INSERT_LIBRARIES"], doorstop + ":" + overlay)
        self.assertEqual(self.check(self.run_launcher(LC_NO_OVERLAY="1"), "Café Run")[1]["DYLD_INSERT_LIBRARIES"], doorstop)

    def test_missing_profile_hands_over_to_the_kit(self):
        py = os.path.join(self.support, "venv", "bin", "python"); os.makedirs(os.path.dirname(py)); shutil.copy2(self.fake_game, py)
        r = self.run_launcher(LC_PROFILE="Fresh")
        self.assertEqual(r.returncode, 0, r.stderr)
        args, env = self.game_saw()
        self.assertEqual(args, [py, "-m", "lcport", "play-modded", "Fresh"])
        self.assertEqual(os.path.realpath(env["<cwd>"]), os.path.realpath(self.kit)); self.assertEqual(env["LC_DIRECT_LAUNCH"], "1")
        self.assertNotIn("DOORSTOP_ENABLED", env)

    def test_errors_are_logged(self):
        os.remove(self.game)
        r = self.run_launcher()
        self.assertEqual(r.returncode, 1); self.assertFalse(os.path.exists(self.out))
        with open(os.path.join(self.support, "work", "modded-launcher.log"), encoding="utf-8") as f: log = f.read()
        self.assertIn("modded launcher error: the game is not built", log); self.assertIn(self.game, log)
        shutil.copy2(self.fake_game, self.game)  # profile missing and no kit venv: a clear error, exit 1
        r = self.run_launcher(LC_PROFILE="Nope")
        self.assertEqual(r.returncode, 1)
        with open(os.path.join(self.support, "work", "modded-launcher.log"), encoding="utf-8") as f: self.assertIn("lcport play-modded Nope", f.read())

    def test_prebuilt_is_universal(self):
        pre = os.path.join(ROOT, "prebuilt", "modded_launcher")
        self.assertTrue(os.access(pre, os.X_OK))
        out = subprocess.run(["lipo", "-archs", pre], capture_output=True, text=True).stdout.split()
        self.assertEqual(sorted(out), ["arm64", "x86_64"])

if __name__ == "__main__": unittest.main()
