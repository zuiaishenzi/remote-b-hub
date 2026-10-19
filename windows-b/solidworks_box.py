"""SOLIDWORKS 2023 rectangular boss extrusion, controlled by safe dimensions."""
import math
import re
from pathlib import Path

def com_read(obj, member):
    v = getattr(obj, member)
    if not callable(v):
        return v
    try:
        return v()
    except Exception as e:
        if getattr(e, "hresult", None) == -2147352573 and hasattr(v, "_oleobj_"):
            return v
        raise

def find_feature(model, type_name):
    features = model.FeatureManager.GetFeatures(False)
    for feature in features or ():
        if com_read(feature, "GetTypeName2") == type_name:
            return feature
    return None

def create_box(name, length_mm, width_mm, height_mm, output_dir, part_template):
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,50}", name):
        raise ValueError("Part name must be 1-50 ASCII letters/digits/_/-")
    dims = (length_mm, width_mm, height_mm)
    if any(type(d) not in (int, float) or not math.isfinite(d) or not 1 <= d <= 500 for d in dims):
        raise ValueError("Dimensions must be finite numbers between 1 and 500 mm")
    output_dir = Path(output_dir)
    part_template = Path(part_template)
    if not part_template.is_file():
        raise FileNotFoundError(f"Part template missing: {part_template}")
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / (name + ".SLDPRT")
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite: {path}")

    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    try:
        sw = win32com.client.GetActiveObject("SldWorks.Application")
        model = sw.NewDocument(str(part_template), 0, 0.0, 0.0)
        if model is None:
            raise RuntimeError("NewDocument returned None")
        plane = find_feature(model, "RefPlane")
        if plane is None:
            raise RuntimeError("Reference plane missing")
        model.ClearSelection2(True)
        if not plane.Select2(False, 0):
            raise RuntimeError("Cannot select reference plane")
        plane_name = str(com_read(plane, "Name"))

        sketch_manager = model.SketchManager
        sketch_manager.InsertSketch(True)
        sketch_manager.CreateCenterRectangle(
            0.0, 0.0, 0.0,
            float(length_mm) / 2000.0, float(width_mm) / 2000.0, 0.0
        )
        sketch_manager.InsertSketch(True)
        sketch = find_feature(model, "ProfileFeature")
        if sketch is None:
            raise RuntimeError("Rectangle sketch not found")
        model.ClearSelection2(True)
        if not sketch.Select2(False, 0):
            raise RuntimeError("Cannot select sketch")
        extrusion = model.FeatureManager.FeatureExtrusion3(
            True, False, False, 0, 0,
            float(height_mm) / 1000.0, 0.0,
            False, False, False, False,
            0.0, 0.0,
            False, False, False, False,
            True, False, True,
            0, 0.0, False
        )
        if extrusion is None:
            raise RuntimeError("Boss extrusion failed")
        model.ForceRebuild3(False)
        status = model.SaveAs3(str(path), 0, 1)
        saved = status if isinstance(status, bool) else status == 0
        if not saved or not path.is_file() or path.stat().st_size <= 0:
            raise RuntimeError(f"Save failed: status={status!r}, exists={path.is_file()}")
        return {
            "saved": str(path), "bytes": path.stat().st_size,
            "part_name": name, "length_mm": float(length_mm),
            "width_mm": float(width_mm), "height_mm": float(height_mm),
            "plane": plane_name, "feature": str(com_read(extrusion, "Name")),
            "sketch_dimension_constrained": False
        }
    finally:
        pythoncom.CoUninitialize()
