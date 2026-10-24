#!/usr/bin/env python3
"""Compare the original Windows build with the macOS rebuild: asset counts by type, scenes, shaders, materials, plugins.
Usage: compare_builds.py <windows Lethal Company_Data> <mac Contents/Resources/Data>"""
import os, sys, collections
import UnityPy
def scan(data):
    files = [f for f in os.listdir(data) if (f.startswith(('level','sharedassets','globalgamemanagers','resources')) and not f.endswith(('.resS','.resource')))]
    types = collections.Counter(); shaders = set(); mats = {}; names = collections.defaultdict(set); scenes = []
    for f in sorted(files):
        try: env = UnityPy.load(os.path.join(data, f))
        except Exception as e: print("  skip", f, e); continue
        for o in env.objects:
            t = o.type.name; types[t] += 1
            if t in ("Shader","Material","AudioClip","Texture2D","Mesh","AnimationClip","VideoClip","Font","MonoScript","PhysicMaterial","Cubemap","ComputeShader","VisualEffectAsset","NavMeshData","TerrainData"):
                try:
                    d = o.read()
                    if t == "Shader":
                        n = d.m_ParsedForm.m_Name; shaders.add(n)
                    elif t == "Material":
                        sh = d.m_Shader
                        mats[d.m_Name] = None
                        try:
                            s = sh.read(); mats[d.m_Name] = s.m_ParsedForm.m_Name
                        except Exception: pass
                    elif t == "MonoScript":
                        names[t].add((d.m_Namespace, d.m_ClassName, d.m_AssemblyName))
                    else:
                        names[t].add(getattr(d, "m_Name", "?"))
                except Exception:
                    pass
    return types, shaders, mats, names
win, mac = sys.argv[1], sys.argv[2]
print("scanning windows build..."); wt, ws, wm, wn = scan(win)
print("scanning mac build...");     mt, ms, mm, mn = scan(mac)
print("\n== asset counts by type (windows -> mac), differences only")
for t in sorted(set(wt) | set(mt)):
    if wt[t] != mt[t]: print(f"  {t:28s} {wt[t]:6d} -> {mt[t]:6d}")
print(f"  total objects {sum(wt.values())} -> {sum(mt.values())}")
print("\n== named assets missing on mac / extra on mac")
for t in sorted(set(wn) | set(mn)):
    miss = wn[t] - mn[t]; extra = mn[t] - wn[t]
    if miss or extra:
        print(f"  {t}: missing {len(miss)}, extra {len(extra)}")
        for x in sorted(miss, key=str)[:12]: print("     - missing:", x)
        for x in sorted(extra, key=str)[:6]: print("     + extra:", x)
print("\n== shaders: windows", len(ws), "mac", len(ms))
print("  missing on mac:", sorted(ws - ms))
print("  extra on mac:", sorted(ms - ws)[:40])
print("\n== materials:", len(wm), "->", len(mm))
changed = [(n, wm[n], mm.get(n)) for n in wm if n in mm and wm[n] != mm.get(n)]
print("  materials whose shader differs:", len(changed))
for n, a, b in sorted(changed)[:60]: print(f"     {n}: {a} -> {b}")
print("  materials missing on mac:", sorted(set(wm) - set(mm))[:20])
