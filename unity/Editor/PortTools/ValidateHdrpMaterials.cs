using System.Linq;
using UnityEditor;
using UnityEngine.Rendering.HighDefinition;
using UnityEngine;

// Re-validate every HDRP material under Assets so keywords, passes and render queues match their properties
// (needed after materials were re-pointed at package shaders by text edits).
public static class ValidateHdrpMaterials
{
    [MenuItem("PortTools/Validate HDRP materials")]
    public static void Run()
    {
        int n = 0, failed = 0;
        foreach (var g in AssetDatabase.FindAssets("t:Material", new[] { "Assets" }))
        {
            var path = AssetDatabase.GUIDToAssetPath(g);
            var mat = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (mat == null || mat.shader == null) continue;
            if (!mat.shader.name.StartsWith("HDRP/")) continue;
            try { HDMaterial.ValidateMaterial(mat); EditorUtility.SetDirty(mat); n++; }
            catch (System.Exception e) { failed++; Debug.LogWarning($"[PortTools] validate failed for {path}: {e.Message}"); }
        }
        AssetDatabase.SaveAssets();
        Debug.Log($"[PortTools] validated {n} HDRP materials, {failed} failed");
    }
}
