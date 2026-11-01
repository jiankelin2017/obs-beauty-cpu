import ctypes, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
dll = ctypes.WinDLL(os.path.join(HERE, sys.argv[1] if len(sys.argv)>1 else 'beauty_core_test.dll'))
dll.BeautyCoreRun.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_int,ctypes.c_int,ctypes.c_double,ctypes.c_int,ctypes.c_float,ctypes.c_float,ctypes.c_int,ctypes.c_char_p,ctypes.c_int]
dll.BeautyCoreRun.restype=ctypes.c_int
dll.BeautyCoreSetPerf.argtypes=[ctypes.c_int,ctypes.c_int]
RAW=os.path.join(HERE,'goldens','real','m00_in.raw'); TMP=os.path.join(HERE,'_f_out.raw')
msg=ctypes.create_string_buffer(512)
dll.BeautyCoreSetPerf(0,1)
for i in range(8):
    dll.BeautyCoreRun(RAW.encode(),TMP.encode(),1920,1080,95.0,0,0.0,0.0,1,msg,512)
    t=msg.value.decode('ascii','replace')
    m=re.search(r'ms=([0-9.]+)',t)
    print('frame%d  ms=%s  %s'%(i, m.group(1) if m else '?', t[:90]))
