"""Fingerprint the actual bundled executor, independently of traceback line numbers."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def source_info():
    directory = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted(directory.glob("*.py")):
        digest.update(path.name.encode("utf-8") + b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
    for path in sorted((directory / "interop").glob("*")):
        if path.is_file():
            digest.update(path.name.encode("utf-8") + b"\0")
            digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
    return {"executor_sha256": digest.hexdigest(), "mode": "source"}


def runtime_info():
    if getattr(sys, "frozen", False):
        path = Path(sys._MEIPASS) / "runtime-info.json"
        if not path.is_file():
            return {"mode": "frozen", "executor_sha256": "unknown-old-build"}
        return json.loads(path.read_text(encoding="utf-8"))
    return source_info()


if __name__ == "__main__":
    info = source_info()
    info.update(mode="frozen", built_at=datetime.now(timezone.utc).isoformat())
    repo = Path(__file__).resolve().parents[1]
    info["source_commit"] = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    info["working_tree_dirty"] = bool(subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"], text=True).strip())
    destination = Path(sys.argv[1])
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(info), encoding="utf-8")
