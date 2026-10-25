using System;
using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using BepInEx;
using BepInEx.Logging;
using HarmonyLib;
using UnityEngine;

// Mod asset bundles are built for Windows: their shader blobs carry no Metal code, so on macOS every material that
// references a bundle shader renders pink. Shader.isSupported does NOT report this, so instead this plugin snapshots the
// game's own shader instances at startup and re-points any material whose shader is not one of them:
//   * same name exists in the game (HDRP/Lit, HDRP/Unlit, TextMeshPro/..., Sprites/Default, ...) -> that exact shader
//   * unknown custom shader graph -> HDRP/Lit (or HDRP/Unlit for unlit-looking names), textures/colours carried across
[BepInPlugin("com.lethalcompanymac.macshaderfix", "MacShaderFix", "1.1.0")]
public class MacShaderFix : BaseUnityPlugin
{
    internal static ManualLogSource Log;
    static readonly Dictionary<string, Shader> game = new Dictionary<string, Shader>();   // name -> game's shader instance
    static readonly HashSet<int> gameIds = new HashSet<int>();                            // instance ids of game shaders
    static readonly HashSet<int> seen = new HashSet<int>();
    static readonly HashSet<string> loggedFallback = new HashSet<string>();
    static Shader lit, unlit;
    static int fixedCount, fallbackCount;
    static readonly string[] colorMapCandidates = { "_BaseColorMap", "_MainTex", "_BaseMap", "_Diffuse", "_Albedo", "_Texture", "_Tex" };
    static readonly string[] normalCandidates = { "_NormalMap", "_BumpMap", "_Normal", "_NormalMapTex" };
    static readonly string[] colorCandidates = { "_BaseColor", "_Color", "_MainColor", "_Tint", "_TintColor" };

    void Awake()
    {
        Log = Logger;
        Snapshot();
        var h = new Harmony("com.lethalcompanymac.macshaderfix");
        foreach (var name in new[] { "LoadFromFile", "LoadFromMemory", "LoadFromStream" })
            foreach (var m in typeof(AssetBundle).GetMethods(BindingFlags.Public | BindingFlags.Static))
                if (m.Name == name) h.Patch(m, postfix: new HarmonyMethod(typeof(MacShaderFix), nameof(AfterBundleLoad)));
        StartCoroutine(Sweep());
        Log.LogInfo($"MacShaderFix 1.1 active: {game.Count} game shaders snapshotted; mod materials will be remapped to them");
    }

    // Shaders that are already loaded now and do not belong to any loaded asset bundle are the game's own.
    static void Snapshot()
    {
        var fromBundles = new HashSet<int>();
        foreach (var b in AssetBundle.GetAllLoadedAssetBundles())
        {
            try { foreach (var s in b.LoadAllAssets<Shader>()) fromBundles.Add(s.GetInstanceID()); } catch { }
        }
        foreach (var s in Resources.FindObjectsOfTypeAll<Shader>())
        {
            if (s == null || fromBundles.Contains(s.GetInstanceID())) continue;
            if (!game.ContainsKey(s.name)) game[s.name] = s;
            gameIds.Add(s.GetInstanceID());
        }
        game.TryGetValue("HDRP/Lit", out lit); game.TryGetValue("HDRP/Unlit", out unlit);
        if (lit == null) lit = Shader.Find("HDRP/Lit");
        if (unlit == null) unlit = Shader.Find("HDRP/Unlit");
    }

    static void AfterBundleLoad(AssetBundle __result)
    {
        if (__result == null) return;
        try
        {
            int n = 0;
            foreach (var mat in __result.LoadAllAssets<Material>()) if (SafeFix(mat)) n++;
            if (n > 0) Log.LogInfo($"bundle '{__result.name}': remapped {n} materials");
        }
        catch (Exception e) { Log.LogWarning("bundle scan failed: " + e.Message); }
    }

    IEnumerator Sweep()
    {
        float started = Time.realtimeSinceStartup;
        while (true)
        {
            yield return new WaitForSeconds(Time.realtimeSinceStartup - started < 60f ? 0.5f : 2f);
            int n = 0;
            Material[] mats = null;
            try { mats = Resources.FindObjectsOfTypeAll<Material>(); } catch { }
            if (mats == null) continue;
            foreach (var mat in mats) if (SafeFix(mat)) n++;
            if (n > 0) Log.LogInfo($"sweep: remapped {n} materials (total {fixedCount}, custom-shader fallbacks {fallbackCount})");
        }
    }

    static bool SafeFix(Material mat)
    {
        try { return Fix(mat); }
        catch (Exception e) { Log.LogWarning($"could not remap '{(mat ? mat.name : "?")}': {e.Message}"); return false; }
    }

    static bool Fix(Material mat)
    {
        if (mat == null) return false;
        int id = mat.GetInstanceID();
        if (seen.Contains(id)) return false;
        var sh = mat.shader;
        if (sh != null && gameIds.Contains(sh.GetInstanceID())) { seen.Add(id); return false; }   // game's own shader: fine
        string name = sh != null ? sh.name : "";
        Shader real;
        if (name.Length > 0 && game.TryGetValue(name, out real) && real != null)
        {
            var keywords = mat.shaderKeywords; var queue = mat.renderQueue;
            mat.shader = real; mat.shaderKeywords = keywords;
            if (queue > 0) mat.renderQueue = queue;
            seen.Add(id); fixedCount++; return true;
        }
        // custom shader: approximate with HDRP/Lit (or Unlit), carrying the main texture / normal map / colour
        bool wantUnlit = name.IndexOf("unlit", StringComparison.OrdinalIgnoreCase) >= 0 || name.IndexOf("sprite", StringComparison.OrdinalIgnoreCase) >= 0;
        real = wantUnlit && unlit != null ? unlit : lit;
        if (real == null) return false;
        Texture colorMap = FirstTexture(mat, colorMapCandidates, true), normal = FirstTexture(mat, normalCandidates, false);
        Color? color = FirstColor(mat, colorCandidates);
        bool transparent = mat.renderQueue >= 3000 || name.IndexOf("transparent", StringComparison.OrdinalIgnoreCase) >= 0 || name.IndexOf("water", StringComparison.OrdinalIgnoreCase) >= 0;
        mat.shader = real;
        if (colorMap != null) { if (mat.HasProperty("_BaseColorMap")) mat.SetTexture("_BaseColorMap", colorMap); if (mat.HasProperty("_UnlitColorMap")) mat.SetTexture("_UnlitColorMap", colorMap); }
        if (normal != null && mat.HasProperty("_NormalMap")) mat.SetTexture("_NormalMap", normal);
        if (color.HasValue) { if (mat.HasProperty("_BaseColor")) mat.SetColor("_BaseColor", color.Value); if (mat.HasProperty("_UnlitColor")) mat.SetColor("_UnlitColor", color.Value); }
        if (transparent && mat.HasProperty("_SurfaceType")) { mat.SetFloat("_SurfaceType", 1); mat.SetFloat("_BlendMode", 0); mat.SetFloat("_ZWrite", 0); mat.EnableKeyword("_SURFACE_TYPE_TRANSPARENT"); mat.EnableKeyword("_BLENDMODE_ALPHA"); mat.renderQueue = 3000; }
        seen.Add(id); fixedCount++; fallbackCount++;
        if (loggedFallback.Add(name)) Log.LogWarning($"custom shader '{name}' is Windows-only; materials using it now use {real.name} (textures carried over)");
        return true;
    }

    static Texture FirstTexture(Material mat, string[] preferred, bool anyFallback)
    {
        foreach (var p in preferred) if (mat.HasProperty(p) && mat.GetTexture(p) != null) return mat.GetTexture(p);
        if (!anyFallback) return null;
        foreach (var p in mat.GetTexturePropertyNames())
        {
            var l = p.ToLowerInvariant();
            if (l.Contains("normal") || l.Contains("bump") || l.Contains("mask") || l.Contains("emis") || l.Contains("noise") || l.Contains("lightmap")) continue;
            var t = mat.GetTexture(p); if (t != null) return t;
        }
        return null;
    }

    static Color? FirstColor(Material mat, string[] preferred)
    {
        foreach (var p in preferred) if (mat.HasProperty(p)) return mat.GetColor(p);
        return null;
    }
}
