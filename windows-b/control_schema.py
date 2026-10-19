"""Shared allowlist for document control, not a remote shell/COM evaluator."""
import re

CAD_FILE = re.compile(r"^[A-Za-z0-9_-]{1,50}\.(?:SLDPRT|SLDASM)$", re.IGNORECASE)
ACTIONS = {"inspect", "open", "rebuild", "save_copy", "close"}


def validate_document_request(params):
    if type(params) is not dict or set(params) - {"action", "file", "new_file"}:
        raise ValueError("Only action, file and new_file are accepted")
    action = params.get("action")
    if type(action) is not str or action not in ACTIONS:
        raise ValueError("Unsupported document action")
    if action != "inspect" and "file" not in params:
        raise ValueError("This action requires a managed CAD filename")
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
