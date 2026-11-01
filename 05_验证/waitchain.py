# -*- coding: utf-8 -*-
"""用 Windows 等待链遍历（WCT）诊断 OBS 卡死：谁被谁阻塞。

不需要提权（同一用户进程即可 OpenThread / OpenProcess）。
用法：
  python waitchain.py [pid_or_name]
输出每个阻塞线程的等待链，例如：
  tid 8123 (obs64.exe) BLOCKED on CritSect  <- owned by tid 7000 (in fuai.dll)

地址→模块映射用进程内已加载模块基址，判断卡在哪个 DLL。
"""
import ctypes
import ctypes.wintypes as wt
import sys

# ---- WCT ----
WCT_MAX_NODE_COUNT = 16
WCT_OBJNAME_LENGTH = 128

WctCriticalSectionType = 1
WctSendMessageType = 2
WctMutexType = 3
WctAlpcType = 4
WctComType = 5
WctThreadWaitType = 6
WctProcessWaitType = 7
WctThreadIdType = 8
WctComActivationType = 9
WctUnknownType = 10
WctMaxType = 11

TYPE_NAME = {
    1: "CriticalSection", 2: "SendMessage", 3: "Mutex", 4: "Alpc",
    5: "Com", 6: "ThreadWait", 7: "ProcessWait", 8: "ThreadId",
    9: "ComActivation", 10: "Unknown",
}

STATE_NAME = {0: "Blocked", 1: "Owned", 2: "NotOwned", 3: "Abandoned", 4: "Unknown"}


class WAITCHAIN_NODE_INFO(ctypes.Structure):
    _fields_ = [
        ("ObjectType", wt.DWORD),
        ("ObjectStatus", wt.DWORD),
        ("ObjectName", wt.WCHAR * WCT_OBJNAME_LENGTH),
        ("Timeout", wt.ULONG),
        ("Alertable", wt.BOOL),
        # union: LockObject / ThreadObject / ProcessObject
        ("_u", ctypes.c_ulonglong),
    ]


advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)

advapi32.OpenThreadWaitChainSession.restype = ctypes.c_void_p
advapi32.OpenThreadWaitChainSession.argtypes = [wt.DWORD, wt.DWORD]
advapi32.CloseThreadWaitChainSession.argtypes = [ctypes.c_void_p]
advapi32.GetThreadWaitChain.restype = ctypes.c_bool
advapi32.GetThreadWaitChain.argtypes = [
    ctypes.c_void_p, wt.DWORD, wt.DWORD, wt.DWORD,
    ctypes.POINTER(WAITCHAIN_NODE_INFO), ctypes.POINTER(wt.DWORD),
]

THREAD_GET_CONTEXT = 0x0008
THREAD_QUERY_INFORMATION = 0x0040
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
MAX_PATH = 260


class MODULEENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD), ("th32ModuleID", wt.DWORD),
        ("th32ProcessID", wt.DWORD), ("GlblcntUsage", wt.DWORD),
        ("ProccntUsage", wt.DWORD), ("modBaseAddr", ctypes.POINTER(ctypes.c_char)),
        ("modBaseSize", wt.DWORD), ("hModule", wt.HANDLE),
        ("szModule", ctypes.c_char * 256), ("szExePath", ctypes.c_char * MAX_PATH),
    ]


def enum_modules(pid):
    """返回 [(name, base, size)]，用 CreateToolhelp32Snapshot。"""
    kernel32.CreateToolhelp32Snapshot.restype = wt.HANDLE
    kernel32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
    kernel32.Module32First.argtypes = [wt.HANDLE, ctypes.POINTER(MODULEENTRY32)]
    kernel32.Module32Next.argtypes = [wt.HANDLE, ctypes.POINTER(MODULEENTRY32)]
    TH32CS_SNAPMODULE = 0x00000008
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, pid)
    if snap == ctypes.c_void_p(-1).value or not snap:
        return []
    out = []
    me = MODULEENTRY32()
    me.dwSize = ctypes.sizeof(MODULEENTRY32)
    ok = kernel32.Module32First(snap, ctypes.byref(me))
    while ok:
        try:
            out.append((me.szModule.decode("mbcs", "replace"),
                        ctypes.cast(me.modBaseAddr, ctypes.c_void_p).value or 0,
                        me.modBaseSize))
        except Exception:
            pass
        ok = kernel32.Module32Next(snap, ctypes.byref(me))
    kernel32.CloseHandle(snap)
    out.sort(key=lambda x: x[1])
    return out


def module_of(addr, mods):
    for name, base, size in mods:
        if base and base <= addr < base + size:
            return name
    return "?"


def find_pid(target):
    """target 可以是 pid（数字）或进程名。"""
    try:
        return int(target)
    except (TypeError, ValueError):
        pass
    kernel32.CreateToolhelp32Snapshot.restype = wt.HANDLE
    TH32CS_SNAPPROCESS = 0x00000002

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD),
                    ("th32ProcessID", wt.DWORD), ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                    ("th32ModuleID", wt.DWORD), ("cntThreads", wt.DWORD),
                    ("th32ParentProcessID", wt.DWORD), ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wt.DWORD), ("szExeFile", ctypes.c_char * 260)]
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    pe = PROCESSENTRY32()
    pe.dwSize = ctypes.sizeof(PROCESSENTRY32)
    kernel32.Process32First.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
    kernel32.Process32Next.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
    res = []
    ok = kernel32.Process32First(snap, ctypes.byref(pe))
    while ok:
        nm = pe.szExeFile.decode("mbcs", "replace")
        if nm.lower() == str(target).lower():
            res.append(pe.th32ProcessID)
        ok = kernel32.Process32Next(snap, ctypes.byref(pe))
    kernel32.CloseHandle(snap)
    return res[0] if res else None


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "obs64.exe"
    pid = find_pid(target)
    if not pid:
        print("找不到进程:", target)
        return 1
    print("pid=%d" % pid)
    mods = enum_modules(pid)
    print("已加载模块 %d 个（含 %s）" % (
        len(mods), ", ".join(m[0] for m in mods if "nama" in m[0].lower() or "fuai" in m[0].lower())))

    # 枚举线程
    kernel32.CreateToolhelp32Snapshot.restype = wt.HANDLE
    TH32CS_SNAPTHREAD = 0x00000004

    class THREADENTRY32(ctypes.Structure):
        _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD),
                    ("th32ThreadID", wt.DWORD), ("th32OwnerProcessID", wt.DWORD),
                    ("tpBasePri", ctypes.c_long), ("tpDeltaPri", ctypes.c_long),
                    ("dwFlags", wt.DWORD)]
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    te = THREADENTRY32()
    te.dwSize = ctypes.sizeof(THREADENTRY32)
    kernel32.Thread32First.argtypes = [wt.HANDLE, ctypes.POINTER(THREADENTRY32)]
    kernel32.Thread32Next.argtypes = [wt.HANDLE, ctypes.POINTER(THREADENTRY32)]
    tids = []
    ok = kernel32.Thread32First(snap, ctypes.byref(te))
    while ok:
        if te.th32OwnerProcessID == pid:
            tids.append(te.th32ThreadID)
        ok = kernel32.Thread32Next(snap, ctypes.byref(te))
    kernel32.CloseHandle(snap)
    print("线程 %d 个" % len(tids))

    sess = advapi32.OpenThreadWaitChainSession(0, 0)
    if not sess:
        print("OpenThreadWaitChainSession 失败:", ctypes.get_last_error())
        return 1

    WCT_OUT_OF_PROC = 0x00000001
    blocked = 0
    for tid in tids:
        nodes = (WAITCHAIN_NODE_INFO * WCT_MAX_NODE_COUNT)()
        count = wt.DWORD(WCT_MAX_NODE_COUNT)
        is_cycle = wt.DWORD(0)
        okc = advapi32.GetThreadWaitChain(sess, 0, WCT_OUT_OF_PROC, tid,
                                          nodes, ctypes.byref(count))
        if not okc:
            continue
        n = min(count.value, WCT_MAX_NODE_COUNT)
        # 只看有阻塞语义的链
        chain = []
        for i in range(n):
            nd = nodes[i]
            chain.append("%s/%s%s" % (
                TYPE_NAME.get(nd.ObjectType, "?"),
                STATE_NAME.get(nd.ObjectStatus, "?"),
                (":" + nd.ObjectName) if nd.ObjectName else ""))
        if n <= 1:
            continue
        first = nodes[0]
        if first.ObjectStatus != 0:  # 0 = Blocked
            continue
        blocked += 1
        print("-" * 70)
        print("BLOCKED tid=%d  链长=%d  %s" % (tid, n, " <- ".join(chain)))
        if is_cycle.value:
            print("  *** 检测到死锁环 ***")
    advapi32.CloseThreadWaitChainSession(sess)
    print("=" * 70)
    print("阻塞线程数: %d / %d" % (blocked, len(tids)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
