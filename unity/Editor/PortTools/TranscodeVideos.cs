using UnityEditor;
using UnityEngine;

// macOS AVFoundation cannot read some H.264 clips straight out of Unity's packed .resource file.
// Enabling transcoding makes Unity re-encode them into its own container, which the player decodes itself.
public static class TranscodeVideos
{
    [MenuItem("PortTools/Enable video transcoding")]
    public static void Run()
    {
        int n = 0;
        foreach (var g in AssetDatabase.FindAssets("t:VideoClip", new[] { "Assets" }))
        {
            var path = AssetDatabase.GUIDToAssetPath(g);
            var imp = AssetImporter.GetAtPath(path) as VideoClipImporter;
            if (imp == null) continue;
            var s = imp.defaultTargetSettings;
            if (s.enableTranscoding && s.codec == VideoCodec.H264) continue;
            s.enableTranscoding = true;
            s.codec = VideoCodec.H264;
            s.resizeMode = VideoResizeMode.OriginalSize;
            s.spatialQuality = VideoSpatialQuality.HighSpatialQuality;
            s.bitrateMode = VideoBitrateMode.High;
            imp.defaultTargetSettings = s;
            imp.SaveAndReimport();
            n++;
        }
        Debug.Log($"[PortTools] enabled transcoding on {n} video clips");
    }
}
