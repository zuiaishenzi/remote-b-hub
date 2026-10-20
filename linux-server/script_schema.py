"""Wire contract for the explicitly enabled, full-trust SW Python COM channel."""
import ast
import hashlib


def validate_script_request(params):
    if type(params) is not dict or set(params) - {'mode', 'code', 'timeout_seconds'}:
        raise ValueError('Only mode, code and timeout_seconds are accepted')
    if params.get('mode') not in ('inspect', 'execute'):
        raise ValueError('mode must be inspect or execute')
    timeout = params.get('timeout_seconds', 60)
    if type(timeout) is not int or not 10 <= timeout <= 300:
        raise ValueError('timeout_seconds must be an integer from 10 to 300')
    code = params.get('code', '')
    if params['mode'] == 'inspect':
        if 'code' in params:
            raise ValueError('inspect does not accept code')
    else:
        if type(code) is not str or not code.strip() or len(code.encode('utf-8')) > 24000:
            raise ValueError('execute requires 1..24000 UTF-8 bytes of Python code')
        try:
            ast.parse(code, filename='<remote-sw-script>')
        except (SyntaxError, ValueError, RecursionError) as exc:
            raise ValueError('Invalid Python script: ' + str(exc)) from exc
    return hashlib.sha256(code.encode('utf-8')).hexdigest()
