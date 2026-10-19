"""Regression tests for pywin32 COM members exported as properties or methods.

Run: py -3 -m unittest discover -s tests -p test_sw_constraints.py -v
No SOLIDWORKS installation or COM server required.
"""
import sys
import unittest
from unittest.mock import Mock, patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "windows-b"))
from sw_constraints import (add_explicit_dimensions, create_select_data, select_segment, fully_define_or_fail,
                            verify_circle_geometry, add_circle_position_dimensions,
                            suppress_dimension_input, SW_INPUT_DIM_VAL_ON_CREATE)
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
        with patch("sw_constraints.add_circle_position_dimensions", return_value=[]):
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


class DimensionDialogRegressionTests(unittest.TestCase):
    def application(self, original=True):
        sw = Mock()
        sw.state = original
        sw.GetUserPreferenceToggle.side_effect = lambda option: sw.state
        def set_value(option, value):
            self.assertEqual(option, SW_INPUT_DIM_VAL_ON_CREATE)
            sw.state = value
            return True
        sw.SetUserPreferenceToggle.side_effect = set_value
        return sw

    def test_disable_then_restore_original_true_or_false(self):
        for original in (True, False):
            with self.subTest(original=original):
                sw = self.application(original)
                with suppress_dimension_input(sw):
                    self.assertIs(sw.state, False)
                self.assertIs(sw.state, original)

    def test_restore_after_com_failure(self):
        sw = self.application()
        with self.assertRaisesRegex(OSError, "dimension failed"):
            with suppress_dimension_input(sw):
                raise OSError("dimension failed")
        self.assertIs(sw.state, True)

    def test_do_not_enter_body_if_disable_was_ignored(self):
        sw = self.application()
        sw.SetUserPreferenceToggle.side_effect = None
        body = Mock()
        with self.assertRaisesRegex(RuntimeError, "Cannot disable"):
            with suppress_dimension_input(sw):
                body()
        body.assert_not_called()

    def test_failed_restore_is_reported(self):
        sw = self.application()
        sw.SetUserPreferenceToggle.side_effect = lambda option, value: setattr(sw, "state", False)
        with self.assertRaisesRegex(RuntimeError, "Unable to restore"):
            with suppress_dimension_input(sw):
                self.assertIs(sw.state, False)

    def test_production_part_build_is_guarded(self):
        from sw_recipe import build_part
        sw = self.application()
        def build(app, recipe, path):
            self.assertIs(app.state, False)
            return {"rebuild_ok": True}
        with patch("sw_recipe._build_part", side_effect=build):
            self.assertEqual(build_part(sw, {}, None), {"rebuild_ok": True})
        self.assertIs(sw.state, True)

    def test_production_failure_also_restores_setting(self):
        from sw_recipe import build_part
        sw = self.application()
        with patch("sw_recipe._build_part", side_effect=OSError("build failed")):
            with self.assertRaisesRegex(OSError, "build failed"):
                build_part(sw, {}, None)
        self.assertIs(sw.state, True)


class FullyDefineRegressionTests(unittest.TestCase):
    def model_and_manager(self, statuses):
        class Sketch:
            def GetConstrainedStatus(self):
                return next(self.statuses)
        sketch = Sketch()
        sketch.statuses = iter(statuses)
        model = type("Model", (), {})()
        model.GetActiveSketch2 = sketch
        model.ClearSelection2 = Mock()
        manager = type("Manager", (), {})()
        manager.FullyDefineSketch = Mock(return_value=0)
        return model, manager

    def com_types(self):
        try:
            import pythoncom
            from win32com.client import VARIANT
            return pythoncom, VARIANT
        except ImportError:
            self.skipTest("pywin32 is required for real VARIANT argument regression")

    def test_real_variant_nulls_are_passed_in_positions_six_and_eight(self):
        pythoncom, _ = self.com_types()
        model, manager = self.model_and_manager([2, 3])
        self.assertTrue(fully_define_or_fail(model, manager)["fully_defined"])
        args = manager.FullyDefineSketch.call_args.args
        self.assertEqual(len(args), 10)
        for index in (5, 7):
            self.assertEqual(args[index].varianttype, pythoncom.VT_DISPATCH)
            self.assertIsNone(args[index].value)
        self.assertEqual((args[:5], args[6], args[8:]), ((True, True, 3, True, 1), 1, (1, 1)))
        self.assertEqual(manager.FullyDefineSketch.call_count, 1)

    def test_successful_api_return_does_not_override_underdefined_status(self):
        self.com_types()
        model, manager = self.model_and_manager([2, 2])
        with self.assertRaisesRegex(RuntimeError, "remains under-defined"):
            fully_define_or_fail(model, manager)
        self.assertEqual(manager.FullyDefineSketch.call_count, 1)

    def test_api_exception_is_not_retried_and_selection_is_cleared(self):
        self.com_types()
        model, manager = self.model_and_manager([2])
        manager.FullyDefineSketch.side_effect = OSError("type mismatch")
        with self.assertRaisesRegex(OSError, "type mismatch"):
            fully_define_or_fail(model, manager)
        self.assertEqual(manager.FullyDefineSketch.call_count, 1)
        self.assertEqual(model.ClearSelection2.call_count, 2)

    def test_already_defined_sketch_does_not_call_auto_definition(self):
        model, manager = self.model_and_manager([3])
        self.assertTrue(fully_define_or_fail(model, manager)["fully_defined"])
        manager.FullyDefineSketch.assert_not_called()

    def test_non_strict_does_not_invoke_auto_definition(self):
        model, manager = self.model_and_manager([2])
        self.assertFalse(fully_define_or_fail(model, manager, strict=False)["fully_defined"])
        manager.FullyDefineSketch.assert_not_called()

    def test_invalid_status_still_fails(self):
        model, manager = self.model_and_manager([4])
        with self.assertRaisesRegex(RuntimeError, "over_defined"):
            fully_define_or_fail(model, manager)
        manager.FullyDefineSketch.assert_not_called()

    def test_off_origin_circle_coordinates_are_checked_with_sign(self):
        for x, y in ((20, 0), (-20, 0), (20, 12)):
            with self.subTest(x=x, y=y):
                center = type("Point", (), {"X": x / 1000, "Y": y / 1000})()
                circle = type("Circle", (), {"GetCenterPoint2": center, "GetRadius": 0.004})()
                result = verify_circle_geometry(circle, {"cx_mm": x, "cy_mm": y, "radius_mm": 4})
                self.assertEqual((result["cx_mm"], result["cy_mm"]), (x, y))

    def test_solver_movement_radius_change_and_nan_are_rejected(self):
        for x, y, radius in ((0, 0, .004), (.02, .012, .005), (float("nan"), .012, .004)):
            center = type("Point", (), {"X": x, "Y": y})()
            circle = type("Circle", (), {"GetCenterPoint2": center, "GetRadius": radius})()
            with self.subTest(x=x, radius=radius), self.assertRaisesRegex(RuntimeError, "refusing to save"):
                verify_circle_geometry(circle, {"cx_mm": 20, "cy_mm": 12, "radius_mm": 4})


class CirclePositionRegressionTests(unittest.TestCase):
    def setup_geometry(self, x, y, status=2):
        from types import SimpleNamespace
        origin = SimpleNamespace(Select4=Mock(return_value=True))
        center = SimpleNamespace(Select4=Mock(return_value=True))
        circle = SimpleNamespace(GetCenterPoint2=center)
        sketch = SimpleNamespace(GetConstrainedStatus=status)
        feature = SimpleNamespace(GetSpecificFeature2=SimpleNamespace(GetSketchPoints2=(origin,)))
        model = MockModel([])
        model.GetActiveSketch2 = sketch
        model.SketchAddConstraints = Mock()
        model.AddHorizontalDimension2 = Mock(return_value=MockDisplayDimension(abs(x) / 1000, "D2@Sketch1"))
        model.AddVerticalDimension2 = Mock(return_value=MockDisplayDimension(abs(y) / 1000, "D3@Sketch1"))
        return model, circle, feature, origin, center

    def check_case(self, x, y):
        model, circle, feature, origin, center = self.setup_geometry(x, y)
        with patch("sw_constraints.find_feature", return_value=feature) as find:
            result = add_circle_position_dimensions(model, circle, {"cx_mm": x, "cy_mm": y})
        find.assert_called_once_with(model, "OriginProfileFeature")
        for call in origin.Select4.call_args_list:
            self.assertIs(call.args[0], False)
            self.assertEqual(call.args[1].Mark, 0)
        for call in center.Select4.call_args_list:
            self.assertIs(call.args[0], True)
        return model, result

    def test_positive_and_negative_x_on_axis(self):
        for x in (20, -20):
            with self.subTest(x=x):
                model, result = self.check_case(x, 0)
                self.assertEqual(result[0]["role"], "center_x")
                self.assertEqual(result[0]["coordinate_mm"], x)
                self.assertEqual(result[0]["mm"], 20)
                model.SketchAddConstraints.assert_called_once_with("sgHORIZONTALPOINTS2D")
                model.AddVerticalDimension2.assert_not_called()

    def test_y_axis_uses_vertical_distance_and_vertical_relation(self):
        model, result = self.check_case(0, -12)
        self.assertEqual(result[0]["role"], "center_y")
        self.assertEqual(result[0]["coordinate_mm"], -12)
        model.SketchAddConstraints.assert_called_once_with("sgVERTPOINTS2D")
        model.AddHorizontalDimension2.assert_not_called()

    def test_both_nonzero_coordinates_get_driving_dimensions(self):
        model, result = self.check_case(20, 12)
        self.assertEqual([item["role"] for item in result], ["center_x", "center_y"])
        model.SketchAddConstraints.assert_not_called()

    def test_origin_uses_coincidence_and_no_zero_dimensions(self):
        model, result = self.check_case(0, 0)
        self.assertEqual(result, [])
        model.SketchAddConstraints.assert_called_once_with("sgCOINCIDENT")
        model.AddHorizontalDimension2.assert_not_called()
        model.AddVerticalDimension2.assert_not_called()

    def test_already_fully_defined_circle_skips_duplicate_relations(self):
        model, circle, *_ = self.setup_geometry(0, 0, status=3)
        with patch("sw_constraints.find_feature") as find:
            self.assertEqual(add_circle_position_dimensions(model, circle, {"cx_mm": 0, "cy_mm": 0}), [])
        find.assert_not_called()

    def test_missing_origin_is_an_error(self):
        model, circle, *_ = self.setup_geometry(20, 0)
        with patch("sw_constraints.find_feature", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "model origin"):
                add_circle_position_dimensions(model, circle, {"cx_mm": 20, "cy_mm": 0})
        model.AddHorizontalDimension2.assert_not_called()

    def test_point_selection_failure_does_not_create_dimension(self):
        model, circle, feature, origin, _ = self.setup_geometry(20, 0)
        origin.Select4.return_value = False
        with patch("sw_constraints.find_feature", return_value=feature):
            with self.assertRaisesRegex(RuntimeError, "Cannot select"):
                add_circle_position_dimensions(model, circle, {"cx_mm": 20, "cy_mm": 0})
        model.AddHorizontalDimension2.assert_not_called()

    def test_circle_strict_check_never_falls_back_to_auto_definition(self):
        model, *_ = self.setup_geometry(20, 0)
        manager = Mock()
        with self.assertRaisesRegex(RuntimeError, "under-defined"):
            fully_define_or_fail(model, manager, strict=True, auto_define=False)
        manager.FullyDefineSketch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
