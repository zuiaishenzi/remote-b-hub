"""Authenticated A-to-B lifecycle requests, independent of CAD/script execution."""
import re


def validate_cad_control(params):
    if type(params) is not dict or params.get('action') not in ('state', 'start', 'resume'):
        raise ValueError('action must be state, start or resume')
    if params['action'] == 'resume':
        if set(params) != {'action', 'pause_id', 'acknowledge_state'}:
            raise ValueError('resume requires pause_id and acknowledge_state')
        if type(params['pause_id']) is not str or not re.fullmatch('[0-9a-f]{64}', params['pause_id']):
            raise ValueError('pause_id must be the current SHA256 returned by CAD state')
        if params['acknowledge_state'] is not True:
            raise ValueError('Inspect CAD state before acknowledging recovery')
    elif set(params) != {'action'}:
        raise ValueError('state/start accept only action')
    return params
