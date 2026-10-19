"""Read-only Windows B COM probe for the two official selection manager properties.

Open SolidWorks and activate any part/assembly document before running:
    py -3 .\\windows-b\\probe_selection_manager.py

Does not create CAD documents or modify existing model data.
"""
import pythoncom
import win32com.client


def main():
    pythoncom.CoInitialize()
    try:
        sw = win32com.client.GetActiveObject("SldWorks.Application")
        model = sw.ActiveDoc
        if model is None:
            print("Open or activate a SolidWorks part before running this probe.")
            return
        for name in ("ISelectionManager", "SelectionManager"):
            print("PROBING", name)
            try:
                manager = getattr(model, name)
                print("  Manager type:", type(manager).__name__)
                member = getattr(manager, "CreateSelectData")
                data = member() if callable(member) else member
                if data is None:
                    print("  FAILED: CreateSelectData returned None")
                else:
                    print("  SUCCESS: data type:", type(data).__name__)
            except Exception as exc:
                print("  ERROR:", type(exc).__name__, str(exc)[:500])
    finally:
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    main()
