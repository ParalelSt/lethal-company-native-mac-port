"""lcport.net_hashes pure parts: raw layout offsets, matching, and the in-place patch. No UnityPy needed."""
import json, os, struct, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lcport import net_hashes as nh

def raw_networkobject(name, h, src, tail=b"\x01\x00\x01\x01"):
    """Bytes of a NetworkObject MonoBehaviour: m_GameObject, m_Enabled+pad, m_Script, m_Name (aligned), hashes, rest."""
    b = struct.pack("<iq", 0, 1234) + b"\x01\x00\x00\x00" + struct.pack("<iq", 1, 5678)
    nb = name.encode()
    b += struct.pack("<i", len(nb)) + nb
    b += b"\x00" * (-len(b) % 4)
    return b + struct.pack("<II", h, src) + tail

def slurp(p):
    with open(p, "rb") as f: return f.read()

def put(p, data):
    with open(p, "wb") as f: f.write(data)

def rec(file, path_id, name, h, src=0, hierarchy=None, offset=0):
    return {"file": file, "path_id": path_id, "name": name, "hierarchy": name if hierarchy is None else hierarchy,
            "scene_key": file if nh.is_level(file) else "", "offset": offset, "hash": h, "in_scene_source_hash": src}

class OffsetTest(unittest.TestCase):
    def test_alignment_for_name_lengths(self):
        for name, expect in [("", 32), ("A", 36), ("Ab", 36), ("Abc", 36), ("Abcd", 36), ("Abcde", 40), ("x" * 8, 40), ("x" * 9, 44)]:
            raw = raw_networkobject(name, 0xDEADBEEF, 0x01020304)
            off = nh.hash_field_offset(raw)
            self.assertEqual(off, expect, name)
            self.assertEqual(off % 4, 0)
            self.assertEqual(nh.read_hashes(raw, off), (0xDEADBEEF, 0x01020304))

    def test_empty_name_is_the_usual_case(self):
        # component MonoBehaviours normally serialize m_Name as "" so the hash sits right after the 4-byte length
        raw = raw_networkobject("", 7, 0)
        self.assertEqual(nh.hash_field_offset(raw), 28 + 4)

    def test_rejects_garbage(self):
        with self.assertRaises(ValueError): nh.hash_field_offset(b"\x00" * 10)
        bad = struct.pack("<iq", 0, 1) + b"\x01\x00\x00\x00" + struct.pack("<iq", 1, 2) + struct.pack("<i", 999) + b"ab"
        with self.assertRaises(ValueError): nh.hash_field_offset(bad)
        with self.assertRaises(ValueError): nh.hash_field_offset(raw_networkobject("abc", 1, 2, tail=b"")[:-4])

    def test_data_files_filter(self):
        with tempfile.TemporaryDirectory() as d:
            for n in ["level0", "level12", "level3.orig", "sharedassets1.assets", "sharedassets1.assets.orig", "sharedassets1.resource",
                      "resources.assets.resS", "globalgamemanagers", "globalgamemanagers.assets", "boot.config"]:
                put(os.path.join(d, n), b"")
            self.assertEqual(nh.data_files(d), ["globalgamemanagers", "globalgamemanagers.assets", "level0", "level12", "sharedassets1.assets"])

class MatchTest(unittest.TestCase):
    def test_unique_names(self):
        orig = [rec("sharedassets1.assets", 10, "Flashlight", 111), rec("sharedassets1.assets", 11, "Shovel", 222)]
        ours = [rec("sharedassets1.assets", 50, "Shovel", 9), rec("sharedassets1.assets", 40, "Flashlight", 8)]
        pairs, info = nh.match(orig, ours)
        self.assertEqual({(a["name"], b["hash"]) for a, b in pairs}, {("Flashlight", 111), ("Shovel", 222)})
        self.assertEqual((info["matched"], info["unmatched_ours"], info["unmatched_orig"]), (2, 0, 0))
        self.assertEqual(info["ambiguities"], [])

    def test_duplicate_names_resolved_by_hierarchy_even_when_order_differs(self):
        orig = [rec("sharedassets3.assets", 1, "KillTrigger", 101, hierarchy="CaveForkStairTile/KillTrigger"),
                rec("sharedassets3.assets", 2, "KillTrigger", 102, hierarchy="MineshaftStartTile/KillTrigger")]
        ours = [rec("sharedassets3.assets", 1, "KillTrigger", 5, hierarchy="MineshaftStartTile/KillTrigger"),
                rec("sharedassets3.assets", 2, "KillTrigger", 6, hierarchy="CaveForkStairTile/KillTrigger")]
        pairs, info = nh.match(orig, ours)
        self.assertEqual({(a["hierarchy"], b["hash"]) for a, b in pairs},
                         {("MineshaftStartTile/KillTrigger", 102), ("CaveForkStairTile/KillTrigger", 101)})
        self.assertEqual(info["ambiguities"], [])

    def test_duplicate_names_resolved_by_order(self):
        # no transform path available (or identical paths): same name pairs up by order of appearance and is reported
        orig = [rec("sharedassets1.assets", 30, "Vent", 3, hierarchy=""), rec("sharedassets1.assets", 10, "Vent", 1, hierarchy=""),
                rec("resources.assets", 99, "Vent", 0, hierarchy=""), rec("sharedassets1.assets", 20, "Vent", 2, hierarchy="")]
        ours = [rec("sharedassets1.assets", 7, "Vent", 70, hierarchy=""), rec("resources.assets", 5, "Vent", 50, hierarchy=""),
                rec("sharedassets1.assets", 6, "Vent", 60, hierarchy=""), rec("sharedassets1.assets", 8, "Vent", 80, hierarchy="")]
        pairs, info = nh.match(orig, ours)
        self.assertEqual(sorted((a["hash"], b["hash"]) for a, b in pairs), [(50, 0), (60, 1), (70, 2), (80, 3)])
        self.assertEqual(len(info["ambiguities"]), 1)
        self.assertEqual(info["ambiguities"][0]["name"], "Vent")
        self.assertEqual(info["ambiguities"][0]["resolved"], "by order")

    def test_duplicate_counts_differ_leaves_unmatched(self):
        orig = [rec("sharedassets1.assets", 1, "A", 1), rec("sharedassets1.assets", 2, "A", 2)]
        ours = [rec("sharedassets1.assets", 1, "A", 9)]
        pairs, info = nh.match(orig, ours)
        self.assertEqual(len(pairs), 1)
        self.assertEqual((info["unmatched_ours"], info["unmatched_orig"], info["unmatched_prefabs_orig"]), (0, 1, 1))
        self.assertIn("counts differ", info["ambiguities"][0]["resolved"])

    def test_level_mapping_by_name_multiset(self):
        # our level numbering is shifted by one; level5 (ours) has one extra object compared to level4 (original)
        orig = [rec("level3", 1, "Door", 1), rec("level3", 2, "Door", 2), rec("level3", 3, "Lever", 3),
                rec("level4", 1, "Ship", 4), rec("level4", 2, "Terminal", 5)]
        ours = [rec("level4", 8, "Door", 11), rec("level4", 9, "Door", 12), rec("level4", 10, "Lever", 13),
                rec("level5", 1, "Ship", 14), rec("level5", 2, "Terminal", 15), rec("level5", 3, "Extra", 16)]
        pairs, info = nh.match(orig, ours)
        self.assertEqual(info["levels"], {"level4": {"original": "level3", "score": 1.0}, "level5": {"original": "level4", "score": 0.667}})
        got = sorted((a["file"], a["hash"], b["file"], b["hash"]) for a, b in pairs)
        self.assertEqual(got, [("level4", 11, "level3", 1), ("level4", 12, "level3", 2), ("level4", 13, "level3", 3),
                               ("level5", 14, "level4", 4), ("level5", 15, "level4", 5)])
        self.assertEqual(info["unmatched_ours_list"], ["level5:Extra"])
        self.assertTrue(any(a["where"] == "level5" and "level4" in a["resolved"] for a in info["ambiguities"]))

    def test_level_mapping_prefers_same_name_on_tie(self):
        orig = [rec("level1", 1, "X", 1), rec("level2", 1, "X", 2)]
        ours = [rec("level1", 1, "X", 10), rec("level2", 1, "X", 20)]
        lvl = nh.map_levels([r for r in ours], [r for r in orig])
        self.assertEqual({a: b for a, (b, s) in lvl.items()}, {"level1": "level1", "level2": "level2"})

    def test_level_mapping_tie_broken_by_scene_fingerprint(self):
        # two moons with identical NetworkObjects (like level6/level12); our numbering swapped them
        big, small = {"GameObject": 900, "Transform": 900, "MeshRenderer": 400}, {"GameObject": 200, "Transform": 200}
        def lv(file, h, sig): return [dict(rec(file, 1, "Map", h), scene_sig=sig), dict(rec(file, 2, "Props", h + 1), scene_sig=sig)]
        orig = lv("level6", 60, big) + lv("level12", 120, small)
        ours = lv("level6", 1, small) + lv("level12", 3, big)
        pairs, info = nh.match(orig, ours)
        self.assertEqual({a: v["original"] for a, v in info["levels"].items()}, {"level6": "level12", "level12": "level6"})
        self.assertEqual(sorted((a["file"], b["hash"]) for a, b in pairs), [("level12", 60), ("level12", 61), ("level6", 120), ("level6", 121)])
        self.assertEqual(info["ambiguities"], [])

    def test_prefabs_never_match_scene_objects(self):
        orig = [rec("level3", 1, "Ship", 1)]
        ours = [rec("sharedassets1.assets", 1, "Ship", 2)]
        pairs, info = nh.match(orig, ours)
        self.assertEqual(pairs, [])
        self.assertEqual((info["unmatched_prefabs_ours"], info["unmatched_orig"]), (1, 1))

    def test_compare_counts(self):
        orig = [rec("sharedassets1.assets", 1, "A", 1), rec("level3", 1, "B", 2, 1)]
        ours = [rec("sharedassets1.assets", 1, "A", 1), rec("level3", 1, "B", 3, 1)]
        v = nh.compare(orig, ours)[0]
        self.assertEqual((v["prefabs_same"], v["prefabs_different"], v["scene_same"], v["scene_different"]), (1, 0, 0, 1))
        self.assertEqual(v["different_list"], ["level3:B"])

class ApplyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.d = self.tmp.name
        # a fake serialized file: 64 bytes header, then two NetworkObjects
        self.raw1 = raw_networkobject("", 0x11111111, 0); self.raw2 = raw_networkobject("Named", 0x22222222, 0x33333333)
        blob = b"H" * 64 + self.raw1 + self.raw2 + b"T" * 16
        self.path = os.path.join(self.d, "sharedassets1.assets")
        put(self.path, blob); self.size = len(blob)
        o1 = 64 + nh.hash_field_offset(self.raw1); o2 = 64 + len(self.raw1) + nh.hash_field_offset(self.raw2)
        self.ours = [rec("sharedassets1.assets", 1, "A", 0x11111111, 0, offset=o1), rec("sharedassets1.assets", 2, "B", 0x22222222, 0x33333333, offset=o2)]
        self.orig = [rec("sharedassets1.assets", 7, "A", 0xAAAAAAAA, 0), rec("sharedassets1.assets", 8, "B", 0xBBBBBBBB, 0xCCCCCCCC)]
        self.pairs = list(zip(self.ours, self.orig))
    def tearDown(self): self.tmp.cleanup()

    def read_at(self, off):
        with open(self.path, "rb") as f: f.seek(off); return struct.unpack("<II", f.read(8))

    def test_patch_backup_report(self):
        before = slurp(self.path)
        rep = nh.apply(self.d, self.pairs, rescan=False)
        self.assertEqual((rep["patched"], rep["already"], rep["files"]), (2, 0, ["sharedassets1.assets"]))
        self.assertEqual(self.read_at(self.ours[0]["offset"]), (0xAAAAAAAA, 0))
        self.assertEqual(self.read_at(self.ours[1]["offset"]), (0xBBBBBBBB, 0xCCCCCCCC))
        after = slurp(self.path)
        self.assertEqual(len(after), self.size)
        diff = [i for i in range(self.size) if before[i] != after[i]]
        allowed = set(range(self.ours[0]["offset"], self.ours[0]["offset"] + 8)) | set(range(self.ours[1]["offset"], self.ours[1]["offset"] + 8))
        self.assertTrue(set(diff) <= allowed)
        self.assertEqual(slurp(self.path + ".orig"), before)
        report = json.loads(slurp(os.path.join(self.d, nh.REPORT)))
        self.assertEqual(report["patched"], 2)
        self.assertEqual(report["objects"][1]["new"], [0xBBBBBBBB, 0xCCCCCCCC])
        self.assertEqual(report["objects"][1]["old"], [0x22222222, 0x33333333])

    def test_second_run_keeps_first_backup_and_is_a_noop(self):
        before = slurp(self.path)
        nh.apply(self.d, self.pairs, rescan=False)
        patched = slurp(self.path)
        rep = nh.apply(self.d, self.pairs, rescan=False)   # records are stale now, but the bytes already carry the wanted values
        self.assertEqual((rep["patched"], rep["already"], rep["files"]), (0, 2, []))
        self.assertEqual(slurp(self.path), patched)
        self.assertEqual(slurp(self.path + ".orig"), before)

    def test_backup_not_overwritten_when_it_exists(self):
        put(self.path + ".orig", b"pristine")
        nh.apply(self.d, self.pairs, rescan=False)
        self.assertEqual(slurp(self.path + ".orig"), b"pristine")

    def test_dry_run_changes_nothing(self):
        before = slurp(self.path)
        rep = nh.apply(self.d, self.pairs, dry_run=True)
        self.assertEqual(rep["patched"], 2)
        self.assertEqual(slurp(self.path), before)
        self.assertFalse(os.path.exists(self.path + ".orig"))
        self.assertFalse(os.path.exists(os.path.join(self.d, nh.REPORT)))

    def test_refuses_unexpected_bytes(self):
        bad = dict(self.ours[0], hash=0x99999999)
        with self.assertRaises(RuntimeError): nh.apply(self.d, [(bad, self.orig[0])], rescan=False)
        self.assertFalse(os.path.exists(self.path + ".orig"))

if __name__ == "__main__":
    unittest.main()
