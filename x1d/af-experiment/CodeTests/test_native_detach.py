"""观察装载后的原厂入口撤销和故障停止；整个过程使用报文/CPU模型。"""
import copy,hashlib,json,sys,time,unittest
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
from native_detach import ObservationContract,ObservationDetach
from native_install import *
from test_native_loader import staged,FARM,RELOC,BLOB,Journal

def installed():
    c,io,l,j,r,h=staged();l.install(r,h,RELOC,BLOB)
    # 原先装载模型在 gate 返回边界暂停；执行原厂下一次 wait，建立后续撤销批次的等待上下文。
    io.cpu.block_af()
    record=copy.deepcopy(j.record);new=ObservationContract(record,RELOC,BLOB,FARM)
    io.c=new;io.requests=io.writes=io.opens=io.closes=0;io.effects=[];io.journal=None;io.phase='new'
    io.hold_requests=0;io.hold_results=[];io.segment_deadline=None
    return new,io,ObservationDetach(new,io),record

def prepared():
    c,io,l,record=installed();l.preflight();j=Journal();l.attach(j);return c,io,l,j,record

class DetachTests(unittest.TestCase):
    def test_original_af_is_restored_without_freeing_memory_or_touching_flash(self):
        c,io,l,j,record=prepared();cpu=io.cpu
        resident=bytes(cpu.u.mem_read(c.candidate['base'],len(BLOB)))
        flash=bytes(cpu.u.mem_read(0x2b2880,0xb80));scratch=bytes(cpu.u.mem_read(SCRATCH,64))
        heap=cpu.word(0x6bacb4);allocations=cpu.malloc_calls
        l.probe();l.gate();l.detach()
        self.assertEqual(l.phase,'original_af_restored_memory_retained')
        self.assertEqual(cpu.word(0x6bacb4),heap);self.assertEqual(cpu.malloc_calls,allocations)
        self.assertEqual(bytes(cpu.u.mem_read(c.candidate['base'],len(BLOB))),resident)
        self.assertEqual(bytes(cpu.u.mem_read(0x2b2880,0xb80)),flash)
        self.assertEqual(bytes(cpu.u.mem_read(SCRATCH,64)),scratch)
        self.assertTrue(all(cpu.word(a)==old for a,old,new in c.candidate['emulatorOnlyHooks']))
        self.assertTrue(all(cpu.word(a)==v for a,v in c.flash_expected.items()))
        self.assertEqual(cpu.word(CB),ORIG_CB);self.assertEqual(cpu.word(ARG),ORIG_ARG)
        self.assertTrue(j.record['removed']);self.assertFalse(j.record['heapFreed']);self.assertFalse(j.record['installed'])
        self.assertEqual(io.opens,io.closes);self.assertTrue(io.closed)
        self.assertFalse(any(k=='write' and c.candidate['base']<=a<c.candidate['end'] for p,k,a,v in io.effects))
    def test_missing_changed_resident_code_and_active_configuration_are_zero_write_stop(self):
        for offset in ('hook','body','speed','config','ownership'):
            c,io,l,record=installed();s=c.candidate['symbols']
            a={'hook':c.candidate['emulatorOnlyHooks'][0][0],'body':c.candidate['base'],
                'speed':s['na_speed_overrides'],'config':s['na_config_bank']+8,'ownership':c.allocation[8]-8}[offset]
            io.cpu.put(a,1)
            with self.assertRaises(RuntimeError):l.preflight()
            self.assertEqual(io.writes,0)
    def test_half_finished_or_non_observation_installation_record_is_rejected(self):
        c,io,l,record=installed()
        for key,value in (('installed',False),('inFlight',['write',0,0]),('predictionActuation',True),('speedOverrides',True),('allHandlesClosed',False)):
            changed=copy.deepcopy(record);changed[key]=value
            with self.assertRaises(ValueError):ObservationContract(changed,RELOC,BLOB,FARM)
    def test_retained_body_allocation_results_and_flash_are_outside_detach_writes(self):
        c,io,l,j,record=prepared()
        for a,v in ((c.candidate['base'],0),(c.request+24,3),(c.count,1),(c.exec_ack,EXEC_MAGIC),
            (DESC+12,1),(0x2b2880,0),(c.allocation[8]-8,0)):
            with self.assertRaises(ValueError):c.packet('write',a,v)
        for a,old,new in c.candidate['emulatorOnlyHooks']:
            with self.assertRaises(ValueError):c.packet('write',a,new)
    def test_missing_idle_ack_keeps_candidate_hooks_and_does_not_free(self):
        c,io,l,j,record=prepared();io.suppress_wake=True;l.probe()
        with self.assertRaisesRegex(RuntimeError,'idle ACK missing'):l.gate()
        self.assertFalse(l.gated)
        self.assertTrue(all(io.cpu.word(a)==new for a,old,new in c.candidate['emulatorOnlyHooks']))
        self.assertEqual(io.cpu.malloc_calls,1)
    def test_ambiguous_removal_failure_preserves_journal_and_refuses_further_requests(self):
        for phase in ('preparing_detach_gate','detaching_native_hooks','releasing_native_gate','restoring_shared_scratch'):
            c,io,l,j,record=prepared();hit=[]
            def fail(p,k,a,v):
                if p==phase and k=='write' and not hit:hit.append(a);return 'after'
            io.fault=fail
            with self.assertRaises(OSError):l.probe();l.gate();l.detach()
            self.assertTrue(hit);self.assertTrue(io.failed);self.assertIsNotNone(j.record['inFlight'])
            self.assertEqual(io.opens,io.closes);self.assertFalse(j.record.get('removed',False))
            n=io.requests
            with self.assertRaises(RuntimeError):io.read(CB)
            self.assertEqual(io.requests,n)

if __name__=='__main__':
    start=time.perf_counter();r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(DetachTests))
    c=NativeContract(FARM)
    report={'passed':r.wasSuccessful(),'tests':r.testsRun,'failures':len(r.failures),'errors':len(r.errors),
        'seconds':time.perf_counter()-start,'contractSha256':c.identity,'baselineSha256':FARM.sha256,
        'payloadSha256':RELOC['payload_sha256'],'testSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'hardwareRequests':0,'scope':'已装载观察候选的撤销入口事务；原厂再次空闲唤醒、不重复分配、逐字保留堆块/引闪及失败停止',
        'limitations':['USB/缓存为模型；原厂任务/分配器指令实际执行','只支持未改配置且未启用执行的观察模式；代码和已分配内存保留']}
    (HERE/'build/native-capture-r1/detach-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False));raise SystemExit(not r.wasSuccessful())
