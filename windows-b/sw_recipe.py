"""Safe SolidWorks recipe executor: only explicitly supported COM operations.

NOT a generic Python/script/macro runner. Designed for interactive SOLIDWORKS 2023.
Part base shape, cuts, and assembly mates require machine-specific COM validation.
"""
import math
import os
from pathlib import Path
from sw_schema import validate_recipe
from solidworks_box import com_read

OUTPUT_DIR = Path(os.environ.get("REMOTE_B_OUTPUT_DIR", r"D:\codex\output"))
PART_TEMPLATE = Path(os.environ.get(
    "REMOTE_B_PART_TEMPLATE",
    r"C:\ProgramData\SolidWorks\SOLIDWORKS 2023\templates\gb_part.prtdot"))
ASM_TEMPLATE = Path(os.environ.get(
    "REMOTE_B_ASSEMBLY_TEMPLATE",
    r"C:\ProgramData\SolidWorks\SOLIDWORKS 2023\templates\gb_assembly.asmdot"))

PLANE_WORDS = {
    "front": ("前视", "front"),
    "top": ("上视", "top"),
    "right": ("右视", "right"),
}
MATE_TYPES = {
    "coincident": 0, "concentric": 1, "perpendicular": 2,
    "parallel": 3, "distance": 5, "angle": 6,
}
ALIGN_TYPES = {"aligned": 0, "anti_aligned": 1, "closest": 2}

def all_features(model, type_name):
    raw = model.FeatureManager.GetFeatures(False)
    return [f for f in (raw or ()) if com_read(f, "GetTypeName2") == type_name]

def plane_feature(model, plane_key):
    for feature in all_features(model, "RefPlane"):
        display = str(com_read(feature, "Name")).lower()
        if any(term in display for term in PLANE_WORDS[plane_key]):
            return feature
    raise RuntimeError(f"Cannot find reference plane {plane_key}; check SOLIDWORKS template localization")

def selected_sketch(model, before):
    sketches = [f for f in all_features(model, "ProfileFeature")
                if str(com_read(f, "Name")) not in before]
    if len(sketches) != 1:
        raise RuntimeError(f"Expected exactly one newly created sketch, found {len(sketches)}")
    return sketches[0]

def draw_profile(sketch_manager, profile):
    typ = profile["type"]
    if typ == "rectangle":
        cx, cy = profile["cx_mm"] / 1000, profile["cy_mm"] / 1000
        half_x, half_y = profile["width_mm"] / 2000, profile["height_mm"] / 2000
        sketch_manager.CreateCenterRectangle(cx, cy, 0.0, cx + half_x, cy + half_y, 0.0)
    elif typ == "circle":
        sketch_manager.CreateCircleByRadius(
            profile["cx_mm"] / 1000, profile["cy_mm"] / 1000,
            0.0, profile["radius_mm"] / 1000)
    else:
        points = profile["points_mm"]
        for p1, p2 in zip(points, points[1:] + points[:1]):
            segment = sketch_manager.CreateLine(p1[0] / 1000, p1[1] / 1000, 0.0,
                                               p2[0] / 1000, p2[1] / 1000, 0.0)
            if segment is None:
                raise RuntimeError("CreateLine returned None for a polygon segment")

def extrude(model, operation):
    depth = operation["depth_mm"] / 1000
    reverse = operation.get("reverse", False)
    if operation["op"] == "boss_extrude":
        return model.FeatureManager.FeatureExtrusion3(
            True, False, reverse, 0, 0, depth, 0.0,
            False, False, False, False, 0.0, 0.0,
            False, False, False, False,
            True, False, True, 0, 0.0, False)
    return model.FeatureManager.FeatureCut3(
        True, False, reverse, 0, 0, depth, 0.0,
        False, False, False, False, 0.0, 0.0,
        False, False, False, False, False,
        False, True, False, False, False,
        0, 0.0, False)

def save_checked(model, path):
    status = model.SaveAs3(str(path), 0, 1)
    ok = status if isinstance(status, bool) else status == 0
    if not ok or not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(
            f"SaveAs3 failed/invalid output: status={status!r}, file_exists={path.is_file()}, path={path}")
    return path.stat().st_size

def build_part(sw, recipe, path):
    if not PART_TEMPLATE.is_file():
        raise FileNotFoundError(f"Part template missing: {PART_TEMPLATE}")
    model = sw.NewDocument(str(PART_TEMPLATE), 0, 0.0, 0.0)
    if model is None:
        raise RuntimeError("NewDocument(part) returned None")
    features = []
    for index, op in enumerate(recipe["operations"], 1):
        model.ClearSelection2(True)
        plane = plane_feature(model, op["plane"])
        if not plane.Select2(False, 0):
            raise RuntimeError(f"Cannot select {op['plane']} reference plane")
        previous = {str(com_read(f, "Name")) for f in all_features(model, "ProfileFeature")}
        sketch_mgr = model.SketchManager
        sketch_mgr.InsertSketch(True)
        draw_profile(sketch_mgr, op["profile"])
        sketch_mgr.InsertSketch(True)
        sketch = selected_sketch(model, previous)
        model.ClearSelection2(True)
        if not sketch.Select2(False, 0):
            raise RuntimeError(f"Cannot select sketch for step {index}")
        created = extrude(model, op)
        if created is None:
            raise RuntimeError(f"Extrusion/cut failed at step {index}")
        features.append({"step": index, "op": op["op"], "feature": str(com_read(created, "Name"))})
    model.ForceRebuild3(False)
    size = save_checked(model, path)
    return {"saved": str(path), "bytes": size, "doc_type": "part",
            "features": features, "sketch_dimension_constrained": False}

def select_mate_entity(model, comp, selector, part_doc, title, append):
    if "plane" in selector:
        feature = plane_feature(part_doc, selector["plane"])
        entity = str(com_read(feature, "Name"))
        entity_type = "PLANE"
    else:
        entity = selector["entity_name"]
        entity_type = selector["entity_type"]
    component_name = str(com_read(comp, "Name2"))
    full_name = f"{entity}@{component_name}@{title}"
    success = model.Extension.SelectByID2(
        full_name, entity_type, 0.0, 0.0, 0.0, append, 1, None, 0)
    if not success:
        raise RuntimeError(
            f"Mate selection failed: {full_name} [{entity_type}]; "
            "verify exact component/face/plane/axis name in SOLIDWORKS")
    return full_name

def parse_mate_result(value):
    # The pywin32 type library may expose out parameters as tuple values.
    if isinstance(value, tuple):
        mate = value[0] if value else None
        status = value[-1] if len(value) > 1 and isinstance(value[-1], int) else None
    else:
        mate, status = value, None
    if mate is None or status not in (None, 1):
        raise RuntimeError(f"AddMate5 returned no mate or an error: status={status}")
    return mate, status

def build_assembly(sw, recipe, path):
    if not ASM_TEMPLATE.is_file():
        raise FileNotFoundError(f"Assembly template missing: {ASM_TEMPLATE}")
    model = sw.NewDocument(str(ASM_TEMPLATE), 0, 0.0, 0.0)
    if model is None:
        raise RuntimeError("NewDocument(assembly) returned None")
    asm_title = str(com_read(model, "GetTitle"))
    components = {}
    part_docs = {}
    summary = []
    for item in recipe["components"]:
        file_path = OUTPUT_DIR / item["file"]
        if not file_path.is_file():
            raise FileNotFoundError(f"Assembly source part missing: {file_path}")
        # In SOLIDWORKS AddComponent5 expects the document already loaded.
        part = sw.OpenDoc6(str(file_path), 1, 1, "", 0, 0)
        if part is None:
            raise RuntimeError(f"OpenDoc6 failed: {file_path}")
        # Opening a part may change active document. Reactivate the assembly.
        sw.ActivateDoc2(asm_title, False, 0)
        x, y, z = (float(v) / 1000 for v in item["position_mm"])
        component = model.AddComponent5(str(file_path), 0, "", False, "", x, y, z)
        if component is None:
            raise RuntimeError(f"AddComponent5 failed: {file_path}")
        components[item["id"]] = component
        part_docs[item["id"]] = part
        summary.append({"id": item["id"], "file": item["file"],
                        "component_name": str(com_read(component, "Name2"))})
    created_mates = []
    for index, mate in enumerate(recipe.get("mates", []), 1):
        model.ClearSelection2(True)
        try:
            for side, append in (("a", False), ("b", True)):
                selector = mate[side]
                id_ = selector["component"]
                select_mate_entity(
                    model, components[id_], selector, part_docs[id_], asm_title, append)
            mate_type = MATE_TYPES[mate["type"]]
            align = ALIGN_TYPES[mate.get("align", "closest")]
            distance = mate.get("value", 0.0) / 1000 if mate_type == 5 else 0.0
            angle = math.radians(mate.get("value", 0.0)) if mate_type == 6 else 0.0
            mate_result = model.AddMate5(
                mate_type, align, bool(mate.get("flip", False)),
                distance, distance, distance,
                1.0, 1.0, angle, angle, angle,
                False, False, 0, 0)
            new_mate, status = parse_mate_result(mate_result)
            created_mates.append({"index": index, "type": mate["type"],
                                  "feature": str(com_read(new_mate, "Name")),
                                  "status": status})
        except Exception as exc:
            raise RuntimeError(f"Mate {index} ({mate['type']}) failed: {exc}") from exc
        finally:
            model.ClearSelection2(True)
    model.ForceRebuild3(False)
    size = save_checked(model, path)
    return {"saved": str(path), "bytes": size, "doc_type": "assembly",
            "components": summary, "mates": created_mates,
            "mate_geometry_verified": False}

def execute_recipe(recipe):
    validate_recipe(recipe)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = ".SLDPRT" if recipe["doc_type"] == "part" else ".SLDASM"
    path = OUTPUT_DIR / (recipe["name"] + suffix)
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite: {path}")
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    try:
        sw = win32com.client.GetActiveObject("SldWorks.Application")
        if recipe["doc_type"] == "part":
            return build_part(sw, recipe, path)
        return build_assembly(sw, recipe, path)
    finally:
        pythoncom.CoUninitialize()
