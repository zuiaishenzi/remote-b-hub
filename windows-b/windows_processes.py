"""Read-only native process/session checks. No WMI, shell, COM or elevation."""
import ctypes
from ctypes import wintypes
import os


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
                ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.c_size_t),
                ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
                ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', wintypes.LONG),
                ('dwFlags', wintypes.DWORD), ('szExeFile', wintypes.WCHAR * 260)]


def kernel():
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    api.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    for name in ('Process32FirstW', 'Process32NextW'):
        method = getattr(api, name)
        method.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
        method.restype = wintypes.BOOL
    api.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    api.ProcessIdToSessionId.restype = wintypes.BOOL
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    return api


def process_snapshot():
    api = kernel()
    handle = api.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS only
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        found = api.Process32FirstW(handle, ctypes.byref(entry))
        result = []
        while found:
            result.append((entry.th32ProcessID, entry.szExeFile))
            found = api.Process32NextW(handle, ctypes.byref(entry))
        error = ctypes.get_last_error()
        if error != 18:  # ERROR_NO_MORE_FILES is the only valid end of enumeration
            raise ctypes.WinError(error)
        return result
    finally:
        api.CloseHandle(handle)


def process_session(pid=None):
    value = wintypes.DWORD()
    if not kernel().ProcessIdToSessionId(os.getpid() if pid is None else pid, ctypes.byref(value)):
        raise ctypes.WinError(ctypes.get_last_error())
    return value.value


def processes_in_session(executable_name, session):
    return [pid for pid, name in process_snapshot()
            if name.casefold() == executable_name.casefold() and process_session(pid) == session]
