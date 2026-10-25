"""mods delete-profile against a temp PROFILES dir."""
import io, os, sys, tempfile, types, unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try: import dnfile  # noqa: F401
except ImportError: sys.modules["dnfile"] = types.ModuleType("dnfile")
from lcport import config, mods

class DeleteProfileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        p = mock.patch.object(config, "PROFILES", self.tmp.name); p.start(); self.addCleanup(p.stop)
        for n in ("Default", "Friends"): os.makedirs(os.path.join(self.tmp.name, n, "BepInEx"))
    def run_cmd(self, *args):
        out = io.StringIO()
        with redirect_stdout(out):
            try: mods.main(["delete-profile", *args]); code = 0
            except SystemExit as e: code = e.code
        return code, out.getvalue()
    def test_deletes(self):
        code, out = self.run_cmd("Friends")
        self.assertEqual(code, 0); self.assertIn("deleted profile Friends", out); self.assertIn("##done", out)
        self.assertEqual(os.listdir(self.tmp.name), ["Default"])
    def test_refuses_last(self):
        self.run_cmd("Friends"); code, out = self.run_cmd("Default")
        self.assertEqual(code, 1); self.assertIn("only profile", out); self.assertTrue(os.path.isdir(os.path.join(self.tmp.name, "Default")))
    def test_refuses_missing(self):
        code, out = self.run_cmd("Nope"); self.assertEqual(code, 1); self.assertIn("no such profile", out); self.assertEqual(len(os.listdir(self.tmp.name)), 2)
    def test_refuses_path_escape(self):
        code, _ = self.run_cmd("../x"); self.assertEqual(code, 1); self.assertEqual(len(os.listdir(self.tmp.name)), 2)

if __name__ == "__main__": unittest.main()
