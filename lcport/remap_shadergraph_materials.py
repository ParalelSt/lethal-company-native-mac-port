#!/usr/bin/env python3
"""Point materials that used unrecoverable Shader Graphs at HDRP/Lit, carrying over textures/colours.
Operates on AssetRipper's map-style material YAML. Usage: remap_shadergraph_materials.py <ExportedProject>"""
import os, re, sys

def run(proj):
    matdir = os.path.join(proj, "Assets/Material")
    LIT = "6e4ae4064600d784cac1e41a9e6f2e59"
    GRASS = {"tex": {"_MainTex": "_BaseColorMap", "_Normal": "_NormalMap"}, "col": {}, "floats": {"_AlphaCutoffEnable": 1, "_AlphaCutoff": 0.5, "_DoubleSidedEnable": 1, "_SurfaceType": 0, "_Smoothness": 0.1}}
    FUR   = {"tex": {"_Diffuse": "_BaseColorMap", "_NormalMapTex": "_NormalMap"}, "col": {}, "floats": {"_SurfaceType": 0, "_Smoothness": 0.15}}
    BLOB  = {"tex": {"_MainTex": "_BaseColorMap"}, "col": {"_Gradient_Color": "_BaseColor"}, "floats": {"_SurfaceType": 0, "_Smoothness": 0.6}}
    HOLO  = {"tex": {}, "col": {"_MainColor": "_BaseColor", "_FresnelColor": "_EmissiveColor"}, "floats": {"_SurfaceType": 1, "_BlendMode": 0, "_ZWrite": 0, "_UseEmissiveIntensity": 0, "_Smoothness": 0.2}}
    WATER = {"tex": {"Texture2D_75234e64d8d74583bd442975e49b1b99": "_NormalMap"}, "col": {"Color_c9a840f2115c4802ba54d713194f761d": "_BaseColor"}, "floats": {"_SurfaceType": 1, "_BlendMode": 0, "_ZWrite": 0, "_Smoothness": 0.95, "_NormalScale": 0.3}}
    FILES = {**{f: GRASS for f in ["flowersMat.mat","WavingGrassMat2.mat","Weed2.mat","WavingGrassMat.mat","CadaverBloomPlants.mat","Weed2Snowy.mat","WavingGrass3.mat","WavingGrass3 1.mat"]},
             "BushWolfMat.mat": FUR, "BlobMaterial.mat": BLOB, "HologramMat.mat": HOLO,
             **{f: WATER for f in ["CaveWater.mat","MarchWater.mat","VowWater.mat","Water_mat_04.mat","PoolWater.mat"]}}
    tex_re = lambda n: re.compile(r"      %s:\n        m_Texture: (\{[^}]*\})\n        m_Scale: (\{[^}]*\})\n        m_Offset: (\{[^}]*\})\n" % re.escape(n))
    col_re = lambda n: re.compile(r"      %s: (\{[^}]*\})\n" % re.escape(n))
    flt_re = lambda n: re.compile(r"      %s: [-0-9.eE+]+\n" % re.escape(n))
    broken = re.compile(r"^    - _\w+: .*\n", re.M)  # list-style lines inserted by the earlier buggy run
    for f, plan in FILES.items():
        p = os.path.join(matdir, f)
        if not os.path.exists(p): continue
        s = open(p, encoding="utf-8").read()
        s = broken.sub("", s)
        s = re.sub(r"m_Shader: \{fileID: 4800000, guid: [0-9a-f]{32}, type: 3\}", f"m_Shader: {{fileID: 4800000, guid: {LIT}, type: 3}}", s, 1)
        for old, new in plan["tex"].items():
            m = tex_re(old).search(s)
            if m and "guid:" in m.group(1):
                s = tex_re(new).sub("", s)
                s = s.replace("    m_TexEnvs:\n", "    m_TexEnvs:\n      %s:\n        m_Texture: %s\n        m_Scale: %s\n        m_Offset: %s\n" % (new, m.group(1), m.group(2), m.group(3)), 1)
        for old, new in plan["col"].items():
            m = col_re(old).search(s)
            if m:
                s = col_re(new).sub("", s)
                s = s.replace("    m_Colors:\n", "    m_Colors:\n      %s: %s\n" % (new, m.group(1)), 1)
        for k, v in plan["floats"].items():
            s = flt_re(k).sub("", s)
            s = s.replace("    m_Floats:\n", "    m_Floats:\n      %s: %s\n" % (k, v), 1)
        s = re.sub(r"m_ShaderKeywords: .*\n", "m_ShaderKeywords: \n", s)
        open(p, "w", encoding="utf-8").write(s)
        print(" ", f, "ok" if "_BaseColorMap" in s or not plan["tex"] else "NO TEX")
    print("done")


if __name__ == "__main__":
    run(sys.argv[1])