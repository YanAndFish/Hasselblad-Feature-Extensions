"""有界命令通道；不将命令、输出或秘密写入日志。"""
import sys,struct,secrets,time
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'x1d/wireless-flash/research'))
from mechanical_sync_session import CommandUsb,validate_interface,_reviewed_helpers,RESPONSE_HEADER
make,crc=_reviewed_helpers()
def command(text):
    if not 0<len(text.encode('ascii'))<=231 or '\n' in text:raise ValueError('command size')
    token=secrets.randbelow(0xffffffff)+1
    packet=bytearray(make(text));struct.pack_into('<I',packet,13,token);packet+=bytes(512-len(packet))
    t=CommandUsb(bytes(packet))
    try:
        if validate_interface(t.open())!=512:raise RuntimeError('interface')
        t.prepare()
        if t.write_query(512)!=512:raise RuntimeError('short request; no retry')
        for _ in range(3):
            r=t.read_with_timeout(15000)
            if len(r)!=512 or r[:5]!=RESPONSE_HEADER:raise RuntimeError('response route')
            b=r[5:257];kind,op,tag,check,status=struct.unpack_from('<5I',b)
            if tag!=token:continue
            if kind!=52 or op!=0 or check!=crc(b[16:]):raise RuntimeError('response integrity')
            if status:raise RuntimeError('remote command failed; output not logged')
            return b[20:].split(b'\0',1)[0].decode('ascii')
        raise RuntimeError('no matching reply; no retry')
    finally:
        if not all(t.close().values()):raise RuntimeError('closure')
