# -*- coding: utf-8 -*-
"""探测 bundle 是否接受 blur_scale / heavy_blur 等连续强度参数。"""
import os, re, subprocess, sys
HERE = os.path.abspath("."); PY = sys.executable

def run(lines, tag):
    p = os.path.join(HERE, "extra_blur.txt")
    open(p, "w").write("\n".join(lines) + "\n")
    env = os.environ.copy(); env["BEAUTY_EXTRA_PARAMS_FILE"] = p
    r = subprocess.run([PY, "probe_302.py"], cwd=HERE, env=env,
                       capture_output=True, text=True, timeout=240)
    if r.returncode != 0:
        print("  %-22s FAIL" % tag); return
    a = subprocess.run([PY, "analyze_302.py"], cwd=HERE, env=env,
                       capture_output=True, text=True, timeout=180)
    for line in a.stdout.splitlines():
        m = re.match(r"\s*base\s+\S+\s+([0-9.]+)/\s*([0-9.]+)%\s+"
                     r"([0-9.]+)/\s*([0-9.]+)%\s+([0-9.]+)/\s*([0-9.]+)%", line)
        if m:
            print("  %-22s base %5.1f/%5.1f/%5.1f"
                  % (tag, float(m.group(2)), float(m.group(4)), float(m.group(6))))
            return
    print("  %-22s no-parse" % tag)

run(["blur_level=3.0"], "baseline lv3.0")
run(["blur_level=3.0", "blur_scale=0.2"], "blur_scale=0.2")
run(["blur_level=3.0", "blur_scale=1.0"], "blur_scale=1.0")
run(["blur_level=3.0", "heavy_blur=1"], "heavy_blur=1")
run(["blur_level=3.0", "nonskin_blur_scale=1.0"], "nonskin_scale=1.0")
