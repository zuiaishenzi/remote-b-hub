"""Strict shared schema for SolidWorks recipe operations. No arbitrary COM commands."""
import math
import re

NAME = re.compile(r"^[A-Za-z0-9_-]{1,50}$")
PLANE = {"front", "top", "right"}
SELECT_TYPE = {"PLANE", "FACE", "AXIS"}
MATES = {"coincident", "concentric", "parallel", "perpendicular", "distance", "angle"}
ALIGN = {"aligned", "anti_aligned", "closest"}

def obj(value, keys, required=None):
    if type(value) is not dict:
        raise ValueError("Expected an object")
    if not set(value).issubset(keys) or not set(required or ()).issubset(value):
        raise ValueError("Invalid/missing keys; expected " + ", ".join(sorted(keys)))

def name(value, what="name"):
    if type(value) is not str or not NAME.fullmatch(value):
        raise ValueError(f"{what} must match [A-Za-z0-9_-] and be 1-50 characters")

def number(value, what, low=-500.0, high=500.0):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{what} must be finite and in [{low}, {high}] mm")

def text(value, what):
    if type(value) is not str or not 1 <= len(value) <= 100 or any(x in value for x in ("@", "/", "\\", ":", "\n", "\r")):
        raise ValueError(f"{what} is invalid")

def validate_recipe(recipe):
    obj(recipe, {"doc_type", "name", "operations", "components", "mates"},
        {"doc_type", "name"})
    name(recipe["name"])
    kind = recipe["doc_type"]
    if kind == "part":
        obj(recipe, {"doc_type", "name", "operations", "allow_underdefined"}, {"doc_type", "name", "operations"})
        if "allow_underdefined" in recipe and type(recipe["allow_underdefined"]) is not bool:
            raise ValueError("allow_underdefined must be a boolean")
        ops = recipe["operations"]
        if type(ops) is not list or not 1 <= len(ops) <= 12:
            raise ValueError("Part must have 1-12 operations")
        for index, op in enumerate(ops):
            obj(op, {"op", "plane", "profile", "depth_mm", "reverse"},
                {"op", "plane", "profile", "depth_mm"})
            if op["op"] not in {"boss_extrude", "cut_extrude"}:
                raise ValueError("Unknown part operation")
            if index == 0 and op["op"] != "boss_extrude":
                raise ValueError("First operation must be boss_extrude")
            if op["plane"] not in PLANE:
                raise ValueError("plane must be front/top/right")
            number(op["depth_mm"], "depth_mm", 0.1, 500)
            if "reverse" in op and type(op["reverse"]) is not bool:
                raise ValueError("reverse must be bool")
            profile = op["profile"]
            if type(profile) is not dict or "type" not in profile:
                raise ValueError("Missing profile")
            ptype = profile["type"]
            if ptype == "rectangle":
                obj(profile, {"type", "cx_mm", "cy_mm", "width_mm", "height_mm"},
                    {"type", "cx_mm", "cy_mm", "width_mm", "height_mm"})
                for key in ("cx_mm", "cy_mm"):
                    number(profile[key], key)
                for key in ("width_mm", "height_mm"):
                    number(profile[key], key, 0.1, 500)
            elif ptype == "circle":
                obj(profile, {"type", "cx_mm", "cy_mm", "radius_mm"},
                    {"type", "cx_mm", "cy_mm", "radius_mm"})
                for key in ("cx_mm", "cy_mm"):
                    number(profile[key], key)
                number(profile["radius_mm"], "radius_mm", 0.05, 250)
            elif ptype == "polygon":
                obj(profile, {"type", "points_mm"}, {"type", "points_mm"})
                points = profile["points_mm"]
                if type(points) is not list or not 3 <= len(points) <= 512:
                    raise ValueError("polygon requires 3-512 vertices")
                for p in points:
                    if type(p) is not list or len(p) != 2:
                        raise ValueError("polygon vertices must be [x,y]")
                    for v in p:
                        number(v, "polygon vertex")
                if points[0] == points[-1]:
                    raise ValueError("Do not repeat first vertex")
            else:
                raise ValueError("Unknown profile type")
    elif kind == "assembly":
        obj(recipe, {"doc_type", "name", "components", "mates"},
            {"doc_type", "name", "components"})
        comps = recipe["components"]
        if type(comps) is not list or not 1 <= len(comps) <= 20:
            raise ValueError("Assembly must include 1-20 components")
        ids = set()
        for comp in comps:
            obj(comp, {"id", "file", "position_mm"}, {"id", "file", "position_mm"})
            name(comp["id"], "component id")
            filename = comp["file"]
            if type(filename) is not str or not filename.endswith(".SLDPRT"):
                raise ValueError("Component file must end in .SLDPRT")
            name(filename[:-7], "component filename")
            position = comp["position_mm"]
            if type(position) is not list or len(position) != 3:
                raise ValueError("position_mm must be [x,y,z]")
            for v in position:
                number(v, "component position")
            if comp["id"] in ids:
                raise ValueError("Duplicate component id")
            ids.add(comp["id"])
        mates = recipe.get("mates", [])
        if type(mates) is not list or len(mates) > 40:
            raise ValueError("At most 40 mates")
        for mate in mates:
            obj(mate, {"type", "a", "b", "align", "value", "flip"},
                {"type", "a", "b"})
            if mate["type"] not in MATES:
                raise ValueError("Unknown mate type")
            if "align" in mate and mate["align"] not in ALIGN:
                raise ValueError("Unknown alignment")
            if "flip" in mate and type(mate["flip"]) is not bool:
                raise ValueError("flip must be bool")
            if mate["type"] in {"distance", "angle"}:
                if "value" not in mate:
                    raise ValueError("distance/angle requires value")
                number(mate["value"], "mate value", -360, 500)
            elif "value" in mate:
                raise ValueError("Mate value only for distance/angle")
            for side in ("a", "b"):
                sel = mate[side]
                obj(sel, {"component", "plane", "entity_name", "entity_type"},
                    {"component"})
                if sel["component"] not in ids:
                    raise ValueError("Unknown component reference")
                if ("plane" in sel) == ("entity_name" in sel):
                    raise ValueError("Specify either plane or entity_name")
                if "plane" in sel and (sel["plane"] not in PLANE or "entity_type" in sel):
                    raise ValueError("Invalid plane selector")
                if "entity_name" in sel:
                    text(sel["entity_name"], "entity_name")
                    if sel.get("entity_type") not in SELECT_TYPE:
                        raise ValueError("entity_type must be PLANE/FACE/AXIS")
    else:
        raise ValueError("doc_type must be part or assembly")
    return recipe
