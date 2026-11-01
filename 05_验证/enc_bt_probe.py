"""enc_bt_probe.py — 用产品那个**加密** bundle 实测 blur_type 裸默认档。

背景：此前"裸默认 = bt2"是用明文 bundle（ai_face_processor_pc_plain.bundle）测的。
产品实际加载的是加密 bundle（md5 a3bef0d1183fe9c7567ccc8fe89c9eab，23,353,677 B），
两者差 44 字节，默认参数表可能不同，必须单独测。

用法：
  python enc_bt_probe.py <bt> <outdir>
    bt = -1  表示不下发（走 legacy_engine.cpp:1926 的守卫）
    bt = 0/1/2  显式下发
每个 bt 必须在**独立进程**里跑（避免 DLL 跨状态污染）。

只读：读 bundle / auth_package.bin，输出 raw 到 outdir，不改任何已装文件。
"""
import ctypes, os, sys, json, hashlib

BT = int(sys.argv[1])
OUTDIR = sys.argv[2] if len(sys.argv) > 2 else 'goldens_encrypted'

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = r'D:\插件\OBS美颜\04_依赖与SDK\installer-stage'   # 加密 bundle + auth_package.bin
SRC = os.path.join(HERE, 'goldens_legacy', 'flat', 'blur000_bt1', 'out.raw')  # blur=0 → 源
W, H = 640, 394
PANEL = [100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]   # 只开磨皮=100

os.makedirs(OUTDIR, exist_ok=True)

dll = ctypes.WinDLL(os.path.join(HERE, 'ref_golden.dll'))
fn = dll.RefGoldenRun
fn.restype = ctypes.c_int
fn.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
               ctypes.c_int, ctypes.c_int,
               ctypes.POINTER(ctypes.c_double), ctypes.c_int,
               ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
               ctypes.c_char_p, ctypes.c_int]

arr = (ctypes.c_double * len(PANEL))(*[float(x) for x in PANEL])
final = os.path.join(OUTDIR, 'out_bt%d.raw' % BT)
msg = ctypes.create_string_buffer(1024)

rc = -1
for i in range(3):                     # warmup 2 次 + 正式 1 次，取最后一次
    msg.value = b''
    rc = fn(ENGINE_DIR.encode('mbcs'), SRC.encode('mbcs'), final.encode('mbcs'),
            W, H, arr, len(PANEL),
            BT, 1, 0, 1,           # blurType, skinDetect, smoothMode, resetSlot
            msg, 1024)
    text = msg.value.decode('mbcs', 'replace')
    print('[pass %d] rc=%d  %s' % (i, rc, text))

if rc == 0:
    data = open(final, 'rb').read()
    print('OUT %s  size=%d  md5=%s' % (final, len(data), hashlib.md5(data).hexdigest()))
    json.dump({'bt': BT, 'rc': rc, 'msg': msg.value.decode('mbcs', 'replace'),
               'md5': hashlib.md5(data).hexdigest(), 'size': len(data),
               'engine_dir': ENGINE_DIR, 'src': SRC, 'panel': PANEL,
               'bundle_md5': 'a3bef0d1183fe9c7567ccc8fe89c9eab'},
              open(os.path.join(OUTDIR, 'meta_bt%d.json' % BT), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)
dll.RefGoldenRelease()
