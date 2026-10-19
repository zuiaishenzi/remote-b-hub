"""Test the production strict part recipe on Windows B / SOLIDWORKS.

Creates a NEW part and saves it only after the production constraint/rebuild
checks pass. Each run uses a unique filename; existing CAD files are not edited.
Run rectangle first, then circle. Failures leave the new document open.
"""
import argparse
from datetime import datetime
import json
import os
import time
import traceback
import uuid


def make_recipe(profile, cx_mm=None, cy_mm=None):
    if profile == "rectangle":
        geometry = {"type": "rectangle", "cx_mm": 0, "cy_mm": 0,
                    "width_mm": 100, "height_mm": 60}
        depth = 10
    elif profile in ("circle", "offset-circle"):
        geometry = {"type": "circle", "cx_mm": 20 if profile == "offset-circle" else 0,
                    "cy_mm": 12 if profile == "offset-circle" else 0,
                    "radius_mm": 4 if profile == "offset-circle" else 15}
        depth = 10 if profile == "offset-circle" else 60
    else:
        raise ValueError(f"Unsupported profile: {profile}")
    if cx_mm is not None:
        geometry["cx_mm"] = cx_mm
    if cy_mm is not None:
        geometry["cy_mm"] = cy_mm
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return {"doc_type": "part",
            "name": f"Probe_{profile}_{stamp}_{uuid.uuid4().hex[:8]}",
            # Omit allow_underdefined: production defaults to strict=True.
            "operations": [{"op": "boss_extrude", "plane": "front",
                            "profile": geometry, "depth_mm": depth}]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, choices=("rectangle", "circle", "offset-circle"))
    parser.add_argument("--cx-mm", type=float, help="Override sketch center X (mm)")
    parser.add_argument("--cy-mm", type=float, help="Override sketch center Y (mm)")
    parser.add_argument("--template", help="Override REMOTE_B_PART_TEMPLATE")
    parser.add_argument("--output-dir", help="Override REMOTE_B_OUTPUT_DIR")
    args = parser.parse_args()
    if args.template:
        os.environ["REMOTE_B_PART_TEMPLATE"] = args.template
    if args.output_dir:
        os.environ["REMOTE_B_OUTPUT_DIR"] = args.output_dir
    recipe = make_recipe(args.profile, args.cx_mm, args.cy_mm)
    print("STRICT PARAMETRIC PART TEST", flush=True)
    print("Creates a new part; saves only after production checks pass.", flush=True)
    print("Recipe:", json.dumps(recipe, ensure_ascii=False), flush=True)
    started = time.monotonic()
    try:
        # Import after optional overrides so the executor uses the chosen paths.
        from sw_recipe import execute_recipe, OUTPUT_DIR
        from desktop_version import runtime_info
        print("Executor:", json.dumps(runtime_info(), ensure_ascii=False), flush=True)
        print("Output directory:", OUTPUT_DIR, flush=True)
        result = execute_recipe(recipe)
        print("RESULT:", json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        if result.get("all_sketches_fully_defined") is not True or result.get("rebuild_ok") is not True:
            raise RuntimeError("Production result did not confirm full definition and rebuild")
        print(f"PARAMETRIC TEST PASSED ({time.monotonic() - started:.1f}s)", flush=True)
        print("Inspect driving dimensions and extrusion depth in SOLIDWORKS.", flush=True)
        return 0
    except Exception:
        print(f"PARAMETRIC TEST FAILED ({time.monotonic() - started:.1f}s)", flush=True)
        traceback.print_exc()
        print("Keep the full traceback. The new document may remain open; do not retry by changing dimensions.", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
