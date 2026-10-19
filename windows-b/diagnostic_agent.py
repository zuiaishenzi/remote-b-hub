"""Structured diagnostics wrapper. Never sends Python tracebacks or arbitrary code to execute."""
import traceback
import uuid
import agent
from sw_agent import execute as previous_execute
from sw_recipe import execute_recipe

def execute(operation, params):
    if operation != "sw_recipe":
        return previous_execute(operation, params)
    return execute_recipe(params["recipe"])

agent.execute = execute

def main():
    print("PC B diagnostic agent started: " + agent.BASE_URL, flush=True)
    while True:
        try:
            response = agent.api('GET', '/agent/next')
            job = response.get('job')
            if job is None:
                agent.time.sleep(2)
                continue
            job_id = job['job_id']
            stage = 'received'
            def progress(next_stage, detail=None):
                nonlocal stage
                stage = next_stage
                try:
                    agent.api('POST', f'/agent/jobs/{job_id}/progress',
                        {'stage': next_stage, 'detail': detail})
                except Exception as exc:
                    print('Progress report unavailable:', str(exc)[:160], flush=True)
            progress('executing', job['operation'])
            try:
                result = execute(job['operation'], job['params'])
                progress('completed')
                answer = {'ok': True, 'value': result}
            except Exception as exc:
                trace = traceback.format_exc(limit=12)
                print(trace, flush=True)
                answer = {
                    'ok': False, 'error': f'{type(exc).__name__}: {str(exc)[:900]}',
                    'diagnostics': {
                        'stage': stage,
                        'exception_type': type(exc).__name__,
                        'traceback': trace[-5000:],
                        'operation': job['operation']
                    }}
            agent.api('POST', f'/agent/jobs/{job_id}/result', answer)
            print('Job', job_id, 'ok' if answer['ok'] else answer['error'], flush=True)
        except Exception as exc:
            print('Agent network/loop error:', repr(exc), flush=True)
            agent.time.sleep(5)

if __name__ == '__main__':
    main()
