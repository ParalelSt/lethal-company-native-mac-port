#!/usr/bin/env python3
"""Scan Unity asset bundles: print JSON per file {file, shaders:[{name, platforms[]}], materials, metal_ok, d3d_only[]}"""
import sys, json, os
import UnityPy
from UnityPy.enums import ShaderCompilerPlatform
METAL = {"kShaderCompPlatformMetal"}
for f in sys.argv[1:]:
    r = {"file": f, "shaders": [], "materials": 0}
    try:
        env = UnityPy.load(f)
        for o in env.objects:
            if o.type.name == "Material": r["materials"] += 1
            elif o.type.name == "Shader":
                try:
                    sh = o.read(); plats = []
                    for p in getattr(sh, "platforms", []) or []:
                        try: plats.append(ShaderCompilerPlatform(p).name)
                        except Exception: plats.append(str(p))
                    r["shaders"].append({"name": sh.m_ParsedForm.m_Name, "platforms": plats})
                except Exception as e:
                    r["shaders"].append({"name": "?", "platforms": [], "err": str(e)[:60]})
        r["d3d_only"] = [s["name"] for s in r["shaders"] if s["platforms"] and not (set(s["platforms"]) & METAL)]
        r["metal_ok"] = not r["d3d_only"]
    except Exception as e:
        r["error"] = str(e)[:120]
    print(json.dumps(r))
