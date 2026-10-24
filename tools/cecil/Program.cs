using Mono.Cecil;
if (args.Length == 5 && args[0] == "retarget") { Retarget.Run(args[1], args[2], args[3], args[4]); return; }
// Build a pure type-forwarding facade: every top-level type (public or not) of <source> is exported from
// a new assembly named <facadeName>, forwarding to the source assembly. Nested types resolve via their parent.
var src = args[0]; var facadeName = args[1]; var outPath = args[2];
var source = AssemblyDefinition.ReadAssembly(src);
var facade = AssemblyDefinition.CreateAssembly(new AssemblyNameDefinition(facadeName, source.Name.Version), facadeName + ".dll", ModuleKind.Dll);
var srcRef = new AssemblyNameReference(source.Name.Name, source.Name.Version);
facade.MainModule.AssemblyReferences.Add(srcRef);
int n = 0;
foreach (var t in source.MainModule.Types)
{
    if (t.Name == "<Module>") continue;
    var et = new ExportedType(t.Namespace, t.Name, facade.MainModule, srcRef) { IsForwarder = true, Attributes = TypeAttributes.Forwarder | (t.IsPublic ? TypeAttributes.Public : TypeAttributes.NotPublic) };
    facade.MainModule.ExportedTypes.Add(et); n++;
}
facade.Write(outPath);
Console.WriteLine($"forwarded {n} top-level types from {source.Name.Name} as {facadeName}");
