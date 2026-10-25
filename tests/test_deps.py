"""Unity Hub install, Unity sign-in detection and the check-unity / setup commands. Nothing real is downloaded, mounted,
opened or slept: download, run, the licence folders and the Applications folders are patched onto temp dirs."""
import io, json, os, shutil, stat, sys, tempfile, types, unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try: import dnfile  # noqa: F401  (kit venv only; lcport.mods imports it)
except ImportError: sys.modules["dnfile"] = types.ModuleType("dnfile")
from lcport import config, deps, cli, unity, util

def capture(fn, *a, **k):
    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(io.StringIO()): result = fn(*a, **k)
    return result, buf.getvalue().splitlines()

def put(path, text):
    with open(path, "wb" if isinstance(text, bytes) else "w") as f: f.write(text)

def statuses(lines): return [l[len("##status "):] for l in lines if l.startswith("##status ")]

def licence_xml(namespace="unity_editor", entitlement="com.unity.editor", update="2099-01-01T00:00:00.000Z"):
    upd = f"<UpdateDate>{update}</UpdateDate>" if update else ""
    return (f'<root><License Id="x" Version="1"><EntitlementGroups><EntitlementGroup Namespace="{namespace}" Type="EDITOR">'
            f'<Context><User Id="1"/><StartDate>2022-10-12T18:18:19Z</StartDate>{upd}</Context>'
            f'<Entitlements><Entitlement Id="{entitlement}"/></Entitlements></EntitlementGroup></EntitlementGroups></License></root>')

class TempHome(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(); self.addCleanup(self.cleanup)
        self.sys_apps = os.path.join(self.tmp, "Applications"); self.user_apps = os.path.join(self.tmp, "home", "Applications")
        os.makedirs(self.sys_apps)
        self.lic = os.path.join(self.tmp, "licenses"); os.makedirs(self.lic)
        for target, name, value in [(deps, "APP_DIRS", (self.sys_apps, self.user_apps)), (deps, "LICENCE_DIR", self.lic),
                                    (deps, "LEGACY_LICENCES", (os.path.join(self.tmp, "none.ulf"),)), (config, "CACHE", os.path.join(self.tmp, "cache"))]:
            p = mock.patch.object(target, name, value); p.start(); self.addCleanup(p.stop)
    def cleanup(self):
        for root, dirs, _ in os.walk(self.tmp):
            for d in dirs: os.chmod(os.path.join(root, d), 0o755)
        shutil.rmtree(self.tmp, ignore_errors=True)
    def make_hub(self, apps):
        b = deps.hub_binary(os.path.join(apps, deps.HUB_APP)); os.makedirs(os.path.dirname(b)); put(b, "hub")
        return os.path.join(apps, deps.HUB_APP)

class HubPathTest(TempHome):
    def test_none_when_missing(self):
        self.assertIsNone(deps.hub_path())
    def test_user_applications(self):
        self.make_hub(self.user_apps)
        self.assertEqual(deps.hub_path(), os.path.join(self.user_apps, deps.HUB_APP))
    def test_system_applications_first(self):
        self.make_hub(self.user_apps); self.make_hub(self.sys_apps)
        self.assertEqual(deps.hub_path(), os.path.join(self.sys_apps, deps.HUB_APP))
    def test_app_without_binary_does_not_count(self):
        os.makedirs(os.path.join(self.sys_apps, deps.HUB_APP, "Contents"))
        self.assertIsNone(deps.hub_path())

class InstallHubTest(TempHome):
    def setUp(self):
        super().setUp(); self.calls = []; self.attach_ok = True
        self.dmg = os.path.join(config.CACHE, "UnityHubSetup.dmg")
        def fake_download(url, name=None, force=False, show_progress=False):
            self.download_args = (url, name, show_progress)
            os.makedirs(config.CACHE, exist_ok=True); put(self.dmg, b"dmg"); return self.dmg
        def fake_run(cmd, check=True, capture=False, **k):
            self.calls.append(list(cmd))
            if cmd[:2] == ["hdiutil", "attach"]:
                if not self.attach_ok: return types.SimpleNamespace(returncode=1, stdout="", stderr="image not recognized")
                mnt = cmd[cmd.index("-mountpoint") + 1]; b = deps.hub_binary(os.path.join(mnt, deps.HUB_APP))
                os.makedirs(os.path.dirname(b)); put(b, "hub")
            elif cmd[0] == "ditto": shutil.copytree(cmd[1], cmd[2])
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")
        for name, fn in (("download", fake_download), ("run", fake_run)):
            p = mock.patch.object(deps, name, fn); p.start(); self.addCleanup(p.stop)
    def kinds(self): return [c[0] if c[0] != "hdiutil" else "hdiutil " + c[1] for c in self.calls]

    def test_installs_into_applications(self):
        dst, lines = capture(deps.install_hub)
        self.assertEqual(dst, os.path.join(self.sys_apps, deps.HUB_APP))
        self.assertEqual(self.download_args, (deps.HUB_DMG_URL, "UnityHubSetup.dmg", True))
        self.assertTrue(os.path.exists(deps.hub_binary(dst)))
        self.assertEqual(self.kinds(), ["hdiutil attach", "ditto", "hdiutil detach", "xattr"])
        attach = self.calls[0]
        for flag in ("-nobrowse", "-quiet", "-mountpoint"): self.assertIn(flag, attach)
        self.assertEqual(attach[-1], self.dmg)
        mnt = attach[attach.index("-mountpoint") + 1]
        self.assertEqual(self.calls[1], ["ditto", os.path.join(mnt, deps.HUB_APP), dst])
        self.assertEqual(self.calls[2][-1], mnt)
        self.assertEqual(self.calls[3], ["xattr", "-dr", "com.apple.quarantine", dst])
        self.assertFalse(os.path.exists(mnt))  # mount point cleaned up
        self.assertEqual(deps.hub_path(), dst)
        self.assertIn("Downloading Unity Hub", statuses(lines)); self.assertIn("Installing Unity Hub", statuses(lines))

    def test_falls_back_to_user_applications(self):
        os.chmod(self.sys_apps, stat.S_IRUSR | stat.S_IXUSR)  # /Applications not writable
        dst, _ = capture(deps.install_hub)
        self.assertEqual(dst, os.path.join(self.user_apps, deps.HUB_APP))
        self.assertTrue(os.path.exists(deps.hub_binary(dst)))
        self.assertEqual(self.kinds(), ["hdiutil attach", "ditto", "hdiutil detach", "xattr"])
        self.assertEqual(deps.hub_path(), dst)

    def test_replaces_broken_leftover(self):
        os.makedirs(os.path.join(self.sys_apps, deps.HUB_APP, "Contents", "junk"))
        dst, _ = capture(deps.install_hub)
        self.assertFalse(os.path.exists(os.path.join(dst, "Contents", "junk")))
        self.assertTrue(os.path.exists(deps.hub_binary(dst)))

    def test_not_a_disk_image(self):
        self.attach_ok = False
        buf = io.StringIO()
        with redirect_stdout(buf), self.assertRaises(RuntimeError) as cm: deps.install_hub()
        self.assertIn("not a valid disk image", str(cm.exception))
        self.assertEqual(self.kinds(), ["hdiutil attach"])  # nothing copied, nothing to detach
        self.assertFalse(os.path.exists(self.dmg))  # the bad download is deleted so the next run fetches it again
        self.assertEqual([d for d in os.listdir(config.CACHE) if d.startswith("unityhub-mount-")], [])
        self.assertIsNone(deps.hub_path())

class DownloadProgressTest(TempHome):
    class Resp(io.BytesIO):
        def __init__(self, data): super().__init__(data); self.headers = {"Content-Length": str(len(data))}
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def test_progress_is_scaled_into_the_current_step(self):
        data = b"x" * (4 << 20)  # four 1 MiB chunks
        def go():
            with util.progress_steps(4):
                with util.Step("one"): pass
                with util.Step("two"): return util.download("http://example.invalid/hub.dmg", show_progress=True)
        with mock.patch("urllib.request.urlopen", return_value=self.Resp(data)): path, lines = capture(go)
        pcts = [int(l.split()[1]) for l in lines if l.startswith("##progress ")]
        self.assertEqual(pcts, [0, 25, 25, 31, 38, 44, 50, 50])  # step 2 of 4 spans 25-50
        with open(path, "rb") as f: self.assertEqual(f.read(), data)

    def test_plain_download_is_silent(self):
        with mock.patch("urllib.request.urlopen", return_value=self.Resp(b"y" * 1000)):
            _, lines = capture(util.download, "http://example.invalid/a.zip")
        self.assertEqual([l for l in lines if l.startswith("##")], [])

class SignedInTest(TempHome):
    def write(self, name, text): put(os.path.join(self.lic, name), text)

    def test_absent(self):
        self.assertFalse(deps.unity_signed_in())
    def test_personal_licence_present(self):
        self.write("UnityEntitlementLicense.xml", licence_xml())
        self.assertTrue(deps.unity_signed_in())
    def test_headless_entitlement_counts(self):
        self.write("UnityEntitlementLicense.xml", licence_xml(entitlement="com.unity.editor.headless"))
        self.assertTrue(deps.unity_signed_in())
    def test_without_update_date(self):
        self.write("UnityEntitlementLicense.xml", licence_xml(update=None))
        self.assertTrue(deps.unity_signed_in())
    def test_expired_licence(self):
        self.write("UnityEntitlementLicense.xml", licence_xml(update="2020-01-01T00:00:00Z"))
        self.assertFalse(deps.unity_signed_in())
    def test_other_namespace_only(self):
        self.write("UnityEntitlementLicense.xml", licence_xml(namespace="asset_store", entitlement="com.meta.xr.sdk.core"))
        self.assertFalse(deps.unity_signed_in())
    def test_garbage_and_subfolder_ignored(self):
        self.write("broken.xml", "<root><unclosed>")
        os.makedirs(os.path.join(self.lic, "packages")); put(os.path.join(self.lic, "packages", "x.xml"), licence_xml())
        self.assertFalse(deps.unity_signed_in())
    def test_legacy_ulf(self):
        ulf = os.path.join(self.tmp, "Unity_lic.ulf"); put(ulf, "x")
        with mock.patch.object(deps, "LEGACY_LICENCES", (ulf,)): self.assertTrue(deps.unity_signed_in())

class EnsureSignedInTest(unittest.TestCase):
    def setUp(self): self.sleeps = []; self.opens = 0
    def sleep(self, s): self.sleeps.append(s)
    def opener(self): self.opens += 1
    def answers(self, *seq):
        it = iter(seq); return lambda: next(it)

    def test_already_signed_in(self):
        ok, lines = capture(deps.ensure_unity_signed_in, check=lambda: True, sleep=self.sleep, opener=self.opener)
        self.assertTrue(ok); self.assertEqual(self.opens, 0); self.assertEqual(self.sleeps, []); self.assertEqual(statuses(lines), [])

    def test_signs_in_after_two_polls(self):
        ok, lines = capture(deps.ensure_unity_signed_in, check=self.answers(False, False, True), sleep=self.sleep, opener=self.opener)
        self.assertTrue(ok); self.assertEqual(self.opens, 1); self.assertEqual(self.sleeps, [3, 3])
        self.assertEqual(statuses(lines), [deps.SIGNIN_STATUS])
        self.assertIn("##status Sign in to Unity Hub (free Personal licence), then come back here", lines)

    def test_status_every_30_seconds(self):
        ok, lines = capture(deps.ensure_unity_signed_in, check=self.answers(*([False] * 21 + [True])), sleep=self.sleep, opener=self.opener)
        self.assertTrue(ok); self.assertEqual(len(self.sleeps), 21); self.assertEqual(self.opens, 1)
        self.assertEqual(statuses(lines), [deps.SIGNIN_STATUS, deps.SIGNIN_STATUS + " (waiting 0:30)", deps.SIGNIN_STATUS + " (waiting 1:00)"])

    def test_timeout_raises(self):
        checks = []
        def check(): checks.append(1); return False
        buf = io.StringIO()
        with redirect_stdout(buf), self.assertRaises(RuntimeError) as cm:
            deps.ensure_unity_signed_in(check=check, sleep=self.sleep, opener=self.opener)
        self.assertIn("No Unity sign-in after 15 minutes", str(cm.exception))
        self.assertEqual(self.opens, 1); self.assertEqual(sum(self.sleeps), 15 * 60); self.assertEqual(len(checks), 15 * 60 // 3 + 1)
        self.assertEqual(len(statuses(buf.getvalue().splitlines())), 1 + 15 * 60 // 30)

    def test_default_opener_opens_the_hub(self):
        with mock.patch.object(deps, "run") as run:
            capture(deps.ensure_unity_signed_in, check=self.answers(False, True), sleep=self.sleep)
        run.assert_called_once_with(["open", "-a", "Unity Hub"], check=False)

class CommandsTest(TempHome):
    def run_main(self, *argv):
        buf = io.StringIO()
        with mock.patch.object(cli, "bootstrap", lambda: None), mock.patch.object(sys, "argv", ["lcport", *argv]), redirect_stdout(buf), redirect_stderr(io.StringIO()):
            cli.main()
        return buf.getvalue().splitlines()

    def test_check_unity_ready(self):
        hub = self.make_hub(self.sys_apps); put(os.path.join(self.lic, "UnityEntitlementLicense.xml"), licence_xml())
        editor = os.path.join(self.tmp, "Editor", config.UNITY_VERSION, "Unity.app"); os.makedirs(os.path.join(editor, "Contents", "MacOS"))
        put(os.path.join(editor, "Contents", "MacOS", "Unity"), "u")
        with mock.patch.object(config, "UNITY_EDITORS", os.path.join(self.tmp, "Editor")), mock.patch.object(config, "STATE", os.path.join(self.tmp, "state.json")):
            lines = self.run_main("check-unity")
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0]), {"hub": hub, "signed_in": True, "editor": editor})

    def test_check_unity_nothing_installed(self):
        with mock.patch.object(config, "UNITY_EDITORS", os.path.join(self.tmp, "Editor")), mock.patch.object(config, "STATE", os.path.join(self.tmp, "state.json")):
            lines = self.run_main("check-unity")
        self.assertEqual(lines, ['{"hub": null, "signed_in": false, "editor": null}'])

    def test_setup_runs_the_four_steps_in_order(self):
        order = []
        patches = [mock.patch.object(deps, "ensure_venv", lambda: order.append("venv")),
                   mock.patch.object(deps, "hub_path", lambda: order.append("hub_path")),
                   mock.patch.object(deps, "install_hub", lambda: order.append("install_hub") or "/x/Unity Hub.app"),
                   mock.patch.object(deps, "ensure_unity_signed_in", lambda: order.append("signin")),
                   mock.patch.object(unity, "editor_for", lambda v: order.append("editor") or "/x/Unity.app"),
                   mock.patch.object(config, "STATE", os.path.join(self.tmp, "state.json"))]
        for p in patches: p.start(); self.addCleanup(p.stop)
        lines = self.run_main("setup")
        self.assertEqual(order, ["venv", "hub_path", "install_hub", "signin", "editor"])
        self.assertEqual(statuses(lines), ["Checking the Python packages (1/4)", "Checking Unity Hub (2/4)", "Checking the Unity sign-in (3/4)", f"Checking Unity {config.UNITY_VERSION} (4/4)"])
        self.assertEqual([l for l in lines if l.startswith("##progress")][-1], "##progress 100")
        self.assertEqual(lines[-1], f"##done Unity {config.UNITY_VERSION} is ready")

if __name__ == "__main__": unittest.main()
