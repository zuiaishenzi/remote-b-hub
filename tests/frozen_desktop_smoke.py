"""Exercise the actual EXE worker against a local fake NAS; never starts SW."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "windows-b"))
from desktop_config import DEFAULTS, save_config


def main():
    executable = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="remote-b-frozen-") as directory:
        root = Path(directory)
        results, stages = [], []
        operations = ["ping", "system_info"]
        token = "local-smoke-not-a-real-token-" * 2
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def respond(self, value):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(value).encode())

            def do_GET(self):
                assert self.headers["Authorization"] == "Bearer " + token
                index = len(results)
                self.respond({"job": {"job_id": f"smoke-{index}", "operation": operations[index], "params": {}}})

            def do_POST(self):
                assert self.headers["Authorization"] == "Bearer " + token
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path.endswith("/progress"):
                    stages.append(body["stage"])
                elif self.path.endswith("/result"):
                    results.append(body)
                    if len(results) == 2:
                        (root / "stop.request").touch()
                self.respond({"saved": True})

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        try:
            save_config(root, {**DEFAULTS, "token": token,
                              "server_url": f"http://127.0.0.1:{server.server_port}",
                              "output_dir": str(root / "output")})
            threading.Thread(target=server.serve_forever, daemon=True).start()
            process = subprocess.run([str(executable), "--worker", "--data-dir", str(root)],
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW,
                                     timeout=60)
            if process.returncode != 0:
                error_file = root / "startup-error.log"
                raise RuntimeError(error_file.read_text(encoding="utf-8") if error_file.exists() else "Worker failed")
            assert len(results) == 2 and all(item["ok"] for item in results), results
            assert results[0]["value"]["message"] == "pong from PC B"
            assert results[1]["value"]["host"]
            assert {"received", "executing", "completed"}.issubset(stages), stages
            assert "starting_solidworks" not in stages
            assert token not in (root / "agent.log").read_text(encoding="utf-8")
            print("Frozen EXE worker HTTP/DPAPI/logging smoke test passed (ping + system_info; no SW started)")
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    main()
