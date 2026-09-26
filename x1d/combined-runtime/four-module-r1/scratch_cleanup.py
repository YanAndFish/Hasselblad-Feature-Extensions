"""核对 AF 已结束事务留下的缓存跳板，仅归零共用暂存区；不改 AF 或引闪代码。"""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,struct,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import session
c=session.capture
def expected():
    r,m,_=session.inspect_af.source()
    values={int(a):v for a,v in r['scratchBefore'].items()}
    events=session.inspect_af.SOURCE.with_suffix('.events.jsonl')
    last=None
    for line in events.read_text(encoding='utf-8').splitlines():
        event=json.loads(line);op=event['change'].get('lastCompleted')
        if op and op['kind']=='write' and op['address'] in values:
            assert op['result']=='request_reply_matched_handles_closed'
            values[op['address']]=op['value'];last=op
    # 最后一次 sync_hook 的目标端 ACK 是 1；主机写日志只记录清零请求。
    old=session.inspect_af.runtime.old
    assert values[c.DESC]==old.GATE_HOOK&~31 and values[c.DESC+4]==32 and values[c.DESC+8]==c.INVALIDATE_RANGE
    values[c.DESC+12]=1
    assert b''.join(struct.pack('<I',values[c.BASE+i]) for i in range(0,28,4))==old.THUNK
    return r,values
ALLOWED={a:{0} for a in range(c.BASE,c.BASE+64,4)}
ALLOWED.update({c.CB:{c.NOOP,c.CLEAN,c.INVALIDATE,c.ORIG_CB},c.ARG:{c.BASE,c.ORIG_ARG},c.SGIR:{c.SELF15}})
def preflight(io,values):
    io.exchange('version')
    for a,(mask,value) in c.IRQ_GUARDS.items():
        if io.read(a)&mask!=value:raise RuntimeError('scratch cleanup guard mismatch')
    from farm_diagnostic_binary import FarmApplication
    farm=FarmApplication().data
    for a in sorted(set(c.CACHE_CODE+c.HOOK_LINES+(0x214110,0x233c7c))):
        if io.read(a)!=struct.unpack_from('<I',farm,a-0x100000)[0]:raise RuntimeError('original cache/flash code mismatch')
    for a in c.ZERO_WORDS:
        if io.read(a)!=values.get(a,0):raise RuntimeError('scratch differs from completed AF transaction or flash arena occupied')
    if io.read(c.pre.AF_IDLE)&255:raise RuntimeError('AF busy')
class Cleanup(c.Loader):
    def write(self,a,v):
        if v not in ALLOWED.get(a,()):raise ValueError('outside cleanup write scope')
        super().write(a,v)
def clean(loader,values):
    preflight(loader.io,values)
    loader.record={'stage':'verified-af-cache-scratch-only','scratchBefore':values,'installed':False,'afCodeChanged':False,'flashCodeChanged':False}
    loader.save();loader.saved=True
    loader.clean_scratch()
    if any(loader.io.read(a) for a in range(c.BASE,c.BASE+64,4)) or loader.io.read(c.CB)!=c.ORIG_CB or loader.io.read(c.ARG)!=c.ORIG_ARG:raise RuntimeError('cleanup final mismatch')
    loader.record.update(stage='scratch-zero-original-callbacks-restored');loader.save()
def offline():
    r,values=expected()
    from farm_diagnostic_binary import FarmApplication
    f=FarmApplication().data
    class Model:
        def __init__(self,bad=False,fail=False):
            self.memory={a:struct.unpack_from('<I',f,a-0x100000)[0] for a in set(c.CACHE_CODE+c.HOOK_LINES+(0x214110,0x233c7c))}
            self.memory.update({a:v for a,(_,v) in c.IRQ_GUARDS.items()});self.memory.update({a:0 for a in c.ZERO_WORDS});self.memory.update(values)
            self.memory[c.pre.AF_IDLE]=0
            if bad:self.memory[c.BASE]^=1
            self.requests=0;self.writes=0;self.closed=True;self.failed=False;self.fail=fail
        def read(self,a):return self.memory[a]
        def exchange(self,kind,a=None,v=None):
            if self.failed:raise RuntimeError('no retry')
            self.requests+=1
            if kind=='version':return []
            assert kind=='write' and v in ALLOWED[a]
            self.writes+=1
            if self.fail:self.failed=True;raise RuntimeError('ambiguous write')
            if a!=c.SGIR:self.memory[a]=v
    class TestCleanup(Cleanup):
        def save(self):pass
    normal=Model();clean(TestCleanup(normal),values)
    bad=Model(bad=True)
    try:clean(TestCleanup(bad),values)
    except RuntimeError:pass
    else:raise AssertionError('unknown scratch accepted')
    assert bad.writes==0
    fail=Model(fail=True)
    try:clean(TestCleanup(fail),values)
    except RuntimeError:pass
    else:raise AssertionError('write uncertainty ignored')
    assert fail.writes==1
    proof={'passed':True,'sourceJournalLastSha256':r['journalAudit']['lastSha256'],'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'cleanupWrites':normal.writes,'unknownScratchRejectedBeforeWrite':True,'uncertainWriteNotRetried':True,'hardwareRequests':0}
    (HERE/'CodeTests/scratch-cleanup-validation.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof
def live():
    r,values=expected();proof=json.loads((HERE/'CodeTests/scratch-cleanup-validation.json').read_text())
    assert proof['passed'] and proof['sourceSha256']==hashlib.sha256(Path(__file__).read_bytes()).hexdigest() and proof['sourceJournalLastSha256']==r['journalAudit']['lastSha256']
    session.inspect_af.run(True)
    s=session.Session('scratch-health')
    assert s.command('held','/tmp/hbl-wireless-flash/formal-system-check --require-held')['output'].strip()=='system=2 suc=0 farm=0 pwr=0 ui-power=0 hold=1'
    loader=Cleanup();loader.path=c.HERE/'build'/('four-module-scratch-cleanup-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
    try:clean(loader,values)
    except BaseException:
        if loader.saved:loader.save()
        raise
    session.inspect_af.run(True)
    print(json.dumps({'scratchCleared':True,'afPreserved':True,'requests':loader.io.requests,'writes':loader.io.writes,'allHandlesClosed':loader.io.closed,'record':str(loader.path)}))
if __name__=='__main__':
    if sys.argv[1:]==['--clear-verified-af-scratch']:live()
    elif not sys.argv[1:]:print(json.dumps(offline()))
    else:raise SystemExit('unsupported args')
