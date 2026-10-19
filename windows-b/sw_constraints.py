"""Explicit sketch driving dimensions and fail-closed constraint checks.

SolidWorks 2023 / pywin32 COM: not yet validated on the target workstation.
"""
from contextlib import contextmanager
import math
from solidworks_box import com_read, find_feature

# swUserPreferenceToggle_e.swInputDimValOnCreate (late-bound COM constant).
SW_INPUT_DIM_VAL_ON_CREATE = 10


@contextmanager
def suppress_dimension_input(sw):
    """Disable the modal Modify dialog during automation, then restore the user setting.

    SOLIDWORKS AddDimension2 / AddDiameterDimension2 can block inside the COM
    call while this option is enabled. Verify the option before creating CAD.
    """
    original = bool(sw.GetUserPreferenceToggle(SW_INPUT_DIM_VAL_ON_CREATE))
    try:
        sw.SetUserPreferenceToggle(SW_INPUT_DIM_VAL_ON_CREATE, False)
        if sw.GetUserPreferenceToggle(SW_INPUT_DIM_VAL_ON_CREATE):
            raise RuntimeError("Cannot disable swInputDimValOnCreate; refusing interactive dimensioning")
        yield
    finally:
        sw.SetUserPreferenceToggle(SW_INPUT_DIM_VAL_ON_CREATE, original)
        if bool(sw.GetUserPreferenceToggle(SW_INPUT_DIM_VAL_ON_CREATE)) != original:
            raise RuntimeError("Unable to restore swInputDimValOnCreate to its original value")

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

def dimension_info(display_dimension, expected_mm, key, magnitude=False):
    if display_dimension is None:
        raise RuntimeError(f"Driving dimension {key} was not created")
    dimension = display_dimension.GetDimension2(0)
    if dimension is None:
        raise RuntimeError(f"Model dimension for {key} is missing")
    value = float(com_read(dimension, "SystemValue")) * 1000
    if magnitude:
        value = abs(value)
    if not math.isfinite(value) or abs(value - expected_mm) > 0.01:
        raise RuntimeError(
            f"Dimension {key} measured {value:.6f} mm; expected {expected_mm:.6f}")
    full_name = str(com_read(dimension, "FullName"))
    if not full_name or "@" not in full_name:
        raise RuntimeError(f"Dimension {key} has no stable model name")
    return {"role": key, "dimension": full_name, "mm": round(value, 6),
            "driving_dimension_created": True}


def add_circle_position_dimensions(model, circle, profile):
    """Locate the center against the actual model origin, without fixing it.

    Nonzero coordinates use horizontal/vertical driving dimensions; zero
    coordinates use point relations so no zero-length dimension is created.
    The origin feature is located by type, independent of UI language/name.
    """
    sketch = com_read(model, "GetActiveSketch2")
    if read_status(sketch) == SW_FULLY_DEFINED:
        return []  # For example, an origin-centered circle already coincident.
    feature = find_feature(model, "OriginProfileFeature")
    if feature is None:
        raise RuntimeError("Cannot find the model origin feature for circle positioning")
    origin_sketch = com_read(feature, "GetSpecificFeature2")
    points = com_read(origin_sketch, "GetSketchPoints2") if origin_sketch is not None else None
    if not isinstance(points, (list, tuple)) or len(points) != 1:
        raise RuntimeError("Expected one actual origin sketch point")
    origin = points[0]
    center = com_read(circle, "GetCenterPoint2")
    if center is None:
        raise RuntimeError("Circle center point is unavailable for positioning")
    data = create_select_data(model)

    def select_points():
        model.ClearSelection2(True)
        if not origin.Select4(False, data) or not center.Select4(True, data):
            raise RuntimeError("Cannot select origin and circle center for positional constraints")

    cx, cy = profile["cx_mm"], profile["cy_mm"]
    dimensions = []
    try:
        if cx == 0 and cy == 0:
            select_points()
            print("[SW] circle center: coincident with model origin", flush=True)
            model.SketchAddConstraints("sgCOINCIDENT")
            return dimensions
        for axis, coordinate in (("x", cx), ("y", cy)):
            # Do not add duplicate constraints after an existing infer relation
            # plus the first dimension has already defined the circle.
            if read_status(sketch) == SW_FULLY_DEFINED:
                break
            select_points()
            if coordinate == 0:
                relation = "sgVERTPOINTS2D" if axis == "x" else "sgHORIZONTALPOINTS2D"
                print(f"[SW] circle center {axis}=0 mm: {relation} relative to origin", flush=True)
                model.SketchAddConstraints(relation)
            else:
                print(f"[SW] circle center {axis}={coordinate} mm: create driving dimension from origin", flush=True)
                if axis == "x":
                    display = model.AddHorizontalDimension2(cx / 2000, cy / 1000 + .012, 0)
                else:
                    display = model.AddVerticalDimension2(cx / 1000 + .012, cy / 2000, 0)
                item = dimension_info(display, abs(coordinate), f"center_{axis}", magnitude=True)
                # Dimension magnitudes are positive; geometry verification checks
                # the requested signed side of the origin independently.
                item["coordinate_mm"] = coordinate
                dimensions.append(item)
        return dimensions
    finally:
        model.ClearSelection2(True)

def create_select_data(model):
    """Use the Automation property, without invoking a returned COM interface.

    In late binding, CreateSelectData may already be evaluated by getattr.
    Calling that CDispatch again invokes its default member, NOT the factory.
    ISelectionManager is not used: reading it fails on the target workstation.
    """
    manager = com_read(model, "SelectionManager")
    if manager is None:
        raise RuntimeError("SelectionManager returned None")
    select_data = com_read(manager, "CreateSelectData")
    if select_data is None:
        raise RuntimeError("CreateSelectData returned None")
    select_data.Mark = 0
    return select_data


def select_segment(model, segment):
    """Select exactly one segment at mark zero; return the successful API path.

    Select2 is obsolete but avoids the ISelectData argument that is problematic
    with late-bound SW 2023. Keep Select4 as a fallback for other bindings.
    """
    errors = []
    for method in ("Select2", "Select4"):
        model.ClearSelection2(True)
        try:
            if method == "Select2":
                selected = segment.Select2(False, 0)
            else:
                selected = segment.Select4(False, create_select_data(model))
            if not selected:
                raise RuntimeError("returned False")
            return method
        except Exception as exc:
            errors.append(f"{method}: {type(exc).__name__}: {exc}")
    model.ClearSelection2(True)
    raise RuntimeError("Failed to select a sketch segment for a driving dimension; "
                       + " | ".join(errors))

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
        info.extend(add_circle_position_dimensions(model, created, profile))
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

def fully_define_or_fail(model, sketch_manager, strict=True, auto_define=True):
    # Must execute before leaving sketch-edit mode.
    sketch = com_read(model, "GetActiveSketch2")
    status = read_status(sketch)
    if status == 2 and strict and auto_define:
        model.ClearSelection2(True)
        # Signature positions 6 and 8 are object references (HorizontalDatumDisp
        # and VerticalDatumDisp). Python None can become VT_NULL in late binding,
        # unlike VBA Nothing. Explicitly marshal NULL IDispatch references.
        import pythoncom
        from win32com.client import VARIANT
        horizontal_datum = VARIANT(pythoncom.VT_DISPATCH, None)
        vertical_datum = VARIANT(pythoncom.VT_DISPATCH, None)
        print("[SW] FullyDefineSketch: datum parameters 6/8 = VT_DISPATCH(null)", flush=True)
        try:
            advisory = sketch_manager.FullyDefineSketch(
                True, True, 3, True, 1, horizontal_datum, 1, vertical_datum, 1, 1)
            print(f"[SW] FullyDefineSketch returned {advisory!r}; checking actual sketch status", flush=True)
        finally:
            model.ClearSelection2(True)
        status = read_status(sketch)
    if status not in (2, 3):
        raise RuntimeError(f"Invalid sketch constraints: {STATUS[status]} (code={status})")
    if strict and status != 3:
        raise RuntimeError(
            "Sketch remains under-defined after dimensioning; refusing to save")
    return {"status_code": status, "status": STATUS[status],
            "fully_defined": status == 3}


def verify_circle_geometry(segment, profile):
    """Check circle coordinates in sketch space after the constraint solver ran.

    A full-definition status alone does not prove the requested hole location.
    Do not silently fix/move entities or accept a different solved position.
    """
    center = com_read(segment, "GetCenterPoint2")
    if center is None:
        raise RuntimeError("Unable to read the constrained circle center")
    actual = {"cx_mm": float(com_read(center, "X")) * 1000,
              "cy_mm": float(com_read(center, "Y")) * 1000,
              "radius_mm": float(com_read(segment, "GetRadius")) * 1000}
    for key, value in actual.items():
        if not math.isfinite(value) or abs(value - profile[key]) > 0.01:
            raise RuntimeError(f"Constrained circle {key}={value:.6f} mm; expected {profile[key]:.6f}; refusing to save")
    return {"checked": True, **{key: round(value, 6) for key, value in actual.items()}}
