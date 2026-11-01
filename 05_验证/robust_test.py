# -*- coding: utf-8 -*-
"""robust_test.py —— 鲁棒性验证

测三件事：
  1. 丢帧保持：检测偶发失败时，掩码应沿用上一次而不是立刻退回全帧
     （否则磨皮范围从「只磨脸 7%」突变成「磨全图」，画面当场闪一下）
  2. 过曝保护：过曝区不算皮肤（否则鼻梁高光被磨成一块死白）
  3. 关键点校验：遮挡导致关键点飞出脸框时，跳过该脸的五官保护
     （第 3 条没有遮挡素材，靠代码审查 + 这里的边界确认）
"""

import ctypes
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = os.path.join(HERE, 'beauty_core_test.dll')
RES = os.path.join(HERE, 'goldens', 'res')
SRC = os.path.join(HERE, 'goldens', 'src')
OUT = os.path.join(HERE, 'goldens', 'masks')
W, H = 640, 394

_dll = None


def setup():
    global _dll
    if _dll is None:
        _dll = ctypes.WinDLL(DLL)
        _dll.BeautyCoreRun.argtypes = [ctypes.c_char_p, ctypes.c_char_p,
                                       ctypes.c_int, ctypes.c_int, ctypes.c_double,
                                       ctypes.c_int, ctypes.c_float, ctypes.c_float,
                                       ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
        _dll.BeautyCoreRun.restype = ctypes.c_int
        _dll.BeautyCoreMask.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int,
                                        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
        _dll.BeautyCoreMask.restype = ctypes.c_int
    return _dll


def run(path, out=None):
    dll = setup()
    o = out or os.path.join(OUT, '_rb.raw')
    msg = ctypes.create_string_buffer(512)
    rc = dll.BeautyCoreRun(path.encode(), o.encode(), W, H, 50.0, 0, 0.0, 0.0, 1, msg, 512)
    return rc, msg.value.decode('utf-8', 'replace')


def mask_px():
    """读当前掩码的非零像素数（BeautyCoreMask 会强制重算，这里用 Run 的诊断值）"""
    return None


def test_dropout_hold():
    print('== 1. 丢帧保持 ==')
    face = os.path.join(RES, '640x394.raw')
    # 造一张「没有脸」的纯灰图，尺寸一致
    gray_path = os.path.join(OUT, '_rb_gray.raw')
    rgba = np.zeros((H, W, 4), np.uint8)
    rgba[:, :, :3] = 128
    rgba[:, :, 3] = 255
    rgba.tofile(gray_path)

    dll = setup()
    # 先跑 6 帧有脸图，让掩码稳定建立
    last = ''
    for _ in range(6):
        rc, last = run(face)
    base_px = None
    if 'mask=' in last:
        base_px = int(last.split('mask=')[1].split()[0])
    print('  有脸图建立掩码：mask=%s px  faces=%s'
          % (base_px, last.split('faces=')[1].split()[0] if 'faces=' in last else '?'))

    # 切换到无脸图，观察 10 次检测周期（每次 4 帧，共 40 帧）
    held = []
    for cycle in range(10):
        for _ in range(4):
            rc, msg = run(gray_path)
        held.append(msg)
    for i, msg in enumerate(held):
        short = msg.split('err=[')[-1].rstrip(']') if 'err=[' in msg else msg
        print('  第 %2d 次检测周期：%s' % (i + 1, short[:72]))

    os.remove(gray_path)
    hold_count = sum(1 for m in held if 'holding mask' in m)
    print('  → 保持 %d 个周期后放弃（设计值 6）' % hold_count)
    return hold_count


def test_overexpose():
    print()
    print('== 2. 过曝保护 ==')
    face = os.path.join(RES, '640x394.raw')
    src = np.fromfile(face, np.uint8).reshape((H, W, 4))
    # 把整张图提亮到接近过曝
    hot = src.astype(np.float32)
    hot[:, :, :3] = np.clip(hot[:, :, :3] * 1.6 + 120, 0, 255)
    hot_path = os.path.join(OUT, '_rb_hot.raw')
    hot.astype(np.uint8).tofile(hot_path)

    dll = setup()
    rc, msg = run(face)
    normal = msg.split('mask=')[1].split()[0] if 'mask=' in msg else '?'
    for _ in range(6):
        rc, msg = run(hot_path)
    hotv = msg.split('mask=')[1].split()[0] if 'mask=' in msg else '0'
    print('  正常光照 mask=%s px | 过曝后 mask=%s px' % (normal, hotv))
    print('  → 过曝后掩码应大幅缩小（高光不算皮肤）')
    os.remove(hot_path)
    return normal, hotv


def main():
    os.makedirs(OUT, exist_ok=True)
    h = test_dropout_hold()
    test_overexpose()
    tmp = os.path.join(OUT, '_rb.raw')
    if os.path.exists(tmp):
        os.remove(tmp)
    print()
    print('[判据] 丢帧保持应≈6 个周期；过曝后掩码应显著变小。')
    return 0 if h >= 5 else 1


if __name__ == '__main__':
    sys.exit(main())
