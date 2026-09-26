"""实际R3装载器的固定USB包、延迟SGI、失败后留驻与恢复记录测试。仅模拟传输。"""
import sys,json,struct,copy,hashlib,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import full_loader_r3 as L
from r3_install_plan import visible_safety
from test_r3_task_wake import TaskWakeCase

class MemoryJournal:
    """事务记录接口的内存替身；真实文件语义另有独立测试。"""
    def __init__(self):self.record={'inFlight':None};self.failed=False
    def persist(self,record):self.record=record
    def begin(self,phase,operation):
        if self.failed or self.record['inFlight'] is not None:raise RuntimeError('unresolved operation')
        self.record['phase']=phase;self.record['inFlight']=operation
    def complete(self):self.record['inFlight']=None

class PacketModel:
    def __init__(self,contract,native_ack):
        self.contract=contract;self.plan=contract.plan;self.native_ack=native_ack
        self.memory=dict(contract.expected)
        for a,(mask,value) in contract.guards.items():self.memory[a]=(self.memory.get(a,0)&~mask)|value
        self.visible=dict(contract.expected);self.back=dict(self.visible)
        self.gate_ack=False;self.pending=False;self.active=False;self.callback=None
        self.pending_delay=0;self.active_delay=0;self.finish_delay=0;self.callback_done=False
        self.af_delay=None;self.notifications=0;self.probes=0;self.ranges=0
        self.operations=[];self.fail_at=None;self.fail_after=False;self.fail_predicate=None
        self.closed_count=0;self.opened_count=0;self.freeze_sgi=False;self.fail_close=False
    def read(self,a):return self.memory.get(a,0)
    def sync(self,a,n,clean):
        for address in range(a&~31,(a+n+31)&~31,4):
            if clean:self.back[address]=self.memory.get(address,0)
            else:self.visible[address]=self.back.get(address,0)
    def advance(self):
        if self.af_delay is not None:
            self.af_delay-=1
            if self.af_delay<=0:
                assert self.visible[L.HOOK]==self.plan.gate
                self.memory[L.COUNT]+=self.native_ack;self.gate_ack=True;self.af_delay=None
        if self.freeze_sgi:return
        if self.pending:
            self.pending_delay-=1
            if self.pending_delay<=0:
                self.pending=False;self.active=True
                self.callback=(self.read(L.CB),self.read(L.ARG));self.active_delay=2
            return
        if self.active:
            if not self.callback_done:
                self.active_delay-=1
                if self.active_delay<=0:self.execute_callback();self.callback_done=True;self.finish_delay=2
            else:
                self.finish_delay-=1
                if self.finish_delay<=0:self.active=False;self.callback=None;self.callback_done=False
    def execute_callback(self):
        fn,arg=self.callback
        if fn==L.NOOP:return
        if fn==L.ORIG_CB:assert arg==L.ORIG_ARG;return
        if fn in (L.CLEAN,L.INVALIDATE):
            assert arg==L.SCRATCH;self.sync(arg,32,fn==L.CLEAN);return
        assert fn==L.SCRATCH and arg==L.DESC
        code=b''.join(struct.pack('<I',self.visible.get(a,0)) for a in range(L.SCRATCH,L.SCRATCH+28,4))
        if code[:16]==L.PROBE:self.memory[L.DESC]=L.MAGIC;self.probes+=1;return
        assert code==L.THUNK,'incomplete or stale cache callback'
        a,n,fn=(self.read(L.DESC+4*i) for i in range(3))
        assert (a,n) in self.contract.ranges and fn in (L.CLEAN_RANGE,L.INVALIDATE_RANGE)
        self.sync(a,n,fn==L.CLEAN_RANGE);self.memory[L.DESC+12]=1;self.ranges+=1
    def late_completion(self):
        for _ in range(32):self.advance()
        self.assert_safe()
    def assert_safe(self):
        assert visible_safety(self.plan,self),'published entry has incomplete dependencies'
        if self.pending or self.active:
            fn,arg=self.callback if self.active else (self.read(L.CB),self.read(L.ARG))
            assert fn in (L.ORIG_CB,L.NOOP,L.CLEAN,L.INVALIDATE,L.SCRATCH)
            if fn==L.SCRATCH:
                code=b''.join(struct.pack('<I',self.visible.get(a,0)) for a in range(L.SCRATCH,L.SCRATCH+28,4))
                assert arg==L.DESC and (code[:16]==L.PROBE or code==L.THUNK)
    def effect(self,kind,a,v):
        self.advance()
        if kind=='version':return L.VERSIONS
        if kind=='read':
            if a==L.PENDING:return 0x8000 if self.pending else 0
            if a==L.ACTIVE:return 0x8000 if self.active else 0
            if a==L.COUNT and self.visible[L.WAKE_HOOK]==self.plan.wake_hook:
                assert self.visible[L.HOOK]==self.plan.gate
                assert all(self.visible[k]==w for k,w in self.plan.helper.items())
                if self.read(L.SENT)==0 and self.read(0x6bb46c)&255==0:
                    self.memory[L.SENT]=1;self.notifications+=1;self.af_delay=3
            return self.read(a)
        if a in (L.CB,L.ARG,L.DESC,L.DESC+4,L.DESC+8,L.DESC+12) or L.SCRATCH<=a<L.SCRATCH+28:
            assert not self.pending and not self.active,'modified live callback dependency'
        if a==L.SGIR:
            assert not self.pending and not self.active
            self.pending=True;self.pending_delay=2
        else:self.memory[a]=v
        self.assert_safe();return 0
    def submit(self,kind,a,v,phase):
        n=len(self.operations);op=(phase,kind,a,v);self.operations.append(op)
        fail=n==self.fail_at or self.fail_predicate is not None and self.fail_predicate(op)
        if fail and not self.fail_after:raise IOError('modeled failure before effect')
        result=self.effect(kind,a,v)
        if fail and self.fail_after:raise IOError('modeled reply loss after effect')
        return result

class FakePacket:
    def __init__(self,io,kind,a,v):
        self.io=io;self.model=io.model;self.kind=kind;self.a=a;self.v=v
        self.packet_size=512;self.sent=False;self.result=None
    def open(self):
        self.model.opened_count+=1
        return {'alternate':0,'class':255,'subclass':0,'protocol':0,'number':0,
            'pipes':[{'id':p,'type':2,'maximumPacketSize':512} for p in (1,2,129,130)]}
    def prepare(self):pass
    def write_query(self,size):
        packet=self.io.contract.packet(self.kind,self.a,self.v,size);assert len(packet)==512
        payload=12 if self.kind=='write' else 8 if self.kind=='read' else 4
        assert not any(packet[payload:]);self.sent=True
        self.result=self.model.submit(self.kind,self.a,self.v,self.io.phase)
        return size
    def read_reply(self,size):
        result=bytearray(size)
        if self.kind=='version':
            result[:4]=bytes.fromhex('0e000108')
            for a,value in zip((4,68,132),self.result):result[a:a+len(value)]=value.encode()
        elif self.kind=='read':result[:8]=bytes.fromhex('f5000108')+struct.pack('<I',self.result)
        else:result[:4]=bytes.fromhex('f3000108')
        return bytes(result)
    def close(self):
        self.model.closed_count+=1
        return {'device':not self.model.fail_close,'winusb':True}

class ModelIO(L.FixedIO):
    is_hardware=False
    def __init__(self,contract,model):super().__init__(contract);self.model=model
    def transport(self,kind,a,v):return FakePacket(self,kind,a,v)

class FullLoaderR3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.farm=L.FarmApplication();cls.contract=L.FixedContract(cls.farm)
        native=TaskWakeCase(cls.farm);native.block_af();cls.ack=native.request(schedule_at_svc=True)
        cls.failure_counts={};cls.success_requests=0
    def prepared(self,preflight=False):
        m=PacketModel(self.contract,self.ack);io=ModelIO(self.contract,m);loader=L.R3Loader(self.contract,io)
        if preflight:loader.preflight()
        else:loader.phase_to('prepared')
        loader.attach_journal(MemoryJournal());return loader,m
    def cache_ready(self):
        loader,m=self.prepared();loader.probe();return loader,m
    def assert_failed_stops(self,loader,model):
        n=len(model.operations)
        with self.assertRaises(RuntimeError):loader.io.read(L.CB)
        self.assertEqual(len(model.operations),n)
        self.assertEqual(model.closed_count,model.opened_count)
        self.assertIsNotNone(loader.journal.record['inFlight'])
        model.late_completion()
    def test_complete_actual_packet_pipeline_with_delayed_callbacks(self):
        loader,m=self.prepared(preflight=True)
        loader.probe();loader.stage();loader.install()
        self.assertEqual(loader.phase,'installed_armed_until_restart')
        self.assertEqual(m.probes,1);self.assertEqual(m.notifications,1)
        self.assertTrue(loader.io.closed);self.assertLess(loader.io.requests,L.REQUEST_LIMIT)
        self.assertEqual(m.read(L.CB),L.ORIG_CB);self.assertEqual(m.read(L.ARG),L.ORIG_ARG)
        for a,(old,new) in self.contract.plan.hooks.items():self.assertEqual(m.visible[a],new)
        self.assertEqual(m.visible[L.WAKE_HOOK],self.contract.plan.wake_original)
        self.assertEqual(loader.summary()['hardwareRequests'],0)
        self.assertEqual(m.closed_count,m.opened_count);self.success_requests=loader.io.requests
        type(self).success_requests=loader.io.requests
    def test_cold_preflight_refuses_resident_gfs3_arena_and_changed_original_code(self):
        for address in (L.SCRATCH,L.M['base'],L.BASE,L.COUNT,L.SENT,0x21409c,0x1c4380,
                        0x1c4458,0x1c44f4,0x1007e8,0x18b090,L.WAKE_HOOK):
            m=PacketModel(self.contract,self.ack);m.memory[address]^=1
            loader=L.R3Loader(self.contract,ModelIO(self.contract,m))
            with self.assertRaises(RuntimeError):loader.preflight()
            self.assertEqual(loader.io.writes,0)
    def test_fixed_packets_deny_unlisted_writes_forged_ack_and_wrong_replies(self):
        c=self.contract
        for address,value in ((L.COUNT,1),(L.SENT,1),(L.SGIR,0x0100000f),(0xf8f0010c,0),
                              (0x442c0060,1),(L.M['base'],0x12345678)):
            with self.assertRaises(ValueError):c.packet('write',address,value)
        for address in (0xf8f0010c,L.SGIR,0,0x442c0060):
            with self.assertRaises(ValueError):c.packet('read',address)
        for kind in ('read','write'):
            raw=bytearray(512);raw[:4]=bytes.fromhex('f5000108' if kind=='read' else 'f3000108')
            self.assertEqual(c.reply(kind,bytes(raw),512),0)
            for index in (0,2,8 if kind=='read' else 4):
                changed=raw.copy();changed[index]^=1
                with self.assertRaises(ValueError):c.reply(kind,bytes(changed),512)
            with self.assertRaises(ValueError):c.reply(kind,bytes(raw[:-1]),512)
    def test_all_probe_transfer_failures_leave_dependencies_for_late_callback(self):
        loader,m=self.prepared();loader.probe();total=len(m.operations)
        for after in (False,True):
            for n in range(total):
                loader,m=self.prepared();m.fail_at=n;m.fail_after=after
                with self.assertRaises(IOError):loader.probe()
                self.assert_failed_stops(loader,m)
        self.failure_counts['bootstrapPacketFailures']=total*2
    def test_each_cache_transaction_transfer_failure_does_not_rewrite_live_descriptor(self):
        loader,m=self.cache_ready();template=copy.deepcopy(m)
        for fn in (L.CLEAN_RANGE,L.INVALIDATE_RANGE):
            start=len(m.operations);loader.range_cache(L.BASE,self.contract.plan.helper_size,fn)
            count=len(m.operations)-start
            for after in (False,True):
                for n in range(count):
                    model=copy.deepcopy(template);io=ModelIO(self.contract,model);obj=L.R3Loader(self.contract,io)
                    obj.phase_to('prepared');obj.attach_journal(MemoryJournal());obj.probe_executed=True
                    obj.phase_to('cache_ready');model.fail_at=len(model.operations)+n;model.fail_after=after
                    with self.assertRaises(IOError):obj.range_cache(L.BASE,self.contract.plan.helper_size,fn)
                    self.assert_failed_stops(obj,model)
            self.failure_counts['cachePacketFailures'+str(fn)]=count*2
    def test_all_gate_publication_transfer_failures_keep_safe_executable_entries(self):
        loader,m=self.cache_ready();template=copy.deepcopy(m);start=len(m.operations)
        loader.stage();count=len(m.operations)-start
        for after in (False,True):
            for n in range(count):
                model=copy.deepcopy(template);io=ModelIO(self.contract,model);obj=L.R3Loader(self.contract,io)
                obj.phase_to('prepared');obj.attach_journal(MemoryJournal());obj.probe_executed=True
                obj.phase_to('cache_ready');model.fail_at=len(model.operations)+n;model.fail_after=after
                with self.assertRaises(IOError):obj.stage()
                self.assert_failed_stops(obj,model)
        self.failure_counts['gatePacketFailures']=count*2
    def test_body_hook_activation_and_slot_restoration_reply_loss_fail_stops(self):
        loader,m=self.cache_ready();loader.stage();template=copy.deepcopy(m)
        targets=[('uploading_gated',L.M['base']),('uploading_gated',0x19bfb8),
            ('uploading_gated',self.contract.plan.uploads[-1][0]),
            ('installing_hooks_gated',0x1cdbac),('installing_hooks_gated',0x1a1fdc),
            ('verifying_gated',self.contract.plan.af_armed),
            ('releasing_af_gate',L.HOOK),('restoring_cache_slot',L.ARG),('restoring_cache_slot',L.CB)]
        for phase,address in targets:
            for after in (False,True):
                model=copy.deepcopy(template);io=ModelIO(self.contract,model);obj=L.R3Loader(self.contract,io)
                obj.phase_to('prepared');obj.attach_journal(MemoryJournal());obj.probe_executed=True
                obj.gated=True;obj.cache_verified=set(loader.cache_verified);obj.phase_to('gated')
                model.fail_predicate=lambda op,p=phase,a=address:op[0]==p and op[1]=='write' and op[2]==a
                model.fail_after=after
                with self.assertRaises(IOError,msg=(phase,address,after)):obj.install()
                self.assert_failed_stops(obj,model)
        self.failure_counts['bodyAndReleasePacketFailures']=len(targets)*2
    def test_missing_sgi_completion_and_handle_close_failure_do_not_cleanup_or_retry(self):
        loader,m=self.prepared();m.freeze_sgi=True
        with self.assertRaises(RuntimeError):loader.probe()
        # 没有完成证明时保持原回调/参数，继续调用入口不会默默清理后重试。
        self.assertTrue(m.pending);self.assertEqual(m.read(L.CB),L.CLEAN)
        self.assertFalse(loader.probe_executed);self.assertEqual(m.probes,0)
        self.assertIsNotNone(loader.journal.record['cacheInFlight'])
        loader,m=self.prepared();m.fail_close=True
        with self.assertRaises(RuntimeError):loader.probe()
        self.assertTrue(loader.io.failed);self.assertIsNotNone(loader.journal.record['inFlight'])
    def test_real_journal_wraps_packet_requests_before_device_effect(self):
        with tempfile.TemporaryDirectory(prefix='packet-journal-',dir=L.BUILD) as folder:
            assert Path(folder).resolve().is_relative_to(L.BUILD.resolve())
            loader,m=self.prepared();path=Path(folder)/'record.json'
            journal=L.InstallJournal(path,L.ARTIFACT,backend='offline_packet_model')
            loader.journal=journal;loader.io.journal=journal
            try:
                loader.write(L.CB,L.NOOP)
                record=L.InstallJournal.read_record(path,L.ARTIFACT)
                self.assertIsNone(record['inFlight']);self.assertEqual(record['sequence'],2)
                self.assertEqual(record['hardwareRequests'],0)
                m.fail_at=len(m.operations);m.fail_after=True
                with self.assertRaises(IOError):loader.write(L.ARG,L.SCRATCH)
                record=L.InstallJournal.read_record(path,L.ARTIFACT)
                self.assertEqual(record['inFlight']['address'],L.ARG)
                self.assertEqual(m.read(L.ARG),L.SCRATCH)
                count=len(m.operations)
                self.assertTrue(L.record_failure(loader,journal,IOError()))
                record=L.InstallJournal.read_record(path,L.ARTIFACT)
                self.assertEqual(record['requests'],loader.io.requests)
                self.assertIsNotNone(record['inFlight']);self.assertTrue(record['requiresReview'])
                self.assertEqual(len(m.operations),count)
            finally:journal.close()
    def test_complete_pipeline_real_append_journal_with_open_reader(self):
        with tempfile.TemporaryDirectory(prefix='full-pipeline-journal-',dir=L.BUILD) as folder:
            assert Path(folder).resolve().is_relative_to(L.BUILD.resolve())
            m=PacketModel(self.contract,self.ack);loader=L.R3Loader(self.contract,ModelIO(self.contract,m))
            loader.preflight();path=Path(folder)/'record.json'
            journal=L.InstallJournal(path,L.ARTIFACT,backend='offline_packet_model')
            try:
                loader.attach_journal(journal);original=path.read_bytes()
                with path.open('r',encoding='utf-8') as held:
                    with patch('r3_install_journal.os.replace',side_effect=PermissionError('Windows reader holds anchor')) as replace:
                        loader.probe();loader.stage();loader.install();replace.assert_not_called()
                    self.assertTrue(held.read())
                record=L.InstallJournal.read_record(path,L.ARTIFACT)
                self.assertTrue(record['installed']);self.assertEqual(record['phase'],'installed_armed_until_restart')
                self.assertEqual(record['requests'],loader.io.requests)
                self.assertEqual(record['hardwareRequests'],0);self.assertIsNone(record['inFlight'])
                self.assertIsNone(record['cacheInFlight']);self.assertFalse(record['journalAudit']['incompleteTail'])
                self.assertGreater(record['journalAudit']['verifiedEvents'],30000)
                self.assertEqual(path.read_bytes(),original);self.assertTrue(record['allHandlesClosed'])
                m.assert_safe()
            finally:journal.close()
    @classmethod
    def tearDownClass(cls):
        (L.BUILD/'loader-packet-model.json').write_text(json.dumps({
            'artifactSha256':L.ARTIFACT,'contractSha256':cls.contract.digest,
            'successfulRequestCount':cls.success_requests,'failureCases':cls.failure_counts,
            'hardwareRequests':0,'scope':'实际装载器与固定字节包，USB传输/缓存一致性为显式模型',
            'lateCallbackExecutedAfterHostFailure':True,'automaticRetry':False,
            'limitations':['模型不能替代相机首次缓存探针、AF屏障ACK及完整回读',
                '真实文件断电恢复不在本测试范围，未知错误后保留代码而非自动撤回']},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':unittest.main(verbosity=2)
