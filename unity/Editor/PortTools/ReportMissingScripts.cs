using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

// Diagnostic: open the first build scene and report components whose script class cannot be resolved in the Editor.
public static class ReportMissingScripts
{
    public static void Run()
    {
        var scenes = EditorBuildSettings.scenes.Where(s => s.enabled).Select(s => s.path).ToList();
        foreach (var path in scenes.Take(2))
        {
            var scene = EditorSceneManager.OpenScene(path, OpenSceneMode.Single);
            int total = 0, missing = 0; var names = new System.Collections.Generic.List<string>();
            foreach (var go in scene.GetRootGameObjects())
                foreach (var t in go.GetComponentsInChildren<Transform>(true))
                    foreach (var c in t.GetComponents<Component>())
                    {
                        total++;
                        if (c == null) { missing++; if (names.Count < 15) names.Add(t.name); }
                    }
            var mbs = scene.GetRootGameObjects().SelectMany(g => g.GetComponentsInChildren<MonoBehaviour>(true)).Where(m => m != null).ToList();
            var asm = mbs.GroupBy(m => m.GetType().Assembly.GetName().Name).Select(g => g.Key + ":" + g.Count());
            Debug.Log($"[PortTools] {path}: {total} components, {missing} with missing script, MonoBehaviours by assembly: {string.Join(", ", asm)}; missing on: {string.Join(", ", names)}");
        }
    }
}
