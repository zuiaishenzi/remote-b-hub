"""Regression tests for pywin32 COM members exported as properties or methods.

Run: py -3 -m unittest discover -s tests -p test_sw_constraints.py -v
No SOLIDWORKS installation or COM server required.
"""
import sys
import unittest
from unittest.mock import Mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "windows-b"))
from sw_constraints import add_explicit_dimensions, create_select_data, select_segment
from solidworks_box import com_read


class MockDimension:
    def __init__(self, meters, name):
        self.SystemValue = meters
        self.FullName = name


class MockDisplayDimension:
    def __init__(self, meters, name):
        self.dimension = MockDimension(meters, name)

    def GetDimension2(self, _):
        return self.dimension


class MockSelectData:
    def __init__(self):
        self.Mark = None


class CallableDispatchData(MockSelectData):
    """Like CDispatch: callable, but __call__ invokes an unrelated DISPID_VALUE."""
    _oleobj_ = object()

    def __call__(self):
        raise AssertionError("Must not invoke the returned COM interface")


class MockSelectionManager:
    def __init__(self):
        self.created = []

    def CreateSelectData(self):
        value = MockSelectData()
        self.created.append(value)
        return value


class MockModel:
    def __init__(self, expected_meters):
        self.values = iter(expected_meters)
        self.index = 0
        self.SelectionManager = MockSelectionManager()
        self.ISelectionManager = MockSelectionManager()

    def ClearSelection2(self, _):
        return True

    def AddDimension2(self, x, y, z):
        self.index += 1
        return MockDisplayDimension(next(self.values), f"D{self.index}@Sketch1")


class PropertyLengthSegment:
    ConstructionGeometry = False

    def __init__(self, meters):
        self.GetLength = meters

    def Select4(self, append, data):
        if append is not False or not isinstance(data, MockSelectData):
            raise TypeError("Select4 requires a real SelectData object")
        if data.Mark != 0:
            raise ValueError("Dimensions should use selection mark zero")
        return True


class MethodLengthSegment:
    ConstructionGeometry = False

    def __init__(self, meters):
        self.meters = meters

    def GetLength(self):
        return self.meters

    def Select4(self, append, data):
        if append is not False or not isinstance(data, MockSelectData):
            raise TypeError("Select4 requires a real SelectData object")
        if data.Mark != 0:
            raise ValueError("Dimensions should use selection mark zero")
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
        self.assertEqual(len(model.SelectionManager.created), 2)
        self.assertEqual(len(model.ISelectionManager.created), 0)

    def test_com_get_length_as_property(self):
        self.check_geometry(PropertyLengthSegment)

    def test_com_get_length_as_method(self):
        self.check_geometry(MethodLengthSegment)

    def test_uses_automation_selection_manager(self):
        model = MockModel([])
        del model.ISelectionManager
        data = create_select_data(model)
        self.assertEqual(data.Mark, 0)
        self.assertEqual(len(model.SelectionManager.created), 1)

    def test_does_not_read_unsupported_i_selection_manager(self):
        class TargetModel(MockModel):
            @property
            def ISelectionManager(self):
                raise AssertionError("Cannot read write-only property")

            @ISelectionManager.setter
            def ISelectionManager(self, value):
                pass

        data = create_select_data(TargetModel([]))
        self.assertEqual(data.Mark, 0)

    def test_create_select_data_as_callable_com_property(self):
        model = MockModel([])
        data_property = CallableDispatchData()
        model.SelectionManager.CreateSelectData = data_property
        data = create_select_data(model)
        self.assertIs(data, data_property)
        self.assertEqual(data.Mark, 0)

    def test_select2_skips_broken_manager(self):
        model = Mock(ClearSelection2=Mock())
        segment = Mock(Select2=Mock(return_value=True))
        self.assertEqual(select_segment(model, segment), "Select2")
        segment.Select2.assert_called_once_with(False, 0)
        segment.Select4.assert_not_called()
        self.assertNotIn("SelectionManager", model._mock_children)
        model.ClearSelection2.assert_called_once_with(True)

    def test_select2_false_or_error_falls_back_to_select4(self):
        for failure in (False, OSError("Member not found")):
            with self.subTest(failure=failure):
                model = MockModel([])
                model.ClearSelection2 = Mock()
                segment = PropertyLengthSegment(0.06)
                segment.Select2 = Mock(return_value=False)
                if isinstance(failure, Exception):
                    segment.Select2.side_effect = failure
                self.assertEqual(select_segment(model, segment), "Select4")
                self.assertEqual(model.ClearSelection2.call_count, 2)

    def test_selection_failure_preserves_both_errors_and_clears_selection(self):
        model = MockModel([])
        model.ClearSelection2 = Mock()
        model.SelectionManager.CreateSelectData = Mock(spec=lambda: None, side_effect=OSError("factory failed"))
        segment = Mock(Select2=Mock(side_effect=OSError("Select2 unavailable")))
        with self.assertRaisesRegex(RuntimeError, "Select2:.*Select2 unavailable.*Select4:.*factory failed"):
            select_segment(model, segment)
        self.assertEqual(model.ClearSelection2.call_count, 3)
        segment.Select4.assert_not_called()

    def test_select4_false_is_not_success(self):
        model = MockModel([])
        segment = PropertyLengthSegment(0.06)
        segment.Select4 = Mock(return_value=False)
        with self.assertRaisesRegex(RuntimeError, "Select4:.*returned False"):
            select_segment(model, segment)

    def test_none_select_data_is_rejected(self):
        model = MockModel([])
        model.SelectionManager.CreateSelectData = Mock(spec=lambda: None, return_value=None)
        with self.assertRaisesRegex(RuntimeError, "CreateSelectData returned None"):
            create_select_data(model)

    def test_com_read_preserves_dispatch_without_invoking_default_member(self):
        data = CallableDispatchData()
        self.assertIs(com_read(type("Owner", (), {"value": data})(), "value"), data)

    def test_com_read_calls_real_python_method_once(self):
        factory = Mock(spec=lambda: None, return_value=CallableDispatchData())
        owner = type("Owner", (), {})()
        owner.value = factory
        self.assertIs(com_read(owner, "value"), factory.return_value)
        factory.assert_called_once_with()

    def test_circle_dimension_uses_select2_without_manager(self):
        model = MockModel([0.03])
        model.AddDiameterDimension2 = model.AddDimension2
        model.SelectionManager = None
        segment = PropertyLengthSegment(0.03)
        segment.Select2 = Mock(return_value=True)
        dimensions = add_explicit_dimensions(model, None, {
            "type": "circle", "cx_mm": 0, "cy_mm": 0, "radius_mm": 15}, segment)
        self.assertEqual(dimensions[0]["role"], "diameter")
        self.assertEqual(dimensions[0]["mm"], 30)
        segment.Select2.assert_called_once_with(False, 0)

    def test_failed_selection_does_not_create_dimension(self):
        model = MockModel([])
        segment = PropertyLengthSegment(0.03)
        segment.Select4 = Mock(return_value=False)
        model.AddDiameterDimension2 = Mock()
        with self.assertRaisesRegex(RuntimeError, "Failed to select"):
            add_explicit_dimensions(model, None, {
                "type": "circle", "cx_mm": 0, "cy_mm": 0, "radius_mm": 15}, segment)
        model.AddDiameterDimension2.assert_not_called()

    def test_select4_rejects_missing_select_data(self):
        segment = PropertyLengthSegment(0.06)
        with self.assertRaises(TypeError):
            segment.Select4(False, None)


if __name__ == "__main__":
    unittest.main()
