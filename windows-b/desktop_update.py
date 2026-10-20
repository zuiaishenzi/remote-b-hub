"""GitHub Release updater shared by A/B. Never reads tokens or updates CAD files."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from urllib.parse import urlsplit
import uuid

REPOSITORY = 'zuiaishenzi/remote-b-hub'
API = 'https://api.github.com/repos/' + REPOSITORY + '/releases/latest'
PRODUCTS = {'a': 'RemoteBClient.exe', 'b': 'RemoteBHub.exe'}
MAX_EXE = 200 * 1024 * 1024


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def no_links(path):
    for item in (Path(path), *Path(path).parents):
        if item.is_symlink() or getattr(item, 'is_junction', lambda: False)():
            raise ValueError('更新路径不能经过符号链接或 junction')


def trusted_url(url, asset=False):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('更新必须使用官方 HTTPS 地址')
    if asset:
        prefix = '/' + REPOSITORY + '/releases/download/'
        if parsed.hostname != 'github.com' or not parsed.path.startswith(prefix):
            raise ValueError('更新文件不属于本项目 Release')
    elif url != API:
        raise ValueError('不支持的更新 API')
    return url


def fetch_bytes(url, limit, asset=False):
    trusted_url(url, asset)
    request = urllib.request.Request(url, headers={'User-Agent': 'RemoteBHub-Updater',
                                                  'Accept': 'application/vnd.github+json' if not asset else 'application/octet-stream'})
    with urllib.request.urlopen(request, timeout=30) as response:
        end = urlsplit(response.geturl())
        if end.scheme != 'https' or end.hostname not in ('api.github.com', 'github.com',
                'release-assets.githubusercontent.com', 'objects.githubusercontent.com'):
            raise ValueError('更新重定向来源不受信任')
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError('更新文件超过大小限制')
        return data


def release_number(tag):
    match = re.fullmatch(r'desktop-(\d+)-(\d+)', tag or '')
    return tuple(map(int, match.groups())) if match else (0, 0)


def check_update(product, current):
    if product not in PRODUCTS:
        raise ValueError('Unknown product')
    release = json.loads(fetch_bytes(API, 1024 * 1024))
    tag = release.get('tag_name', '')
    if release.get('draft') or release.get('prerelease') or release_number(tag) == (0, 0):
        raise ValueError('最新版本不是可用的稳定桌面版')
    assets = {a['name']: a for a in release.get('assets', [])}
    if 'update-manifest.json' not in assets or PRODUCTS[product] not in assets:
        raise ValueError('此 Release 缺少自动更新清单；请等待新版或手动下载一次')
    manifest = json.loads(fetch_bytes(assets['update-manifest.json']['browser_download_url'], 65536, True))
    if manifest.get('schema') != 1 or manifest.get('repository') != REPOSITORY or manifest.get('tag') != tag:
        raise ValueError('更新清单与 Release 不一致')
    commit = manifest.get('source_commit', '')
    if not re.fullmatch('[0-9a-f]{40}', commit) or release.get('target_commitish') != commit:
        raise ValueError('更新清单缺少匹配的源码提交')
    info = manifest.get('assets', {}).get(PRODUCTS[product], {})
    digest, size = info.get('sha256', ''), info.get('size')
    if not re.fullmatch('[0-9a-f]{64}', digest) or type(size) is not int or not 1000 <= size <= MAX_EXE:
        raise ValueError('更新文件校验信息不合法')
    if assets[PRODUCTS[product]].get('size') != size:
        raise ValueError('Release 文件大小与清单不一致')
    url = assets[PRODUCTS[product]]['browser_download_url']
    trusted_url(url, True)
    available = (commit != current.get('source_commit') and
                 release_number(tag) > release_number(current.get('release_tag', '')))
    return {'available': available, 'tag': tag, 'source_commit': commit, 'product': product,
            'sha256': digest, 'size': size, 'url': url,
            'release_url': 'https://github.com/' + REPOSITORY + '/releases/tag/' + tag}


def stage_update(release, directory, current_executable=None, self_test=True):
    """Download and check new EXE before asking the running process to exit."""
    target = Path(current_executable or sys.executable).absolute()
    if target.name != PRODUCTS[release['product']] or not target.is_file():
        raise ValueError('请保留官方 EXE 文件名，并从可写目录运行')
    no_links(target)
    no_links(Path(directory).absolute())
    folder = Path(directory).absolute() / 'updates' / uuid.uuid4().hex
    folder.mkdir(parents=True, exist_ok=False)
    no_links(folder)
    data = fetch_bytes(release['url'], min(release['size'], MAX_EXE), True)
    if len(data) != release['size'] or hashlib.sha256(data).hexdigest() != release['sha256'] or data[:2] != b'MZ':
        raise ValueError('下载的 EXE 大小、SHA256 或文件头校验失败；原程序未修改')
    candidate = folder / 'payload.exe'
    candidate.write_bytes(data)
    if self_test:
        flag = '--smoke-test' if release['product'] == 'a' else '--self-test'
        result = subprocess.run([str(candidate), flag, '--data-dir', str(folder / 'self-test')],
            timeout=90, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env={**os.environ, 'PYINSTALLER_RESET_ENVIRONMENT': '1'},
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        marker = 'client-smoke.json' if release['product'] == 'a' else 'self-test.json'
        if result.returncode or not (folder / 'self-test' / marker).is_file():
            raise RuntimeError('新版 EXE 自检失败；原程序未修改')
    plan = {'product': release['product'], 'target': str(target), 'old_sha256': sha256(target),
            'sha256': release['sha256'], 'size': release['size'], 'tag': release['tag'],
            'data_directory': str(Path(directory).absolute()), 'wait_pids': [os.getpid()],
            'resume_agent': False}
    (folder / 'plan.json').write_text(json.dumps(plan), encoding='utf-8')
    return folder / 'plan.json'


def launch_helper(plan_path, wait_pids=(), resume_agent=False):
    path = Path(plan_path)
    plan = json.loads(path.read_text(encoding='utf-8'))
    plan.update(wait_pids=[os.getpid(), *wait_pids], resume_agent=bool(resume_agent))
    path.write_text(json.dumps(plan), encoding='utf-8')
    helper = path.parent / 'updater.exe'
    shutil.copy2(sys.executable, helper)
    subprocess.Popen([str(helper), '--apply-update', str(path)], stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env={**os.environ, 'PYINSTALLER_RESET_ENVIRONMENT': '1'},
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def wait_process(pid, deadline):
    import win32api, win32event
    try:
        process = win32api.OpenProcess(0x100000, False, pid)  # SYNCHRONIZE
    except Exception as exc:
        if getattr(exc, 'winerror', None) == 87:  # already exited
            return
        raise
    try:
        if win32event.WaitForSingleObject(process, max(0, int((deadline-time.monotonic())*1000))) != 0:
            raise TimeoutError('等待程序/代理退出超时；未强杀进程，原版本保留')
    finally:
        win32api.CloseHandle(process)


def replace_checked(candidate, target, expected_hash, old_hash, timeout=30):
    candidate, target = Path(candidate), Path(target)
    no_links(candidate)
    no_links(target)
    if sha256(candidate) != expected_hash or sha256(target) != old_hash:
        raise ValueError('更新前文件已变化；停止替换')
    # Stage beside the target so replacement is atomic even when LOCALAPPDATA
    # and the application live on different drives.
    incoming = target.with_name(target.stem + '.incoming-' + uuid.uuid4().hex[:8] + '.exe')
    with incoming.open('xb') as output, candidate.open('rb') as source:
        shutil.copyfileobj(source, output)
    if sha256(incoming) != expected_hash:
        incoming.unlink()
        raise ValueError('本地复制校验失败；原版本保留')
    backup = target.with_name(target.stem + '.previous-' + uuid.uuid4().hex[:8] + '.exe')
    deadline = time.monotonic() + timeout
    while True:
        try:
            target.replace(backup)
            break
        except PermissionError:
            if time.monotonic() >= deadline:
                raise PermissionError('原 EXE 仍被占用或目录不可写；没有替换')
            time.sleep(.25)
    try:
        incoming.replace(target)
        if sha256(target) != expected_hash:
            raise ValueError('替换后校验失败')
    except Exception:
        backup.replace(target)
        raise
    return backup


def apply_update(plan_path):
    """Local bootstrap mode, before any Tk/config/worker initialization."""
    path = Path(plan_path).absolute()
    no_links(path)
    plan = json.loads(path.read_text(encoding='utf-8'))
    directory = Path(plan['data_directory']).absolute()
    if path.name != 'plan.json' or path.parent.parent != directory / 'updates':
        raise ValueError('更新计划路径不合法')
    target = Path(plan['target']).absolute()
    if target.name != PRODUCTS.get(plan['product']) or not re.fullmatch('[0-9a-f]{64}', plan['sha256']):
        raise ValueError('更新目标不合法')
    result_path = directory / 'update-result.json'
    try:
        deadline = time.monotonic() + 180
        for pid in plan['wait_pids']:
            if type(pid) is not int or pid <= 0 or pid == os.getpid():
                raise ValueError('无效等待进程')
            wait_process(pid, deadline)
        backup = replace_checked(path.parent / 'payload.exe', target, plan['sha256'], plan['old_sha256'])
        command = [str(target), '--data-dir', str(directory)]
        if plan.get('restart_smoke_test'):
            marker = 'client-smoke.json' if plan['product'] == 'a' else 'gui-smoke.json'
            (directory / marker).unlink(missing_ok=True)
            command.append('--smoke-test')
        if plan['product'] == 'b' and plan.get('resume_agent'):
            command.append('--resume-agent')
        try:
            subprocess.Popen(command, env={**os.environ, 'PYINSTALLER_RESET_ENVIRONMENT': '1'},
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except Exception:
            backup.replace(target)
            raise
        result = {'ok': True, 'tag': plan['tag'], 'backup': str(backup)}
        result_path.write_text(json.dumps(result), encoding='utf-8')
        return 0
    except Exception as exc:
        result_path.write_text(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False), encoding='utf-8')
        return 1
