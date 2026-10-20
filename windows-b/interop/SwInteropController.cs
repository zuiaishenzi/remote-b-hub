// Fixed local controller. Stdin accepts a small JSON action schema, never code.
using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Web.Script.Serialization;
using SolidWorks.Interop.sldworks;

public static class Program {
    static JavaScriptSerializer json = new JavaScriptSerializer();
    static Dictionary<string, object> Map(params object[] pairs) {
        var result = new Dictionary<string, object>();
        for (int i = 0; i < pairs.Length; i += 2) result[(string)pairs[i]] = pairs[i + 1];
        return result;
    }
    [STAThread]
    public static int Main(string[] args) {
        Console.OutputEncoding = new UTF8Encoding(false);
        Console.InputEncoding = new UTF8Encoding(false);
        AppDomain.CurrentDomain.AssemblyResolve += delegate(object sender, ResolveEventArgs ev) {
            var name = new AssemblyName(ev.Name).Name;
            if (!name.StartsWith("SolidWorks.Interop.", StringComparison.OrdinalIgnoreCase)) return null;
            var path = Path.Combine(Environment.GetEnvironmentVariable("REMOTE_B_INTEROP_DIR") ?? "", name + ".dll");
            return File.Exists(path) ? Assembly.LoadFrom(path) : null;
        };
        try {
            if (args.Length == 1 && args[0] == "--contract-test") {
                Console.WriteLine(json.Serialize(Map("ok", true, "actions", new [] {"inspect", "open", "rebuild", "save_copy", "close"})));
                return 0;
            }
            var input = Console.In.ReadToEnd();
            if (input.Length > 4096) throw new Exception("Request too large");
            var req = json.Deserialize<Dictionary<string, object>>(input);
            var value = Run(req);
            Console.WriteLine(json.Serialize(Map("ok", true, "value", value)));
            return 0;
        } catch (Exception ex) {
            Console.WriteLine(json.Serialize(Map("ok", false, "error", ex.ToString())));
            return 1;
        }
    }
    static string Managed(string root, string filename, bool newFile) {
        if (!Regex.IsMatch(filename, @"^[A-Za-z0-9_-]{1,50}\.(SLDPRT|SLDASM)$", RegexOptions.IgnoreCase)) throw new Exception("Invalid CAD filename");
        string fullRoot = Path.GetFullPath(root);
        for (var dir = new DirectoryInfo(fullRoot); dir != null; dir = dir.Parent)
            if (dir.Exists && (dir.Attributes & FileAttributes.ReparsePoint) != 0) throw new Exception("Reparse point in CAD root");
        string path = Path.Combine(fullRoot, filename);
        if (File.Exists(path) && (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0) throw new Exception("Reparse point CAD file");
        if (newFile && File.Exists(path)) throw new Exception("Refusing to overwrite CAD file");
        if (!newFile && !File.Exists(path)) throw new Exception("CAD file does not exist");
        return path;
    }
    static object Run(Dictionary<string, object> req) {
        if (req.Keys.Any(k => !new [] {"action", "file", "new_file", "root", "dimension_names"}.Contains(k))) throw new Exception("Unexpected request fields");
        string action = (string)req["action"];
        if (!new [] {"inspect", "open", "rebuild", "save_copy", "close"}.Contains(action)) throw new Exception("Unsupported action");
        var dimensionNames = new List<string>();
        if (req.ContainsKey("dimension_names")) {
            var rawNames = req["dimension_names"] as System.Collections.IEnumerable;
            if (action != "inspect" || rawNames == null || req["dimension_names"] is string) throw new Exception("Dimensions require inspect and an array");
            foreach (object item in rawNames) {
                string name = item as string;
                if (name == null || !Regex.IsMatch(name, @"^[^@\x00-\x1f\\/:]{1,80}@[^@\x00-\x1f\\/:]{1,80}\z")) throw new Exception("Invalid dimension name");
                dimensionNames.Add(name);
            }
            if (dimensionNames.Count < 1 || dimensionNames.Count > 20) throw new Exception("Expected 1-20 dimension names");
        }
        ISldWorks sw = (ISldWorks)Marshal.GetActiveObject("SldWorks.Application");
        dynamic app = sw;
        string path = req.ContainsKey("file") ? Managed((string)req["root"], (string)req["file"], false) : null;
        if (action != "inspect" && path == null) throw new Exception("Managed CAD filename required");
        dynamic doc;
        if (action == "open") {
            int errors = 0, warnings = 0;
            // Silent + read-only; opening for inspection never enables file edits.
            doc = app.OpenDoc6(path, path.EndsWith(".SLDPRT", StringComparison.OrdinalIgnoreCase) ? 1 : 2, 3, "", ref errors, ref warnings);
            if (doc == null || errors != 0) throw new Exception("OpenDoc6 failed: " + errors + ", warnings=" + warnings);
        } else doc = path == null ? app.ActiveDoc : app.GetOpenDocumentByName(path);
        if (doc == null) throw new Exception("Target document is not open");
        IModelDoc2 typedDocument = (IModelDoc2)doc;
        if (action == "close") {
            if ((bool)doc.GetSaveFlag()) throw new Exception("Refusing to close a modified/unsaved document");
            string title = (string)doc.GetTitle();
            app.CloseDoc(title);
            return Map("action", action, "closed", app.GetOpenDocumentByName(path) == null, "path", path);
        }
        if (action == "rebuild") {
            bool ok = (bool)doc.ForceRebuild3(false);
            if (!ok) throw new Exception("ForceRebuild3 failed");
            return Map("action", action, "rebuild_ok", true, "saved", false, "path", path);
        }
        if (action == "save_copy") {
            string newName = (string)req["new_file"];
            if (!String.Equals(Path.GetExtension(newName), Path.GetExtension(path), StringComparison.OrdinalIgnoreCase)) throw new Exception("Document type cannot change");
            string target = Managed((string)req["root"], newName, true);
            int errors = 0, warnings = 0;
            bool ok = (bool)doc.Extension.SaveAs(target, 0, 3, null, ref errors, ref warnings);
            if (!ok || errors != 0 || !File.Exists(target) || new FileInfo(target).Length == 0) throw new Exception("Save copy failed, errors=" + errors + ", warnings=" + warnings);
            return Map("action", action, "saved", target, "bytes", new FileInfo(target).Length, "warnings", warnings,
                       "copy_only", true, "assembly_references_copied", false);
        }
        var inspection = (Dictionary<string, object>)Inspect(doc);
        if (dimensionNames.Count > 0) inspection["requested_dimensions"] = ReadDimensions(doc, dimensionNames);
        return inspection;
    }
    // Reviewed AngelSix/SolidDNA concepts: explicit dimension identities, model
    // type checks and separate inspection from edits. Uses B's local SW2023 PIA;
    // no third-party ScriptRunner, DLLs or arbitrary expressions are loaded.
    public static object ReadDimensions(dynamic doc, IEnumerable<string> names) {
        var dimensions = new List<object>();
        foreach (string name in names) {
            try {
                dynamic dimension = doc.Parameter(name);
                if (dimension == null) throw new Exception("Dimension not found");
                double value = (double)dimension.SystemValue;
                if (Double.IsNaN(value) || Double.IsInfinity(value)) throw new Exception("Non-finite dimension");
                dimensions.Add(Map("requested_name", name, "full_name", (string)dimension.FullName,
                    "system_value", value, "system_units", "length=m; angle=rad", "read_only", true));
            } catch (Exception ex) {
                dimensions.Add(Map("requested_name", name, "error", ex.Message, "read_only", true));
            }
        }
        return dimensions;
    }
    static object Inspect(dynamic doc) {
        var errors = new List<string>();
        int type = ((IModelDoc2)doc).GetType();
        var result = Map("title", (string)doc.GetTitle(), "path", (string)doc.GetPathName(), "document_type", type,
                         "modified", (bool)doc.GetSaveFlag(), "backend", "C# / SolidWorks.Interop.sldworks",
                         "engineering_validation_complete", false);
        var features = new List<object>();
        WalkFeatures(doc.FirstFeature(), features, 0);
        result["features"] = features;
        result["features_truncated"] = features.Count >= 150;
        if (type == 2) {
            var components = new List<object>();
            object[] all = ((IAssemblyDoc)doc).GetComponents(false) as object[];
            if (all != null) foreach (dynamic comp in all.Take(150)) {
                try {
                    dynamic parent = comp.GetParent();
                    components.Add(Map("name", (string)comp.Name2, "path", (string)comp.GetPathName(),
                        "parent", parent == null ? null : (string)parent.Name2, "suppression", (int)comp.GetSuppression()));
                } catch (Exception ex) { errors.Add("component: " + ex.Message); }
            }
            result["components"] = components;
            result["components_truncated"] = all != null && all.Length > 150;
        }
        if (type == 1) {
            try {
                var bodies = new List<object>();
                object[] all = ((IPartDoc)doc).GetBodies2(0, false) as object[];
                if (all != null) foreach (dynamic body in all.Take(30)) {
                    object[] faces = body.GetFaces() as object[];
                    object[] edges = body.GetEdges() as object[];
                    bodies.Add(Map("name", (string)body.Name, "face_count", faces == null ? 0 : faces.Length,
                        "edge_count", edges == null ? 0 : edges.Length, "bounding_box_m_approximate", body.GetBodyBox()));
                }
                result["solid_bodies"] = bodies;
                result["bodies_truncated"] = all != null && all.Length > 30;
            } catch (Exception ex) { errors.Add("geometry: " + ex.Message); }
        }
        try {
            dynamic mass = doc.Extension.CreateMassProperty();
            if (mass != null) result["mass_properties_si"] = Map("volume_m3", (double)mass.Volume, "area_m2", (double)mass.SurfaceArea, "mass_kg", (double)mass.Mass);
        } catch (Exception ex) { errors.Add("mass properties: " + ex.Message); }
        result["inspection_warnings"] = errors;
        return result;
    }
    static void WalkFeatures(dynamic feature, List<object> result, int depth) {
        while (feature != null && result.Count < 150 && depth < 8) {
            string kind = (string)feature.GetTypeName2();
            var row = Map("name", (string)feature.Name, "type", kind, "depth", depth);
            if (kind == "ProfileFeature" || kind == "3DProfileFeature") {
                try { row["constraint_status"] = (int)feature.GetSpecificFeature2().GetConstrainedStatus(); }
                catch (Exception ex) { row["constraint_error"] = ex.Message; }
            }
            result.Add(row);
            WalkFeatures(feature.GetFirstSubFeature(), result, depth + 1);
            feature = depth == 0 ? feature.GetNextFeature() : feature.GetNextSubFeature();
        }
    }
}
