"""Shared allowlist for document control, not a remote shell/COM evaluator."""
import re

CAD_FILE = re.compile(r"^[A-Za-z0-9_-]{1,50}\.(?:SLDPRT|SLDASM)$", re.IGNORECASE)
ACTIONS = {"inspect", "open", "rebuild", "save_copy", "close"}
DIMENSION = re.compile(r'^[^@\x00-\x1f\\/:]{1,80}@[^@\x00-\x1f\\/:]{1,80}$')


def validate_document_request(params):
    if type(params) is not dict or set(params) - {"action", "file", "new_file", "dimension_names"}:
        raise ValueError("Only action, file, new_file and dimension_names are accepted")
    action = params.get("action")
    if type(action) is not str or action not in ACTIONS:
        raise ValueError("Unsupported document action")
    if action != "inspect" and "file" not in params:
        raise ValueError("This action requires a managed CAD filename")
    if 'dimension_names' in params:
        names = params['dimension_names']
        if action != 'inspect' or type(names) is not list or not 1 <= len(names) <= 20 or any(
                type(n) is not str or not DIMENSION.fullmatch(n) for n in names):
            raise ValueError('inspect accepts 1-20 explicit dimension names such as D1@Sketch1')
    for key in ("file", "new_file"):
        if key in params and (type(params[key]) is not str or not CAD_FILE.fullmatch(params[key])):
            raise ValueError("CAD references must be simple SLDPRT/SLDASM filenames")
    if action == "save_copy":
        if "new_file" not in params or params["new_file"].lower() == params["file"].lower():
            raise ValueError("save_copy requires a different new_file")
        if params["new_file"].rsplit(".", 1)[1].lower() != params["file"].rsplit(".", 1)[1].lower():
            raise ValueError("save_copy cannot change the CAD document type")
    elif "new_file" in params:
        raise ValueError("new_file is only supported by save_copy")
    return params
