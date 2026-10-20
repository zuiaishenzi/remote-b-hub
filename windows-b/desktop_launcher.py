"""Remote B Hub desktop launcher and PyInstaller entry point."""
import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import traceback
import urllib.request

from desktop_config import (DEFAULTS, data_directory, load_config, save_config,
                            validate_config, redact)


def command(*arguments):
    if getattr(sys, "frozen", False):
        return [sys.executable, *arguments]
    return [sys.executable, str(Path(__file__).resolve()), *arguments]


def worker_running():
    """Detect a worker finishing after its owning launcher has closed."""
    import win32api, win32event
    handle = win32event.CreateMutex(None, False, "Local\\RemoteBHubWorker")
    try:
        return win32api.GetLastError() == 183
    finally:
        win32api.CloseHandle(handle)


def set_login_start(enabled):
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
        if enabled:
            if not getattr(sys, "frozen", False):
                raise ValueError("登录自启请使用打包后的 EXE，并将 EXE 放在固定位置")
            winreg.SetValueEx(key, "RemoteBHub", 0, winreg.REG_SZ,
                             subprocess.list2cmdline(command("--autostart")))
        else:
            try:
                winreg.DeleteValue(key, "RemoteBHub")
            except FileNotFoundError:
                pass


class Launcher:
    def __init__(self, root, directory, smoke=False):
        import tkinter as tk
        from tkinter import ttk, scrolledtext
        self.root = root
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.messages = queue.Queue()
        self.process = None
        self.want_agent = False
        self.log_position = 0
        self.last_restart = 0
        self.smoke = smoke
        self.starting_sw = False
        self.worker_log = self.directory / "agent.log"
        self.gui_log = self.directory / "launcher.log"
        self.config_error = None
        try:
            self.config = load_config(directory)
        except Exception as exc:
            self.config = dict(DEFAULTS)
            self.config_error = str(exc)
        self.secret = self.config["token"]
        from desktop_version import runtime_info
        version = runtime_info()
        root.title("Remote B Hub — 电脑 B 启动器 — " + version["executor_sha256"][:12])
        root.geometry("1020x780")
        root.minsize(880, 680)
        body = ttk.Frame(root, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Remote B Hub · 配置、状态与任务日志", font=("Microsoft YaHei UI", 15, "bold")).pack(anchor="w")
        ttk.Label(body, text="服务指本机任务代理；建模在当前 Windows 登录会话执行。Token 使用当前用户加密保存。").pack(anchor="w", pady=(4, 10))
        fields = ttk.LabelFrame(body, text="连接与建模设置（停止代理后保存修改）", padding=10)
        fields.pack(fill="x")
        fields.columnconfigure(1, weight=1)
        self.variables = {}
        labels = (("server_url", "NAS 服务地址", None), ("token", "B Token / HUB_B_TOKEN", None),
                  ("output_dir", "CAD 输出目录", "directory"), ("part_template", "零件模板 (.prtdot)", "file"),
                  ("assembly_template", "装配模板 (.asmdot)", "file"), ("sw_exe", "SOLIDWORKS 程序", "file"),
                  ("interop_dir", "Interop 目录（留空自动定位）", "directory"))
        for row, (key, label, browse) in enumerate(labels):
            ttk.Label(fields, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=4)
            variable = tk.StringVar(value=self.config[key])
            self.variables[key] = variable
            ttk.Entry(fields, textvariable=variable, show="*" if key == "token" else "").grid(row=row, column=1, sticky="ew", pady=4)
            if browse:
                ttk.Button(fields, text="浏览…", command=lambda k=key, b=browse: self.browse(k, b)).grid(row=row, column=2, padx=(6, 0))
        options = ttk.Frame(body)
        options.pack(fill="x", pady=8)
        for key, label in (("auto_start_sw", "CAD 任务到达时自动启动 SW"), ("auto_start_agent", "打开程序自动启动代理"),
                           ("auto_restart_agent", "代理意外退出后自动重启"), ("start_at_login", "Windows 登录后驻留")):
            self.variables[key] = tk.BooleanVar(value=self.config[key])
            ttk.Checkbutton(options, text=label, variable=self.variables[key]).pack(side="left", padx=(0, 12))
        controls = ttk.Frame(body)
        capture_options = ttk.Frame(body)
        capture_options.pack(fill="x", pady=(0, 6))
        for key, label in (("screenshots_enabled", "允许上传 SOLIDWORKS 窗口截图（需要 NAS 附件接口）"),
                           ("capture_on_error", "CAD 失败时自动截图；截图失败保留原错误")):
            self.variables[key] = tk.BooleanVar(value=self.config[key])
            ttk.Checkbutton(capture_options, text=label, variable=self.variables[key]).pack(side="left", padx=(0, 12))
        scripts = ttk.Frame(body)
        scripts.pack(fill="x", pady=(0, 6))
        self.variables["allow_sw_scripts"] = tk.BooleanVar(value=self.config["allow_sw_scripts"])
        ttk.Checkbutton(scripts, text="允许 A 执行完整权限 SW Python 脚本（可修改文件；非沙箱）",
                        variable=self.variables["allow_sw_scripts"]).pack(side="left")
        ttk.Button(scripts, text="核对 CAD 状态后解除脚本暂停", command=self.clear_script_pause).pack(side="left", padx=8)
        controls.pack(fill="x", pady=4)
        for label, callback in (("保存设置", self.save), ("检查状态", self.check), ("启动 SOLIDWORKS", self.start_sw),
                                ("启动代理", self.start), ("停止代理（完成当前任务后）", self.stop),
                                ("打开日志目录", lambda: os.startfile(str(self.directory)))):
            ttk.Button(controls, text=label, command=callback).pack(side="left", padx=(0, 6))
        ttk.Button(controls, text="最小化驻留", command=root.iconify).pack(side="left")
        ttk.Button(controls, text="检查更新", command=self.open_update).pack(side="left", padx=6)
        self.status = tk.StringVar(value="准备就绪")
        ttk.Label(body, textvariable=self.status, wraplength=960).pack(anchor="w", pady=(8, 4))
        self.log_widget = scrolledtext.ScrolledText(body, state="disabled", font=("Consolas", 10), wrap="word")
        self.log_widget.pack(fill="both", expand=True)
        ttk.Label(body, text="关闭窗口会退出启动器；代理完成当前任务并回传后停止。驻留请点“最小化驻留”。", foreground="#555555").pack(side="left", pady=(8, 0))
        ttk.Button(body, text="退出启动器", command=self.quit).pack(side="right", pady=(8, 0))
        root.protocol("WM_DELETE_WINDOW", self.quit)
        if self.config_error:
            self.message("配置读取失败，请重新填写并保存: " + self.config_error)
        else:
            self.message("配置位于 " + str(self.directory / "config.json"))
        self.message("执行器版本: " + json.dumps(version, ensure_ascii=False))
        if not smoke:
            root.after(300, self.check)
            if self.config["auto_start_agent"] and self.config["server_url"] and not self.config_error:
                root.after(600, self.start)
        root.after(500, self.tick)

    def clear_script_pause(self):
        from tkinter import messagebox
        from sw_script import LOCK
        if worker_running():
            messagebox.showinfo("请先停止代理", "等待代理完成当前任务并停止后再操作。", parent=self.root)
            return
        path = self.directory / LOCK
        if not path.exists():
            self.message("没有脚本暂停标记。")
            return
        info = json.loads(path.read_text(encoding="utf-8"))
        from windows_processes import process_snapshot
        if any(pid == info.get("pid") for pid, name in process_snapshot()):
            messagebox.showinfo("脚本仍在运行", "请先检查 B 的 SW 窗口；脚本进程尚未退出，不能解除暂停。", parent=self.root)
            return
        if messagebox.askyesno("确认 CAD 状态", "已检查 SW 无运行中的命令、模型状态明确？解除后仍不得无修改重复失败脚本。", parent=self.root):
            path.unlink()
            self.message("已解除 CAD 暂停；请先读取模型状态，再继续编辑。")

    def open_update(self):
        from update_window import UpdateWindow
        return UpdateWindow(self.root, self.directory, 'b', self.prepare_update)

    def prepare_update(self, plan):
        from desktop_update import launch_helper
        running = self.process is not None and self.process.poll() is None
        if worker_running() and not running:
            raise RuntimeError('另一个代理仍在完成任务，请待其停止后更新')
        launch_helper(plan, [self.process.pid] if running else [], resume_agent=running)
        self.quit()  # graceful stop; helper waits for both GUI and worker

    def values(self):
        config = dict(self.config)
        for key, variable in self.variables.items():
            config[key] = variable.get().strip() if key in ("server_url", "output_dir", "part_template", "assembly_template", "sw_exe", "interop_dir") else variable.get()
        config["server_url"] = config["server_url"].rstrip("/")
        self.secret = config["token"]
        return config

    def message(self, value):
        self.messages.put(redact(value, self.secret))

    def browse(self, key, kind):
        from tkinter import filedialog
        path = filedialog.askdirectory() if kind == "directory" else filedialog.askopenfilename()
        if path:
            self.variables[key].set(path)

    def save(self):
        from tkinter import messagebox
        if (self.process and self.process.poll() is None) or worker_running():
            messagebox.showinfo("代理正在运行", "请先停止代理，等待当前任务结束后再保存设置。")
            return False
        try:
            config = self.values()
            validate_config(config)
            # Check login registration first so source-mode cannot save an unusable setting.
            set_login_start(config["start_at_login"])
            save_config(self.directory, config)
            self.config = config
            self.message("设置已保存；Token 已使用当前 Windows 用户加密。")
            return True
        except Exception as exc:
            messagebox.showerror("设置未保存", redact(str(exc), self.variables["token"].get()))
            return False

    def start(self):
        if self.process and self.process.poll() is None:
            self.message("代理已运行。")
            return
        if not self.save():
            return
        self.want_agent = True
        self.spawn_worker()

    def spawn_worker(self):
        if worker_running():
            self.want_agent = False
            self.message("已有代理仍在运行或完成退出；请等待其停止后再启动。")
            return
        (self.directory / "stop.request").unlink(missing_ok=True)
        # Retain an old status file only as historical data; never present it as current.
        (self.directory / "status.json").unlink(missing_ok=True)
        try:
            self.process = subprocess.Popen(command("--worker", "--data-dir", str(self.directory)),
                                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                            stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW,
                                            env={**os.environ, 'PYINSTALLER_RESET_ENVIRONMENT': '1'})
        except Exception as exc:
            self.want_agent = False
            self.message(f"代理进程无法启动: {exc}")
            return
        self.last_restart = time.monotonic()
        self.message(f"代理进程已启动 PID={self.process.pid}；等待已鉴权的 NAS 轮询确认。")

    def stop(self):
        self.want_agent = False
        (self.directory / 'start-sw.request').unlink(missing_ok=True)
        (self.directory / "stop.request").touch()
        self.message("已请求停止；等待当前建模/网络调用完成，不强杀 SOLIDWORKS。")

    def check(self):
        config = self.values()
        def run():
            try:
                from desktop_worker import sw_status
                sw = sw_status()
                self.message(f"SOLIDWORKS：COM 已连接，版本 {sw['revision']}，可见={sw['visible']}")
            except Exception as exc:
                self.message("SOLIDWORKS：当前登录会话 COM 未就绪；" + str(exc))
            try:
                request = urllib.request.Request(config["server_url"].rstrip("/") + "/health")
                with urllib.request.urlopen(request, timeout=8) as response:
                    health = json.load(response)
                self.message(f"NAS 健康检查：{health.get('status')}（Token 是否有效以代理轮询结果为准）")
            except Exception as exc:
                self.message("NAS 健康检查失败：" + str(exc))
            for key in ("part_template", "assembly_template", "sw_exe"):
                self.message(f"路径检查 {key}: {'存在' if Path(config[key]).is_file() else '未找到'}")
        threading.Thread(target=run, daemon=True).start()

    def start_sw(self):
        if (self.process and self.process.poll() is None) or worker_running():
            from desktop_worker import request_solidworks_start
            request_solidworks_start(self.directory)
            self.message("已请求代理启动 SW；当前任务结束后执行，使用已保存的 SW 程序路径。")
            return
        if self.starting_sw:
            return
        config = self.values()
        config["auto_start_sw"] = True
        self.starting_sw = True
        def run():
            import pythoncom
            pythoncom.CoInitialize()
            try:
                from desktop_worker import ensure_solidworks
                result = ensure_solidworks(config, lambda stage, detail: self.message(detail))
                self.message("SOLIDWORKS 已就绪，版本 " + result["revision"])
            except Exception as exc:
                self.message("SOLIDWORKS 启动失败：" + str(exc))
            finally:
                self.starting_sw = False
                pythoncom.CoUninitialize()
        threading.Thread(target=run, daemon=True).start()

    def tick(self):
        try:
            if self.worker_log.stat().st_size < self.log_position:
                self.log_position = 0
            with self.worker_log.open("rb") as stream:
                stream.seek(self.log_position)
                data = stream.read(100_000)
                self.log_position = stream.tell()
            if data:
                self.messages.put(data.decode("utf-8", errors="replace").rstrip())
        except OSError:
            pass  # File may not exist yet, or be temporarily renamed during rotation.
        if self.process and self.process.poll() is not None:
            code = self.process.returncode
            if self.want_agent and self.config["auto_restart_agent"] and code != 2 and time.monotonic() - self.last_restart > 5:
                self.message(f"代理退出 code={code}；自动重启。")
                self.spawn_worker()
            elif not self.want_agent or not self.config["auto_restart_agent"] or code == 2:
                self.want_agent = False
                self.message("代理已停止。" if code == 0 else f"代理已退出 code={code}；检查 startup-error.log 或是否已有代理运行。")
                self.process = None
        running = (self.process is not None and self.process.poll() is None) or worker_running()
        description = "代理未运行"
        if running:
            description = "代理进程运行中；等待状态"
            try:
                state = json.loads((self.directory / "status.json").read_text(encoding="utf-8"))
                age = int(time.time() - state["updated"])
                description = f"代理：{state['stage']} · 状态更新于 {age} 秒前 · {state.get('detail', state.get('error', ''))}"
            except (OSError, ValueError, KeyError):
                pass
        self.status.set(description)
        while not self.messages.empty():
            message = self.messages.get_nowait()
            line = time.strftime("%H:%M:%S ") + message + "\n"
            self.log_widget.configure(state="normal")
            self.log_widget.insert("end", line)
            if int(self.log_widget.index("end-1c").split(".")[0]) > 2000:
                self.log_widget.delete("1.0", "500.0")
            self.log_widget.see("end")
            self.log_widget.configure(state="disabled")
            # Worker history has its own rotation; bound the UI event file as well.
            if self.gui_log.exists() and self.gui_log.stat().st_size > 2_000_000:
                self.gui_log.replace(self.gui_log.with_suffix(".previous.log"))
            with self.gui_log.open("a", encoding="utf-8") as stream:
                stream.write(line)
        self.root.after(500, self.tick)

    def quit(self):
        # Worker owns an independent PyInstaller extraction directory, so it can
        # finish the current task after this GUI exits. Do not kill COM/SW.
        self.stop()
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-sw-script")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--autostart", action="store_true")
    parser.add_argument("--data-dir")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--apply-update")
    parser.add_argument("--resume-agent", action="store_true")
    args = parser.parse_args()
    if args.run_sw_script:
        from sw_script import run_payload
        return run_payload(args.run_sw_script)
    if args.apply_update:
        from desktop_update import apply_update
        return apply_update(args.apply_update)
    directory = data_directory(args.data_dir)
    directory.mkdir(parents=True, exist_ok=True)
    try:
        if args.self_test:
            # Exercise bundled COM modules and current-user token protection.
            import win32com.client, win32crypt, desktop_worker, sw_recipe
            from desktop_config import protect_token, unprotect_token
            assert unprotect_token(protect_token("self-test-token")) == "self-test-token"
            from desktop_version import runtime_info
            assert len(runtime_info()["executor_sha256"]) == 64
            import interop_control, screen_capture, sw_script
            from script_schema import validate_script_request
            assert len(validate_script_request({"mode": "inspect"})) == 64
            from windows_processes import process_snapshot, process_session
            assert any(pid == os.getpid() for pid, name in process_snapshot())
            assert process_session() >= 0
            source_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "interop"
            assert (source_dir / "SwInteropController.cs").is_file()
            assert (source_dir / "BuildInterop.ps1").is_file()
            (directory / "self-test.json").write_text(json.dumps({"ok": True, "frozen": bool(getattr(sys, "frozen", False))}), encoding="utf-8")
            return 0
        if args.worker:
            from desktop_worker import run_worker
            return run_worker(directory)
        import tkinter as tk
        from tkinter import messagebox
        import win32api, win32event
        root = tk.Tk()
        root.withdraw()
        mutex = None
        if not args.smoke_test:
            mutex = win32event.CreateMutex(None, False, "Local\\RemoteBHubLauncher")
            if win32api.GetLastError() == 183:
                messagebox.showinfo("Remote B Hub", "启动器已在运行，请从任务栏恢复窗口。", parent=root)
                root.destroy()
                return 0
        app = Launcher(root, directory, args.smoke_test)
        if args.smoke_test:
            updater = app.open_update()
            updater.window.withdraw()
            if app.config['server_url'] and app.config['token']:
                # Build-only lifecycle probe: close while a fake NAS has the
                # worker blocked in a request. Never save/login-register config.
                deadline = time.monotonic() + 15
                def close_busy_worker():
                    try:
                        state = json.loads((directory / 'status.json').read_text(encoding='utf-8'))
                    except (OSError, ValueError):
                        state = {}
                    if state.get('stage') == 'executing' or time.monotonic() >= deadline:
                        app.quit()
                    else:
                        root.after(100, close_busy_worker)
                root.after(100, app.spawn_worker)
                root.after(200, close_busy_worker)
            else:
                root.after(1000, app.quit)
        else:
            root.deiconify()
            if args.resume_agent and not app.config['auto_start_agent']:
                root.after(600, app.start)
            if args.autostart:
                root.after(100, root.iconify)
        root.mainloop()
        if mutex:
            win32api.CloseHandle(mutex)
        if args.smoke_test:
            (directory / "gui-smoke.json").write_text('{"ok": true, "updater_support": true}', encoding="utf-8")
        return 0
    except Exception:
        trace = traceback.format_exc()
        # Use only a local crash file; never include environment or config dumps.
        try:
            token = load_config(directory).get("token", "")
        except Exception:
            token = ""
        (directory / "startup-error.log").write_text(redact(trace, token), encoding="utf-8")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
