# -*- coding: utf-8 -*-
"""扫描 50 档磨皮的实际 SDK blur_level，观察细节保留率。

用 BEAUTY_EXTRA_PARAMS_FILE 每帧覆盖 blur_level（在面板参数之后下发），
这样不改生产映射也能测不同实际强度。
"""
import os
import re
import subprocess
import sys

HERE = os.path.abspath(".")
PY = sys.executable


def run(level):
    p = os.path.join(HERE, "extra_blur.txt")
    with open(p, "w") as f:
        f.write("blur_level=%.2f\n" % level)
    env = os.environ.copy()
    env["BEAUTY_EXTRA_PARAMS_FILE"] = p
    r = subprocess.run([PY, "probe_302.py"], cwd=HERE, env=env,
                       capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        return None
    a = subprocess.run([PY, "analyze_302.py"], cwd=HERE, env=env,
                       capture_output=True, text=True, timeout=120)
    rows = {}
    for line in a.stdout.splitlines():
        m = re.match(r"\s*(base|s50)\s+\S+\s+([0-9.]+)/\s*([0-9.]+)%\s+"
                     r"([0-9.]+)/\s*([0-9.]+)%\s+([0-9.]+)/\s*([0-9.]+)%",
                     line)
        if m:
            rows[m.group(1)] = tuple(float(m.group(i)) for i in (3, 5, 7))
    return rows


def main():
    print("面板磨皮=50，扫描实际 blur_level；保留率 r1/r2/r3")
    for lv in (0.02, 0.1, 0.3, 0.6, 1.0):
        rows = run(lv)
        if not rows:
            print("  %.1f  FAIL" % lv)
            continue
        print("  blur_level=%.1f  base %5.1f/%5.1f/%5.1f   s50 %5.1f/%5.1f/%5.1f"
              % (lv, rows["base"][0], rows["base"][1], rows["base"][2],
                 rows["s50"][0], rows["s50"][1], rows["s50"][2]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
