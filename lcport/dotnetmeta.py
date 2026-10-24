"""Pure-Python .NET assembly metadata (via dnfile): type lists, references, embedded Unity bundles, reference retargeting."""
import os, dnfile

def _s(x):
    return str(x) if x is not None else ""

def load(path):
    return dnfile.dnPE(path, fast_load=False)

def is_managed(path):
    try:
        pe = load(path); return pe.net is not None and pe.net.mdtables is not None
    except Exception:
        return False

def machine(path):
    try: return hex(load(path).FILE_HEADER.Machine)
    except Exception: return "?"

def info(path):
    """{managed, assemblyName, assemblyRefs[], moduleRefs[]}"""
    r = {"file": path, "managed": False, "machine": machine(path)}
    try:
        pe = load(path); md = pe.net.mdtables if pe.net else None
        if md is None: return r
        r["managed"] = True
        r["assemblyName"] = _s(md.Assembly.rows[0].Name) if md.Assembly and md.Assembly.num_rows else ""
        r["assemblyRefs"] = sorted({_s(x.Name) for x in md.AssemblyRef.rows}) if md.AssemblyRef else []
        r["moduleRefs"] = sorted({_s(x.Name) for x in md.ModuleRef.rows}) if md.ModuleRef else []
    except Exception as e:
        r["error"] = str(e)[:120]
    return r

def types(path):
    """Top-level type names as 'Namespace.Name' (what Unity hashes for MonoScript fileIDs)."""
    pe = load(path); md = pe.net.mdtables
    nested = set()
    if md.NestedClass:
        for row in md.NestedClass.rows:
            nested.add(row.NestedClass.row_index if hasattr(row.NestedClass, "row_index") else int(row.NestedClass))
    out = []
    for i, t in enumerate(md.TypeDef.rows, start=1):
        name = _s(t.TypeName)
        if name == "<Module>" or i in nested: continue
        ns = _s(t.TypeNamespace)
        out.append(ns + "." + name if ns else name)
    return out

def embedded_bundles(path, out_dir):
    """Extract embedded resources that are Unity asset bundles (UnityFS); returns extracted paths."""
    out = []
    try:
        pe = load(path)
        for res in (pe.net.resources or []):
            data = res.data if isinstance(res.data, (bytes, bytearray)) else None
            if data and data[:7] == b"UnityFS":
                os.makedirs(out_dir, exist_ok=True)
                p = os.path.join(out_dir, os.path.splitext(os.path.basename(path))[0] + "__" + _s(res.name) + ".bundle")
                open(p, "wb").write(data); out.append(p)
    except Exception:
        pass
    return out

def retarget(src, dst, old, new):
    """Rename an assembly reference by patching the #Strings heap in place (names must have equal length)."""
    if len(old) != len(new): raise ValueError("retarget needs equal-length names")
    raw = bytearray(open(src, "rb").read())
    needle = old.encode() + b"\x00"; n = 0; i = raw.find(needle)
    while i >= 0:
        # only replace whole heap entries (preceded by a NUL or at heap start)
        if i == 0 or raw[i - 1] == 0:
            raw[i:i + len(old)] = new.encode(); n += 1
        i = raw.find(needle, i + 1)
    open(dst, "wb").write(raw); return n
