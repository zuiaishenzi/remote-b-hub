"""Explicit sketch driving dimensions and fail-closed constraint checks.

SolidWorks 2023 / pywin32 COM: not yet validated on the target workstation.
"""
from contextlib import contextmanager
import math
from solidworks_box import com_read

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
