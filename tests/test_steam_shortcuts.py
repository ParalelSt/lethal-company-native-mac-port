"""Steam non-Steam-game shortcuts: binary shortcuts.vdf codec, ids, loginusers.vdf parsing, the steam-shortcut command and
launch() choosing steam:// vs a direct start. Everything runs on temp files; Steam, `open` and the game are never started."""
import io, json, os, plistlib, struct, sys, tempfile, types, unittest, zlib
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try: import dnfile  # noqa: F401  (kit venv only; lcport.mods imports it)
except ImportError: sys.modules["dnfile"] = types.ModuleType("dnfile")
from lcport import config, steam, install, cli, mods, steam_shortcuts as sc

def write(path, data):
    with open(path, "wb" if isinstance(data, bytes) else "w") as f: f.write(data)
def read(path, mode="r"):
    with open(path, mode) as f: return f.read()

# --- hand-built binary KeyValues (independent of the module's encoder) ---
def kv_obj(name, *children): return b"\x00" + name.encode() + b"\x00" + b"".join(children) + b"\x08"
def kv_str(name, value): return b"\x01" + name.encode() + b"\x00" + value.encode() + b"\x00"
def kv_int(name, value): return b"\x02" + name.encode() + b"\x00" + struct.pack("<I", value)

def entry_bytes(index, appid, name, exe, startdir, tags=()):
    return kv_obj(str(index), kv_int("appid", appid), kv_str("AppName", name), kv_str("Exe", exe), kv_str("StartDir", startdir),
                  kv_str("icon", ""), kv_str("ShortcutPath", ""), kv_str("LaunchOptions", "--fullscreen"), kv_int("IsHidden", 0),
                  kv_int("AllowDesktopConfig", 1), kv_int("AllowOverlay", 1), kv_int("OpenVR", 0), kv_int("Devkit", 0),
                  kv_str("DevkitGameID", ""), kv_int("DevkitOverrideAppID", 0), kv_int("LastPlayTime", 1761000000),
                  kv_str("FlatpakAppID", ""), kv_obj("tags", *[kv_str(str(i), t) for i, t in enumerate(tags)]))

OTHER = entry_bytes(0, 0x9ABCDEF0, "Some Emulator", '"/Applications/Emu.app/Contents/MacOS/Emu"', '"/Applications/Emu.app/Contents/MacOS"',
                    tags=("favorite", "Emulators"))
def file_bytes(*entries): return kv_obj("shortcuts", *entries) + b"\x08"
RAW = file_bytes(OTHER)

class CodecTest(unittest.TestCase):
    def test_round_trip_is_byte_stable(self):
        entries = sc.decode(RAW)
        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertEqual(e["AppName"], "Some Emulator"); self.assertEqual(e["appid"], 0x9ABCDEF0)
        self.assertEqual(e["tags"], {"0": "favorite", "1": "Emulators"})
        self.assertEqual(sc.encode(entries), RAW)
        self.assertEqual(sc.decode(sc.encode(entries)), entries)

    def test_empty_and_missing(self):
        self.assertEqual(sc.decode(b""), [])
        self.assertEqual(sc.encode([]), b"\x00shortcuts\x00\x08\x08")
        self.assertEqual(sc.load("/nonexistent/shortcuts.vdf"), [])

    def test_keys_case_insensitive_on_read(self):
        raw = file_bytes(kv_obj("0", kv_int("AppID", 5), kv_str("appname", "Old"), kv_str("exe", '"/x"'), kv_str("Weird", "kept")))
        e = sc.decode(raw)[0]
        self.assertEqual((e["appid"], e["AppName"], e["Exe"], e["Weird"]), (5, "Old", '"/x"', "kept"))
        self.assertIsNotNone(sc.find(sc.decode(raw), "Old"))

    def test_upsert_replaces_by_appname_and_keeps_other_entry(self):
        entries = sc.decode(RAW)
        a = sc.upsert(entries, "Lethal Company", "/Apps/LC.app/Contents/MacOS/Lethal Company", "/Apps/LC.app/Contents/MacOS")
        self.assertEqual(a["Exe"], '"/Apps/LC.app/Contents/MacOS/Lethal Company"')  # quoted
        self.assertEqual(a["StartDir"], '"/Apps/LC.app/Contents/MacOS"')
        self.assertEqual(list(a), sc.FIELDS)  # written in the listed order
        self.assertEqual(a["AllowOverlay"], 1)
        a["tags"] = {"0": "Games"}; a["LastPlayTime"] = 42
        b = sc.upsert(entries, "Lethal Company", '"/Apps/LC2.app/Contents/MacOS/Lethal Company"', "/Apps/LC2.app/Contents/MacOS", launch_options="-x")
        self.assertEqual(len(entries), 2)
        self.assertIs(entries[1], b)
        self.assertEqual(b["Exe"], '"/Apps/LC2.app/Contents/MacOS/Lethal Company"')  # already quoted: not double-quoted
        self.assertEqual(b["appid"], sc.shortcut_appid(b["Exe"], "Lethal Company"))
        self.assertEqual((b["tags"], b["LastPlayTime"], b["LaunchOptions"]), ({"0": "Games"}, 42, "-x"))
        out = sc.encode(entries)
        self.assertTrue(out.startswith(b"\x00shortcuts\x00" + OTHER))  # the unrelated shortcut is untouched, byte for byte
        self.assertEqual(sc.encode(sc.decode(out)), out)

    def test_save_is_atomic_with_backup(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "config", "shortcuts.vdf")
            sc.save(p, sc.decode(RAW))
            self.assertEqual(read(p, "rb"), RAW); self.assertFalse(os.path.exists(p + ".bak"))
            entries = sc.load(p); sc.upsert(entries, "New", "/a", "/")
            sc.save(p, entries)
            self.assertEqual(read(p + ".bak", "rb"), RAW)
            self.assertEqual([e["AppName"] for e in sc.load(p)], ["Some Emulator", "New"])
            self.assertEqual(sorted(os.listdir(os.path.dirname(p))), ["shortcuts.vdf", "shortcuts.vdf.bak"])  # no temp file left

    def test_ids(self):
        # Steam: appid = CRC32(Exe as stored, quotes included, + AppName) with the top bit set; for this pair CRC32 is
        # 0x2a459e6a, so appid = 0xaa459e6a = 2856689258. rungameid = appid << 32 | 0x02000000.
        exe, name = '"/Applications/Foo.app/Contents/MacOS/Foo"', "Foo"
        self.assertEqual(zlib.crc32((exe + name).encode()), 0x2A459E6A)
        self.assertEqual(sc.shortcut_appid(exe, name), 2856689258)
        self.assertEqual(sc.rungameid(2856689258), 2856689258 * 2**32 + 0x02000000)
        self.assertEqual(sc.rungameid(2856689258), 12269386937978060800)
        self.assertTrue(sc.shortcut_appid("", "") & 0x80000000)

LOGINUSERS = '''"users"
{
	"76561198000000001"
	{
		"AccountName"		"alice"
		"PersonaName"		"Alice \\"A\\""
		"MostRecent"		"0"
		"timestamp"		"1700000000"
	}
	// comment line
	"76561198000000002"
	{
		"AccountName"		"bob"
		"mostrecent"		"1"
		"Timestamp"		"1600000000"
	}
}
'''

class LoginUsersTest(unittest.TestCase):
    def test_parse(self):
        root = steam.parse_text_vdf(LOGINUSERS)
        self.assertEqual(root["users"]["76561198000000001"]["PersonaName"], 'Alice "A"')

    def test_most_recent(self):
        self.assertEqual(steam.account_from_loginusers(LOGINUSERS), 76561198000000002 - 76561197960265728)  # 39734274

    def test_newest_timestamp_when_no_mostrecent(self):
        text = LOGINUSERS.replace('"mostrecent"\t\t"1"', '"AutoLogin"\t\t"1"')
        self.assertEqual(steam.account_from_loginusers(text), 76561198000000001 - 76561197960265728)  # 39734273

    def test_current_account_id_with_fallback(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "userdata", "0")); os.makedirs(os.path.join(root, "userdata", "123"))
            self.assertEqual(steam.current_account_id(root), 123)  # no loginusers.vdf: the single non-zero folder
            os.makedirs(os.path.join(root, "userdata", "456"))
            self.assertIsNone(steam.current_account_id(root))  # ambiguous
            os.makedirs(os.path.join(root, "config")); write(os.path.join(root, "config", "loginusers.vdf"), LOGINUSERS)
            self.assertEqual(steam.current_account_id(root), 39734274)
            self.assertEqual(steam.shortcuts_path(39734274, root), os.path.join(root, "userdata", "39734274", "config", "shortcuts.vdf"))

class Sandbox(unittest.TestCase):
    """Temp SUPPORT/state.json, apps and Steam folder; nothing outside the temp dir is touched."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); t = self.tmp.name
        self.app = os.path.join(t, "Applications", "Lethal Company.app"); self.modded = os.path.join(t, "Applications", "Lethal Company Modded.app")
        os.makedirs(os.path.join(self.app, "Contents", "MacOS")); os.makedirs(os.path.join(self.app, "Contents", "Resources"))
        write(os.path.join(self.app, "Contents", "Resources", "PlayerIcon.icns"), "icns")
        os.makedirs(os.path.join(self.modded, "Contents", "MacOS"))
        with open(os.path.join(self.modded, "Contents", "Info.plist"), "wb") as f: plistlib.dump({"CFBundleExecutable": "launch"}, f)
        self.old_script = '#!/bin/zsh\ncd "/kit" && exec "/venv/bin/python" -m lcport play-modded "${LC_PROFILE:-Default}"\n'
        write(os.path.join(self.modded, "Contents", "MacOS", "launch"), self.old_script)
        self.steam_root = os.path.join(t, "Steam"); os.makedirs(os.path.join(self.steam_root, "config"))
        write(os.path.join(self.steam_root, "config", "loginusers.vdf"), LOGINUSERS)
        self.vdf = steam.shortcuts_path(39734274, self.steam_root); os.makedirs(os.path.dirname(self.vdf))
        write(self.vdf, RAW)
        self.overlay = os.path.join(t, "gameoverlayrenderer.dylib"); write(self.overlay, "")
        support = os.path.join(t, "support")
        self.patches = [mock.patch.object(config, "SUPPORT", support), mock.patch.object(config, "STATE", os.path.join(support, "state.json")),
                        mock.patch.object(config, "WORK", os.path.join(support, "work")), mock.patch.object(config, "APP_DST", self.app),
                        mock.patch.object(config, "MODDED_DST", self.modded), mock.patch.object(steam, "STEAM_ROOT", self.steam_root),
                        mock.patch.object(steam, "OVERLAY", self.overlay), mock.patch.object(install, "reset_window_state", lambda: None),
                        mock.patch.object(install, "run", lambda *a, **k: self.codesigned.append(a[0])),
                        mock.patch.dict(os.environ, {}, clear=False)]
        self.codesigned = []
        for p in self.patches: p.start()
        for k in ("LC_DIRECT_LAUNCH", "SteamGameId", "SteamAppId", "LC_NO_OVERLAY", "DYLD_INSERT_LIBRARIES"): os.environ.pop(k, None)
    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.tmp.cleanup()
    def state(self): return json.loads(read(config.STATE)) if os.path.exists(config.STATE) else {}
    def cli(self, *args):
        buf = io.StringIO()
        with redirect_stdout(buf): cli.cmd_steam_shortcut(list(args))
        return buf.getvalue()

class SteamShortcutCommandTest(Sandbox):
    def test_add_then_remove(self):
        out = self.cli()
        entries = sc.load(self.vdf)
        self.assertEqual([e["AppName"] for e in entries], ["Some Emulator", "Lethal Company", "Lethal Company (Modded)"])
        raw = read(self.vdf, "rb")
        self.assertTrue(raw.startswith(b"\x00shortcuts\x00" + OTHER))  # the user's own shortcut survives byte for byte
        self.assertEqual(read(self.vdf + ".bak", "rb"), RAW)
        v, m = entries[1], entries[2]
        vexe = os.path.join(self.app, "Contents", "MacOS", "Lethal Company"); mexe = os.path.join(self.modded, "Contents", "MacOS", "launch")
        self.assertEqual(v["Exe"], f'"{vexe}"'); self.assertEqual(v["StartDir"], f'"{os.path.dirname(vexe)}"')
        self.assertEqual(v["icon"], os.path.join(self.app, "Contents", "Resources", "PlayerIcon.icns"))
        self.assertIn("-logFile", v["LaunchOptions"])
        self.assertEqual(m["Exe"], f'"{mexe}"'); self.assertEqual(m["icon"], "")
        st = self.state()["steam_shortcuts"]
        self.assertEqual(st["vanilla"]["appid"], sc.shortcut_appid(f'"{vexe}"', "Lethal Company"))
        self.assertEqual(st["vanilla"]["rungameid"], sc.rungameid(v["appid"])); self.assertEqual(st["vanilla"]["exe"], vexe)
        self.assertEqual(st["modded"]["exe"], mexe); self.assertEqual(st["modded"]["appid"], m["appid"])
        self.assertIn(f"steam://rungameid/{st['vanilla']['rungameid']}", out); self.assertIn(f"steam://rungameid/{st['modded']['rungameid']}", out)
        self.assertIn("Restart Steam once so it picks up the new shortcuts.", out)
        # the older launch script was replaced by the native launcher + launcher.json (and the bundle was re-signed)
        self.assertEqual(read(mexe, "rb"), read(install.LAUNCHER_BIN, "rb"))
        self.assertEqual(json.loads(read(os.path.join(self.modded, "Contents", "Resources", "launcher.json"))), install.launcher_config())
        self.assertEqual(install.launcher_config()["support"], config.SUPPORT); self.assertEqual(install.launcher_config()["app"], self.app)
        self.assertEqual(read(os.path.join(self.modded, "Contents", "MacOS", "steam_appid.txt")), str(config.APPID))
        self.assertTrue(os.access(mexe, os.X_OK)); self.assertEqual(self.codesigned[0][:2], ["codesign", "--force"])
        # running it again replaces instead of duplicating, and leaves the updated launcher alone
        self.cli(); self.assertEqual(len(sc.load(self.vdf)), 3); self.assertEqual(len(self.codesigned), 1)
        out = self.cli("--remove")
        self.assertEqual(read(self.vdf, "rb"), RAW)
        self.assertNotIn("steam_shortcuts", self.state())
        self.assertIn("Removed 2", out)

    def test_not_built(self):
        import shutil; shutil.rmtree(self.app)
        with self.assertRaises(SystemExit): self.cli()
        self.assertEqual(read(self.vdf, "rb"), RAW)

class LaunchChoiceTest(Sandbox):
    def setUp(self):
        super().setUp()
        self.calls = []
        def fake_run(cmd, *a, **k):
            self.calls.append(("run", list(cmd), k.get("env"))); return types.SimpleNamespace(returncode=0, stdout="", stderr="")
        def fake_popen(cmd, *a, **k):
            self.calls.append(("popen", list(cmd), k.get("env"))); return types.SimpleNamespace(pid=1, wait=lambda: 0)
        for p in (mock.patch.object(steam.subprocess, "run", fake_run), mock.patch.object(steam.subprocess, "Popen", fake_popen),
                  mock.patch.object(steam, "running", lambda: True), mock.patch.object(steam, "started_at", lambda: None)):
            p.start(); self.patches.append(p)
        with redirect_stdout(io.StringIO()): cli.cmd_steam_shortcut([])
        self.st = self.state()["steam_shortcuts"]

    def opened(self): return [c[1] for c in self.calls if c[0] == "run" and c[1][:1] == ["open"]]
    def popened(self): return [c for c in self.calls if c[0] == "popen"]

    def test_vanilla_goes_through_steam(self):
        self.assertIsNone(steam.launch(self.app, logfile="/tmp/x.log"))
        self.assertEqual(self.opened(), [["open", f"steam://rungameid/{self.st['vanilla']['rungameid']}"]])
        self.assertEqual(self.popened(), [])
        self.assertTrue(all(c[2] is None or "DYLD_INSERT_LIBRARIES" not in c[2] for c in self.calls))

    def test_modded_uses_modded_shortcut(self):
        self.assertIsNone(steam.launch(self.app, env={"DOORSTOP_ENABLED": "1"}, shortcut_app=self.modded))
        self.assertEqual(self.opened(), [["open", f"steam://rungameid/{self.st['modded']['rungameid']}"]])

    def assertDirect(self, p):
        self.assertIsNotNone(p); self.assertEqual(self.opened(), [])
        (_, cmd, env), = self.popened()
        self.assertEqual(cmd[0], os.path.join(self.app, "Contents", "MacOS", "Lethal Company"))
        self.assertTrue(env["DYLD_INSERT_LIBRARIES"].startswith(self.overlay))  # today's direct launch, unchanged
        return env

    def test_direct_launch_guard_env(self):
        os.environ["LC_DIRECT_LAUNCH"] = "1"
        self.assertDirect(steam.launch(self.app, shortcut_app=self.modded))

    def test_steamgameid_means_already_launched_by_steam(self):
        os.environ["SteamGameId"] = str(self.st["modded"]["appid"])
        env = self.assertDirect(steam.launch(self.app, shortcut_app=self.modded))
        self.assertEqual(env["SteamGameId"], str(self.st["modded"]["appid"]))  # Steam's value is kept
        self.calls.clear(); os.environ["SteamGameId"] = str(self.st["modded"]["rungameid"])
        self.assertDirect(steam.launch(self.app, shortcut_app=self.modded))
        self.calls.clear(); os.environ["SteamGameId"] = str(config.APPID)  # some other id: still go through Steam
        self.assertIsNone(steam.launch(self.app, shortcut_app=self.modded))

    def test_steam_not_running(self):
        with mock.patch.object(steam, "running", lambda: False): self.assertDirect(steam.launch(self.app))

    def test_no_shortcut_recorded(self):
        st = self.state(); del st["steam_shortcuts"]; write(config.STATE, json.dumps(st))
        self.assertDirect(steam.launch(self.app))

    def test_steam_not_restarted_since_adding(self):
        with mock.patch.object(steam, "started_at", lambda: self.st["vanilla"]["added"] - 60), redirect_stdout(io.StringIO()):
            self.assertDirect(steam.launch(self.app))

    def test_cmd_play_does_not_wait_when_launched_through_steam(self):
        buf = io.StringIO()
        with mock.patch.object(steam, "ensure_running", lambda: True), redirect_stdout(buf): cli.cmd_play([])
        self.assertIn("Launched through Steam (overlay by Steam). Game log: " + os.path.join(config.WORK, "player.log"), buf.getvalue())
        self.assertEqual(len(self.opened()), 1)

    def test_cmd_play_modded_remembers_profile(self):
        from lcport import thirdparty
        with mock.patch.object(steam, "ensure_running", lambda: True), mock.patch.object(thirdparty, "bepinex", lambda: "/bep"), \
             mock.patch.object(mods, "profile_dir", lambda name: os.path.join(self.tmp.name, "profiles", name, "BepInEx")), redirect_stdout(io.StringIO()):
            cli.cmd_play(["Fun"], modded=True)
            self.assertEqual(self.state()["modded_profile"], "Fun")
            buf = io.StringIO()
            with redirect_stdout(buf): cli.cmd_play([], modded=True)  # no profile given: the last chosen one
        self.assertIn("profile Fun", buf.getvalue())
        self.assertEqual(self.opened(), [["open", f"steam://rungameid/{self.st['modded']['rungameid']}"]] * 2)

if __name__ == "__main__": unittest.main()
