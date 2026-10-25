"""Launcher control lines on stdout ("##status", "##progress", "##done", "##fail"): util.Step / progress_steps, the build,
play and mods commands, and cli.main's failure line. Everything runs on temp dirs; Steam, Unity and the network are patched."""
import io, os, sys, tempfile, types, unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try: import dnfile  # noqa: F401  (kit venv only; lcport.mods imports it)
except ImportError: sys.modules["dnfile"] = types.ModuleType("dnfile")
from lcport import config, util, unity, cli, mods, steam, install, thirdparty, rip, dotnetmeta, net_hashes, check_update
from lcport.util import Step, progress_steps

def write(path, data):
    with open(path, "wb" if isinstance(data, bytes) else "w") as f: f.write(data)

def capture(fn, *a, **k):
    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(io.StringIO()): fn(*a, **k)
    return buf.getvalue().splitlines()

def control(lines, kind=None):
    """The ## lines (optionally one kind) without the prefix: [("status", "text"), ...]."""
    out = []
    for l in lines:
        if l.startswith("##"):
            k, _, rest = l[2:].partition(" ")
            if kind is None or k == kind: out.append(rest if kind else (k, rest))
    return out

class StepTest(unittest.TestCase):
    def test_step_without_scope_prints_banner_and_status(self):
        def go():
            with Step("Unity: validate HDRP materials"): pass
        lines = capture(go)
        self.assertEqual(lines[0], "==> Unity: validate HDRP materials")
        self.assertEqual(lines[1], "##status Unity: validate HDRP materials")
        self.assertTrue(lines[2].startswith("    done in "))
        self.assertEqual(control(lines, "progress"), [])  # no scope, no bar

    def test_human_title(self):
        self.assertEqual(util.human("extract assets from your game copy (AssetRipper)"), "Extract assets from your game copy")
        self.assertEqual(util.human("Steam ownership check"), "Steam ownership check")
        self.assertEqual(Step("x (y)", status="Doing x").title, "Doing x")

    def test_progress_steps_numbers_top_level_steps(self):
        def go():
            with progress_steps(3):
                with Step("one"): pass
                with Step("two"):
                    with Step("inner detail"): pass  # nested: same number, no bar movement
                with progress_steps(99):  # a nested scope joins the outer one
                    with Step("three", status="Third thing"): pass
        lines = capture(go)
        self.assertEqual(control(lines, "status"), ["One (1/3)", "Two (2/3)", "Inner detail (2/3)", "Third thing (3/3)"])
        self.assertEqual(control(lines, "progress"), ["0", "33", "33", "67", "67", "100"])
        self.assertIsNone(util._scope)  # the scope closes again

    def test_failed_step_does_not_advance_bar_and_scope_resets(self):
        def go():
            with progress_steps(2):
                with Step("one"): raise RuntimeError("boom")
        buf = io.StringIO()
        with redirect_stdout(buf), self.assertRaises(RuntimeError): go()
        self.assertEqual(control(buf.getvalue().splitlines(), "progress"), ["0"])
        self.assertIsNone(util._scope)

    def test_progress_is_clamped(self):
        self.assertEqual(capture(util.progress, 140.2), ["##progress 100"])
        self.assertEqual(capture(util.progress, -3), ["##progress 0"])
        self.assertEqual(capture(util.progress, 44.4), ["##progress 44"])

class BuildProgressTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); t = self.tmp.name
        self.game = os.path.join(t, "Lethal Company"); managed = os.path.join(self.game, "Lethal Company_Data", "Managed"); os.makedirs(managed)
        for f in ("Assembly-CSharp.dll", "Assembly-CSharp-firstpass.dll"): write(os.path.join(managed, f), b"MZ")
        write(os.path.join(self.game, "Lethal Company.exe"), b"MZ")
        work = os.path.join(t, "work"); os.makedirs(os.path.join(work, "rip")); write(os.path.join(work, "rip", ".assembled"), "ok")
        def fake_install_app(*a):
            with Step("install app", status="Installing the game in Applications"): pass
        def fake_install_modded():
            with Step("install modded", status="Installing the modded launcher"): pass
        self.patches = [mock.patch.object(config, "SUPPORT", t), mock.patch.object(config, "WORK", work), mock.patch.object(config, "STATE", os.path.join(t, "state.json")),
                        mock.patch.object(steam, "ensure_running", lambda *a: True), mock.patch.object(steam, "owns_game", lambda *a: True),
                        mock.patch.object(thirdparty, "natives", lambda: t), mock.patch.object(unity, "game_unity_version", lambda g: "2022.3.62f2"),
                        mock.patch.object(unity, "editor_for", lambda v: "/fake/Unity.app"), mock.patch.object(unity, "batch", lambda *a, **k: None),
                        mock.patch.object(rip, "export", lambda *a: os.path.join(work, "rip")), mock.patch.object(dotnetmeta, "retarget", lambda *a: 0),
                        mock.patch.object(net_hashes, "fix_build", lambda *a: None), mock.patch.object(install, "install_app", fake_install_app),
                        mock.patch.object(install, "install_modded_launcher", fake_install_modded), mock.patch.object(cli, "record_game_shaders", lambda: None),
                        mock.patch.object(check_update, "check", lambda **k: 0)]
        for p in self.patches: p.start()
    def tearDown(self):
        for p in self.patches: p.stop()
        self.tmp.cleanup()

    def test_build_counts_every_top_level_step(self):
        lines = capture(cli.cmd_build, [self.game])
        statuses = control(lines, "status")
        numbered = [s for s in statuses if s.endswith(f"/{cli.BUILD_STEPS})")]
        self.assertEqual(numbered, statuses)  # every status carries the step count
        tops = sorted({int(s.rsplit("(", 1)[1].split("/")[0]) for s in statuses})
        self.assertEqual(tops, list(range(1, cli.BUILD_STEPS + 1)))  # BUILD_STEPS matches the real number of steps
        self.assertIn("Compiling shaders and building the app (30-60 min) (9/14)", statuses)
        pcts = [int(p) for p in control(lines, "progress")]
        self.assertEqual(pcts, sorted(pcts)); self.assertEqual(pcts[-1], 100)
        self.assertEqual(control(lines)[-1], ("done", "Build finished. Lethal Company is in your Applications folder"))

    def test_full_build_alone_has_its_own_scope(self):
        lines = capture(unity.full_build, "/fake/Unity.app", "/proj", os.path.join(self.tmp.name, "out.app"))
        self.assertEqual(control(lines, "status"), ["Importing the project into Unity (1/5)", "Fixing material shaders (2/5)", "Checking materials (3/5)",
                                                    "Preparing videos (4/5)", "Compiling shaders and building the app (30-60 min) (5/5)"])
        self.assertEqual(control(lines, "progress")[-1], "100")

class PlayAndFailTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); t = self.tmp.name
        self.app = os.path.join(t, "Lethal Company.app"); os.makedirs(self.app)
        self.patches = [mock.patch.object(config, "APP_DST", self.app), mock.patch.object(config, "WORK", t), mock.patch.object(config, "SUPPORT", t),
                        mock.patch.object(config, "STATE", os.path.join(t, "state.json")), mock.patch.object(steam, "ensure_running", lambda *a: True),
                        mock.patch.object(cli, "bootstrap", lambda: None)]
        for p in self.patches: p.start()
    def tearDown(self):
        for p in self.patches: p.stop()
        self.tmp.cleanup()

    def test_play_direct(self):
        proc = types.SimpleNamespace(pid=4242, wait=lambda: 0)
        with mock.patch.object(steam, "launch", lambda *a, **k: proc): lines = capture(cli.cmd_play, [])
        self.assertEqual(control(lines), [("status", "Launching..."), ("status", "Game running"), ("done", "Game closed")])
        self.assertIn("Game closed (exit 0)", lines)  # the log keeps the plain lines

    def test_play_through_steam(self):
        with mock.patch.object(steam, "launch", lambda *a, **k: None): lines = capture(cli.cmd_play, [])
        self.assertEqual(control(lines), [("status", "Launching..."), ("done", "Launched through Steam")])

    def run_main(self, *argv):
        buf = io.StringIO()
        with mock.patch.object(sys, "argv", ["lcport", *argv]), redirect_stdout(buf), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm: cli.main()
        return cm.exception.code, buf.getvalue().splitlines()

    def test_error_prints_fail_line(self):
        with mock.patch.object(config, "APP_DST", os.path.join(self.tmp.name, "missing.app")):
            code, lines = self.run_main("play")
        self.assertEqual(code, 1)
        self.assertEqual(control(lines, "fail"), ["Lethal Company is not built yet. Run: build <game folder>"])

    def test_plain_exit_code_is_kept_without_fail_line(self):
        with mock.patch.object(check_update, "check", lambda **k: 0): code, lines = self.run_main("check-update")
        self.assertEqual(code, 0); self.assertEqual(control(lines, "fail"), [])
        with mock.patch.object(check_update, "check", lambda **k: 2): code, lines = self.run_main("check-update")
        self.assertEqual(code, 2); self.assertEqual(control(lines, "fail"), [])

def pkg(owner, name, version, deps=()):
    return {"name": name, "full_name": f"{owner}-{name}", "owner": owner, "rating_score": 1, "is_deprecated": False, "categories": [], "date_updated": "",
            "versions": [{"version_number": version, "full_name": f"{owner}-{name}-{version}", "description": "", "downloads": 1, "icon": "",
                          "website_url": "", "dependencies": list(deps), "download_url": "https://example.invalid/x.zip"}]}

FAKE_INDEX = [pkg("BepInEx", "BepInExPack", "5.4.2100"), pkg("notnotnotswipez", "MoreCompany", "1.14.0", deps=["BepInEx-BepInExPack-5.4.2100"]),
              pkg("Owner", "Other", "2.0.0")]

class ModsProgressTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); t = self.tmp.name
        os.makedirs(os.path.join(t, "profiles", "P"))
        self.patches = [mock.patch.object(config, "CACHE", t), mock.patch.object(config, "PROFILES", os.path.join(t, "profiles")),
                        mock.patch.object(mods, "index", lambda: FAKE_INDEX), mock.patch.object(mods, "profile_dir", lambda p: t),
                        mock.patch.object(mods, "download", lambda v: "unused.zip"), mock.patch.object(mods, "extract_mod", lambda *a: None)]
        for p in self.patches: p.start()
    def tearDown(self):
        for p in self.patches: p.stop()
        self.tmp.cleanup()

    def test_install_reports_each_mod_and_progress(self):
        with mock.patch.object(mods, "audit", lambda prof, save=True: util.status("checking the mods for Mac compatibility")):
            lines = capture(mods.main, ["install", "P", "notnotnotswipez-MoreCompany", "Owner-Other"])
        self.assertEqual(control(lines, "status"), ["installing MoreCompany 1.14.0", "installing Other 2.0.0", "installing BepInExPack 5.4.2100",
                                                    "checking the mods for Mac compatibility"])
        pcts = [int(p) for p in control(lines, "progress")]
        self.assertEqual(pcts, sorted(pcts)); self.assertEqual(pcts[0], 0); self.assertEqual(pcts[-1], 90)
        self.assertEqual(control(lines)[-1], ("done", "Mods installed"))
        self.assertIn("installing notnotnotswipez-MoreCompany 1.14.0", lines)  # the plain log line stays

    def test_apply_removes_then_installs_then_audits(self):
        removed = []
        with mock.patch.object(mods, "remove", lambda prof, name: removed.append(name)), mock.patch.object(mods, "audit", lambda prof, save=True: None):
            lines = capture(mods.main, ["apply", "P", "--install", "Owner-Other", "--remove", "A-One", "B-Two"])
        self.assertEqual(removed, ["A-One", "B-Two"])
        self.assertEqual(control(lines, "status"), ["removing One", "removing Two", "installing Other 2.0.0"])
        pcts = [int(p) for p in control(lines, "progress")]
        self.assertEqual(pcts, sorted(pcts)); self.assertEqual(pcts[:2], [0, 30]); self.assertEqual(pcts[-1], 90)
        self.assertEqual(control(lines)[-1], ("done", "Changes applied"))

    def test_remove_update_import_audit_finish_with_done(self):
        with mock.patch.object(mods, "remove", lambda *a: None), mock.patch.object(mods, "install", lambda *a, **k: None), \
             mock.patch.object(mods, "import_code", lambda *a: None), mock.patch.object(mods, "audit", lambda *a, **k: None):
            self.assertEqual(control(capture(mods.main, ["remove", "P", "A-One"])), [("status", "removing One"), ("done", "Removed One")])
            self.assertEqual(control(capture(mods.main, ["update", "P"])), [("done", "Mods up to date")])
            self.assertEqual(control(capture(mods.main, ["import", "P", "code"])), [("done", "Profile imported")])
            self.assertEqual(control(capture(mods.main, ["audit", "P"])), [("done", "Mod check finished")])

    def test_json_commands_stay_pure_json(self):
        for args in (["json-search", ""], ["json-info", "Owner-Other"], ["json-installed", "P"]):
            self.assertFalse([l for l in capture(mods.main, args) if l.startswith("##")], args)

if __name__ == "__main__": unittest.main()
