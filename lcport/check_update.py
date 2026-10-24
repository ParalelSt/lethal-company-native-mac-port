"""Detect a new public build of the game via the Mac Steam client's appinfo cache (no login needed)."""
import os, struct, time, json
from . import config
from .util import read_state, write_state

APPINFO = os.path.expanduser("~/Library/Application Support/Steam/appcache/appinfo.vdf")

def _cstr(b, i):
    j = b.index(b"\x00", i); return b[i:j].decode("utf-8", "replace"), j + 1

def parse_appinfo(path, appid):
    b = open(path, "rb").read(); magic, _ = struct.unpack_from("<II", b, 0)
    if magic not in (0x07564429, 0x07564428): raise RuntimeError(f"unsupported appinfo.vdf format {magic:#x}")
    v29 = magic == 0x07564429; pos = 8; strings = None
    if v29:
        (st,) = struct.unpack_from("<q", b, pos); pos += 8
        n = struct.unpack_from("<I", b, st)[0]; i = st + 4; strings = []
        for _ in range(n): s, i = _cstr(b, i); strings.append(s)
    def key(i):
        return (strings[struct.unpack_from("<I", b, i)[0]], i + 4) if v29 else _cstr(b, i)
    def node(i):
        d = {}
        while True:
            t = b[i]; i += 1
            if t == 8: return d, i
            k, i = key(i)
            if t == 0: v, i = node(i)
            elif t == 1: v, i = _cstr(b, i)
            elif t == 2: v = struct.unpack_from("<i", b, i)[0]; i += 4
            elif t == 3: v = struct.unpack_from("<f", b, i)[0]; i += 4
            elif t == 7: v = struct.unpack_from("<Q", b, i)[0]; i += 8
            else: raise ValueError(t)
            d[k] = v
    while pos < len(b):
        aid, size = struct.unpack_from("<II", b, pos)
        if aid == 0: break
        if aid == appid:
            n, _ = node(pos + 8 + 4 + 4 + 8 + 20 + 4 + 20); return n
        pos += 8 + size
    return None

def live_build():
    info = parse_appinfo(APPINFO, config.APPID)
    if not info: return None
    pub = info.get("appinfo", info)["depots"]["branches"]["public"]
    return {"buildid": str(pub.get("buildid")), "timeupdated": int(pub.get("timeupdated", 0))}

def check(notify=False, accept=False):
    st = read_state(); live = live_build()
    if not live: print("Lethal Company not found in Steam's cache yet (open Steam, view the game once)"); return 0
    if accept or "known_buildid" not in st:
        st["known_buildid"] = live["buildid"]; st["known_timeupdated"] = live["timeupdated"]; write_state(st)
        print("recorded known build", live["buildid"]); return 0
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(live["timeupdated"]))
    if live["buildid"] != st["known_buildid"]:
        msg = f"New Lethal Company build {live['buildid']} ({when}); your Mac build is from {st['known_buildid']}. Update your Steam copy, then rebuild."
        print(msg)
        if notify: os.system(f'osascript -e \'display notification "{msg[:200]}" with title "Lethal Company update"\'')
        return 2
    print(f"up to date (build {live['buildid']}, {when})"); return 0
