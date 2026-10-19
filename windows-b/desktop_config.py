"""Local desktop configuration. Tokens are protected with current-user DPAPI."""
import base64
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

DEFAULTS = {
    "server_url": "", "token": "",
    "output_dir": r"D:\codex\output",
    "part_template": r"C:\ProgramData\SolidWorks\SOLIDWORKS 2023\templates\gb_part.prtdot",
    "assembly_template": r"C:\ProgramData\SolidWorks\SOLIDWORKS 2023\templates\gb_assembly.asmdot",
    "sw_exe": r"D:\SW\SOLIDWORKS Corp\SOLIDWORKS\SLDWORKS.exe",
    "auto_start_sw": True, "auto_start_agent": True, "auto_restart_agent": True,
    "start_at_login": False, "sw_start_timeout": 180,
    "interop_dir": "", "screenshots_enabled": False, "capture_on_error": True,
}


def data_directory(override=None):
    return Path(override) if override else Path(os.environ["LOCALAPPDATA"]) / "RemoteBHub"


def protect_token(token):
    import win32crypt
    encrypted = win32crypt.CryptProtectData(token.encode("utf-8"), "RemoteBHub", None, None, None, 1)
    return base64.b64encode(encrypted).decode("ascii")


def unprotect_token(value):
    import win32crypt
    return win32crypt.CryptUnprotectData(base64.b64decode(value), None, None, None, 1)[1].decode("utf-8")


def load_config(directory):
    config = dict(DEFAULTS)
    path = Path(directory) / "config.json"
    if path.exists():
        stored = json.loads(path.read_text(encoding="utf-8"))
        config.update({key: stored[key] for key in DEFAULTS if key != "token" and key in stored})
        if stored.get("token_dpapi"):
            config["token"] = unprotect_token(stored["token_dpapi"])
    else:
        for field, env in (("server_url", "REMOTE_B_SERVER_URL"), ("token", "REMOTE_B_AGENT_TOKEN"),
                           ("output_dir", "REMOTE_B_OUTPUT_DIR"), ("part_template", "REMOTE_B_PART_TEMPLATE"),
                           ("assembly_template", "REMOTE_B_ASSEMBLY_TEMPLATE")):
            config[field] = os.environ.get(env, config[field])
    return config


def validate_config(config):
    url = urlsplit(config["server_url"])
    if url.scheme not in ("https", "http") or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError("NAS 地址必须是 http(s) URL，不能包含账号、查询参数或片段")
    if len(config["token"]) < 32 or any(c.isspace() for c in config["token"]):
        raise ValueError("B Token 至少 32 个字符，不能包含空白；应填写 NAS 的 HUB_B_TOKEN")
    if not config["output_dir"] or not Path(config["output_dir"]).is_absolute():
        raise ValueError("输出目录必须为绝对路径")
    for key, suffix in (("part_template", ".prtdot"), ("assembly_template", ".asmdot")):
        if config[key] and Path(config[key]).suffix.lower() != suffix:
            raise ValueError(f"{key} 应指向 {suffix} 模板")
    if config["sw_exe"] and Path(config["sw_exe"]).suffix.lower() != ".exe":
        raise ValueError("SOLIDWORKS 程序位置应为 .exe 文件")


def save_config(directory, config):
    validate_config(config)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stored = {key: config[key] for key in DEFAULTS if key != "token"}
    stored["token_dpapi"] = protect_token(config["token"])
    path = directory / "config.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def apply_environment(config):
    for key, env in (("server_url", "REMOTE_B_SERVER_URL"), ("token", "REMOTE_B_AGENT_TOKEN"),
                     ("output_dir", "REMOTE_B_OUTPUT_DIR"), ("part_template", "REMOTE_B_PART_TEMPLATE"),
                     ("assembly_template", "REMOTE_B_ASSEMBLY_TEMPLATE")):
        os.environ[env] = config[key]


def redact(text, token):
    return str(text).replace(token, "[TOKEN REDACTED]") if token else str(text)
