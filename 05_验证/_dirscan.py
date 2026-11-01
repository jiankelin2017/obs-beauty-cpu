import ctypes, os, sys
import numpy as np
import low_path_test as L
H,W=394,640
dll=ctypes.WinDLL(L.DLL)
dll.BeautyCoreRun.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_int,ctypes.c_int,ctypes.c_double,ctypes.c_int,ctypes.c_float,ctypes.c_float,ctypes.c_int,ctypes.c_char_p,ctypes.c_int]
for n in ("BeautyCoreSetTone","BeautyCoreSetDetail"): getattr(dll,n).argtypes=[ctypes.c_double,ctypes.c_double]
dll.BeautyCoreSetClarityPanel.argtypes=[ctypes.c_double]; dll.BeautyCoreSetRegion.argtypes=[ctypes.c_int,ctypes.c_double]
for n in ("BeautyCoreSetTone","BeautyCoreSetDetail"): getattr(dll,n)(0,0)
dll.BeautyCoreSetClarityPanel(0)
for i in range(5): dll.BeautyCoreSetRegion(i,0.0)
out=os.path.join(L.OUT,'_ds.raw'); MSG=ctypes.create_string_buffer(512)
dll.BeautyCoreRun(os.path.join(L.RES,'640x394.raw').encode(),out.encode(),W,H,50.0,0,0.0,0.0,1,MSG,512)
def Y(a):
    a=a[:,:,:3].astype(np.float32); return 0.299*a[:,:,0]+0.587*a[:,:,1]+0.114*a[:,:,2]
src=Y(np.fromfile(os.path.join(L.RES,'640x394.raw'),dtype=np.uint8).reshape((H,W,4)))
sp=os.path.join('goldens','flat','blur050_bt0'); f=[x for x in os.listdir(sp) if x.endswith('.raw')]
sdk=Y(np.fromfile(os.path.join(sp,f[0]),dtype=np.uint8).reshape((H,W,4)))
cur=Y(np.fromfile(out,dtype=np.uint8).reshape((H,W,4)))
BX,BY,BW_,BH_=276.4,84.8,111.3,140.8
m=np.zeros((H,W),bool); m[int(BY):int(BY+BH_),int(BX):int(BX+BW_)]=True
ds=(sdk-src)[m]; d=(cur-src)[m]
k=float((d*ds).sum()/max((ds*ds).sum(),1e-9)); c=float(np.corrcoef(d,ds)[0,1])
res=float((d-k*ds).std())
print('%-26s corr=%.3f  k=%.2f  残差σ=%.2f  改动σ=%.2f'%(os.environ.get('TAG','?'),c,k,res,d.std()))
