"""Download and install progress lines (##status / ##progress), with the network and extraction faked."""
import io, os, re, shutil, sys, tempfile, unittest
from unittest import mock
from contextlib import redirect_stdout, redirect_stderr

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import types
try: import dnfile  # noqa: F401
except ImportError: sys.modules["dnfile"] = types.ModuleType("dnfile")
from lcport import mods, config


class FakeResp(io.BytesIO):
    def __init__(self, data, length=True):
        super().__init__(data); self.headers = {"Content-Length": str(len(data))} if length else {}
    def __enter__(self): return self
    def __exit__(self, *a): return False


def pcts(text): return [int(m) for m in re.findall(r"^##progress (\d+)$", text, re.M)]


class ModProgress(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        for name in ("CACHE", "PROFILES"):
            p = mock.patch.object(config, name, os.path.join(self.tmp, name.lower())); p.start(); self.addCleanup(p.stop)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def capture(self, fn, *a, **k):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()): fn(*a, **k)
        return out.getvalue()

    def test_download_progress_follows_bytes_in_span(self):
        data = b"x" * (64 * 1024 * 3)  # three 64 KiB chunks
        v = {"full_name": "A-One", "download_url": "http://example.invalid/a.zip"}
        with mock.patch("urllib.request.urlopen", return_value=FakeResp(data)):
            text = self.capture(mods.download, v, (20, 50))
        p = pcts(text)
        self.assertEqual(p, [30, 40, 50])
        self.assertEqual(p, sorted(p))
        self.assertEqual(open(os.path.join(config.CACHE, "mods", "A-One.zip"), "rb").read(), data)

    def test_download_without_span_or_length_is_silent(self):
        v = {"full_name": "B-Two", "download_url": "http://example.invalid/b.zip"}
        with mock.patch("urllib.request.urlopen", return_value=FakeResp(b"y" * 100000)):
            self.assertEqual(pcts(self.capture(mods.download, v)), [])
        v2 = {"full_name": "C-Three", "download_url": "http://example.invalid/c.zip"}
        with mock.patch("urllib.request.urlopen", return_value=FakeResp(b"y" * 100000, length=False)):
            self.assertEqual(pcts(self.capture(mods.download, v2, (0, 10))), [])

    def test_install_statuses_and_monotonic_progress(self):
        def pkg(name, deps=()):
            return {"full_name": name, "versions": [{"version_number": "1.0.0", "full_name": name + "-1.0.0", "dependencies": list(deps), "download_url": "http://x/" + name}]}
        idx = [pkg("A-One", ["C-Dep-1.0.0"]), pkg("B-Two"), pkg("C-Dep")]
        spans = []
        def fake_download(v, span=None):
            spans.append(span)
            if span: mods.say_progress(span[0]); mods.say_progress(span[1])
            return "fake.zip"
        with mock.patch.object(mods, "index", return_value=idx), mock.patch.object(mods, "extract_mod"), \
             mock.patch.object(mods, "download", side_effect=fake_download), \
             mock.patch.object(mods, "pick_version", side_effect=lambda p, ver: p["versions"][0]):
            text = self.capture(mods.install, "p", ["A-One", "B-Two"])
        self.assertIn("##status Downloading One 1.0.0 (1 of 2)", text)  # C-Dep joins after A-One: the total grows 2 -> 3
        self.assertIn("##status Installing One 1.0.0 (1 of 2)", text)
        self.assertIn("##status Downloading Two 1.0.0 (2 of 3)", text)
        self.assertIn("##status Downloading Dep 1.0.0 (3 of 3)", text)
        p = pcts(text)
        self.assertEqual(p, sorted(p)); self.assertEqual(p[-1], 90)
        self.assertTrue(all(s and s[0] <= s[1] for s in spans))

    def test_two_packages_numbered_one_and_two_of_two(self):
        idx = [{"full_name": n, "versions": [{"version_number": "2.0.0", "dependencies": [], "download_url": "u"}]} for n in ("A-One", "B-Two")]
        with mock.patch.object(mods, "index", return_value=idx), mock.patch.object(mods, "extract_mod"), \
             mock.patch.object(mods, "download", return_value="z"), \
             mock.patch.object(mods, "pick_version", side_effect=lambda p, ver: p["versions"][0]):
            text = self.capture(mods.install, "p", ["A-One", "B-Two"])
        self.assertIn("##status Downloading One 2.0.0 (1 of 2)", text)
        self.assertIn("##status Downloading Two 2.0.0 (2 of 2)", text)
        p = pcts(text); self.assertEqual(p, sorted(p))


if __name__ == "__main__": unittest.main()
