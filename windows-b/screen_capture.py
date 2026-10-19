"""Opt-in SOLIDWORKS-window screenshots. Never fall back to the entire desktop."""
import ctypes
from ctypes import wintypes
import io
import json
import urllib.request


def capture_solidworks_window():
    import win32com.client
    import win32gui
    import win32ui
    from PIL import Image
    from solidworks_box import com_read
    sw = win32com.client.GetActiveObject('SldWorks.Application')
    frame = com_read(sw, 'Frame')
    try:
        hwnd = int(com_read(frame, 'GetHWndx64'))
    except Exception:
        hwnd = int(com_read(frame, 'GetHWnd'))
    if not hwnd or not win32gui.IsWindow(hwnd) or win32gui.IsIconic(hwnd):
        raise RuntimeError('SOLIDWORKS window is unavailable or minimized')
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width, height = right - left, bottom - top
    if width <= 0 or height <= 0 or width * height > 20_000_000:
        raise RuntimeError('Unsupported SOLIDWORKS window dimensions')
    dc_handle = win32gui.GetWindowDC(hwnd)
    source = win32ui.CreateDCFromHandle(dc_handle)
    memory = source.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    try:
        bitmap.CreateCompatibleBitmap(source, width, height)
        memory.SelectObject(bitmap)
        print_window = ctypes.windll.user32.PrintWindow
        print_window.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
        print_window.restype = wintypes.BOOL
        if not print_window(hwnd, memory.GetSafeHdc(), 2):
            raise RuntimeError('PrintWindow failed; no full-desktop fallback is allowed')
        picture = Image.frombuffer('RGB', (width, height), bitmap.GetBitmapBits(True), 'raw', 'BGRX', 0, 1)
        if all(high - low < 3 for low, high in picture.getextrema()):
            raise RuntimeError('Captured window is blank; check lock screen/GPU capture support')
        picture.thumbnail((1920, 1440))
        output = io.BytesIO()
        picture.save(output, format='JPEG', quality=80)
        return output.getvalue(), 'image/jpeg'
    finally:
        win32gui.DeleteObject(bitmap.GetHandle())
        memory.DeleteDC()
        source.DeleteDC()
        win32gui.ReleaseDC(hwnd, dc_handle)


def capture_and_upload(job_id, config):
    if not config.get('screenshots_enabled', False):
        raise PermissionError('B has not enabled SOLIDWORKS screenshot upload in its local settings')
    content, mime = capture_solidworks_window()
    request = urllib.request.Request(config['server_url'].rstrip('/') + f'/agent/jobs/{job_id}/artifacts',
        data=content, method='POST', headers={'Authorization': 'Bearer ' + config['token'], 'Content-Type': mime})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)
