import os, re, subprocess, sys
def run(env_extra):
    e = dict(os.environ); e.update(env_extra)
    out = subprocess.run([sys.executable, '_first.py'], capture_output=True, text=True, env=e).stdout
    v = [float(m) for m in re.findall(r'frame\d\s+ms=([0-9.]+)', out)]
    return v
for tag, env in (('无预热', {'BEAUTY_NO_PREWARM':'1'}), ('有预热', {})):
    f0, steady = [], []
    for _ in range(5):
        v = run(env)
        f0.append(v[0]); steady.extend(v[1:])
    f0.sort(); steady.sort()
    print('%s  frame0 min=%.2f med=%.2f | 稳态 min=%.2f med=%.2f'
          % (tag, f0[0], f0[len(f0)//2], steady[0], steady[len(steady)//2]))
