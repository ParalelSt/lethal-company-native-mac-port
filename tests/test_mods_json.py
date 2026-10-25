"""Launcher-facing JSON commands of lcport.mods. No network: index/install/remove/audit are monkeypatched."""
import io, json, os, sys, tempfile, types, unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try: import dnfile  # noqa: F401  (lives in the kit venv; only the audit needs it and the audit is patched here)
except ImportError: sys.modules["dnfile"] = types.ModuleType("dnfile")
from lcport import config, mods

def pkg(owner, name, versions, downloads, cats=(), deprecated=False, deps=()):
    return {"name": name, "full_name": f"{owner}-{name}", "owner": owner, "rating_score": downloads // 10, "is_deprecated": deprecated,
            "categories": list(cats), "date_updated": "2026-01-02T03:04:05Z", "website_url": "",
            "versions": [{"version_number": v, "description": f"{name} does things", "downloads": downloads,
                          "icon": f"https://cdn.example/{owner}-{name}-{v}.png", "website_url": f"https://github.com/{owner}/{name}",
                          "dependencies": list(deps)} for v in versions]}

FAKE_INDEX = [
    pkg("BepInEx", "BepInExPack", ["5.4.2305", "5.4.2100"], 1000, cats=["BepInEx"]),
    pkg("notnotnotswipez", "MoreCompany", ["1.14.0"], 5000, cats=["Mods", "BepInEx"], deps=["BepInEx-BepInExPack-5.4.2100"]),
    pkg("Old", "Gone", ["0.1.0"], 9999, deprecated=True),
    pkg("Many", "Versions", [f"1.0.{i}" for i in range(15, 0, -1)], 10),
]

class ModsJSONTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [mock.patch.object(config, "CACHE", self.tmp.name), mock.patch.object(config, "PROFILES", os.path.join(self.tmp.name, "profiles")),
                        mock.patch.object(mods, "index", lambda: FAKE_INDEX)]
        for p in self.patches: p.start()
    def tearDown(self):
        for p in self.patches: p.stop()
        self.tmp.cleanup()

    def run_main(self, *args):
        buf = io.StringIO()
        with redirect_stdout(buf): mods.main(list(args))
        return buf.getvalue()

    def test_search_fields_include_icon_and_website(self):
        res = mods.json_search("")
        self.assertEqual([r["full_name"] for r in res], ["notnotnotswipez-MoreCompany", "BepInEx-BepInExPack", "Many-Versions"])  # by downloads, deprecated dropped
        mc = res[0]
        self.assertEqual(set(mc), {"full_name", "name", "owner", "version", "downloads", "rating", "description", "categories", "icon", "website"})
        self.assertEqual(mc["icon"], "https://cdn.example/notnotnotswipez-MoreCompany-1.14.0.png")
        self.assertEqual(mc["website"], "https://github.com/notnotnotswipez/MoreCompany")
        self.assertEqual(mc["categories"], ["Mods", "BepInEx"])
        self.assertEqual(res[1]["downloads"], 2000)  # summed over versions
        self.assertEqual(res[1]["version"], "5.4.2305")

    def test_search_query_and_cli(self):
        self.assertEqual([r["name"] for r in mods.json_search("morecomp")], ["MoreCompany"])
        out = json.loads(self.run_main("json-search", "bepinex"))
        self.assertEqual([r["full_name"] for r in out], ["BepInEx-BepInExPack"])

    def test_search_installed_only(self):
        os.makedirs(os.path.join(config.PROFILES, "P"))
        mods.save_manifest("P", {"Many-Versions": "1.0.15"})
        out = json.loads(self.run_main("json-search", "--installed", "P"))
        self.assertEqual([r["full_name"] for r in out], ["Many-Versions"])

    def test_info_known(self):
        out = json.loads(self.run_main("json-info", "notnotnotswipez-MoreCompany"))
        self.assertEqual(out, {"full_name": "notnotnotswipez-MoreCompany", "dependencies": ["BepInEx-BepInExPack-5.4.2100"],
                               "website": "https://github.com/notnotnotswipez/MoreCompany", "date_updated": "2026-01-02T03:04:05Z", "versions": ["1.14.0"]})
        self.assertEqual(len(mods.json_info("Many-Versions")["versions"]), 10)

    def test_info_unknown(self):
        self.assertEqual(json.loads(self.run_main("json-info", "Nobody-Nothing")), {"error": "unknown"})

    def test_parse_apply(self):
        self.assertEqual(mods.parse_apply(["P", "--install", "A-a", "B-b", "--remove", "C-c", "D-d"]), ("P", ["A-a", "B-b"], ["C-c", "D-d"]))
        self.assertEqual(mods.parse_apply(["P", "--remove", "C-c", "--install", "A-a"]), ("P", ["A-a"], ["C-c"]))
        self.assertEqual(mods.parse_apply(["P", "--install", "--remove", "C-c"]), ("P", [], ["C-c"]))
        self.assertEqual(mods.parse_apply(["P"]), ("P", [], []))
        with self.assertRaises(SystemExit): mods.parse_apply([])
        with self.assertRaises(SystemExit): mods.parse_apply(["P", "stray"])

    def test_apply_removes_before_install_then_audits(self):
        calls = []
        with mock.patch.object(mods, "remove", lambda prof, name: calls.append(("remove", prof, name))), \
             mock.patch.object(mods, "install", lambda prof, refs, pinned=None, span=None: calls.append(("install", prof, list(refs)))), \
             mock.patch.object(mods, "audit", lambda prof, save=True: calls.append(("audit", prof, save))):
            out = self.run_main("apply", "P", "--install", "A-a", "B-b", "--remove", "C-c", "D-d")
        self.assertEqual(calls, [("remove", "P", "C-c"), ("remove", "P", "D-d"), ("install", "P", ["A-a", "B-b"]), ("audit", "P", True)])
        self.assertIn("2 to install, 2 to remove", out)

    def test_apply_remove_only_skips_install(self):
        calls = []
        with mock.patch.object(mods, "remove", lambda prof, name: calls.append("remove")), \
             mock.patch.object(mods, "install", lambda *a, **k: calls.append("install")), \
             mock.patch.object(mods, "audit", lambda prof, save=True: calls.append("audit")):
            self.run_main("apply", "P", "--remove", "C-c")
        self.assertEqual(calls, ["remove", "audit"])

    def test_install_update_import_save_audit(self):
        seen = []
        with mock.patch.object(mods, "install", lambda *a, **k: None), mock.patch.object(mods, "import_code", lambda *a: None), \
             mock.patch.object(mods, "audit", lambda prof, save=True: seen.append(save)):
            self.run_main("install", "P", "A-a"); self.run_main("update", "P"); self.run_main("import", "P", "code")
        self.assertEqual(seen, [True, True, True])

if __name__ == "__main__": unittest.main()
