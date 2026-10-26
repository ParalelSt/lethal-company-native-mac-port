"""Downloadable launcher builds: which files the app carries, where the kit is found, and self-update inside the bundle."""
import os, shutil, subprocess, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from lcport import config, selfupdate

def kit_files():
    with open(os.path.join(ROOT, "launcher", "kit-files")) as f: return [l.strip() for l in f if l.strip()]

def make_kit(path, version):
    os.makedirs(os.path.join(path, "lcport")); os.makedirs(os.path.join(path, "prebuilt"))
    with open(os.path.join(path, "lcport", "__init__.py"), "w") as f: f.write(f'__version__ = "{version}"\n')
    with open(os.path.join(path, "prebuilt", "tool"), "w") as f: f.write(version)
    os.chmod(os.path.join(path, "prebuilt", "tool"), 0o755)

def make_app(path, version):
    """An .app laid out like build.sh --embed: launcher binary, Info.plist, kit in Contents/Resources/kit."""
    os.makedirs(os.path.join(path, "Contents", "MacOS"))
    with open(os.path.join(path, "Contents", "MacOS", "Lethal Company Port"), "w") as f: f.write("bin " + version)
    with open(os.path.join(path, "Contents", "Info.plist"), "w") as f: f.write("plist " + version)
    make_kit(os.path.join(path, config.EMBEDDED_KIT), version)

def read(p):
    with open(p) as f: return f.read()

class EmbeddedFileList(unittest.TestCase):
    def test_exact_list(self):
        self.assertEqual(sorted(kit_files()), sorted(["lcport", "prebuilt", "unity", "README.md", "CHANGELOG.md", "LICENSE", "THIRD_PARTY.md"]))

    def test_excludes_dev_folders(self):
        for name in ("tests", "tools", "native", "scripts", "launcher", "Lethal Company Port.app"):
            self.assertNotIn(name, kit_files())

    def test_every_entry_exists(self):
        for name in kit_files(): self.assertTrue(os.path.exists(os.path.join(ROOT, name)), name)

    def test_build_script_uses_list(self):
        s = read(os.path.join(ROOT, "launcher", "build.sh"))
        self.assertIn("kit-files", s); self.assertIn("rsync -a --delete --exclude __pycache__", s); self.assertIn("Contents/Resources/kit", s)

class KitResolution(unittest.TestCase):
    """config.bundle_app: the bundle that carries the kit (downloaded build) or None (git checkout, the dev layout)."""
    def setUp(self): self.tmp = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.tmp)

    def test_embedded_layout(self):
        app = os.path.join(self.tmp, "Applications", "Lethal Company Port.app"); make_app(app, "1.0.0")
        self.assertEqual(config.bundle_app(os.path.join(app, config.EMBEDDED_KIT)), app)
        self.assertEqual(config.bundle_app(os.path.join(app, config.EMBEDDED_KIT) + "/"), app)

    def test_dev_layout(self):
        kit = os.path.join(self.tmp, "lethal-company-mac-port"); make_kit(kit, "1.0.0")
        os.makedirs(os.path.join(kit, "Lethal Company Port.app", "Contents", "MacOS"))
        self.assertIsNone(config.bundle_app(kit))

    def test_resources_kit_outside_an_app(self):
        self.assertIsNone(config.bundle_app(os.path.join(self.tmp, "Something", "Contents", "Resources", "kit")))

    def test_swift_rule(self):
        """Launcher.swift: Contents/Resources/kit when it holds lcport/__init__.py, else the folder containing the .app."""
        s = read(os.path.join(ROOT, "launcher", "Launcher.swift"))
        self.assertIn('appendingPathComponent("kit")', s); self.assertIn('appendingPathComponent("lcport/__init__.py")', s)
        self.assertIn("Bundle.main.bundleURL.deletingLastPathComponent()", s); self.assertIn("kit = Launcher.resolveKit()", s)

class Latest(unittest.TestCase):
    def rel(self, *names):
        return {"tag_name": "v0.2.0", "body": "notes", "assets": [{"name": n, "browser_download_url": "https://x/" + n} for n in names]}

    def test_prefers_app_zip(self):
        with mock.patch.object(selfupdate, "http_json", return_value=self.rel("L-0.2.0-source.zip", "L-0.2.0.dmg", "L-0.2.0-app.zip")):
            self.assertEqual(selfupdate.latest()["url"], "https://x/L-0.2.0-app.zip")

    def test_falls_back_to_any_zip(self):
        with mock.patch.object(selfupdate, "http_json", return_value=self.rel("L-0.2.0.dmg", "L-0.2.0.zip")):
            l = selfupdate.latest()
        self.assertEqual((l["version"], l["url"]), ("0.2.0", "https://x/L-0.2.0.zip"))

    def test_no_zip(self):
        with mock.patch.object(selfupdate, "http_json", return_value=self.rel("L-0.2.0.dmg")):
            self.assertIsNone(selfupdate.latest()["url"])

class Apply(unittest.TestCase):
    """apply() with a real zip extracted by ditto; codesign and xattr are recorded, never run."""
    def setUp(self):
        self.tmp = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.tmp); self.calls = []
        real = subprocess.run
        def fake(cmd, *a, **k):
            if cmd[0] == "ditto": return real(cmd, *a, **k)
            self.calls.append(cmd); return subprocess.CompletedProcess(cmd, 0, b"", b"")
        p = mock.patch.object(selfupdate.subprocess, "run", side_effect=fake); p.start(); self.addCleanup(p.stop)

    def zip_of(self, src, keep_parent=True):
        z = os.path.join(self.tmp, "release.zip")
        subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc"] + (["--keepParent"] if keep_parent else []) + [src, z], check=True)
        return z

    def run_apply(self, kit, archive):
        with mock.patch.object(config, "KIT", kit), mock.patch.object(selfupdate, "download", return_value=archive), \
             mock.patch.object(selfupdate, "log"):
            selfupdate.apply({"url": "https://x/r-app.zip", "version": "0.2.0"})

    def test_inside_bundle_updates_kit_binary_and_resigns(self):
        app = os.path.join(self.tmp, "Applications", "Lethal Company Port.app"); make_app(app, "0.1.0")
        with open(os.path.join(app, config.EMBEDDED_KIT, "lcport", "stale.py"), "w") as f: f.write("")
        new = os.path.join(self.tmp, "new", "Lethal Company Port.app"); make_app(new, "0.2.0")
        kit = os.path.join(app, config.EMBEDDED_KIT)
        self.run_apply(kit, self.zip_of(new))
        self.assertIn('"0.2.0"', read(os.path.join(kit, "lcport", "__init__.py")))
        self.assertFalse(os.path.exists(os.path.join(kit, "lcport", "stale.py")))
        self.assertTrue(os.access(os.path.join(kit, "prebuilt", "tool"), os.X_OK))
        self.assertEqual(read(os.path.join(app, "Contents", "MacOS", "Lethal Company Port")), "bin 0.2.0")
        self.assertEqual(read(os.path.join(app, "Contents", "Info.plist")), "plist 0.2.0")
        self.assertFalse(os.path.exists(os.path.join(kit, "Contents")))
        self.assertIn(["codesign", "--force", "--deep", "--sign", "-", app], self.calls)
        self.assertIn(["xattr", "-dr", "com.apple.quarantine", app], self.calls)

    def test_dev_layout_with_app_zip_copies_kit_only(self):
        kit = os.path.join(self.tmp, "checkout"); make_kit(kit, "0.1.0")
        new = os.path.join(self.tmp, "new", "Lethal Company Port.app"); make_app(new, "0.2.0")
        self.run_apply(kit, self.zip_of(new))
        self.assertIn('"0.2.0"', read(os.path.join(kit, "lcport", "__init__.py")))
        self.assertFalse(os.path.exists(os.path.join(kit, "Contents")))
        self.assertEqual(self.calls, [])

    def test_dev_layout_with_source_zip(self):
        kit = os.path.join(self.tmp, "checkout"); make_kit(kit, "0.1.0")
        src = os.path.join(self.tmp, "src", "Lethal-Company-Port-0.2.0"); make_kit(src, "0.2.0")
        with open(os.path.join(src, "README.md"), "w") as f: f.write("new readme")
        self.run_apply(kit, self.zip_of(src))
        self.assertIn('"0.2.0"', read(os.path.join(kit, "lcport", "__init__.py")))
        self.assertEqual(read(os.path.join(kit, "README.md")), "new readme")
        self.assertEqual(self.calls, [])

    def test_zip_without_kit_changes_nothing(self):
        kit = os.path.join(self.tmp, "checkout"); make_kit(kit, "0.1.0")
        junk = os.path.join(self.tmp, "junk", "stuff"); os.makedirs(junk)
        with open(os.path.join(junk, "a.txt"), "w") as f: f.write("x")
        with self.assertRaises(RuntimeError): self.run_apply(kit, self.zip_of(junk))
        self.assertIn('"0.1.0"', read(os.path.join(kit, "lcport", "__init__.py")))

class Release(unittest.TestCase):
    def test_three_assets(self):
        s = read(os.path.join(ROOT, "scripts", "release.sh"))
        for part in ('$NAME.dmg', '$NAME-app.zip', '$NAME-source.zip', 'ln -s /Applications', 'hdiutil create', '--sequesterRsrc --keepParent',
                     'build.sh --embed', '--title "Launcher $VER"'):
            self.assertIn(part, s)

    def test_version_bump_is_idempotent(self):
        """release.sh rewrites __version__ with this sed; on a tree already at the version it must not change the file."""
        from lcport import __version__
        tmp = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, tmp)
        p = os.path.join(tmp, "__init__.py"); shutil.copy2(os.path.join(ROOT, "lcport", "__init__.py"), p); before = read(p)
        subprocess.run(["sed", "-i", "", f's/^__version__ = .*/__version__ = "{__version__}"/', p], check=True)
        self.assertEqual(read(p), before)

    def test_changelog_has_version_section(self):
        from lcport import __version__
        self.assertIn(f"## [{__version__}]", read(os.path.join(ROOT, "CHANGELOG.md")))

if __name__ == "__main__": unittest.main()
