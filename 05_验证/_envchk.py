import ctypes, os, sys
HERE=os.path.dirname(os.path.abspath(__file__))
W,H=1920,1080
raw=os.path.join(HERE,'goldens','real','m00_in.raw')
def probe(dll, fn):
    d=ctypes.WinDLL(os.path.join(HERE,dll))
    f=getattr(d, fn)
    f.restype=ctypes.c_int
    arr=(ctypes.c_double*11)(0,0,0,0,0,0,0,0,0,0,0)
    arr[0]=100.0
    msg=ctypes.create_string_buffer(512)
    try:
        rc=f(b'C:/btwork/engine', raw.encode(), b'C:/Users/<user>/AppData/Local/Temp/_probe_out.raw',
             W,H, arr, 11, -1,1,0,1, msg, 512)
        print('%-22s %-16s rc=%d msg=%s' % (dll, fn, rc, msg.value.decode('utf-8','replace')[:90]))
    except Exception as e:
        print('%-22s %-16s EXC %s' % (dll, fn, e))
probe('nama_golden.dll','NamaGoldenRun')
probe('ref_golden.dll','RefGoldenRun')
