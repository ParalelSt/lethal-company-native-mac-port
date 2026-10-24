using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

// Headless build entry point:
//   Unity -batchmode -quit -projectPath <proj> -executeMethod PortTools.BuildMac.Build -buildPath <out.app>
public static class BuildMac
{
    public static void Build()
    {
        string outPath = GetArg("-buildPath") ?? Path.Combine(Directory.GetParent(Application.dataPath).FullName, "build", "Lethal Company.app");
        var scenes = EditorBuildSettings.scenes.Where(s => s.enabled).Select(s => s.path).ToArray();
        if (scenes.Length == 0)
        {
            scenes = AssetDatabase.FindAssets("t:Scene", new[] { "Assets/Scenes" }).Select(AssetDatabase.GUIDToAssetPath).OrderBy(p => p).ToArray();
            Debug.LogWarning("No scenes in EditorBuildSettings; using Assets/Scenes: " + string.Join(", ", scenes));
        }
        PlayerSettings.SetScriptingBackend(BuildTargetGroup.Standalone, ScriptingImplementation.Mono2x);
        PlayerSettings.iOS.microphoneUsageDescription = "Lethal Company uses the microphone for in-game voice chat.";
#if UNITY_EDITOR_OSX
        UnityEditor.OSXStandalone.UserBuildSettings.architecture = UnityEditor.Build.OSArchitecture.ARM64;
#endif
        var opts = new BuildPlayerOptions
        {
            scenes = scenes,
            locationPathName = outPath,
            target = BuildTarget.StandaloneOSX,
            options = BuildOptions.None,
        };
        BuildReport report = BuildPipeline.BuildPlayer(opts);
        Debug.Log($"[PortTools] Build {report.summary.result}: {report.summary.totalErrors} errors, {report.summary.totalWarnings} warnings, {report.summary.totalSize / (1024 * 1024)} MB -> {outPath}");
        if (report.summary.result != BuildResult.Succeeded)
            EditorApplication.Exit(1);
    }

    static string GetArg(string name)
    {
        var args = Environment.GetCommandLineArgs();
        for (int i = 0; i < args.Length - 1; i++)
            if (args[i] == name) return args[i + 1];
        return null;
    }
}
