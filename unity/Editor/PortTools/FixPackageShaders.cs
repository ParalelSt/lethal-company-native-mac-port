using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

// AssetRipper exports every shader as a "dummy" placeholder under Assets/Shader.
// For shaders that also exist in installed packages (HDRP/Lit, Hidden/HDRP/*, Shader Graphs/...),
// point every material at the real package shader instead, then delete the dummy.
public static class FixPackageShaders
{
    [MenuItem("PortTools/Fix package shaders")]
    public static void Run()
    {
        var dummyGuids = AssetDatabase.FindAssets("t:Shader", new[] { "Assets" });
        var dummyByGuid = new Dictionary<string, Shader>();
        foreach (var g in dummyGuids)
        {
            var sh = AssetDatabase.LoadAssetAtPath<Shader>(AssetDatabase.GUIDToAssetPath(g));
            if (sh != null) dummyByGuid[g] = sh;
        }
        // Find real package shaders by name (skip ones that resolve back to an Assets/ dummy).
        var real = new Dictionary<string, Shader>();
        foreach (var g in AssetDatabase.FindAssets("t:Shader", new[] { "Packages" }))
        {
            var p = AssetDatabase.GUIDToAssetPath(g);
            var sh = AssetDatabase.LoadAssetAtPath<Shader>(p);
            if (sh != null && !real.ContainsKey(sh.name)) real[sh.name] = sh;
        }
        int remapped = 0, deleted = 0;
        var matGuids = AssetDatabase.FindAssets("t:Material", new[] { "Assets" });
        var toDelete = new HashSet<string>();
        foreach (var mg in matGuids)
        {
            var path = AssetDatabase.GUIDToAssetPath(mg);
            var mat = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (mat == null || mat.shader == null) continue;
            var shPath = AssetDatabase.GetAssetPath(mat.shader);
            if (!shPath.StartsWith("Assets/")) continue;
            if (real.TryGetValue(mat.shader.name, out var target))
            {
                var keywords = mat.shaderKeywords;
                var queue = mat.renderQueue;
                mat.shader = target;
                mat.shaderKeywords = keywords;
                mat.renderQueue = queue;
                EditorUtility.SetDirty(mat);
                toDelete.Add(shPath);
                remapped++;
            }
        }
        AssetDatabase.SaveAssets();
        foreach (var p in toDelete) { if (AssetDatabase.DeleteAsset(p)) deleted++; }
        // Also delete unreferenced dummies that shadow package shaders (Hidden/HDRP/* etc.)
        foreach (var kv in dummyByGuid)
        {
            var p = AssetDatabase.GUIDToAssetPath(kv.Key);
            if (string.IsNullOrEmpty(p) || !File.Exists(p)) continue;
            if (real.ContainsKey(kv.Value.name) && AssetDatabase.DeleteAsset(p)) deleted++;
        }
        AssetDatabase.Refresh();
        Debug.Log($"[PortTools] remapped {remapped} materials, deleted {deleted} dummy shaders, {real.Count} package shaders known");
    }
}
