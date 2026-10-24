using Mono.Cecil;
// retarget: rename an AssemblyRef inside an assembly (e.g. Facepunch.Steamworks.Win64 -> Facepunch.Steamworks.Posix). IL untouched.
public static class Retarget
{
    public static void Run(string path, string from, string to, string outPath)
    {
        var resolver = new DefaultAssemblyResolver();
        resolver.AddSearchDirectory(System.IO.Path.GetDirectoryName(path));
        foreach (var d in (System.Environment.GetEnvironmentVariable("RETARGET_SEARCH") ?? "").Split(':')) if (d.Length > 0) resolver.AddSearchDirectory(d);
        var asm = AssemblyDefinition.ReadAssembly(path, new ReaderParameters { ReadWrite = false, InMemory = true, AssemblyResolver = resolver });
        int n = 0;
        foreach (var r in asm.MainModule.AssemblyReferences) if (r.Name == from) { r.Name = to; n++; }
        asm.Write(outPath); System.Console.WriteLine($"{System.IO.Path.GetFileName(path)}: retargeted {n} reference(s) {from} -> {to}");
    }
}
