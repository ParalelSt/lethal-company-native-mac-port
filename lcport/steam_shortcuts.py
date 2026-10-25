"""Read and write Steam's binary shortcuts.vdf (the "non-Steam games" list), without third-party packages.

File layout (binary KeyValues): every item is one type byte, a NUL-terminated name, then the value:
  0x00 object  -> children follow, closed by 0x08
  0x01 string  -> NUL-terminated UTF-8 value
  0x02 int32   -> 4 bytes little endian
  0x08         -> end of the current object
The file holds one root object "shortcuts" whose children are objects named "0", "1", ... (one per shortcut),
and the file itself ends with a final 0x08.
"""
import os, shutil, struct, tempfile, zlib

T_OBJECT, T_STRING, T_INT, T_END = 0x00, 0x01, 0x02, 0x08

# canonical spelling and order of a shortcut entry, as current Steam clients write it
FIELDS = ["appid", "AppName", "Exe", "StartDir", "icon", "ShortcutPath", "LaunchOptions", "IsHidden", "AllowDesktopConfig",
          "AllowOverlay", "OpenVR", "Devkit", "DevkitGameID", "DevkitOverrideAppID", "LastPlayTime", "FlatpakAppID", "tags"]
_CANON = {k.lower(): k for k in FIELDS}

# --- low level: bytes <-> nested dicts (insertion order kept, so an untouched file re-encodes to the same bytes) ---

def _cstr(b, i):
    j = b.index(b"\x00", i)
    return b[i:j].decode("utf-8", "surrogateescape"), j + 1

def _read_object(b, i):
    d = {}
    while True:
        if i >= len(b): raise ValueError("shortcuts.vdf: unexpected end of file")
        t = b[i]; i += 1
        if t == T_END: return d, i
        k, i = _cstr(b, i)
        if t == T_OBJECT: v, i = _read_object(b, i)
        elif t == T_STRING: v, i = _cstr(b, i)
        elif t == T_INT: v = struct.unpack_from("<I", b, i)[0]; i += 4
        else: raise ValueError(f"shortcuts.vdf: unsupported value type {t:#x} at offset {i - 1}")
        d[k] = v

def _write_object(d, out):
    for k, v in d.items():
        name = k.encode("utf-8", "surrogateescape") + b"\x00"
        if isinstance(v, dict):
            out += bytes([T_OBJECT]) + name; _write_object(v, out); out.append(T_END)
        elif isinstance(v, int):
            out += bytes([T_INT]) + name + struct.pack("<I", int(v) & 0xFFFFFFFF)
        elif isinstance(v, str):
            out += bytes([T_STRING]) + name + v.encode("utf-8", "surrogateescape") + b"\x00"
        else: raise TypeError(f"shortcuts.vdf: cannot store {type(v).__name__} for key {k!r}")

def decode(b):
    """Bytes of a shortcuts.vdf -> list of entry dicts. Known keys are matched case-insensitively and returned in
    their canonical spelling; unknown keys are kept as they are."""
    if not b: return []
    root, _ = _read_object(b, 0)
    sc = next((v for k, v in root.items() if k.lower() == "shortcuts" and isinstance(v, dict)), {})
    entries = []
    for _, e in sc.items():
        if not isinstance(e, dict): continue
        entries.append({_CANON.get(k.lower(), k): v for k, v in e.items()})
    return entries

def encode(entries):
    """List of entry dicts -> bytes. Entries are renumbered "0", "1", ... in list order."""
    out = bytearray()
    _write_object({"shortcuts": {str(i): e for i, e in enumerate(entries)}}, out)
    out.append(T_END)
    return bytes(out)

# --- file access ---

def load(path):
    if not os.path.exists(path): return []
    with open(path, "rb") as f: return decode(f.read())

def save(path, entries):
    """Atomic write (temp file in the same folder + rename). The previous file is kept as <path>.bak."""
    data = encode(entries)
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".shortcuts-", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        if os.path.exists(path): shutil.copy2(path, path + ".bak")
        os.replace(tmp, path)
    except BaseException:
        try: os.unlink(tmp)
        except OSError: pass
        raise

# --- ids ---

def shortcut_appid(exe, appname):
    """The 32-bit id Steam gives a non-Steam shortcut: CRC32 of the stored Exe string (quotes included) + AppName,
    with the top bit set."""
    return (zlib.crc32((exe + appname).encode("utf-8")) | 0x80000000) & 0xFFFFFFFF

def rungameid(appid):
    """64-bit game id for steam://rungameid/<id>: shortcut appid in the high half, 0x02000000 marks a shortcut."""
    return (appid << 32) | 0x02000000

def quote(p):
    return p if len(p) >= 2 and p.startswith('"') and p.endswith('"') else f'"{p}"'

def find(entries, appname):
    return next((e for e in entries if e.get("AppName") == appname), None)

def remove(entries, appname):
    """Entries without the ones named appname (new list)."""
    return [e for e in entries if e.get("AppName") != appname]

def upsert(entries, appname, exe, startdir, icon="", launch_options=""):
    """Add or replace (same AppName) a shortcut, in place. Exe/StartDir are quoted if they are not already.
    A replaced entry keeps its list position, its Steam categories (tags) and LastPlayTime. Returns the entry."""
    exe, startdir = quote(exe), quote(startdir)
    old = find(entries, appname)
    e = {"appid": shortcut_appid(exe, appname), "AppName": appname, "Exe": exe, "StartDir": startdir, "icon": icon,
         "ShortcutPath": "", "LaunchOptions": launch_options, "IsHidden": 0, "AllowDesktopConfig": 1, "AllowOverlay": 1,
         "OpenVR": 0, "Devkit": 0, "DevkitGameID": "", "DevkitOverrideAppID": 0, "LastPlayTime": 0, "FlatpakAppID": "", "tags": {}}
    if old is not None:
        if isinstance(old.get("tags"), dict): e["tags"] = old["tags"]
        if isinstance(old.get("LastPlayTime"), int): e["LastPlayTime"] = old["LastPlayTime"]
        entries[entries.index(old)] = e
    else:
        entries.append(e)
    return e
