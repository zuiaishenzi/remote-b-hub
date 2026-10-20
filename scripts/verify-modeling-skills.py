"""Real B acceptance through saved A config. No token output or automatic retry.

Requires --execute to create NEW saved CAD parts. Stops at the first failed task.
The result review is process evidence; it does not measure solid topology/depth.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / p) for p in ('windows-a', 'windows-b')]
from cad_skills import plan_part, review_part
from desktop_config import unprotect_token
from relay_client import RelayClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--output', default='build/modeling-skills-acceptance.json')
    parser.add_argument('--timeout', type=int, default=120)
    parser.add_argument('--templates', nargs='+', choices=['box', 'cylinder', 'tube', 'two_hole_plate'])
    args = parser.parse_args()
    cases = [('box', {}), ('cylinder', {}),
             ('cylinder', {'radius_mm': 4, 'cx_mm': 20, 'cy_mm': 0}),
             ('tube', {}), ('two_hole_plate', {})]
    if args.templates:
        cases = [(t, p) for t, p in cases if t in args.templates]
    plans = [plan_part(t, p, 'Skill_' + t + '_' + uuid.uuid4().hex[:10]) for t, p in cases]
    if not args.execute:
        print(json.dumps({'preflight_only': True, 'plans': plans}, indent=2))
        return 0
    if args.templates and any(not plan['execution_ready'] for plan in plans):
        raise ValueError('Selected template is blocked by recorded real acceptance failure; fix/test executor first.')
    plans = [plan for plan in plans if plan['execution_ready']]
    config = json.loads((Path(os.environ['LOCALAPPDATA']) / 'RemoteBHubA' / 'config.json').read_text(encoding='utf-8'))
    client = RelayClient(config['server_url'], unprotect_token(config['token_dpapi']))
    evidence = {'status': client.request('GET', '/api/status'), 'jobs': []}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    def record():
        output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    def execute(operation, params=None):
        submitted = client.request('POST', '/api/jobs', {'operation': operation, 'params': params or {}})
        identity = submitted['job_id']
        print('SUBMITTED', operation, identity, flush=True)
        deadline = time.monotonic() + args.timeout
        while True:
            job = client.request('GET', '/api/jobs/' + identity)
            if job['status'] not in ('queued', 'running'):
                evidence['jobs'].append(job)
                record()
                print('FINISHED', identity, job['status'], flush=True)
                return job
            if time.monotonic() >= deadline:
                evidence['jobs'].append(job)
                record()
                raise RuntimeError('Timed out; task may still be active. Do not resubmit: ' + identity)
            time.sleep(2)
    if evidence['status'].get('online') is not True:
        record()
        raise RuntimeError('B offline; no jobs submitted')
    sw = execute('solidworks_status')
    value = (sw.get('result') or {}).get('value') or {}
    if sw['status'] != 'done' or not value.get('connected') or not str(value.get('revision', value.get('version', ''))).startswith('31.'):
        raise RuntimeError('SW2023 connection not verified; inspect recorded status job')
    for plan in plans:
        job = execute('sw_recipe', {'recipe': plan['recipe']})
        review = review_part(plan['template'], plan['parameters'], plan['name'], job)
        job['skill_review'] = review
        record()
        print(json.dumps(review, ensure_ascii=True), flush=True)
        if not review['checks_passed']:
            raise RuntimeError('Acceptance stopped at failed task; inspect full evidence and diagnostics')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
