"""Give the native build's NetworkObjects the GlobalObjectIdHash values of the original Windows build.

Netcode for GameObjects hashes every network prefab's GlobalObjectIdHash into NetworkConfig.GetConfig(), and a
host silently rejects a client whose hash differs. Unity's NetworkObject.OnValidate regenerates those hashes when
the ripped project is imported, so after every build we copy the original values back: an in-place binary patch
of two uint32 fields per NetworkObject (no re-serialization, file sizes unchanged).

Usage: python -m lcport.net_hashes fix|verify <app> [game_dir]
       python -m lcport.net_hashes fix-data|verify-data <our Data dir> <original Data dir>
"""
import os, re, sys, glob, json, struct, shutil
from collections import Counter, defaultdict

REPORT = "network-hashes.json"
_LEVEL = re.compile(r"^level\d+$")

def is_level(name):
    return bool(_LEVEL.match(name))

def data_files(data_dir):
    """Serialized files that can hold NetworkObjects: *.assets, levelN and globalgamemanagers (no .orig/.resS)."""
    out = []
    for n in sorted(os.listdir(data_dir)):
        if (n.endswith(".assets") or is_level(n) or n == "globalgamemanagers") and os.path.isfile(os.path.join(data_dir, n)):
            out.append(n)
    return out

def _sort_key(name):
    """resources.assets, sharedassets0..N, then everything else; levels by number."""
    m = re.match(r"^(level|sharedassets)(\d+)", name)
    if m: return (1 if m.group(1) == "sharedassets" else 3, int(m.group(2)), name)
    return (0 if name == "resources.assets" else 2, 0, name)

def hash_field_offset(raw):
    """Offset of GlobalObjectIdHash inside a NetworkObject MonoBehaviour's raw bytes (little-endian, no type tree):
    m_GameObject PPtr (12) + m_Enabled (1, padded to 4) + m_Script PPtr (12) + m_Name (int32 len + bytes, aligned 4)."""
    off = 12 + 4 + 12
    if len(raw) < off + 4: raise ValueError("object too short for a MonoBehaviour header")
    n = struct.unpack_from("<i", raw, off)[0]
    if n < 0 or off + 4 + n > len(raw): raise ValueError(f"bad m_Name length {n}")
    off = (off + 4 + n + 3) & ~3
    if off + 8 > len(raw): raise ValueError("object too short for the NetworkObject hash fields")
    return off

def read_hashes(raw, off):
    return struct.unpack_from("<II", raw, off)

# ---------------------------------------------------------------- scan

def _names(mb):
    """(GameObject name, "Root/.../Name" transform path) of a component; ("", "") when unreadable."""
    try:
        go = mb.m_GameObject.read()
        chain, t = [go.m_Name], go.m_Component[0].component.read()   # the Transform is always the first component
        for _ in range(256):
            if not (t.m_Father and t.m_Father.path_id): break
            t = t.m_Father.read(); chain.append(t.m_GameObject.read().m_Name)
        return go.m_Name, "/".join(reversed(chain))
    except Exception:
        return "", ""

def scan(data_dir):
    """Every NetworkObject in the data dir as a record dict (needs UnityPy)."""
    import UnityPy
    records = []
    for fname in data_files(data_dir):
        path = os.path.join(data_dir, fname)
        try: env = UnityPy.load(path)
        except Exception as e: raise RuntimeError(f"cannot read {path}: {e}")
        level = is_level(fname)
        # for level files, a coarse fingerprint of the whole scene (object count per class) to tell apart
        # scenes whose NetworkObjects look identical
        sig = dict(Counter(o.type.name for o in env.objects)) if level else None
        fh = open(path, "rb")
        for obj in env.objects:
            if obj.type.name != "MonoBehaviour": continue
            raw = obj.get_raw_data()
            if len(raw) < 12 or struct.unpack_from("<iq", raw, 0) == (0, 0): continue  # ScriptableObject, not a component
            try:
                mb = obj.read(check_read=False)
                sc = mb.m_Script.read() if mb.m_Script else None
            except FileNotFoundError:   # script lives in "unity default resources"; never NetworkObject
                continue
            if not sc or getattr(sc, "m_ClassName", None) != "NetworkObject": continue
            if obj.reader.endian != "<": raise RuntimeError(f"{fname}: big-endian serialized file, not supported")
            name, hier = _names(mb)
            rel = hash_field_offset(raw)
            h, src = read_hashes(raw, rel)
            fh.seek(obj.byte_start + rel)
            if fh.read(8) != raw[rel:rel + 8]: raise RuntimeError(f"{fname}: object {obj.path_id} is not at byte {obj.byte_start} in the file")
            records.append({"file": fname, "path_id": obj.path_id, "name": name, "hierarchy": hier, "scene_key": fname if level else "",
                            "offset": obj.byte_start + rel, "hash": h, "in_scene_source_hash": src})
            if level: records[-1]["scene_sig"] = sig
        fh.close()
    return records

# ---------------------------------------------------------------- match

def _ordered(recs):
    return sorted(recs, key=lambda r: (_sort_key(r["file"]), r["path_id"]))

def _pair_on(key, ours, origs, where, ambiguities, report_dups):
    a, b = defaultdict(list), defaultdict(list)
    for r in _ordered(ours): a[key(r)].append(r)
    for r in _ordered(origs): b[key(r)].append(r)
    pairs, lo, lb = [], [], []
    for k in sorted(set(a) | set(b)):
        x, y = a.get(k, []), b.get(k, [])
        if report_dups and x and y and (len(x) > 1 or len(y) > 1):
            ambiguities.append({"where": where, "name": k, "ours": len(x), "original": len(y),
                                "resolved": "by order" if len(x) == len(y) else "by order, counts differ"})
        n = min(len(x), len(y))
        pairs += list(zip(x[:n], y[:n])); lo += x[n:]; lb += y[n:]
    return pairs, lo, lb

def _pair_by_name(ours, origs, where, ambiguities):
    """Pair two record lists: first by transform path ("Root/.../Name", unique in practice, and immune to the
    object order differing between builds), then whatever is left by GameObject name, duplicates by order of
    appearance (reported as ambiguities). Returns (pairs, left_ours, left_orig)."""
    has_h = lambda r: bool(r.get("hierarchy"))
    p1, lo, lb = _pair_on(lambda r: r["hierarchy"], [r for r in ours if has_h(r)], [r for r in origs if has_h(r)],
                          where, ambiguities, True)
    p2, lo, lb = _pair_on(lambda r: r["name"], lo + [r for r in ours if not has_h(r)], lb + [r for r in origs if not has_h(r)],
                          where, ambiguities, True)
    return p1 + p2, lo, lb

def jaccard(c1, c2):
    keys = set(c1) | set(c2)
    top = sum(max(c1[k], c2[k]) for k in keys)
    return sum(min(c1[k], c2[k]) for k in keys) / top if top else 1.0

def map_levels(ours, origs, ambiguities=None):
    """Map each of our level files to the original level file with the closest NetworkObject name multiset
    (Jaccard, one-to-one, best scores first, equal scores prefer the same file name). Returns {our_file: (orig_file, score)}."""
    ca, cb = defaultdict(Counter), defaultdict(Counter)
    sa, sb = {}, {}
    for r in ours: ca[r["scene_key"]][r["name"]] += 1; sa[r["scene_key"]] = Counter(r.get("scene_sig") or {})
    for r in origs: cb[r["scene_key"]][r["name"]] += 1; sb[r["scene_key"]] = Counter(r.get("scene_sig") or {})
    # primary: NetworkObject names; secondary (ties such as two moons with the same networked objects): scene fingerprint
    scores = sorted(((jaccard(ca[a], cb[b]), jaccard(sa[a], sb[b]), a, b) for a in ca for b in cb),
                    key=lambda t: (-t[0], -t[1], t[2] != t[3], _sort_key(t[2]), _sort_key(t[3])))
    out, used = {}, set()
    for s, s2, a, b in scores:
        if s <= 0 or a in out or b in used: continue
        out[a] = (b, s); used.add(b)
        ties = [y for x_s, x_s2, x, y in scores if x == a and y != b and y not in used and (x_s, x_s2) == (s, s2)]
        if ties and ambiguities is not None:
            ambiguities.append({"where": a, "name": "*", "ours": sum(ca[a].values()), "original": sum(cb[b].values()),
                                "resolved": f"mapped to {b}; tied with {', '.join(ties)}"})
    return out

def match(orig_records, our_records):
    """Pair our NetworkObjects with the original ones. Returns (pairs, info) where pairs is a list of
    (our_record, orig_record) and info has counts, the level mapping and any ambiguities."""
    amb = []
    op = [r for r in our_records if not r["scene_key"]]; bp = [r for r in orig_records if not r["scene_key"]]
    pairs, lo, lb = _pair_by_name(op, bp, "prefabs", amb)
    prefab_pairs = len(pairs)
    os_ = [r for r in our_records if r["scene_key"]]; bs = [r for r in orig_records if r["scene_key"]]
    lvl = map_levels(os_, bs, amb)
    by_a, by_b = defaultdict(list), defaultdict(list)
    for r in os_: by_a[r["scene_key"]].append(r)
    for r in bs: by_b[r["scene_key"]].append(r)
    for a in sorted(by_a, key=_sort_key):
        if a not in lvl: lo += by_a[a]; continue
        b, s = lvl[a]
        if s < 1: amb.append({"where": a, "name": "*", "ours": len(by_a[a]), "original": len(by_b[b]),
                              "resolved": f"mapped to {b} with name similarity {s:.2f}"})
        p, x, y = _pair_by_name(by_a[a], by_b[b], f"{a}->{b}", amb)
        pairs += p; lo += x; lb += y
    mapped_b = {b for b, _ in lvl.values()}
    for b in sorted(by_b, key=_sort_key):
        if b not in mapped_b: lb += by_b[b]
    info = {"matched": len(pairs), "matched_prefabs": prefab_pairs, "unmatched_ours": len(lo), "unmatched_orig": len(lb),
            "unmatched_ours_list": [f'{r["file"]}:{r["name"]}' for r in lo],
            "unmatched_orig_list": [f'{r["file"]}:{r["name"]}' for r in lb],
            "unmatched_prefabs_ours": sum(1 for r in lo if not r["scene_key"]),
            "unmatched_prefabs_orig": sum(1 for r in lb if not r["scene_key"]),
            "levels": {a: {"original": b, "score": round(s, 3)} for a, (b, s) in sorted(lvl.items(), key=lambda t: _sort_key(t[0]))},
            "ambiguities": amb}
    return pairs, info

# ---------------------------------------------------------------- apply

def apply(our_data_dir, pairs, dry_run=False, rescan=True):
    """Write the original GlobalObjectIdHash and InScenePlacedSourceGlobalObjectIdHash at each of our records'
    offsets. Keeps a one-time <file>.orig backup, writes <data_dir>/network-hashes.json. Returns the report."""
    by_file = defaultdict(list)
    for ours, orig in pairs: by_file[ours["file"]].append((ours, orig))
    entries, changed_files = [], []
    for fname in sorted(by_file, key=_sort_key):
        path = os.path.join(our_data_dir, fname)
        todo = []
        with open(path, "rb") as f:
            for ours, orig in by_file[fname]:
                f.seek(ours["offset"]); cur = struct.unpack("<II", f.read(8))
                want = (orig["hash"], orig["in_scene_source_hash"])
                if cur == want: status = "already"
                elif cur == (ours["hash"], ours["in_scene_source_hash"]): status = "patched"; todo.append((ours["offset"], want))
                else: raise RuntimeError(f"{fname} @ {ours['offset']}: found {cur}, expected {(ours['hash'], ours['in_scene_source_hash'])}; rescan first")
                entries.append({"file": fname, "path_id": ours["path_id"], "name": ours["name"], "offset": ours["offset"],
                                "old": list(cur), "new": list(want), "original_file": orig["file"], "status": status})
        if not todo or dry_run: continue
        backup = path + ".orig"
        if not os.path.exists(backup): shutil.copy2(path, backup)
        size = os.path.getsize(path)
        with open(path, "r+b") as f:
            for off, want in todo: f.seek(off); f.write(struct.pack("<II", *want))
        if os.path.getsize(path) != size: raise RuntimeError(f"{fname}: size changed while patching")
        with open(path, "rb") as f:   # read back
            for off, want in todo:
                f.seek(off)
                if struct.unpack("<II", f.read(8)) != want: raise RuntimeError(f"{fname} @ {off}: read-back mismatch")
        changed_files.append(fname)
    report = {"dry_run": dry_run, "files": changed_files, "patched": sum(e["status"] == "patched" for e in entries),
              "already": sum(e["status"] == "already" for e in entries), "objects": entries}
    if not dry_run:
        with open(os.path.join(our_data_dir, REPORT), "w") as f: json.dump(report, f, indent=1)
        if rescan and changed_files:
            now = {(r["file"], r["path_id"]): (r["hash"], r["in_scene_source_hash"]) for r in scan(our_data_dir)}
            bad = [e for e in entries if now.get((e["file"], e["path_id"])) != tuple(e["new"])]
            if bad: raise RuntimeError(f"{len(bad)} object(s) do not carry the original hash after patching, e.g. {bad[0]['file']}:{bad[0]['name']}")
    return report

# ---------------------------------------------------------------- verify / fix

def compare(orig_records, our_records):
    pairs, info = match(orig_records, our_records)
    res = {"same": 0, "different": 0, "prefabs_same": 0, "prefabs_different": 0, "scene_same": 0, "scene_different": 0,
           "unmatched_ours": info["unmatched_ours"], "unmatched_orig": info["unmatched_orig"],
           "unmatched_prefabs_ours": info["unmatched_prefabs_ours"], "unmatched_prefabs_orig": info["unmatched_prefabs_orig"],
           "different_list": []}
    for ours, orig in pairs:
        ok = (ours["hash"], ours["in_scene_source_hash"]) == (orig["hash"], orig["in_scene_source_hash"])
        kind = "scene" if ours["scene_key"] else "prefabs"
        res["same" if ok else "different"] += 1; res[f"{kind}_same" if ok else f"{kind}_different"] += 1
        if not ok: res["different_list"].append(f'{ours["file"]}:{ours["name"]}')
    return res, pairs, info

def verify(orig_data_dir, our_data_dir):
    return compare(scan(orig_data_dir), scan(our_data_dir))[0]

def summary(v):
    return (f"prefabs same={v['prefabs_same']} different={v['prefabs_different']} | scene objects same={v['scene_same']} "
            f"different={v['scene_different']} | unmatched ours={v['unmatched_ours']} original={v['unmatched_orig']}")

def orig_data_dir(game_dir):
    d = os.path.join(game_dir, "Lethal Company_Data")
    if os.path.isdir(d): return d
    found = glob.glob(os.path.join(game_dir, "*_Data"))
    if not found: raise RuntimeError(f"no *_Data folder in {game_dir}")
    return found[0]

def fix_data(our_data_dir, orig_dir, log=print):
    orig, ours = scan(orig_dir), scan(our_data_dir)
    before, pairs, info = compare(orig, ours)
    log(f"    network hashes before: {summary(before)}")
    for a in info["ambiguities"]: log(f"    note: {a['where']} {a['name']}: ours={a['ours']} original={a['original']} ({a['resolved']})")
    for n in info["unmatched_ours_list"]: log(f"    unmatched (ours): {n}")
    for n in info["unmatched_orig_list"]: log(f"    unmatched (original): {n}")
    rep = apply(our_data_dir, pairs)
    after = compare(orig, scan(our_data_dir))[0]
    log(f"    patched {rep['patched']} object(s) in {len(rep['files'])} file(s), {rep['already']} already matched")
    log(f"    network hashes after:  {summary(after)}")
    if after["prefabs_different"] or after["unmatched_prefabs_ours"] or after["unmatched_prefabs_orig"]:
        raise RuntimeError("network prefab hashes still differ from the original game; multiplayer with Windows players "
                           f"would fail: {summary(after)}")
    return {"before": before, "after": after, "match": info, "apply": {k: rep[k] for k in ("files", "patched", "already")}}

def fix_build(app_path, game_dir):
    from .util import log
    return fix_data(os.path.join(app_path, "Contents", "Resources", "Data"), orig_data_dir(game_dir), log=log)

def _game_dir(argv, i):
    if len(argv) > i: return argv[i]
    from .util import read_state
    g = read_state().get("game_dir")
    if not g: raise SystemExit("no game_dir given and none recorded in state.json")
    return g

def main(argv):
    if len(argv) < 2 or argv[0] not in ("fix", "verify", "fix-data", "verify-data"):
        print(__doc__.strip().split("\n\n")[-1]); return 2
    cmd = argv[0]
    if cmd.endswith("-data"):
        if len(argv) < 3: print("usage: fix-data|verify-data <our Data dir> <original Data dir>"); return 2
        ours, orig = argv[1], argv[2]
    else:
        ours, orig = os.path.join(argv[1], "Contents", "Resources", "Data"), orig_data_dir(_game_dir(argv, 2))
    if cmd.startswith("fix"):
        fix_data(ours, orig); return 0
    v = verify(orig, ours)
    print(summary(v))
    for n in v["different_list"]: print("  different:", n)
    return 0 if not (v["prefabs_different"] or v["unmatched_prefabs_ours"] or v["unmatched_prefabs_orig"]) else 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
