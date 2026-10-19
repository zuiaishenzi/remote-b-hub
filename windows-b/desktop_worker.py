"""Supervised interactive-session worker. Reuses existing recipe/diagnostic code."""
from contextlib import redirect_stdout, redirect_stderr
import io
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import os
import subprocess
import time
import traceback

from desktop_config import load_config, apply_environment, redact
from desktop_version import runtime_info

CAD_OPERATIONS = {"solidworks_status", "create_blank_part", "create_box", "sw_recipe", "sw_document"}


def sw_status():
    import pythoncom
    import win32com.client
    from solidworks_box import com_read
    pythoncom.CoInitialize()
    try:
        sw = win32com.client.GetActiveObject("SldWorks.Application")
        return {"connected": True, "revision": str(com_read(sw, "RevisionNumber")),
                "visible": bool(sw.Visible)}
    finally:
        pythoncom.CoUninitialize()


def ensure_solidworks(config, progress, stop_requested=lambda: False):
    """Only launch for a CAD task or an explicit local Start button."""
    try:
        return sw_status()
    except Exception:
        if not config["auto_start_sw"]:
            raise RuntimeError("SOLIDWORKS 未运行，且未启用自动启动")
    executable = Path(config["sw_exe"])
    if not executable.is_file():
        raise FileNotFoundError(f"SOLIDWORKS 程序不存在，请在启动器中配置: {executable}")
    # Do not spawn a second SW process when one is still registering its COM object.
    import win32com.client
    import win32ts
    session = win32ts.ProcessIdToSessionId(os.getpid())
    processes = win32com.client.GetObject("winmgmts:").ExecQuery(
        f"SELECT ProcessId FROM Win32_Process WHERE Name='SLDWORKS.exe' AND SessionId={session}")
    if not list(processes):
        progress("starting_solidworks", "正在启动 SOLIDWORKS，等待 COM 就绪")
        subprocess.Popen([str(executable)], cwd=str(executable.parent))
    else:
        progress("starting_solidworks", "检测到 SOLIDWORKS 进程，等待本会话 COM 就绪")
    deadline = time.monotonic() + config["sw_start_timeout"]
    while time.monotonic() < deadline:
        if stop_requested():
            raise RuntimeError("等待 SOLIDWORKS 时收到停止请求；未关闭 SOLIDWORKS")
        try:
            status = sw_status()
            progress("solidworks_ready", f"SOLIDWORKS COM 已就绪，版本 {status['revision']}")
            return status
        except Exception:
            time.sleep(2)
    raise TimeoutError("SOLIDWORKS COM 启动超时；检查同一登录会话、许可证和启动弹窗")


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


class TaskOutput(io.TextIOBase):
    def __init__(self, report):
        self.report = report
        self.buffer = ""

    def write(self, value):
        self.buffer += value
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            if line.strip():
                self.report("modeling", line)
        return len(value)

    def flush(self):
        if self.buffer.strip():
            self.report("modeling", self.buffer)
            self.buffer = ""


def run_worker(directory):
    import pythoncom
    import win32api
    import win32event
    directory = Path(directory)
    config = load_config(directory)
    apply_environment(config)
    # New GUI workers share one mutex even when started from different EXE versions.
    mutex = win32event.CreateMutex(None, False, "Local\\RemoteBHubWorker")
    if win32api.GetLastError() == 183:
        return 2
    logger = logging.getLogger("remote-b-worker")
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(directory / "agent.log", maxBytes=2_000_000, backupCount=4, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger.addHandler(handler)
    stop_file = directory / "stop.request"
    state_file = directory / "status.json"
    outbox = directory / "pending-result.json"
    def log(value):
        logger.info(redact(value, config["token"]))
    def state(stage, **extra):
        write_json(state_file, {"stage": stage, "updated": time.time(), "pid": os.getpid(), **extra})
    pythoncom.CoInitialize()
    try:
        # Imports require configuration environment; keep them inside this function.
        import agent
        from diagnostic_agent import execute
        version = runtime_info()
        log("执行器版本: " + json.dumps(version, ensure_ascii=False))
        log("代理启动；等待 NAS 任务。SOLIDWORKS 将按需启动。")
        while not stop_file.exists():
            # An undelivered result is retried before claiming any more CAD jobs.
            if outbox.exists():
                pending = json.loads(outbox.read_text(encoding="utf-8"))
                try:
                    agent.api("POST", f"/agent/jobs/{pending['job_id']}/result", pending["answer"])
                    outbox.unlink()
                    log(f"任务 {pending['job_id']} 结果已回传")
                    if stop_file.exists():
                        break
                except Exception as exc:
                    log(f"结果回传失败，将重试: {exc}")
                    state("result_retry", job_id=pending["job_id"])
                    time.sleep(5)
                    continue
            try:
                state("polling")
                job = agent.api("GET", "/agent/next").get("job")
                if not job:
                    state("idle", authenticated=True)
                    time.sleep(2)
                    continue
            except Exception as exc:
                log(f"NAS 连接/鉴权失败: {exc}")
                state("connection_error", error=redact(str(exc), config["token"]))
                time.sleep(5)
                continue
            job_id = job["job_id"]
            current_stage = "received"
            history = []
            def progress(stage, detail):
                nonlocal current_stage
                current_stage = stage
                safe = redact(detail, config["token"])
                log(f"[{job_id}] {stage}: {safe}")
                history.append(safe)
                del history[:-40]
                state(stage, job_id=job_id, detail=safe[:200])
                try:
                    agent.api("POST", f"/agent/jobs/{job_id}/progress", {"stage": stage, "detail": safe[:200]})
                except Exception as exc:
                    log(f"进度回传失败: {exc}")
            try:
                progress("received", f"收到任务 {job['operation']}")
                status = None
                if job["operation"] in CAD_OPERATIONS:
                    status = ensure_solidworks(config, progress, stop_file.exists)
                progress("executing", f"开始执行 {job['operation']}")
                stream = TaskOutput(progress)
                with redirect_stdout(stream), redirect_stderr(stream):
                    if job["operation"] == "sw_document":
                        from interop_control import execute_document
                        progress("interop_control", "执行受限 C# / SOLIDWORKS Interop 文档操作")
                        result = execute_document(job["params"], config, directory)
                    elif job["operation"] == "screenshot":
                        from screen_capture import capture_and_upload
                        result = {"artifacts": [capture_and_upload(job_id, config)]}
                    else:
                        result = status if job["operation"] == "solidworks_status" else execute(job["operation"], job["params"])
                    stream.flush()
                result["agent_log_tail"] = history[-20:]
                result["executor"] = version
                answer = {"ok": True, "value": result}
                progress("completed", "任务执行成功，准备回传结果")
            except Exception as exc:
                trace = redact(traceback.format_exc(limit=16), config["token"])
                log(trace)
                answer = {"ok": False, "error": redact(f"{type(exc).__name__}: {exc}", config["token"])[:900],
                          "diagnostics": {"stage": current_stage, "traceback": trace[-5000:],
                                          "operation": job["operation"], "log_tail": history[-20:],
                                          "executor": version}}
                if config.get("screenshots_enabled") and config.get("capture_on_error") and job["operation"] in CAD_OPERATIONS:
                    try:
                        from screen_capture import capture_and_upload
                        answer["diagnostics"]["artifacts"] = [capture_and_upload(job_id, config)]
                        log("SOLIDWORKS 错误截图已作为独立附件上传")
                    except Exception as capture_error:
                        answer["diagnostics"]["screenshot_error"] = redact(str(capture_error), config["token"])[:400]
                        log("截图/上传未完成，保留原建模错误: " + str(capture_error))
            write_json(outbox, {"job_id": job_id, "answer": answer})
            # Even if Stop was clicked during CAD, send the result before exiting.
            try:
                agent.api("POST", f"/agent/jobs/{job_id}/result", answer)
                outbox.unlink()
                log(f"任务 {job_id}: {'成功' if answer['ok'] else answer['error']}")
            except Exception as exc:
                log(f"结果已保留本地，等待回传: {exc}")
        state("stopped")
        log("代理已停止；未关闭 SOLIDWORKS，也未终止建模调用。")
        return 0
    finally:
        pythoncom.CoUninitialize()
        win32api.CloseHandle(mutex)
        handler.close()
        logger.removeHandler(handler)
