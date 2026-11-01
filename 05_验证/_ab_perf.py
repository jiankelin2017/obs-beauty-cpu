import ctypes, os, re, sys
import numpy as np
import low_path_test as L
dll=ctypes.WinDLL(L.DLL)
dll.BeautyCoreRun.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_int,ctypes.c_int,ctypes.c_double,ctypes.c_int,ctypes.c_float,ctypes.c_float,ctypes.c_int,ctypes.c_char_p,ctypes.c_int]
for n in ('BeautyCoreSetTone','BeautyCoreSetDetail'): getattr(dll,n).argtypes=[ctypes.c_double,ctypes.c_double]
dll.BeautyCoreSetClarityPanel.argtypes=[ctypes.c_double]; dll.BeautyCoreSetRegion.argtypes=[ctypes.c_int,ctypes.c_double]
MSG=ctypes.create_string_buffer(512)
def setup(mode):
    v = 100.0 if mode else 0.0
    dll.BeautyCoreSetClarityPanel(v); dll.BeautyCoreSetTone(v,v); dll.BeautyCoreSetDetail(v,v)
    for i in range(5): dll.BeautyCoreSetRegion(i,v)
tag=sys.argv[1]; W,H=(1280,720) if tag=='720p' else (1920,1080)
raw=os.path.join(L.RES,'%s.raw'%tag); tmp=os.path.join(L.OUT,'_ab.raw')
res={}
for mode in (False,True):
    setup(mode)
    for _ in range(4): dll.BeautyCoreRun(raw.encode(),tmp.encode(),W,H,50.0,0,0.0,0.0,1,MSG,512)
    best=1e9
    for _ in range(9):
        dll.BeautyCoreRun(raw.encode(),tmp.encode(),W,H,50.0,0,0.0,0.0,1,MSG,512)
        m=re.search(r'ms=([0-9.]+)',MSG.value.decode('ascii','replace'))
        if m: best=min(best,float(m.group(1)))
    res[mode]=best
print('%s  基线 %6.2f   全参数 %6.2f'%(tag,res[False],res[True]))
