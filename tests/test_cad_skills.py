"""Planner contracts and negative acceptance tests; none simulate real CAD acceptance."""
import copy
import importlib.util
import math
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'windows-a'), str(ROOT / 'windows-b')]
import cad_skills as skills


class SkillTests(unittest.TestCase):
    def test_all_templates_compile_strict_contracts(self):
        for template, count in [('box', 1), ('cylinder', 1), ('tube', 2), ('two_hole_plate', 3)]:
            with self.subTest(template=template):
                plan = skills.plan_part(template, {}, 'Test_' + template)
                self.assertEqual(len(plan['recipe']['operations']), count)
                self.assertNotIn('allow_underdefined', plan['recipe'])
                self.assertGreater(plan['expected_volume_mm3'], 0)
                self.assertFalse(plan['volume_is_measured'])
                self.assertEqual(plan['applied_defaults'], skills.DEFAULTS[template])
                for operation in plan['recipe']['operations'][1:]:
                    self.assertIs(operation['reverse'], True)

    def test_bad_parameters_and_impossible_holes_are_rejected(self):
        cases = [('cylinder', {'radius_mm': x}) for x in [True, '10', math.nan, math.inf, 0, -1, 251]]
        cases += [('box', {'length_mm': 501}), ('box', {'script': 1}),
                  ('tube', {'inner_radius_mm': 15}),
                  ('two_hole_plate', {'hole_spacing_mm': 8}),
                  ('two_hole_plate', {'hole_spacing_mm': 95}),
                  ('two_hole_plate', {'hole_radius_mm': 30})]
        for template, params in cases:
            with self.subTest(template=template, params=params), self.assertRaises(ValueError):
                skills.plan_part(template, params, 'Test')
        with self.assertRaises(ValueError): skills.plan_part('box', {}, '../overwrite')

    def test_signed_offset_is_not_lost(self):
        plan = skills.plan_part('cylinder', {'cx_mm': -20, 'cy_mm': 12}, 'Offset')
        self.assertEqual(plan['recipe']['operations'][0]['profile']['cx_mm'], -20)
        self.assertEqual(plan['applied_defaults'], {'radius_mm': 10, 'depth_mm': 10})

    def test_failed_template_is_explicitly_blocked(self):
        self.assertFalse(skills.plan_part('two_hole_plate', {}, 'Draft')['execution_ready'])
        self.assertIn('BLOCKED', skills.catalog()['validation']['two_hole_plate'])

    def fixture(self):
        recipe = skills.plan_part('cylinder', {'cx_mm': 20}, 'Review')['recipe']
        return {'job_id': 'unit-test-fixture', 'operation': 'sw_recipe', 'status': 'done',
                'request': {'recipe': recipe}, 'result': {'ok': True, 'value': {
                    'saved': r'D:\output\Review.SLDPRT', 'bytes': 100, 'doc_type': 'part',
                    'rebuild_ok': True, 'all_sketches_fully_defined': True,
                    'features': [{'step': 1, 'op': 'boss_extrude', 'feature': 'Boss1'}],
                    'sketches': [{'step': 1, 'sketch': 'Sketch1', 'status_code': 3, 'fully_defined': True,
                                 'driving_dimensions': [{'role': 'diameter', 'mm': 20,
                                     'dimension': 'D1@Sketch1', 'driving_dimension_created': True}],
                                 'profile_geometry': {'checked': True, 'cx_mm': 20, 'cy_mm': 0, 'radius_mm': 10}}]}}}

    def review(self, job):
        return skills.review_part('cylinder', {'cx_mm': 20}, 'Review', job)

    def test_process_review_keeps_engineering_gaps_explicit(self):
        result = self.review(self.fixture())
        self.assertTrue(result['checks_passed'])
        self.assertFalse(result['engineering_validation_complete'])
        self.assertFalse(result['volume_is_measured'])
        self.assertTrue(result['unverified'])

    def test_success_flags_do_not_hide_missing_or_wrong_evidence(self):
        mutations = [lambda j: j.update(status='error'),
                     lambda j: j.update(request=None, operation='solidworks_status'),
                     lambda j: j['request']['recipe'].update(name='Other'),
                     lambda j: j['result']['value'].update(bytes=True),
                     lambda j: j['result']['value'].update(saved='Review.SLDPRT'),
                     lambda j: j['result']['value'].update(features=[]),
                     lambda j: j['result']['value'].update(sketches=[]),
                     lambda j: j['result']['value']['sketches'][0].update(status_code=2),
                     lambda j: j['result']['value']['sketches'][0].update(driving_dimensions=[]),
                     lambda j: j['result']['value']['sketches'][0]['driving_dimensions'][0].update(mm=21),
                     lambda j: j['result']['value']['sketches'][0]['profile_geometry'].update(cx_mm=-20),
                     lambda j: j['result']['value'].update(rebuild_ok=False)]
        for mutate in mutations:
            job = copy.deepcopy(self.fixture())
            mutate(job)
            self.assertFalse(self.review(job)['checks_passed'])

    def test_skills_are_bundled_and_fingerprinted(self):
        result = skills.catalog()
        self.assertEqual(len(result['skills']), 2)
        for skill in result['skills']:
            self.assertEqual(len(skill['sha256']), 64)
            self.assertIn('---', skill['instructions'])
        with self.assertRaises(ValueError): skills.catalog('../unreviewed')

    def test_install_is_idempotent_and_preserves_user_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            skills.install_project_skills(tmp)
            skills.install_project_skills(tmp)
            edited = Path(tmp)/'.agents/skills'/skills.SKILLS[0]/'SKILL.md'
            edited.write_text('User change', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Preserving edited'):
                skills.install_project_skills(tmp)
            self.assertEqual(edited.read_text(), 'User change')

    def test_mcp_tools_load_and_review_fetches_server_job(self):
        registry = {}
        class MCP:
            def __init__(self, name): pass
            def tool(self):
                def register(fn): registry[fn.__name__] = fn; return fn
                return register
        fake = types.ModuleType('mcp.server')
        fake.MCPServer = MCP
        exceptions = types.ModuleType('mcp.server.mcpserver.exceptions')
        exceptions.ToolError = ValueError
        spec = importlib.util.spec_from_file_location('skills_mcp_test', ROOT/'windows-a/mcp_bridge.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'mcp.server': fake,
            'mcp.server.mcpserver.exceptions': exceptions}), patch.dict(os.environ, {
            'REMOTE_B_API_URL': 'http://localhost', 'REMOTE_B_CLIENT_TOKEN': 'x'*40}):
            spec.loader.exec_module(module)
        self.assertEqual(len(registry['computer_b_modeling_skills']()['skills']), 2)
        self.assertEqual(registry['computer_b_plan_part']('box', {}, 'MCP')['recipe']['name'], 'MCP')
        with patch.object(module, 'request', return_value=self.fixture()) as fetch:
            result = registry['computer_b_review_part']('cylinder', {'cx_mm': 20}, 'Review',
                                                       '00000000-0000-0000-0000-000000000001')
            self.assertTrue(result['checks_passed'])
            fetch.assert_called_once_with('GET', '/api/jobs/00000000-0000-0000-0000-000000000001')


if __name__ == '__main__':
    unittest.main()
