"""装载事务联合原厂等待/分配器执行与严格缓存模型，USB 为固定报文替身。"""
import copy,hashlib,json,struct,sys,time,unittest
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
from native_install import *
from native_loader import NativeIO
from native_hold import query as hold_query,SUCCESS,helpers as hold_helpers
from test_native_task_wake import NativeWake,FARM
from unicorn.arm_const import *

OUT=HERE/'build/native-capture-r1/002bacc0'
RELOC=json.loads((OUT/'capture-manifest.json').read_text(encoding='utf-8'));BLOB=(OUT/'candidate.bin').read_bytes()

class Journal:
    def __init__(self):self.record={'inFlight':None,'sequence':0};self.events=[];self.failed=False;self.reject=None
    def persist(self,r):
        if self.reject and self.reject(r):self.failed=True;raise OSError('injected durable journal failure')
        self.events.append({k:r.get(k) for k in ('phase','sequence','inFlight','cacheInFlight')})
    def begin(self,phase,operation):
        if self.failed or self.record.get('inFlight') is not None:raise RuntimeError('journal stopped')
        r=dict(self.record);r['phase']=phase;r['sequence']+=1;r['inFlight']=operation
        self.persist(r);self.record=r
    def complete(self):
        r=dict(self.record);r['inFlight']=None;self.persist(r);self.record=r

class Wake(NativeWake):
    def hook(self,u,a,size,data):
        if self.phase=='owned-probe':
            assert self.owned[0]<=a<self.owned[1];self.visited.add(a);return
        super().hook(u,a,size,data)
    def probe(self,address,argument,bounds):
        u=self.u;before=u.context_save();self.owned=bounds;phase=self.phase;self.phase='owned-probe'
        u.reg_write(UC_ARM_REG_CPSR,0x1f);u.reg_write(UC_ARM_REG_SP,0x80ffe0)
        u.reg_write(UC_ARM_REG_LR,0x800000);u.reg_write(UC_ARM_REG_R0,argument)
        u.emu_start(address,0x800000,count=5000)
        assert u.reg_read(UC_ARM_REG_PC)==0x800000 and u.reg_read(UC_ARM_REG_SP)==0x80ffe0
        u.context_restore(before);self.phase=phase

class Packet:
    def __init__(self,owner,kind,a,v):self.owner=owner;self.kind=kind;self.a=a;self.v=v;self.result=None
    def open(self):self.owner.opens+=1;return 512
    def prepare(self):pass
    def write_query(self,size):
        o=self.owner;assert size==512;o.c.packet(self.kind,self.a,self.v,size)
        selected=o.fault and o.fault(o.phase,self.kind,self.a,self.v)
        if selected=='before':raise OSError('injected before dispatch')
        self.result=o.effect(self.kind,self.a,self.v)
        if selected=='after':raise OSError('injected ambiguous completed effect')
        return size
    def read_reply(self,size):
        raw=bytearray(size)
        if self.kind=='version':
            raw[:4]=bytes.fromhex('0e000108')
            for a,v in zip((4,68,132),VERSIONS):raw[a:a+len(v)]=v.encode('ascii')
        else:
            raw[:4]=bytes.fromhex('f5000108' if self.kind=='read' else 'f3000108')
            if self.kind=='read':struct.pack_into('<I',raw,4,self.result)
        return bytes(raw)
    def close(self):self.owner.closes+=1;return {'usb':True,'file':True}

def hold_reply(token,output=SUCCESS,exit_code=0):
    _,crc,_,header=hold_helpers();body=bytearray(252)
    struct.pack_into('<5I',body,0,52,0,token,0,exit_code)
    body[20:20+len(output)]=output;struct.pack_into('<I',body,12,crc(body[16:]))
    return header+bytes(body)+bytes(255)

class HoldPacket(Packet):
    def __init__(self,owner,packet,token):
        super().__init__(owner,'hold_check',0,token);self.packet=packet;self.token=token;self.sent=False
    def write_query(self,size):
        o=self.owner;assert size==512 and self.packet==hold_query(self.token)
        assert o.transfer_active and not o.closed and o.cpu.word(CB)==ORIG_CB and o.cpu.word(ARG)==ORIG_ARG
        assert not (o.cpu.word(PENDING)|o.cpu.word(ACTIVE))&0x8000
        assert not o.journal or o.journal.record.get('cacheInFlight') is None
        self.sent=True;o.effects.append((o.phase,'hold_check',0,self.token))
        selected=o.fault and o.fault(o.phase,'hold_check',0,self.token)
        if selected:raise OSError('injected hold dispatch ambiguity')
        return size
    def read_reply(self,size):return hold_reply(self.token)

class ModelIO(NativeIO):
    is_hardware=False
    def __init__(self,c):
        super().__init__(c);self.cpu=Wake();u=self.cpu.u
        u.mem_write(c.bootstrap['base'],bytes(len(c.bootstrap_blob)))
        for a,(old,new) in c.bootstrap_hooks.items():self.cpu.put(a,old)
        u.mem_map(0xf8f00000,0x2000)
        for a,(mask,value) in c.guards.items():self.cpu.put(a,value)
        for a,value in c.flash_expected.items():self.cpu.put(a,value)
        self.cpu.block_af()
        self.clean={};self.visible={};self.effects=[];self.opens=0;self.closes=0
        self.fault=None;self.suppress_probe=False;self.suppress_wake=False
    def transport(self,kind,a,v):return Packet(self,kind,a,v)
    def hold_transport(self,packet,token):return HoldPacket(self,packet,token)
    def interface_size(self,snapshot):assert snapshot==512;return 512
    def effect(self,kind,a,v):
        self.effects.append((self.phase,kind,a,v))
        if kind=='version':return VERSIONS
        if kind=='read':
            if a==self.c.count and self.cpu.word(WAKE_HOOK)==self.c.bootstrap_hooks[WAKE_HOOK][1] and not self.suppress_wake:
                return self.cpu.request(schedule_at_svc=True)
            return self.cpu.word(a)
        if a==SGIR:self.sgi();return 0
        self.cpu.put(a,v);return 0
    def cache(self,start,size,clean):
        key=(start,size);data=bytes(self.cpu.u.mem_read(start,size))
        if clean:self.clean[key]=data
        else:
            assert self.clean.get(key)==data,'invalidate without current clean'
            self.visible[key]=data
    def sgi(self):
        c=self.c;cpu=self.cpu;fn=cpu.word(CB);arg=cpu.word(ARG)
        if fn in (CLEAN,INVALIDATE):self.cache(arg&~31,32,fn==CLEAN);return
        if fn==SCRATCH:
            code=self.visible.get((SCRATCH,32),b'')
            if code[:16]==PROBE:
                assert arg==DESC
                if not self.suppress_probe:cpu.put(DESC,MAGIC)
            else:
                assert code[:28]==THUNK and arg==DESC
                start,size,operation,ack=struct.unpack('<4I',cpu.u.mem_read(DESC,16))
                assert (start,size) in c.ranges and ack==0
                assert operation in (CLEAN_RANGE,INVALIDATE_RANGE)
                self.cache(start,size,operation==CLEAN_RANGE);cpu.put(DESC+12,1)
            return
        assert c.candidate and fn==c.exec_probe and arg==c.exec_ack
        m=c.candidate;assert self.visible.get((m['base'],m['end']-m['base']))==c.candidate_blob
        cpu.probe(fn,arg,(m['base'],m['state_start']))

def prepared():
    c=NativeContract(FARM);io=ModelIO(c);loader=NativeLoader(c,io)
    loader.preflight();journal=Journal();loader.attach(journal)
    return c,io,loader,journal
def staged():
    c,io,loader,j=prepared();loader.probe();r,h=loader.stage();return c,io,loader,j,r,h

class LoaderTests(unittest.TestCase):
    def test_complete_transaction_owns_heap_executes_thumb_and_preserves_flash(self):
        c,io,l,j=prepared();flash=bytes(io.cpu.u.mem_read(0x2b2880,0xb80))
        l.probe();r,h=l.stage();self.assertEqual(r[9],RELOC['base'])
        l.install(r,h,RELOC,BLOB)
        self.assertEqual(l.phase,'installed_observation_until_restart')
        self.assertEqual(io.cpu.word(CB),ORIG_CB);self.assertEqual(io.cpu.word(ARG),ORIG_ARG)
        self.assertEqual(io.cpu.word(c.exec_ack),EXEC_MAGIC);self.assertEqual(io.cpu.malloc_calls,1)
        self.assertTrue(j.record['installed']);self.assertFalse(j.record['predictionActuation'])
        self.assertIsNone(j.record['inFlight']);self.assertIsNone(j.record['cacheInFlight'])
        self.assertEqual(bytes(io.cpu.u.mem_read(0x2b2880,0xb80)),flash)
        self.assertTrue(j.record['flashCodePreserved'])
        self.assertTrue(all(io.cpu.word(a)==v for a,v in c.flash_expected.items()))
        self.assertEqual(io.opens,io.closes);self.assertTrue(io.closed);self.assertFalse(io.failed)
        first_body=next(i for i,x in enumerate(io.effects) if x[0]=='uploading_owned_body')
        self.assertTrue(any(x[0]=='waiting_native_idle_allocation' and x[1]=='read' and x[2]==c.count for x in io.effects[:first_body]))
    def test_unknown_original_code_is_zero_write_stop(self):
        c=NativeContract(FARM);io=ModelIO(c);io.cpu.put(0x19c314,0);l=NativeLoader(c,io)
        with self.assertRaisesRegex(RuntimeError,'original code'):l.preflight()
        self.assertEqual(io.writes,0)
    def test_existing_flash_missing_changed_or_busy_is_zero_write_stop(self):
        for address,value in ((0x2b2880,0),(0x21409c,FARM.word(0x21409c)),(0x2b31b8,1)):
            c=NativeContract(FARM);io=ModelIO(c);io.cpu.put(address,value);l=NativeLoader(c,io)
            with self.assertRaises(RuntimeError):l.preflight()
            self.assertEqual(io.writes,0)
        c,io,l,j=prepared();io.cpu.put(c.flash['record']+12,1)
        with self.assertRaisesRegex(RuntimeError,'exposure occurred'):l.probe()
        self.assertEqual(io.writes,0)
    def test_contract_rejects_flash_unowned_memory_fake_ack_and_rearming(self):
        c,io,l,j,r,h=staged();c.bind(r,h,RELOC,BLOB)
        for a,v in [(0x2b2880,0),(r[8]-8,0),(r[9]+16384,0),(c.exec_ack,EXEC_MAGIC),(c.count,1),(c.request+24,3)]:
            with self.assertRaises(ValueError):c.packet('write',a,v)
        for a in (*c.flash_expected, *range(c.flash['record'],c.flash['record']+364,4)):
            with self.assertRaises(ValueError):c.packet('write',a,0)
        for a in (c.request+24,c.count,r[9]):
            with self.assertRaises(ValueError):c.check_write_phase('installing_native_hooks',a)
        with self.assertRaises(ValueError):c.bind(r,h,RELOC,BLOB)
    def test_native_heap_rejection_never_uploads_body(self):
        c,io,l,j=prepared();io.cpu.put(0x6bacb4,0);l.probe()
        with self.assertRaisesRegex(ValueError,'not READY'):l.stage()
        self.assertEqual(io.cpu.malloc_calls,0);self.assertIsNone(c.candidate)
        self.assertEqual(j.record['allocationResponse'][6:8],[4,3])
        self.assertFalse(any(x[0]=='uploading_owned_body' for x in io.effects))
    def test_missing_idle_ack_never_binds_or_uploads(self):
        c,io,l,j=prepared();io.suppress_wake=True;l.probe()
        with self.assertRaisesRegex(RuntimeError,'no native idle ACK'):l.stage()
        self.assertEqual(io.cpu.malloc_calls,0);self.assertFalse(l.gated);self.assertIsNone(c.candidate)
    def test_missing_cache_probe_keeps_unknown_intent_and_stops(self):
        c,io,l,j=prepared();io.suppress_probe=True
        with self.assertRaisesRegex(RuntimeError,'completion unknown'):l.probe()
        self.assertIsNotNone(j.record['cacheInFlight']);self.assertFalse(l.probe_executed)
        self.assertFalse(any(x[2]==GATE_HOOK and x[1]=='write' for x in io.effects))
    def test_ownership_header_and_alignment_are_checked_before_write_authorization(self):
        c,io,l,j,r,h=staged()
        with self.assertRaises(ValueError):c.bind(r,(1,h[1]),RELOC,BLOB)
        bad=list(r);bad[9]+=32
        with self.assertRaises(ValueError):c.allocation_header_addresses(bad)
        bad=list(r);bad[12]=131071
        with self.assertRaises(ValueError):c.allocation_header_addresses(bad)
        self.assertEqual(c.candidate_words,{})
    def test_ambiguous_write_failure_closes_handles_and_refuses_further_requests(self):
        for phase in ('cache_probe','staging_idle_allocation','uploading_owned_body','installing_native_hooks','releasing_native_gate'):
            c,io,l,j=prepared();hit=[]
            def fail(p,k,a,v):
                if p==phase and k=='write' and not hit:hit.append(a);return 'after'
            io.fault=fail
            with self.assertRaises(OSError):
                l.probe();r,h=l.stage();l.install(r,h,RELOC,BLOB)
            self.assertTrue(hit);self.assertTrue(io.failed);self.assertEqual(io.opens,io.closes)
            self.assertIsNotNone(j.record['inFlight']);count=io.requests
            with self.assertRaises(RuntimeError):io.read(CB)
            self.assertEqual(io.requests,count);self.assertFalse(j.record.get('installed',False))
    def test_journal_failure_happens_before_first_mutation(self):
        c,io,l,j=prepared();j.reject=lambda r:r.get('inFlight') is not None and r['inFlight'][0]=='write'
        with self.assertRaises(OSError):l.probe()
        self.assertEqual(io.writes,0);self.assertEqual(io.cpu.word(CB),ORIG_CB)
    def test_each_installation_nonce_survives_native_allocation_and_rejects_stale_record(self):
        c=NativeContract(FARM,nonce=0x76543210);io=ModelIO(c);l=NativeLoader(c,io)
        l.preflight();j=Journal();l.attach(j);l.probe();r,h=l.stage()
        self.assertEqual(r[2],0x76543210);self.assertEqual(j.record['bootstrapNonce'],r[2])
        old=NativeContract(FARM,nonce=1)
        self.assertEqual(c.identity,old.identity)
        with self.assertRaisesRegex(ValueError,'not READY'):old.allocation_header_addresses(r)

if __name__=='__main__':
    start=time.perf_counter();result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(LoaderTests))
    c=NativeContract(FARM)
    report={'tests':result.testsRun,'passed':result.wasSuccessful(),'failures':len(result.failures),'errors':len(result.errors),
        'seconds':time.perf_counter()-start,'contractSha256':c.identity,'hardwareRequests':0,
        'testSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'scope':'固定报文装载事务 + 原厂 F4/通知/AF等待/堆分配 + 重定位 Thumb 取指探针；缓存和 USB 为检查顺序的模型',
        'relocatedPayloadSha256':RELOC['payload_sha256'],'actualHeapAllocation':False,
        'limitations':['本组日志为内存故障替身；持久日志另核对文件事件链','SGI/缓存物理效果不由报文模型证明']}
    (HERE/'build/native-capture-r1/loader-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False));raise SystemExit(not result.wasSuccessful())
