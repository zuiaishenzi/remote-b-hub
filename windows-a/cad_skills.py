"""Reviewed SW2023 skills and deterministic plans; never executes third-party code."""
import hashlib
import math
from pathlib import Path, PureWindowsPath
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'windows-b'))
from sw_schema import validate_recipe

SKILLS = ('solidworks-2023-modeling', 'solidworks-2023-visual-check', 'solidworks-2023-interop')
DEFAULTS = {
    'box': {'length_mm': 100, 'width_mm': 60, 'height_mm': 10},
    'cylinder': {'radius_mm': 10, 'depth_mm': 10, 'cx_mm': 0, 'cy_mm': 0},
    'tube': {'outer_radius_mm': 15, 'inner_radius_mm': 10, 'depth_mm': 10},
    'two_hole_plate': {'length_mm': 100, 'width_mm': 60, 'thickness_mm': 10,
                       'hole_radius_mm': 4, 'hole_spacing_mm': 40},
}
VALIDATION = {
    'box': 'Saved/rebuilt in SW2023; later plate base exposed intermittent rectangle constraint failure.',
    'cylinder': 'Centered and offset circles saved/rebuilt with checked driving dimensions in SW2023.',
    'tube': 'Saved/rebuilt in SW2023 after one cut-direction revision; actual topology not measured.',
    'two_hole_plate': 'BLOCKED: base rectangle remained under-defined in B executor d0e93cce; not saved.',
}


def library_root():
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / 'skill-library'
    return Path(__file__).resolve().parents[1] / '.agents' / 'skills'


def catalog(skill=None):
    if skill is not None and skill not in SKILLS:
        raise ValueError('Unknown reviewed skill')
    entries = []
    for name in ((skill,) if skill else SKILLS):
        path = library_root() / name / 'SKILL.md'
        content = path.read_text(encoding='utf-8')
        references = path.parent / 'references'
        entry = {'name': name, 'sha256': hashlib.sha256(content.encode()).hexdigest(), 'instructions': content,
                 'references': [p.name for p in references.glob('*.md')]}
        if skill:
            entry['reference_contents'] = {p.name: p.read_text(encoding='utf-8') for p in references.glob('*.md')}
        entries.append(entry)
    return {'target': 'SOLIDWORKS 2023 (revision 31.x)', 'skills': entries,
            'templates': DEFAULTS, 'validation': VALIDATION, 'strict_constraints': True,
            'unsupported': ['exact involute gears', 'circular patterns', 'gear mechanical mates'],
            'assembly_mates': 'experimental; require real acceptance',
            'upstream_commit': '693386f5d76cca57ee3d80359c3b19128660366c',
            'angelsix_commit': '58787e2cefdcc03aebc15a51bd52ba151f3969d4'}


def plan_part(template, parameters, name):
    if template not in DEFAULTS or type(parameters) is not dict:
        raise ValueError('Unknown template or invalid parameters')
    defaults = DEFAULTS[template]
    if set(parameters) - set(defaults):
        raise ValueError('Unknown parameters: ' + ', '.join(sorted(set(parameters) - set(defaults))))
    p = {**defaults, **parameters}
    for key, value in p.items():
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(key + ' must be a finite number')
        if key not in ('cx_mm', 'cy_mm') and value <= 0:
            raise ValueError(key + ' must be positive')
    def circle(radius, cx=0, cy=0):
        return {'type': 'circle', 'cx_mm': cx, 'cy_mm': cy, 'radius_mm': radius}
    def rect():
        return {'type': 'rectangle', 'cx_mm': 0, 'cy_mm': 0,
                'width_mm': p['length_mm'], 'height_mm': p['width_mm']}
    def op(profile, depth, cut=False):
        result = {'op': 'cut_extrude' if cut else 'boss_extrude', 'plane': 'front',
                  'profile': profile, 'depth_mm': depth}
        # Front-datum cuts must point into the positive base extrusion. Verified
        # with real SW2023 tube revision e0340483-3b70-423b-9c09-7f53ab01f841.
        if cut:
            result['reverse'] = True
        return result
    warnings = []
    if template == 'box':
        operations = [op(rect(), p['height_mm'])]
        volume = p['length_mm'] * p['width_mm'] * p['height_mm']
    elif template == 'cylinder':
        operations = [op(circle(p['radius_mm'], p['cx_mm'], p['cy_mm']), p['depth_mm'])]
        volume = math.pi * p['radius_mm'] ** 2 * p['depth_mm']
    elif template == 'tube':
        if p['inner_radius_mm'] >= p['outer_radius_mm']:
            raise ValueError('Inner radius must be smaller than outer radius')
        operations = [op(circle(p['outer_radius_mm']), p['depth_mm']),
                      op(circle(p['inner_radius_mm']), p['depth_mm'], True)]
        volume = math.pi * (p['outer_radius_mm'] ** 2 - p['inner_radius_mm'] ** 2) * p['depth_mm']
        warnings.append('Confirm actual through-cut, depth and topology in SolidWorks.')
    else:
        r, spacing = p['hole_radius_mm'], p['hole_spacing_mm']
        if spacing <= 2 * r or spacing / 2 + r >= p['length_mm'] / 2 or r >= p['width_mm'] / 2:
            raise ValueError('Holes must be separate and strictly inside the plate')
        operations = [op(rect(), p['thickness_mm'])] + [
            op(circle(r, x), p['thickness_mm'], True) for x in (-spacing / 2, spacing / 2)]
        volume = (p['length_mm'] * p['width_mm'] - 2 * math.pi * r ** 2) * p['thickness_mm']
        warnings.append('Confirm both through-holes, depth and topology in SolidWorks.')
    recipe = validate_recipe({'doc_type': 'part', 'name': name, 'operations': operations})
    return {'template': template, 'parameters': p, 'name': name, 'recipe': recipe,
            'applied_defaults': {k: v for k, v in defaults.items() if k not in parameters},
            'expected_volume_mm3': volume, 'volume_is_measured': False, 'warnings': warnings,
            'execution_ready': template != 'two_hole_plate', 'validation': VALIDATION[template]}


def review_part(template, parameters, name, job):
    """Compare an actual server job/request with the independently regenerated contract."""
    plan = plan_part(template, parameters, name)
    failures = []
    def check(condition, message):
        if not condition:
            failures.append(message)
    if type(job) is not dict:
        raise ValueError('Expected a server job object')
    check(job.get('status') == 'done', 'Task is not done')
    request = job.get('request') or {}
    check(job.get('operation') == 'sw_recipe' and request.get('recipe') == plan['recipe'],
          'Task request differs from the design contract')
    envelope = job.get('result') or {}
    check(envelope.get('ok') is True, 'Executor did not report success')
    value = envelope.get('value') or {}
    saved = value.get('saved')
    check(isinstance(saved, str) and PureWindowsPath(saved).is_absolute() and
          PureWindowsPath(saved).name == name + '.SLDPRT', 'Saved path is missing or unexpected')
    check(type(value.get('bytes')) is int and value['bytes'] > 0, 'Saved size is not positive')
    check(value.get('doc_type') == 'part', 'Result is not a part')
    check(value.get('rebuild_ok') is True, 'Rebuild not confirmed')
    check(value.get('all_sketches_fully_defined') is True, 'Fully defined sketches not confirmed')
    features, sketches = value.get('features'), value.get('sketches')
    operations = plan['recipe']['operations']
    check(type(features) is list and len(features) == len(operations), 'Feature count mismatch')
    check(type(sketches) is list and len(sketches) == len(operations), 'Sketch count mismatch')
    def near(actual, expected):
        return type(actual) in (int, float) and math.isfinite(actual) and abs(actual - expected) <= .001
    for index, operation in enumerate(operations):
        step = index + 1
        if type(features) is list and index < len(features):
            feature = features[index]
            check(feature.get('step') == step and feature.get('op') == operation['op'] and
                  bool(feature.get('feature')), f'Step {step}: wrong/missing feature')
        if type(sketches) is not list or index >= len(sketches):
            continue
        sketch, profile = sketches[index], operation['profile']
        check(sketch.get('step') == step and sketch.get('status_code') == 3 and
              sketch.get('fully_defined') is True and bool(sketch.get('sketch')),
              f'Step {step}: sketch not fully defined')
        dims = sketch.get('driving_dimensions', [])
        expected = ({'diameter': profile['radius_mm'] * 2} if profile['type'] == 'circle' else
                    {'width': profile['width_mm'], 'height': profile['height_mm']})
        for role, mm in expected.items():
            check(any(d.get('role') == role and near(d.get('mm'), mm) and
                      d.get('driving_dimension_created') is True and '@' in d.get('dimension', '')
                      for d in dims), f'Step {step}: missing/wrong driving {role}')
        if profile['type'] == 'circle':
            geometry = sketch.get('profile_geometry') or {}
            check(geometry.get('checked') is True and all(near(geometry.get(k), profile[k])
                  for k in ('cx_mm', 'cy_mm', 'radius_mm')), f'Step {step}: solved circle geometry differs')
    return {'job_id': job.get('job_id'), 'status': job.get('status'), 'checks_passed': not failures,
            'failures': failures, 'saved': saved, 'bytes': value.get('bytes'),
            'error': envelope.get('error'), 'diagnostics': envelope.get('diagnostics'),
            'progress': job.get('progress'), 'revision_of': request.get('revision_of'),
            'engineering_validation_complete': False,
            'unverified': ['Actual extrusion/cut depth', 'Solid topology and measured volume',
                           'Saved file reopened and inspected'],
            'expected_volume_mm3': plan['expected_volume_mm3'], 'volume_is_measured': False}


def install_project_skills(workspace, names=SKILLS):
    """Explicit local install, no overwrites of edited skills, no traversal through links."""
    if not set(names) <= set(SKILLS) | {'remote-b-blender'}:
        raise ValueError('Unknown bundled skill')
    workspace = Path(workspace).absolute()
    if not workspace.is_dir():
        raise ValueError('Workspace must already exist')
    def reject_links(path):
        for part in (path, *path.parents):
            if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
                raise ValueError('Refusing a linked destination: ' + str(part))
    destination = workspace / '.agents' / 'skills'
    reject_links(destination)
    installed = []
    # Preflight all files before writing either skill.
    for name in names:
        source, target = library_root() / name, destination / name
        if not (source / 'SKILL.md').is_file():
            raise ValueError('Bundled skill is missing')
        for item in source.rglob('*'):
            if item.is_file():
                existing = target / item.relative_to(source)
                reject_links(existing)
                if existing.exists() and existing.read_bytes() != item.read_bytes():
                    raise ValueError('Preserving edited file: ' + str(existing))
    destination.mkdir(parents=True, exist_ok=True)
    for name in names:
        source, target = library_root() / name, destination / name
        if target.exists():
            # A partial install is repaired without overwriting existing files.
            for item in source.rglob('*'):
                if item.is_file():
                    output = target / item.relative_to(source)
                    output.parent.mkdir(parents=True, exist_ok=True)
                    if not output.exists():
                        shutil.copy2(item, output)
        else:
            with tempfile.TemporaryDirectory(prefix='.skills-', dir=destination) as temporary:
                staged = Path(temporary) / name
                shutil.copytree(source, staged)
                staged.rename(target)
        installed.append(str(target))
    return {'installed': installed, 'reload': 'Restart the Codex session to discover project skills.'}
