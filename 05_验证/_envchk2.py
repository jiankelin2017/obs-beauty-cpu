import ctypes, os, sys
HERE=os.path.dirname(os.path.abspath(__file__))
W,H=1920,1080
raw=os.path.join(HERE,'goldens','real','m00_in.raw')
dll=sys.argv[1]; fn=sys.argv[2]
d=ctypes.WinDLL(os.path.join(HERE,dll))
f=getattr(d,fn); f.restype=ctypes.c_int
arr=(ctypes.c_double*11)(0,0,0,0,0,0,0,0,0,0,0); arr[0]=100.0
msg=ctypes.create_string_buffer(512)
rc=f(b'C:/btwork/engine', raw.encode(), os.path.join(os.path.expanduser("~"), "AppData/Local/Temp/_probe_out.raw").encode(),
       W,H,arr,11,-1,1,0,1,msg,512)
print('rc=%d msg=%s' % (rc, msg.value.decode('utf-8','replace')[:120]))
