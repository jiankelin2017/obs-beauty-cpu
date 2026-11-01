# -*- coding: utf-8 -*-
"""验证运动时 srcT 的 β 是否升到 1（即 3.0.10 在运动时与 3.0.8 逐位相同）。

原理：磨皮 100（t=1）时 bgraToRgbaBlend 走纯交换分支，输出就是 SDK 的原始
结果 sdk。磨皮 50（t=0.5）时
    3.0.8/3.0.9  out = 0.5·src + 0.5·sdk
    3.0.10      out = 0.5·srcT + 0.5·sdk,   srcT = β·src + (1-β)·srcT
若运动时 β 命中 1，则 srcT = src，两者应当**逐位相同**。
（掩码内 m=255 的像素上 applyRegionEffects 是恒等变换，所以直接可比；
 掩码外会被还原成 src，不可比。）

两个必须踩住的坑：
  1) 磨皮 100 会下发 blur_level=6.0、磨皮 50 只下发 3.0 —— SDK 模糊强度不同，
     「sdk」就不是同一条链路的输出。用 BEAUTY_EXTRA_PARAMS_FILE 钉死 blur_level。
  2) 两次运行必须在**不同进程**里做。同进程连跑会让 SDK 的跨帧时序状态被第一次
     运行污染（第二次第 0 帧接的是第一次最后一帧的跟踪状态），残留可达 1 级。

用法：
  python motion_beta.py <dll> <输入目录> [帧数]           # 全流程（两个子进程）
  python motion_beta.py --one <dll> <indir> <panel> <outdir> <count>
"""
import ctypes
import os
import struct
import subprocess
import sys

HERE = os.path.abspath(".")
sys.path.insert(0, HERE)
import flicker_probe as fp

ASSET_DIR = fp.ASSET_DIR
KNOWN = {1008640: (640, 394), 2594784: (1074, 604)}


def detect(indir):
    sz = os.path.getsize(os.path.join(indir, "seq_000.raw"))
    if sz not in KNOWN:
        raise SystemExit("未知帧尺寸 %d，请在 KNOWN 里补上 (w,h)" % sz)
    return KNOWN[sz]


def run_one(dll, indir, panel, outdir, count):
    os.makedirs(outdir, exist_ok=True)
    open(os.path.join(HERE, "panel.txt"), "w").write(panel)
    import os as _os
    _os.environ.pop('BEAUTY_EXTRA_PARAMS_FILE', None)
    # 不再用诊断注入口钉 blur_level：那条路会在同一帧里先写面板值再写覆盖值，
    # 实测这个瞬态会让 SDK 输出差到 13 级（ctl2 对照），污染比较。
    # 改成给对照组换一个只把 P_BLUR 上限设为 3.0 的 DLL，让两次运行都**原生**
    # 落在 blur_level=3.0 上，零瞬态。
    open(os.path.join(HERE, "dump_mask.txt"), "w").write("on")
    w, h = detect(indir)
    d = ctypes.WinDLL(os.path.abspath(dll))
    d.LegacySeqTest.restype = ctypes.c_int
    d.LegacySeqTest.argtypes = ([ctypes.c_char_p] * 3 + [ctypes.c_int] * 3 +
                              [ctypes.c_double] * 2 +
                              [ctypes.c_char_p, ctypes.c_int])
    msg = ctypes.create_string_buffer(2048)
    ret = d.LegacySeqTest(ASSET_DIR.encode("ascii"), indir.encode("ascii"),
                        outdir.encode("ascii"), w, h, count, 50.0, 50.0,
                        msg, 2048)
    os.remove(os.path.join(HERE, "dump_mask.txt"))
    return ret, msg.value.decode("utf-8", "replace"), (w, h)


def mask_interior(w, h, dumpdir):
    """只取**双线性 mv 恰好 255** 的像素。

    两个必须照抄引擎的地方，否则会混进取整假象：
    1) buildMaskMap 的索引是**端点对齐** x*(mw-1)/(w-1)，不是 x*mw//w；
    2) m256 = mv + (mv>>7)，mv=254 时 m256=255，`d*255>>8` 会把 d=1 截成 0，
       输出比预测低 1 级。实测那 610 个残差全是 -1 且 sdk-src=1，就是这个。
    所以要求 2x2 邻域（按端点对齐取）全 255，mv 才恒为 255、m256=256、
    applyRegionEffects 对这三路是恒等变换。
    """
    dumps = sorted(f for f in os.listdir(dumpdir) if f.startswith("mask_dump_"))
    if not dumps:
        raise SystemExit("没有 mask_dump_*.raw")
    d = open(os.path.join(dumpdir, dumps[-1]), "rb").read()
    mw, mh = struct.unpack_from("<ii", d, 0)
    n = mw * mh
    soft = d[8 + n:8 + 2 * n]

    def axis(v, mv, vv):
        """照抄 buildMaskMap：端点对齐 + 8bit 小数。"""
        if mv > 1 and vv > 1:
            q = (v * (mv - 1) * 65536) // (vv - 1)
            i0 = q >> 16
            if i0 >= mv - 1:
                i0 = mv - 1
            return i0, min(i0 + 1, mv - 1)
        return 0, 0

    idx = []
    for y in range(h):
        j0, j1 = axis(y, mh, h)
        for x in range(w):
            i0, i1 = axis(x, mw, w)
            if (soft[j0 * mw + i0] == 255 and soft[j0 * mw + i1] == 255 and
                    soft[j1 * mw + i0] == 255 and soft[j1 * mw + i1] == 255):
                idx.append((y * w + x) * 4)
    return idx


def child():
    _, _flag, dll, indir, panel, outdir, count = sys.argv
    ret, msg, dim = run_one(dll, indir, panel, outdir, int(count))
    print("%s ret=%d %s %s" % (panel, ret, msg, dim))
    return 0


def main():
    if sys.argv[1] == "--one":
        return child()

    dll = sys.argv[1]
    indir = os.path.abspath(sys.argv[2])
    count = int(sys.argv[3]) if len(sys.argv) > 3 else 8
    py = sys.executable
    me = os.path.abspath(__file__)

    # 对照组用 b3 DLL（P_BLUR 上限 3.0）：面板 100 -> t=1 且 blur_level=3.0
    dlls = (("mb_100", "0:100", os.path.join(HERE, "legacy_engine_test_b3.dll")),
            ("mb_050", "0:50", dll))
    for tag, panel, usedll in dlls:
        outdir = os.path.join(HERE, "flick", tag)
        # 每个配置一个独立进程；掩码转储路径在钩子里写死，跑完立刻搬走隔离
        dump = os.path.join(HERE, "flick", "dump_" + tag)
        os.makedirs(dump, exist_ok=True)
        for f in os.listdir(HERE):
            if f.startswith("mask_dump_"):
                os.remove(os.path.join(HERE, f))
        r = subprocess.run([py, me, "--one", usedll, indir, panel, outdir, str(count)],
                           cwd=HERE,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for f in os.listdir(HERE):
            if f.startswith("mask_dump_"):
                dst = os.path.join(dump, f)
                if os.path.exists(dst):
                    os.remove(dst)
                os.rename(os.path.join(HERE, f), dst)
        tail = [l for l in r.stdout.decode("utf-8", "replace").splitlines()
                if l.startswith("0:")]
        print("  ".join(tail) if tail else "子进程失败：%s"
              % r.stdout.decode("utf-8", "replace")[-400:])

    idx = mask_interior(*detect(indir), os.path.join(HERE, "flick", "dump_mb_100"))
    print("掩码内部像素 %d（取自 t=1 那次运行的转储）" % len(idx))

    print("帧   逐位相同?  最大差   平均差")
    bad = 0
    for k in range(count):
        sdk = open(os.path.join(HERE, "flick", "mb_100", "seq_%03d.raw" % k), "rb").read()
        out = open(os.path.join(HERE, "flick", "mb_050", "seq_%03d.raw" % k), "rb").read()
        src = open(os.path.join(indir, "seq_%03d.raw" % k), "rb").read()
        same = True
        mx = acc = 0
        cnt = 0
        for o in idx[::5]:
            for c in range(3):
                p = o + c
                pred = (src[p] + sdk[p] + 1) >> 1
                d = abs(out[p] - pred)
                cnt += 1
                if d:
                    same = False
                    mx = max(mx, d)
                    acc += d
        if not same:
            bad += 1
        print("  %-3d %-9s %-8d %-8.4f" % (k, "是" if same else "否", mx, acc / cnt))
    print("结论：%d/%d 帧与 3.0.8 公式逐位相同 → %s"
          % (count - bad, count,
             "运动时 β=1，没有引入时序平滑、无拖影风险" if bad == 0
             else "运动时 β<1，EMA 生效，需要评估拖影"))


if __name__ == "__main__":
    sys.exit(main())
