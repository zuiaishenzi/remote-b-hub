"""Launch only the bundled, fixed C# controller. Never run request-supplied code."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from control_schema import validate_document_request


def managed_path(root, filename, must_exist=True):
    from control_schema import CAD_FILE
    if not CAD_FILE.fullmatch(filename):
        raise ValueError("Invalid managed CAD filename")
    root = Path(root).absolute()
    # Reject symlinks/junctions in the configured root and its ancestors as well.
    for path in (root, *root.parents):
        if path.exists() and (path.is_symlink() or getattr(path, "is_junction", lambda: False)()):
            raise ValueError("Managed CAD root cannot traverse a reparse point")
    target = root / filename
    if target.is_symlink() or getattr(target, "is_junction", lambda: False)():
        raise ValueError("Managed CAD file cannot be a reparse point")
    if must_exist and not target.is_file():
        raise FileNotFoundError(f"Managed CAD file not found: {filename}")
    if not must_exist and target.exists():
        raise FileExistsError(f"Refusing to overwrite: {filename}")
    return target


def controller_executable(config, directory):
    source_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "interop"
    interop = Path(config.get("interop_dir") or (Path(config["sw_exe"]).parent / "api" / "redist"))
    library = interop / "SolidWorks.Interop.sldworks.dll"
    if not library.is_file():
        raise FileNotFoundError(f"SOLIDWORKS Interop DLL not found: {library}; configure Interop directory on B")
    source = source_dir / "SwInteropController.cs"
    build_script = source_dir / "BuildInterop.ps1"
    key = hashlib.sha256(source.read_bytes() + build_script.read_bytes() + library.read_bytes()).hexdigest()[:20]
    target_dir = Path(directory) / "interop-build" / key
    target_dir.mkdir(parents=True, exist_ok=True)
    executable = target_dir / "SwInteropController.exe"
    if not executable.exists():
        process = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                  "-File", str(build_script), "-InteropDirectory", str(interop),
                                  "-DestinationExe", str(executable)], capture_output=True, timeout=90,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if process.returncode or not executable.is_file():
            raise RuntimeError("Trusted C# controller build failed: " + (process.stdout + process.stderr).decode("utf-8", errors="replace")[-1800:])
    return executable, interop


def execute_document(params, config, directory):
    validate_document_request(params)
    if "file" in params:
        managed_path(config["output_dir"], params["file"])
    if "new_file" in params:
        managed_path(config["output_dir"], params["new_file"], must_exist=False)
    executable, interop = controller_executable(config, directory)
    request = {**params, "root": str(Path(config["output_dir"]).absolute())}
    env = {**os.environ, "REMOTE_B_INTEROP_DIR": str(interop)}
    try:
        completed = subprocess.run([str(executable)], input=json.dumps(request).encode("utf-8"),
                                   capture_output=True, env=env, timeout=120,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("C# control timed out; CAD state is unknown. Do not automatically repeat the action") from exc
    try:
        result = json.loads(completed.stdout.decode("utf-8-sig"))
    except (ValueError, UnicodeError) as exc:
        raise RuntimeError("C# controller returned invalid output: " + completed.stderr.decode("utf-8", errors="replace")[-1500:]) from exc
    if completed.returncode or not result.get("ok"):
        raise RuntimeError("C# Interop: " + str(result.get("error", "unknown failure")))
    if len(json.dumps(result["value"], ensure_ascii=False)) > 59000:
        raise RuntimeError("Inspection exceeds relay result limit; no engineering validation can be inferred")
    return result["value"]
