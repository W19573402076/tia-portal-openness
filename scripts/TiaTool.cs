using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using Siemens.Engineering;
using Siemens.Engineering.HW;
using Siemens.Engineering.HW.Features;
using Siemens.Engineering.SW;
using Siemens.Engineering.SW.Blocks;
using Siemens.Engineering.SW.ExternalSources;
using Siemens.Engineering.SW.Tags;
using Siemens.Engineering.SW.Types;
using Siemens.Engineering.Compiler;

class TiaTool
{
    static readonly string DefaultApiDir =
        @"E:\TIA_V21\coding\Portal V21\PublicAPI\V21\net48";
    static string apiDir;
    static StreamWriter log;

    static void Main(string[] args)
    {
        apiDir = Environment.GetEnvironmentVariable("TIA_API_DIR");
        if (String.IsNullOrEmpty(apiDir)) apiDir = DefaultApiDir;
        AppDomain.CurrentDomain.AssemblyResolve += ResolveSiemens;
        Run(args);
    }

    static Assembly ResolveSiemens(object sender, ResolveEventArgs args)
    {
        try
        {
            string name = new AssemblyName(args.Name).Name;
            string path = Path.Combine(apiDir, name + ".dll");
            if (File.Exists(path)) return Assembly.LoadFrom(path);
        }
        catch { }
        return null;
    }

    static void Run(string[] args)
    {
        Console.OutputEncoding = Encoding.UTF8;
        string projectPath = Environment.GetEnvironmentVariable("TIA_PROJECT");
        string cmd = args.Length > 0 ? args[0] : "inspect";
        string logPath = Environment.GetEnvironmentVariable("TIA_TOOL_LOG");
        if (String.IsNullOrEmpty(logPath)) logPath = "tia_output.txt";
        log = new StreamWriter(logPath, false, new UTF8Encoding(false));
        log.AutoFlush = true;

        TiaPortal tia = null;
        Project project = null;
        try
        {
            if (String.IsNullOrEmpty(projectPath))
                throw new Exception("Set TIA_PROJECT to the .ap2x project path.");
            tia = new TiaPortal(TiaPortalMode.WithoutUserInterface);
            project = tia.Projects.Open(new FileInfo(projectPath));
            Log("PROJECT: " + project.Name);

            if (cmd == "inspect") Inspect(project);
            else if (cmd == "tags") CreateTags(project, args);
            else if (cmd == "titles") SetTitles(project, args);
            else if (cmd == "importxml") ImportXml(project, args);
            else if (cmd == "importscl") ImportSource(project, args);
            else if (cmd == "compile") Compile(project);
            else if (cmd == "export") ExportBlock(project, args);
            else if (cmd == "exportmany") ExportMany(project, args);
            else if (cmd == "delete") DeleteBlocks(project, args);
            else if (cmd == "mkidb") CreateInstanceDb(project, args);
            else if (cmd == "rename") RenameTags(project, args);
            else if (cmd == "deltags") DeleteTags(project, args);
            else if (cmd == "delsource") DeleteSources(project, args);
            else Log("Unknown command: " + cmd);
        }
        catch (Exception ex)
        {
            Log("ERROR: " + ex.GetType().FullName);
            Log(ex.Message);
            Exception inner = ex.InnerException;
            while (inner != null) { Log("INNER: " + inner.Message); inner = inner.InnerException; }
            Log(ex.StackTrace);
            Environment.ExitCode = 1;
        }
        finally
        {
            if (project != null)
            {
                try { project.Save(); Log("Project saved."); }
                catch (Exception e) { Log("SAVE ERROR: " + e.Message); }
                try { project.Close(); } catch (Exception e) { Log("CLOSE ERROR: " + e.Message); }
            }
            if (tia != null) { try { tia.Dispose(); } catch { } }
            log.Close();
        }
    }

    static void Log(string s) { log.WriteLine(s); }
    static void LogBlock(PlcBlock b, string indent)
    {
        Log(indent + "BLOCK: " + b.Name + " | " + b.GetType().Name +
            " | Number=" + b.Number + " | Lang=" + b.ProgrammingLanguage +
            " | Consistent=" + b.IsConsistent);
    }

    static PlcSoftware FindPlc(Project project)
    {
        foreach (Device dev in project.Devices)
        {
            Log("DEVICE: " + dev.Name + " | Type: " + dev.TypeIdentifier);
            foreach (DeviceItem item in dev.DeviceItems)
            {
                PlcSoftware plc = FindPlc(item);
                if (plc != null) return plc;
            }
        }
        return null;
    }

    static PlcSoftware FindPlc(DeviceItem item)
    {
        try
        {
            SoftwareContainer sc = item.GetService<SoftwareContainer>();
            if (sc != null && sc.Software is PlcSoftware)
            {
                Log("  PLC SOFTWARE: " + sc.Software.Name);
                return (PlcSoftware)sc.Software;
            }
        }
        catch { }
        foreach (DeviceItem child in item.DeviceItems)
        {
            PlcSoftware plc = FindPlc(child);
            if (plc != null) return plc;
        }
        return null;
    }

    static void Inspect(Project project)
    {
        PlcSoftware plc = FindPlc(project);
        if (plc == null) { Log("NO PLC FOUND"); return; }
        Log("== BLOCKS ==");
        DumpGroup(plc.BlockGroup, "  ");
        Log("== TAG TABLES ==");
        foreach (PlcTagTable tt in plc.TagTableGroup.TagTables)
        {
            Log("TAGTABLE: " + tt.Name + " | tags=" + tt.Tags.Count);
            foreach (PlcTag tag in tt.Tags)
                Log("   TAG: " + tag.Name + " | " + tag.DataTypeName +
                    " | " + tag.LogicalAddress);
        }
        Log("== EXTERNAL SOURCES ==");
        foreach (PlcExternalSource src in plc.ExternalSourceGroup.ExternalSources)
            Log("SOURCE: " + src.Name);
        Log("== PLC TYPES ==");
        foreach (PlcType t in plc.TypeGroup.Types) Log("TYPE: " + t.Name);
    }

    static void DumpGroup(PlcBlockGroup group, string indent)
    {
        foreach (PlcBlock b in group.Blocks) LogBlock(b, indent);
        foreach (PlcBlockGroup g in group.Groups)
        {
            Log(indent + "GROUP: " + g.Name);
            DumpGroup(g, indent + "  ");
        }
    }

    static void CreateTags(Project project, string[] args)
    {
        PlcSoftware plc = FindPlc(project);
        if (plc == null) throw new Exception("NO PLC");
        if (args.Length < 3) throw new Exception("usage: tags <table> <csv>");
        string tableName = args[1];
        string file = args[2];
        PlcTagTable table = null;
        foreach (PlcTagTable t in plc.TagTableGroup.TagTables)
            if (t.Name == tableName) table = t;
        if (table == null)
        {
            table = plc.TagTableGroup.TagTables.Create(tableName);
            Log("Created tag table " + tableName);
        }
        foreach (string raw in File.ReadAllLines(file, Encoding.UTF8))
        {
            string line = raw.Trim().TrimStart('\uFEFF');
            if (line.Length == 0 || line.StartsWith("#")) continue;
            string[] p = line.Split(new char[] { ',', '\t' });
            if (p.Length < 3) { Log("SKIP: " + line); continue; }
            string name = p[0].Trim(), type = p[1].Trim(), addr = p[2].Trim();
            PlcTag old = table.Tags.Find(name);
            if (old != null) old.Delete();
            table.Tags.Create(name, type, addr);
            Log("TAG: " + name + " | " + type + " | " + addr);
        }
    }

    static void SetTitles(Project project, string[] args)
    {
        PlcSoftware plc = FindPlc(project);
        if (plc == null) throw new Exception("NO PLC");
        if (args.Length < 2) throw new Exception("usage: titles <tsv>");
        foreach (string raw in File.ReadAllLines(args[1], Encoding.UTF8))
        {
            string line = raw.Trim().TrimStart('\uFEFF');
            if (line.Length == 0 || line.StartsWith("#")) continue;
            string[] p = line.Split('\t');
            PlcBlock b = FindBlock(plc.BlockGroup, p[0]);
            if (b == null) { Log("BLOCK NOT FOUND: " + p[0]); continue; }
            SetText(b.Title, p[1]);
            if (p.Length > 2) SetText(b.Comment, p[2]);
            Log("TITLE SET: " + p[0] + " -> " + p[1]);
        }
    }

    static void SetText(MultilingualText text, string value)
    {
        foreach (MultilingualTextItem item in text.Items) item.Text = value;
    }

    static void ImportXml(Project project, string[] args)
    {
        PlcSoftware plc = FindPlc(project);
        if (plc == null) throw new Exception("NO PLC");
        for (int i = 1; i < args.Length; i++)
        {
            try
            {
                IList<PlcBlock> blocks = plc.BlockGroup.Blocks.Import(
                    new FileInfo(Path.GetFullPath(args[i])), ImportOptions.Override);
                Log("IMPORT OK " + args[i] + " -> " + blocks.Count);
                foreach (PlcBlock b in blocks)
                    Log("  BLOCK " + b.Name + " | " + b.GetType().Name +
                        " | " + b.ProgrammingLanguage);
            }
            catch (Exception ex)
            {
                Log("IMPORT FAIL " + args[i]);
                Log("  MSG: " + ex.Message);
                Exception inner = ex.InnerException;
                while (inner != null) { Log("  INNER: " + inner.Message); inner = inner.InnerException; }
            }
        }
    }

    static void ImportSource(Project project, string[] args)
    {
        PlcSoftware plc = FindPlc(project);
        if (plc == null) throw new Exception("NO PLC");
        if (args.Length < 3) throw new Exception("usage: importscl <name> <file>");
        string name = args[1], file = args[2];
        foreach (PlcExternalSource old in plc.ExternalSourceGroup.ExternalSources.ToList())
            if (old.Name == name) old.Delete();
        PlcExternalSource src = plc.ExternalSourceGroup.ExternalSources.CreateFromFile(
            name, Path.GetFullPath(file));
        src.GenerateBlocksFromSource();
        Log("IMPORTED SCL: " + name);
        DumpGroup(plc.BlockGroup, "  ");
    }

    static void Compile(Project project)
    {
        PlcSoftware plc = FindPlc(project);
        if (plc == null) throw new Exception("NO PLC");
        ICompilable provider = plc as ICompilable;
        if (provider == null) provider = plc.GetService<ICompilable>();
        if (provider == null) { Log("No compile service"); return; }
        CompilerResult result = provider.Compile();
        Log("COMPILE: " + result.State + " errors=" + result.ErrorCount +
            " warnings=" + result.WarningCount);
        foreach (CompilerResultMessage msg in result.Messages) DumpMessage(msg, "  ");
    }

    static void DumpMessage(CompilerResultMessage msg, string indent)
    {
        Log(indent + msg.State + " | " + msg.Path + " | " + msg.Description);
        foreach (CompilerResultMessage child in msg.Messages)
            DumpMessage(child, indent + "  ");
    }

    static void ExportBlock(Project project, string[] args)
    {
        PlcSoftware plc = FindPlc(project);
        if (plc == null) throw new Exception("NO PLC");
        if (args.Length < 3) throw new Exception("usage: export <block> <file>");
        PlcBlock b = FindBlock(plc.BlockGroup, args[1]);
        if (b == null) throw new Exception("Block not found: " + args[1]);
        b.Export(new FileInfo(Path.GetFullPath(args[2])), ExportOptions.None);
        Log("EXPORTED " + args[1] + " -> " + args[2]);
    }

    static void ExportMany(Project project, string[] args)
    {
        PlcSoftware plc = FindPlc(project);
        if (plc == null) throw new Exception("NO PLC");
        if (args.Length < 3) throw new Exception("usage: exportmany <dir> <block...>");
        string dir = args[1];
        for (int i = 2; i < args.Length; i++)
        {
            PlcBlock b = FindBlock(plc.BlockGroup, args[i]);
            if (b == null) { Log("BLOCK NOT FOUND: " + args[i]); continue; }
            string path = Path.Combine(dir, args[i] + ".xml");
            try
            {
                b.Export(new FileInfo(Path.GetFullPath(path)), ExportOptions.None);
                Log("EXPORTED: " + args[i] + " -> " + path);
            }
            catch (Exception ex) { Log("EXPORT FAIL: " + args[i] + " : " + ex.Message); }
        }
    }

    static void CreateInstanceDb(Project project, string[] args)
    {
        PlcSoftware plc = FindPlc(project);
        if (plc == null) throw new Exception("NO PLC");
        if (args.Length < 5)
            throw new Exception("usage: mkidb <dbName> <number> <auto 0|1> <fbName>");
        string name = args[1];
        int number = Int32.Parse(args[2]);
        bool auto = args[3] == "1";
        string fbName = args[4];
        PlcBlock old = FindBlock(plc.BlockGroup, name);
        if (old != null)
        {
            Log("DB EXISTS, deleting: " + name);
            old.Delete();
        }
        InstanceDB db = plc.BlockGroup.Blocks.CreateInstanceDB(
            name, auto, number, fbName);
        Log("CREATED INSTANCE DB: " + db.Name + " | Number=" + db.Number);
    }

    static void DeleteBlocks(Project project, string[] args)
    {
        PlcSoftware plc = FindPlc(project);
        if (plc == null) throw new Exception("NO PLC");
        for (int i = 1; i < args.Length; i++)
        {
            PlcBlock b = FindBlock(plc.BlockGroup, args[i]);
            if (b == null) { Log("NOT FOUND: " + args[i]); continue; }
            b.Delete();
            Log("DELETED: " + args[i]);
        }
    }

    static void RenameTags(Project project, string[] args)
    {
        PlcSoftware plc = FindPlc(project);
        if (plc == null) throw new Exception("NO PLC");
        for (int i = 1; i + 1 < args.Length; i += 2)
        {
            PlcTag tag = FindTag(plc, args[i]);
            if (tag == null) { Log("TAG NOT FOUND: " + args[i]); continue; }
            tag.SetAttribute("Name", args[i + 1]);
            Log("RENAMED: " + args[i] + " -> " + args[i + 1]);
        }
    }

    static void DeleteTags(Project project, string[] args)
    {
        PlcSoftware plc = FindPlc(project);
        if (plc == null) throw new Exception("NO PLC");
        for (int i = 1; i < args.Length; i++)
        {
            PlcTag tag = FindTag(plc, args[i]);
            if (tag == null) { Log("TAG NOT FOUND: " + args[i]); continue; }
            tag.Delete();
            Log("TAG DELETED: " + args[i]);
        }
    }

    static void DeleteSources(Project project, string[] args)
    {
        PlcSoftware plc = FindPlc(project);
        if (plc == null) throw new Exception("NO PLC");
        for (int i = 1; i < args.Length; i++)
        {
            PlcExternalSource found = null;
            foreach (PlcExternalSource s in plc.ExternalSourceGroup.ExternalSources)
                if (s.Name == args[i]) found = s;
            if (found == null) { Log("SOURCE NOT FOUND: " + args[i]); continue; }
            found.Delete();
            Log("SOURCE DELETED: " + args[i]);
        }
    }

    static PlcTag FindTag(PlcSoftware plc, string name)
    {
        foreach (PlcTagTable tt in plc.TagTableGroup.TagTables)
            foreach (PlcTag t in tt.Tags)
                if (t.Name == name) return t;
        return null;
    }

    static PlcBlock FindBlock(PlcBlockGroup group, string name)
    {
        foreach (PlcBlock b in group.Blocks) if (b.Name == name) return b;
        foreach (PlcBlockGroup g in group.Groups)
        {
            PlcBlock b = FindBlock(g, name);
            if (b != null) return b;
        }
        return null;
    }
}
