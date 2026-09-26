"""获授权后只读核对已安装 r7 与当前镜头；不对焦、不写 RAM。"""
import sys,json,hashlib,struct
from pathlib import Path
from datetime import datetime
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
assert Path.cwd().resolve()==ROOT
sys.path[:0]=[str(HERE),str(HERE.parent),str(HERE.parents[1]),str(ROOT/'x1d/tools')]
import runtime
from native_install import NativeContract
FIXED=HERE/'build/release/0039cec0'
EXPECTED='4622b37438b986c38ee404b92680b50a6d9abdd5f82cbb3a720d0c3d73205ace'

class ReadOnly:
    count=-1
    def __init__(self):
        self.m=json.loads((FIXED/'capture-manifest.json').read_text(encoding='utf8'))
        assert hashlib.sha256((FIXED/'candidate.bin').read_bytes()).hexdigest()==EXPECTED
        assert self.m['payload_sha256']==EXPECTED
        self.reads=set(range(self.m['state_start'],self.m['end'],4))
        self.reads.update(a for a,_,_ in self.m['emulatorOnlyHooks'])
        self.reads.update(range(0x2adc20,0x2adc44,4))
        self.reads.update((0x2adc78,0x6bcb7c,0x6bb46c,0x6bb598))
        self.identity=hashlib.sha256(json.dumps(sorted(self.reads)).encode()).hexdigest()
    def packet(self,kind,a=None,v=None,size=512):
        if kind not in ('read','version'):raise ValueError('read-only operation required')
        return NativeContract.packet(self,kind,a,v,size)
    reply=staticmethod(NativeContract.reply)

def run(live):
    c=ReadOnly()
    for a in c.reads:assert len(c.packet('read',a))==512
    for args in (('write',0x2adc20,0),('read',0),('read',0x2adc21)):
        try:c.packet(*args)
        except ValueError:pass
        else:raise AssertionError('denied request accepted')
    if not live:print(json.dumps({'offlineContractPassed':True,'maximumReads':len(c.reads)*2,'hardwareRequests':0}));return
    stamp=datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')
    trace=runtime.Trace(HERE/'recovery'/f'identity-read-{stamp}.trace.jsonl',c.identity)
    io=runtime.TracedIO(c,trace);snapshots=[]
    try:
        io.exchange('version')
        for _ in range(2):snapshots.append({hex(a):io.read(a) for a in sorted(c.reads)})
        report={'hardwareRequests':io.requests,'writeRequests':io.writes,'allHandlesClosed':io.closed,'snapshots':snapshots}
        path=HERE/'recovery'/f'identity-read-{stamp}.json'
        path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
        print(json.dumps(report))
    finally:
        trace.close()
        print(json.dumps({'requests':io.requests,'writes':io.writes,'closed':io.closed,'failed':io.failed}))

if __name__=='__main__':
    assert len(sys.argv)==2 and sys.argv[1] in ('report','read-authorized')
    run(sys.argv[1]=='read-authorized')
