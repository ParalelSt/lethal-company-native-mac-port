using System;
using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using BepInEx;
using BepInEx.Logging;
using HarmonyLib;
using UnityEngine;

// Mod asset bundles are built for Windows (Direct3D shader code only). On macOS those shaders cannot run, so
// every material coming out of a mod bundle is re-pointed at the game's own copy of the shader (same name,
// compiled for Metal). Unknown custom shaders fall back to HDRP/Lit so the object at least renders lit.
[BepInPlugin("com.lethalcompanymac.macshaderfix", "MacShaderFix", "1.0.0")]
public class MacShaderFix : BaseUnityPlugin
{
    internal static ManualLogSource Log;
    static readonly Dictionary<string, Shader> cache = new Dictionary<string, Shader>();
    static readonly HashSet<int> seen = new HashSet<int>();
    static Shader fallback;
    static int fixedCount, fallbackCount;

    void Awake()
    {
        Log = Logger;
        var h = new Harmony("com.lethalcompanymac.macshaderfix");
        foreach (var name in new[] { "LoadFromFile", "LoadFromMemory", "LoadFromStream" })
            foreach (var m in typeof(AssetBundle).GetMethods(BindingFlags.Public | BindingFlags.Static))
                if (m.Name == name) h.Patch(m, postfix: new HarmonyMethod(typeof(MacShaderFix), nameof(AfterBundleLoad)));
        StartCoroutine(Sweep());
        Log.LogInfo("MacShaderFix active: mod materials will be remapped to the game's Metal shaders");
    }

    static void AfterBundleLoad(AssetBundle __result)
    {
        if (__result == null) return;
        try
        {
            int n = 0;
            foreach (var mat in __result.LoadAllAssets<Material>()) if (Fix(mat)) n++;
            if (n > 0) Log.LogInfo($"bundle {__result.name}: remapped {n} materials");
        }
        catch (Exception e) { Log.LogWarning("bundle scan failed: " + e.Message); }
    }

    IEnumerator Sweep()
    {
        var wait = new WaitForSeconds(2f);
        while (true)
        {
            yield return wait;
            int n = 0;
            foreach (var mat in Resources.FindObjectsOfTypeAll<Material>()) if (Fix(mat)) n++;
            if (n > 0) Log.LogInfo($"sweep: remapped {n} materials (total {fixedCount}, fallback {fallbackCount})");
        }
    }

    static bool Fix(Material mat)
    {
        if (mat == null) return false;
        int id = mat.GetInstanceID();
        if (seen.Contains(id)) return false;
        var sh = mat.shader;
        if (sh != null && sh.isSupported) { seen.Add(id); return false; }
        string name = sh != null ? sh.name : "";
        if (!cache.TryGetValue(name, out var real))
        {
            real = string.IsNullOrEmpty(name) ? null : Shader.Find(name);
            if (real != null && !real.isSupported) real = null;
            cache[name] = real;
        }
        bool usedFallback = false;
        if (real == null)
        {
            if (fallback == null) fallback = Shader.Find("HDRP/Lit");
            real = fallback; usedFallback = true;
        }
        if (real == null) return false;
        var keywords = mat.shaderKeywords; var queue = mat.renderQueue;
        mat.shader = real;
        mat.shaderKeywords = keywords;
        if (queue > 0) mat.renderQueue = queue;
        seen.Add(id); fixedCount++;
        if (usedFallback) { fallbackCount++; Log.LogWarning($"material '{mat.name}': custom shader '{name}' not in game, using HDRP/Lit"); }
        return true;
    }
}
