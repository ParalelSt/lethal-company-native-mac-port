#!/usr/bin/env python3
"""Remap MonoScript references from AssetRipper's exported package DLLs to the real package scripts.

Unity references a type inside a DLL as {fileID: <md4 hash of namespace+name>, guid: <dll guid>, type: 3}
and a .cs script as {fileID: 11500000, guid: <script guid>, type: 3}.
Usage: remap_package_scripts.py <ExportedProject> <replaced_dlls.json> <pkgdir> [<pkgdir>...]
"""
import json, os, re, struct, sys

# --- minimal MD4 (RFC 1320); hashlib's md4 is disabled in many OpenSSL 3 builds ---
def _lrot(x, n): return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF
def md4(data: bytes) -> bytes:
    a, b, c, d = 0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476
    ml = len(data) * 8
    data += b"\x80" + b"\x00" * ((56 - (len(data) + 1) % 64) % 64) + struct.pack("<Q", ml)
    F = lambda x, y, z: (x & y) | (~x & z)
    G = lambda x, y, z: (x & y) | (x & z) | (y & z)
    H = lambda x, y, z: x ^ y ^ z
    for off in range(0, len(data), 64):
        X = list(struct.unpack("<16I", data[off:off + 64]))
        aa, bb, cc, dd = a, b, c, d
        for i in range(16):
            k, s = i, [3, 7, 11, 19][i % 4]
            r = [a, b, c, d]
            j = (-i) % 4
            r[j] = _lrot((r[j] + F(r[(j+1)%4], r[(j+2)%4], r[(j+3)%4]) + X[k]) & 0xFFFFFFFF, s)
            a, b, c, d = r
        for i in range(16):
            k, s = (i % 4) * 4 + i // 4, [3, 5, 9, 13][i % 4]
            r = [a, b, c, d]; j = (-i) % 4
            r[j] = _lrot((r[j] + G(r[(j+1)%4], r[(j+2)%4], r[(j+3)%4]) + X[k] + 0x5A827999) & 0xFFFFFFFF, s)
            a, b, c, d = r
        order = [0, 8, 4, 12, 2, 10, 6, 14, 1, 9, 5, 13, 3, 11, 7, 15]
        for i in range(16):
            k, s = order[i], [3, 9, 11, 15][i % 4]
            r = [a, b, c, d]; j = (-i) % 4
            r[j] = _lrot((r[j] + H(r[(j+1)%4], r[(j+2)%4], r[(j+3)%4]) + X[k] + 0x6ED9EBA1) & 0xFFFFFFFF, s)
            a, b, c, d = r
        a, b, c, d = [(x + y) & 0xFFFFFFFF for x, y in zip((a, b, c, d), (aa, bb, cc, dd))]
    return struct.pack("<4I", a, b, c, d)

def unity_file_id(namespace: str, name: str) -> int:
    h = md4(b"s\x00\x00\x00" + namespace.encode() + name.encode())
    return struct.unpack("<i", h[:4])[0]

def split_full(t):
    # ilspycmd prints nested types as Outer.Inner (same separator as namespace); keep last token as name
    if "." in t:
        ns, name = t.rsplit(".", 1)
    else:
        ns, name = "", t
    return ns, name

def index_package_scripts(pkgdirs):
    """Map 'Namespace.ClassName' -> guid for every .cs in the packages (non-editor folders)."""
    cls_re = re.compile(r'^\s*(?:public|internal|private|protected|static|abstract|sealed|partial|\s)*\s*(?:class|struct)\s+([A-Za-z_][A-Za-z0-9_]*)', re.M)
    ns_re = re.compile(r'^\s*namespace\s+([A-Za-z0-9_.]+)', re.M)
    idx = {}
    for pd in pkgdirs:
        for root, _, files in os.walk(pd):
            if "/Editor" in root.replace(pd, "") or "~" in root:
                continue
            for f in files:
                if not f.endswith(".cs"):
                    continue
                cs = os.path.join(root, f)
                meta = cs + ".meta"
                if not os.path.exists(meta):
                    continue
                g = re.search(r'guid: ([0-9a-f]{32})', open(meta).read())
                if not g:
                    continue
                try:
                    src = open(cs, encoding="utf-8", errors="ignore").read()
                except Exception:
                    continue
                nss = ns_re.findall(src)
                ns = nss[0] if nss else ""
                base = f[:-3]
                names = set(cls_re.findall(src))
                # Unity only binds the class whose name matches the file name.
                if base in names:
                    idx.setdefault((ns + "." + base).strip("."), g.group(1))
    return idx

def run(proj, replaced_json, pkgdirs):
    replaced = json.load(open(replaced_json))
    pkg_idx = index_package_scripts(pkgdirs)
    print(f"indexed {len(pkg_idx)} package scripts")
    # old (guid, fileID) -> new guid
    table = {}
    missing = {}
    for dll, info in replaced.items():
        for t in info["types"]:
            ns, name = split_full(t)
            fid = unity_file_id(ns, name)
            full = (ns + "." + name).strip(".")
            if full in pkg_idx:
                table[(info["guid"], fid)] = pkg_idx[full]
            else:
                missing[(info["guid"], fid)] = full
    print(f"remap table: {len(table)} types resolvable, {len(missing)} without a package script")
    ref_re = re.compile(r'\{fileID: (-?\d+), guid: ([0-9a-f]{32}), type: 3\}')
    exts = (".unity", ".prefab", ".asset", ".controller", ".mat", ".playable", ".mixer", ".overrideController", ".anim", ".preset")
    files_changed = refs_changed = 0
    unresolved = {}
    for root, _, files in os.walk(os.path.join(proj, "Assets")):
        for f in files:
            if not f.endswith(exts):
                continue
            p = os.path.join(root, f)
            try:
                s = open(p, encoding="utf-8").read()
            except Exception:
                continue
            def sub(m):
                nonlocal refs_changed
                key = (m.group(2), int(m.group(1)))
                if key in table:
                    refs_changed += 1
                    return "{fileID: 11500000, guid: %s, type: 3}" % table[key]
                if key in missing:
                    unresolved[missing[key]] = unresolved.get(missing[key], 0) + 1
                return m.group(0)
            ns = ref_re.sub(sub, s)
            if ns != s:
                open(p, "w", encoding="utf-8").write(ns)
                files_changed += 1
    print(f"changed {refs_changed} references in {files_changed} files")
    if unresolved:
        print("UNRESOLVED (still pointing at deleted DLLs):")
        for k, v in sorted(unresolved.items(), key=lambda x: -x[1])[:40]:
            print(f"  {v:6d}  {k}")

if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2], sys.argv[3:])
