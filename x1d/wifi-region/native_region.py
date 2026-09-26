"""X1D 1.25.0 fixed native ProdConfig/WifiRegion; no raw response logging."""
from pathlib import Path
import json, secrets, struct, sys, time
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'x1d/wireless-flash/research'))
from mechanical_sync_session import CommandUsb,validate_interface,_reviewed_helpers,REQUEST_HEADER,RESPONSE_HEADER
_,crc16=_reviewed_helpers()
def request(operation,token):
    if operation not in (1,2) or not 0<token<=0xffffffff:raise ValueError('fixed operation')
    b=bytearray(512);b[:5]=REQUEST_HEADER
    struct.pack_into('<III',b,5,49,operation,token)
    struct.pack_into('<I',b,25,13)
    # Fixed target EU=0; no configurable property or arbitrary value.
    struct.pack_into('<I',b,17,crc16(b[21:257]))
    return bytes(b)
def parse(raw,operation,token):
    if len(raw)!=512 or raw[:5]!=RESPONSE_HEADER:raise ValueError('response route')
    body=raw[5:257]
    cmd,op,echo,crc,status,index,value=struct.unpack_from('<7I',body)
    if (cmd,op,echo)!=(49,operation,token):raise ValueError('response correlation')
    if crc!=crc16(body[16:]) or status!=0:raise ValueError('response integrity or status')
    if operation==2 and (index!=13 or value not in (0,1,2,3)):raise ValueError('region response')
    return value if operation==2 else None
def call(operation):
    token=secrets.randbelow(0xffffffff)+1;t=CommandUsb(request(operation,token));result=None
    try:
        if validate_interface(t.open())!=512:raise ValueError('USB interface')
        t.prepare()
        if t.write_query(512)!=512:raise ValueError('short write; no retry')
        deadline=time.monotonic()+15
        for _ in range(3):
            remaining=int((deadline-time.monotonic())*1000)
            if remaining<=0:raise TimeoutError('no retry')
            raw=t.read_with_timeout(remaining)
            if len(raw)==512 and raw[:5]==RESPONSE_HEADER and struct.unpack_from('<I',raw,13)[0]!=token:continue
            result=parse(raw,operation,token);break
        else:raise ValueError('no correlated reply; no retry')
    finally:
        if not all(t.close().values()):raise ValueError('USB handle closure')
    return result
def tests():
    for op in (1,2):
        q=request(op,123);assert q[29:257]==bytes(228)
        r=bytearray(q);r[:5]=RESPONSE_HEADER
        if op==2:struct.pack_into('<I',r,29,2)
        struct.pack_into('<I',r,17,crc16(r[21:257]))
        assert parse(bytes(r),op,123)==(2 if op==2 else None)
        for at in (0,5,9,13,17,21,25):
            bad=bytearray(r);bad[at]^=1
            try:parse(bytes(bad),op,123)
            except ValueError:pass
            else:raise AssertionError('invalid reply accepted')
    print('native-region-contract-tests-passed')
if __name__=='__main__':
    if sys.argv[1:]==['--read']:print(json.dumps({'nativeRegion':call(2),'writes':0}))
    elif not sys.argv[1:]:tests()
    else:raise SystemExit('unsupported; live write requires separate verified transaction')
