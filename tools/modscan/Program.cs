using System.Reflection.Metadata; using System.Reflection.Metadata.Ecma335; using System.Reflection.PortableExecutable; using System.Text; using System.Text.Json;
// modscan <dll...>            -> one JSON line per DLL: {file, managed, machine, assemblyName, assemblyRefs[], moduleRefs[], embeddedBundles[]}
// modscan --types <dll...>    -> one JSON line per DLL: {file, assemblyName, types:["Namespace.Name", ...]} (top-level types only)
var tmp = Environment.GetEnvironmentVariable("MODSCAN_TMP") ?? Path.GetTempPath();
bool typesMode = args.Length > 0 && args[0] == "--types";
foreach (var path in typesMode ? args.Skip(1) : args)
{
    var r = new Dictionary<string, object> { ["file"] = path };
    try
    {
        using var fs = File.OpenRead(path); using var pe = new PEReader(fs);
        r["machine"] = pe.PEHeaders.CoffHeader.Machine.ToString();
        if (!pe.HasMetadata) { r["managed"] = false; }
        else
        {
            var md = pe.GetMetadataReader(); r["managed"] = true;
            r["assemblyName"] = md.IsAssembly ? md.GetString(md.GetAssemblyDefinition().Name) : "";
            if (typesMode)
            {
                var types = new List<string>();
                foreach (var h in md.TypeDefinitions)
                {
                    var t = md.GetTypeDefinition(h);
                    if (!t.GetDeclaringType().IsNil) continue;
                    var ns = md.GetString(t.Namespace); var name = md.GetString(t.Name);
                    if (name == "<Module>") continue;
                    types.Add(ns.Length > 0 ? ns + "." + name : name);
                }
                r["types"] = types;
            }
            else
            {
                r["assemblyRefs"] = md.AssemblyReferences.Select(h => md.GetString(md.GetAssemblyReference(h).Name)).Distinct().OrderBy(x => x).ToList();
                var mods = new List<string>();
                int n = md.GetTableRowCount(TableIndex.ModuleRef);
                for (int i = 1; i <= n; i++) mods.Add(md.GetString(md.GetModuleReference(MetadataTokens.ModuleReferenceHandle(i)).Name));
                r["moduleRefs"] = mods.Distinct().OrderBy(x => x).ToList();
                var bundles = new List<string>();
                var resDir = pe.PEHeaders.CorHeader.ResourcesDirectory;
                if (resDir.Size > 0 && pe.PEHeaders.TryGetDirectoryOffset(resDir, out int resOff))
                {
                    var img = pe.GetEntireImage();
                    foreach (var h in md.ManifestResources)
                    {
                        var res = md.GetManifestResource(h);
                        if (!res.Implementation.IsNil) continue;
                        var reader = img.GetReader(resOff + (int)res.Offset, 4); int len = reader.ReadInt32();
                        var data = img.GetReader(resOff + (int)res.Offset + 4, Math.Min(len, 8));
                        if (len > 8 && data.ReadByte() == (byte)'U' && data.ReadByte() == (byte)'n' && data.ReadByte() == (byte)'i' && data.ReadByte() == (byte)'t' && data.ReadByte() == (byte)'y' && data.ReadByte() == (byte)'F' && data.ReadByte() == (byte)'S')
                        {
                            var name = md.GetString(res.Name); var outp = Path.Combine(tmp, Path.GetFileNameWithoutExtension(path) + "__" + name + ".bundle");
                            File.WriteAllBytes(outp, img.GetContent(resOff + (int)res.Offset + 4, len).ToArray()); bundles.Add(outp);
                        }
                    }
                }
                r["embeddedBundles"] = bundles;
            }
        }
    }
    catch (Exception e) { r["managed"] = false; r["error"] = e.GetType().Name + ": " + e.Message; }
    Console.WriteLine(JsonSerializer.Serialize(r));
}
