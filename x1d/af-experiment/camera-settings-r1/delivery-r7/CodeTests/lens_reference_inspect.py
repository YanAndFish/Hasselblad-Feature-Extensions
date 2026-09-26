"""公开镜头固件的离线地址视图。"""
import sys,struct,re
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[5]
sys.path.insert(0,str(ROOT/'.research-cache/x1d-1.25.0/python'))
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB,CS_MODE_MCLASS
def ihex(f):
    mem={};base=0
    for line in f.read_text().splitlines():
        z=bytes.fromhex(line[1:]);assert sum(z)%256==0 and len(z)==z[0]+5
        a=int.from_bytes(z[1:3],'big')
        if z[3]==4:base=int.from_bytes(z[4:-1],'big')<<16
        elif z[3]==0:
            for j,v in enumerate(z[4:-1]):
                assert base+a+j not in mem
                mem[base+a+j]=v
        else:assert z[3] in (1,5)
    return mem
class View:
    def __init__(self,product):
        self.mem=ihex(Path(__file__).resolve().parent/f'output/lens-max-reference/{product}/artifact.hex')
        self.lo=min(self.mem);self.hi=max(self.mem)+1
        self.b=bytes(self.mem.get(a,255) for a in range(self.lo,self.hi))
        self.cs=Cs(CS_ARCH_ARM,CS_MODE_THUMB|CS_MODE_MCLASS);self.cs.skipdata=True
    def word(self,a):return struct.unpack_from('<I',self.b,a-self.lo)[0]
    def dis(self,a,n):return '\n'.join(f'{i.address:08x} {i.mnemonic:8} {i.op_str}' for i in self.cs.disasm(self.b[a-self.lo:a-self.lo+n],a))
if __name__=='__main__':
    v=View(sys.argv[1]);a=int(sys.argv[2],0) if len(sys.argv)>2 else v.word(0x60015004)&~1
    print(hex(v.word(0x60015004)),v.dis(a,int(sys.argv[3],0) if len(sys.argv)>3 else 256))
