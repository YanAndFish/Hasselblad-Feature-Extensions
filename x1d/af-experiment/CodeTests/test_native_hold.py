"""固定 Linux hold 帧与原厂 AF 事务边界；全部设备/时钟均为明确替身。"""
import hashlib,json,struct,sys,time,unittest
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
from native_hold import query,reply,check,SUCCESS,COMMAND,MIN_REMAINING_MS,SEGMENT_MS,MAX_CHECKS
from native_install import *
from native_loader import NativeIO,readiness
from test_native_loader import NativeContract,ModelIO,NativeLoader,HoldPacket,Packet,Journal,hold_reply,prepared,staged,FARM,RELOC,BLOB

def bad_at(io,phase,output=b'system-active-hold-not-ready\n',exit_code=66):
    class Bad(HoldPacket):
        def read_reply(self,size):
            if io.phase==phase:return hold_reply(self.token,output,exit_code)
            return super().read_reply(size)
    io.hold_transport=lambda packet,token:Bad(io,packet,token)

class HoldTests(unittest.TestCase):
    def test_query_is_fixed_minimum_only_and_nonce_is_checked(self):
        p=query(77);self.assertEqual(len(p),512);self.assertIn(COMMAND.encode()+b'\0',p)
        self.assertEqual(COMMAND,'/tmp/hbl-wireless-flash/formal-system-check --require-held-min-ms 180000')
        self.assertEqual((MIN_REMAINING_MS,SEGMENT_MS),(180000,120000))
        self.assertNotIn(b'--begin-hold',p);self.assertNotIn(b'hold.release',p)
        for token in (0,-1,0x100000000,True,1.0):
            with self.assertRaises(ValueError):query(token)
    def test_reply_rejects_bad_envelope_nonce_crc_exit_and_any_other_output(self):
        packet=hold_reply(77);self.assertTrue(reply(packet,77)['matched'])
        variants=[packet[:-1],bytes(512),hold_reply(78),hold_reply(77,exit_code=66)]
        for off in (5,9,17,25):
            b=bytearray(packet);b[off]^=1;variants.append(bytes(b))
        for out in (SUCCESS.replace(b'hold=1',b'hold=0'),SUCCESS.replace(b'system=2',b'system=4'),
                    SUCCESS.replace(b'ui-power=0',b'ui-power=1'),SUCCESS+b'extra',SUCCESS.rstrip(b'\n'),b''):
            variants.append(hold_reply(77,out))
        for bad in variants:
            with self.assertRaises(ValueError):reply(bad,77)
    def test_failed_initial_hold_sends_no_farm_query_or_write(self):
        c=NativeContract(FARM);io=ModelIO(c);bad_at(io,'preflight');l=NativeLoader(c,io)
        with self.assertRaisesRegex(ValueError,'checker not ready'):l.preflight()
        self.assertEqual(io.requests,1);self.assertEqual(io.writes,0)
        self.assertEqual([e[1] for e in io.effects],['hold_check']);self.assertEqual(io.opens,io.closes)
        self.assertTrue(io.failed);self.assertTrue(io.closed)
    def test_complete_install_checks_closed_parked_boundaries_and_keeps_factory_packets(self):
        c,io,l,j,r,h=staged();l.install(r,h,RELOC,BLOB)
        labels=[x['boundary'] for x in io.hold_results]
        self.assertEqual(labels[0],'entry');self.assertIn('allocated_before_build',labels)
        self.assertIn('before_body',labels);self.assertIn('body_14336',labels)
        self.assertEqual(sum(x.startswith('native_hook_') for x in labels),12)
        self.assertEqual(labels[-1],'before_native_release')
        self.assertTrue(all(x['matched'] and x['closed'] and x['submitted'] for x in io.hold_results))
        self.assertLess(io.hold_requests,MAX_CHECKS);self.assertLess(io.requests,io.request_limit)
        self.assertTrue(j.record['installed']);self.assertFalse(j.record['predictionActuation'])
        self.assertEqual(io.cpu.word(CB),ORIG_CB);self.assertEqual(io.cpu.word(ARG),ORIG_ARG)
    def test_failed_pre_probe_hold_cannot_start_cache_writes(self):
        c,io,l,j=prepared();bad_at(io,'prepared');before=io.writes
        with self.assertRaises(ValueError):l.probe()
        self.assertEqual(io.writes,before);self.assertFalse(l.probe_executed)
        self.assertTrue(io.failed);self.assertIsNotNone(j.record['inFlight'])
    def test_hold_loss_after_allocation_retains_gate_and_never_uploads_body(self):
        c,io,l,j=prepared();bad_at(io,'allocated_and_gated');l.probe()
        with self.assertRaises(ValueError):l.stage()
        self.assertTrue(l.gated);self.assertEqual(io.cpu.malloc_calls,1)
        self.assertFalse(any(e[0]=='uploading_owned_body' for e in io.effects))
        self.assertEqual(io.cpu.word(CB),ORIG_CB);self.assertEqual(io.cpu.word(ARG),ORIG_ARG)
        self.assertEqual(io.cpu.word(c.control),0)
    def test_mid_body_failure_stops_after_one_complete_chunk_and_before_cache_or_hooks(self):
        c,io,l,j,r,h=staged();bad_at(io,'uploading_owned_body')
        with self.assertRaises(ValueError):l.install(r,h,RELOC,BLOB)
        body=[e for e in io.effects if e[0]=='uploading_owned_body' and e[1]=='write']
        self.assertEqual(len(body),256);self.assertEqual(body[0][2],RELOC['base'])
        self.assertEqual(body[-1][2],RELOC['base']+1020)
        self.assertTrue(all(io.cpu.word(a)==old for a,old,new in RELOC['emulatorOnlyHooks']))
        self.assertEqual(io.effects[-1][1],'hold_check')
    def test_hold_loss_after_execution_probe_never_patches_af_hooks(self):
        c,io,l,j,r,h=staged();bad_at(io,'executing_owned_probe')
        with self.assertRaises(ValueError):l.install(r,h,RELOC,BLOB)
        self.assertTrue(j.record['ownedCodeExecuted'])
        self.assertTrue(all(io.cpu.word(a)==old for a,old,new in RELOC['emulatorOnlyHooks']))
    def test_hold_loss_between_hooks_cannot_patch_the_next_hook(self):
        c,io,l,j,r,h=staged();bad_at(io,'installing_native_hooks')
        with self.assertRaises(ValueError):l.install(r,h,RELOC,BLOB)
        self.assertEqual(io.cpu.word(RELOC['emulatorOnlyHooks'][0][0]),RELOC['emulatorOnlyHooks'][0][2])
        self.assertTrue(all(io.cpu.word(a)==old for a,old,new in RELOC['emulatorOnlyHooks'][1:]))
        self.assertEqual(io.cpu.word(c.control),0);self.assertEqual(io.cpu.word(CB),ORIG_CB)
    def test_bad_hold_before_release_does_not_release_the_gate(self):
        c,io,l,j,r,h=staged();bad_at(io,'verifying_gated')
        with self.assertRaises(ValueError):l.install(r,h,RELOC,BLOB)
        self.assertTrue(all(io.cpu.word(a)==new for a,old,new in RELOC['emulatorOnlyHooks']))
        self.assertEqual(io.cpu.word(c.control),0);self.assertFalse(j.record.get('installed',False))
    def test_busy_handles_cache_intent_and_unparked_callback_cannot_query_linux(self):
        for flag in ('transfer_active','closed','cache','wake_live','permission'):
            c=NativeContract(FARM);io=ModelIO(c);io.hold_permitted=True
            if flag=='closed':io.closed=False
            elif flag=='cache':io.journal=Journal();io.journal.record['cacheInFlight']={'unknown':True}
            elif flag=='permission':io.hold_permitted=False
            else:setattr(io,flag,True)
            with self.assertRaises(RuntimeError):check(io,'invalid')
            self.assertEqual(io.requests,0);self.assertEqual(io.opens,0)
        c,io,l,j=prepared();io.cpu.put(CB,NOOP);count=io.hold_requests;writes=io.writes
        with self.assertRaisesRegex(RuntimeError,'original callback'):l.hold_boundary('invalid')
        self.assertEqual(io.hold_requests,count);self.assertEqual(io.writes,writes)
    def test_query_timeout_or_close_failure_never_allows_farm_to_start(self):
        for mode in ('timeout','close','late'):
            c=NativeContract(FARM);io=ModelIO(c);now=[0.0];io.clock=lambda:now[0]
            class Bad(HoldPacket):
                def read_reply(self,size):
                    if mode=='timeout':raise TimeoutError('model timeout')
                    if mode=='late':now[0]=20.0
                    return super().read_reply(size)
                def close(self):
                    super().close();return {'usb':mode!='close','file':True}
            io.hold_transport=lambda packet,token:Bad(io,packet,token);l=NativeLoader(c,io)
            with self.assertRaises((RuntimeError,TimeoutError)):l.preflight()
            self.assertTrue(io.failed);self.assertEqual(io.writes,0)
            self.assertEqual([e[1] for e in io.effects],['hold_check'])
    def test_expired_segment_cannot_dispatch_or_refresh_hold(self):
        c,io,l,j=prepared();io.segment_deadline=0;before=io.requests
        with self.assertRaisesRegex(RuntimeError,'time budget'):l.probe()
        self.assertEqual(io.requests,before);self.assertTrue(io.failed)
        io.hold_permitted=True
        with self.assertRaises(RuntimeError):io.check_hold('cannot-renew')
        self.assertEqual(io.requests,before)
    def test_segment_expiry_during_open_stops_before_farm_dispatch(self):
        c,io,l,j=prepared();now=[0.0];io.clock=lambda:now[0];io.segment_deadline=120
        class Late(Packet):
            def open(self):
                result=super().open();now[0]=121;return result
        io.transport=lambda kind,a,v:Late(io,kind,a,v);before=io.requests;effects=len(io.effects)
        with self.assertRaisesRegex(RuntimeError,'expired before dispatch'):io.read(CB)
        self.assertEqual(io.requests,before);self.assertEqual(len(io.effects),effects)
        self.assertTrue(io.closed);self.assertTrue(io.failed)
    def test_detach_hold_loss_preserves_resident_body_and_stops_hook_removal(self):
        from test_native_detach import prepared as detached_prepared
        c,io,l,j,record=detached_prepared();bad_at(io,'removing_wake_entry')
        body=bytes(io.cpu.u.mem_read(c.candidate['base'],len(BLOB)))
        l.probe();l.gate()
        with self.assertRaises(ValueError):l.detach()
        self.assertEqual(bytes(io.cpu.u.mem_read(c.candidate['base'],len(BLOB))),body)
        self.assertTrue(all(io.cpu.word(a)==new for a,old,new in c.candidate['emulatorOnlyHooks']))
        self.assertFalse(j.record.get('removed',False));self.assertEqual(io.effects[-1][1],'hold_check')

if __name__=='__main__':
    start=time.perf_counter();r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(HoldTests))
    report={'passed':r.wasSuccessful(),'tests':r.testsRun,'failures':len(r.failures),'errors':len(r.errors),
        'seconds':time.perf_counter()-start,'contractSha256':NativeContract(FARM).identity,'baselineSha256':FARM.sha256,
        'payloadSha256':RELOC['payload_sha256'],'testSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'hardwareRequests':0,'scope':'固定 Linux 帧/输出白名单、无并行句柄与回调临界段、最小余量固定命令、阶段/分块/逐钩子失败停止及主机时间预算',
        'limitations':['checker 和 USB 为替身；本测试不证明目标 require-held 组合','主机预算检查不硬取消阻塞的系统调用；不保证整次安装必在 20 分钟内完成']}
    (HERE/'build/native-capture-r1/hold-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False));raise SystemExit(not r.wasSuccessful())
