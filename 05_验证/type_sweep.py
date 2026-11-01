# -*- coding: utf-8 -*-
"""面板磨皮=50，扫描 blur_type（0=高斯 1=双边 2=弱磨皮）。"""
import os, re, subprocess, sys
HERE = os.path.abspath(".")
PY = sys.executable

def run(bt):
    p = os.path.join(HERE, "extra_blur.txt")
    open(p, "w").write("blur_type=%d\n" % bt)
    env = os.environ.copy(); env["BEAUTY_EXTRA_PARAMS_FILE"] = p
    r = subprocess.run([PY, "probe_302.py"], cwd=HERE, env=env,
                       capture_output=True, text=True, timeout=240)
    if r.returncode != 0: return None
    a = subprocess.run([PY, "analyze_302.py"], cwd=HERE, env=env,
                       capture_output=True, text=True, timeout=180)
    rows = {}
    for line in a.stdout.splitlines():
        m = re.match(r"\s*(base|s50)\s+\S+\s+([0-9.]+)/\s*([0-9.]+)%\s+"
                     r"([0-9.]+)/\s*([0-9.]+)%\s+([0-9.]+)/\s*([0-9.]+)%", line)
        if m: rows[m.group(1)] = tuple(float(m.group(i)) for i in (3, 5, 7))
    return rows

for bt in (0, 1, 2):
    rows = run(bt)
    if not rows:
        print("  blur_type=%d  FAIL" % bt); continue
    print("  blur_type=%d  base %5.1f/%5.1f/%5.1f   s50 %5.1f/%5.1f/%5.1f"
          % (bt, rows["base"][0], rows["base"][1], rows["base"][2],
             rows["s50"][0], rows["s50"][1], rows["s50"][2]))
