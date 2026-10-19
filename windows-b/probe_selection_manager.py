"""Windows B COM probe; read-only by default.

Open SolidWorks and activate any part/assembly document before running:
    py -3 .\\windows-b\\probe_selection_manager.py

With --select-test, creates a NEW UNSAVED part and tests line/circle selection.
Leaves that document open for inspection; never saves or edits existing parts.
"""
import argparse
import os
from pathlib import Path

from solidworks_box import com_read, find_feature
from sw_constraints import create_select_data, select_segment


def probe_manager(model):
    print("PROBING SelectionManager.CreateSelectData (COM-aware read)")
    data = create_select_data(model)
    print("  SUCCESS: data type:", type(data).__name__, "mark:", com_read(data, "Mark"))


def probe_segments(sw, template):
    if not Path(template).is_file():
        raise FileNotFoundError(f"Part template missing: {template}")
    model = sw.NewDocument(str(Path(template).resolve()), 0, 0.0, 0.0)
    if model is None:
        raise RuntimeError("NewDocument returned None")
    print("NEW UNSAVED test part:", com_read(model, "GetTitle"))
    plane = find_feature(model, "RefPlane")
    if plane is None or not plane.Select2(False, 0):
        raise RuntimeError("Cannot select test reference plane")
    sketch_mgr = model.SketchManager
    sketch_mgr.InsertSketch(True)
    try:
        rectangle = sketch_mgr.CreateCenterRectangle(0, 0, 0, 0.05, 0.03, 0)
        if not isinstance(rectangle, (list, tuple)):
            raise RuntimeError("CreateCenterRectangle returned no segment array")
        edges = [s for s in rectangle if not com_read(s, "ConstructionGeometry")]
        if len(edges) != 4:
            raise RuntimeError(f"Expected 4 rectangle edges, got {len(edges)}")
        circle = sketch_mgr.CreateCircleByRadius(0.08, 0, 0, 0.015)
        if circle is None:
            raise RuntimeError("CreateCircleByRadius returned None")
        for label, segment in [(f"edge {i}", s) for i, s in enumerate(edges, 1)] + [("circle", circle)]:
            method = select_segment(model, segment)
            print(f"  SUCCESS: {label} selected via {method}(mark=0)")
        print("SELECTION TEST PASSED (dimensioning/full definition NOT tested)")
    finally:
        model.ClearSelection2(True)
        sketch_mgr.InsertSketch(True)
        print("Test part left open and unsaved for inspection.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--select-test", action="store_true",
                        help="Create a new unsaved part to test rectangle/circle selection")
    parser.add_argument("--template", default=os.environ.get(
        "REMOTE_B_PART_TEMPLATE",
        r"C:\ProgramData\SolidWorks\SOLIDWORKS 2023\templates\gb_part.prtdot"))
    args = parser.parse_args()
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    try:
        sw = win32com.client.GetActiveObject("SldWorks.Application")
        if args.select_test:
            # Independent of the optional manager path: Select2 needs no manager.
            probe_segments(sw, args.template)
        else:
            model = com_read(sw, "ActiveDoc")
            if model is None:
                raise RuntimeError("Open or activate a SolidWorks document before running this probe")
            try:
                probe_manager(model)
            except Exception as exc:
                print("  ERROR:", type(exc).__name__, str(exc)[:1500])
                print("Select2 can still work; run --select-test to verify it separately.")
                return 1
        return 0
    except Exception as exc:
        print("ERROR:", type(exc).__name__, str(exc)[:1500])
        return 1
    finally:
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    raise SystemExit(main())
