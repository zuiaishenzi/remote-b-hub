"""Regression tests for pywin32 COM members exported as properties or methods.

Run: py -3 -m unittest discover -s tests -p test_sw_constraints.py -v
No SOLIDWORKS installation or COM server required.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "windows-b"))
from sw_constraints import add_explicit_dimensions


class MockDimension:
    def __init__(self, meters, name):
        self.SystemValue = meters
        self.FullName = name


class MockDisplayDimension:
    def __init__(self, meters, name):
        self.dimension = MockDimension(meters, name)

    def GetDimension2(self, _):
        return self.dimension


class MockModel:
    def __init__(self, expected_meters):
        self.values = iter(expected_meters)
        self.index = 0

    def ClearSelection2(self, _):
        return True

    def AddDimension2(self, x, y, z):
        self.index += 1
        return MockDisplayDimension(next(self.values), f"D{self.index}@Sketch1")


class PropertyLengthSegment:
    ConstructionGeometry = False

    def __init__(self, meters):
        self.GetLength = meters

    def Select4(self, append, callout):
        return True


class MethodLengthSegment:
    ConstructionGeometry = False

    def __init__(self, meters):
        self.meters = meters

    def GetLength(self):
        return self.meters

    def Select4(self, append, callout):
        return True


class ConstraintLengthRegressionTests(unittest.TestCase):
    profile = {"type": "rectangle", "cx_mm": 0, "cy_mm": 0,
               "width_mm": 60, "height_mm": 40}

    def check_geometry(self, segment_type):
        segments = [segment_type(v) for v in (0.06, 0.04, 0.06, 0.04)]
        model = MockModel([0.06, 0.04])
        dimensions = add_explicit_dimensions(model, None, self.profile, segments)
        self.assertEqual([d["role"] for d in dimensions], ["width", "height"])
        self.assertEqual([d["mm"] for d in dimensions], [60.0, 40.0])
        self.assertEqual(model.index, 2)

    def test_com_get_length_as_property(self):
        self.check_geometry(PropertyLengthSegment)

    def test_com_get_length_as_method(self):
        self.check_geometry(MethodLengthSegment)


if __name__ == "__main__":
    unittest.main()
