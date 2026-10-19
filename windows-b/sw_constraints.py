"""Explicit sketch driving dimensions and fail-closed constraint checks.

SolidWorks 2023 / pywin32 COM: not yet validated on the target workstation.
"""
from solidworks_box import com_read

SW_FULLY_DEFINED = 3
STATUS = {1: "unknown", 2: "under_defined", 3: "fully_defined",
          4: "over_defined", 5: "no_solution", 6: "invalid_solution",
          7: "autosolve_off"}

def read_status(sketch):
    if sketch is None:
        raise RuntimeError("Unable to obtain an active ISketch")
    status = com_read(sketch, "GetConstrainedStatus")
    if type(status) is not int or status not in STATUS:
        raise RuntimeError(f"Unknown ISketch constraint status: {status!r}")
    return status

def dimension_info(display_dimension, expected_mm, key):
    if display_dimension is None:
        raise RuntimeError(f"Driving dimension {key} was not created")
    dimension = display_dimension.GetDimension2(0)
    if dimension is None:
        raise RuntimeError(f"Model dimension for {key} is missing")
    value = float(com_read(dimension, "SystemValue")) * 1000
    if abs(value - expected_mm) > 0.01:
        raise RuntimeError(
            f"Dimension {key} measured {value:.6f} mm; expected {expected_mm:.6f}")
    full_name = str(com_read(dimension, "FullName"))
    if not full_name or "@" not in full_name:
        raise RuntimeError(f"Dimension {key} has no stable model name")
    return {"role": key, "dimension": full_name, "mm": round(value, 6),
            "driving_dimension_created": True}

def select_segment(model, segment):
    model.ClearSelection2(True)
    if not segment.Select4(False, None):
        raise RuntimeError("Failed to select a sketch segment for a driving dimension")

def add_explicit_dimensions(model, sketch_manager, profile, created):
    """Use geometry handles to create meaningful primary dimensions."""
    kind = profile["type"]
    if kind == "polygon":
        raise RuntimeError(
            "Strict parametric mode currently excludes polygon outlines. "
            "Use rectangle or circle; do not treat fixed vertices as design dimensions.")
    if kind == "circle":
        if created is None:
            raise RuntimeError("CreateCircleByRadius returned None")
        select_segment(model, created)
        cx, cy = profile["cx_mm"] / 1000, profile["cy_mm"] / 1000
        radius = profile["radius_mm"] / 1000
        display = model.AddDiameterDimension2(cx + radius * 1.8,
                                               cy + radius * 1.8, 0)
        info = [dimension_info(display, profile["radius_mm"] * 2, "diameter")]
        model.ClearSelection2(True)
        return info
    if not isinstance(created, (list, tuple)):
        raise RuntimeError("CreateCenterRectangle did not return sketch segments")
    # Rectangle output also includes diagonals; never dimension construction lines.
    edges = []
    for segment in created:
        if bool(com_read(segment, "ConstructionGeometry")):
            continue
        edges.append((segment, float(com_read(segment, "GetLength")) * 1000))
    if len(edges) < 4:
        raise RuntimeError("No four rectangle edges found for driving dimensions")
    used = set()
    result = []
    for role, desired in (("width", profile["width_mm"]), ("height", profile["height_mm"])):
        choices = [(i, seg, length) for i, (seg, length) in enumerate(edges)
                   if i not in used and abs(length - desired) < 0.01]
        if not choices:
            raise RuntimeError(f"Cannot identify rectangle {role} edge")
        index, segment, _ = choices[0]
        used.add(index)
        select_segment(model, segment)
        cx, cy = profile["cx_mm"] / 1000, profile["cy_mm"] / 1000
        display = model.AddDimension2(cx + desired / 1500,
                                      cy + desired / 1500, 0)
        result.append(dimension_info(display, desired, role))
    model.ClearSelection2(True)
    return result

def fully_define_or_fail(model, sketch_manager, strict=True):
    # Must execute before leaving sketch-edit mode.
    sketch = com_read(model, "GetActiveSketch2")
    status = read_status(sketch)
    if status == 2 and strict:
        model.ClearSelection2(True)
        # SW example passes True for all entities and a H|V relation mask (3).
        # Treat the API result as advisory; actual sketch state is authoritative.
        sketch_manager.FullyDefineSketch(True, True, 3, True, 1, None,
                                         1, None, 1, 1)
        model.ClearSelection2(True)
        status = read_status(sketch)
    if status not in (2, 3):
        raise RuntimeError(f"Invalid sketch constraints: {STATUS[status]} (code={status})")
    if strict and status != 3:
        raise RuntimeError(
            "Sketch remains under-defined after dimensioning; refusing to save")
    return {"status_code": status, "status": STATUS[status],
            "fully_defined": status == 3}
