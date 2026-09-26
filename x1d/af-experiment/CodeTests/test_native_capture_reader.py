"""同轮身份、稳定快照与不确定帧关联的负例；不连接设备。"""
import hashlib,json,struct,sys,tempfile,time,unittest
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
from native_capture_reader import Snapshot,CaptureReadIO,decode,EXEC_MAGIC
from test_native_loader import staged,NativeContract,FARM,RELOC,BLOB
from r3_install_journal import InstallJournal

def fixture():
    header=[0x3150434e,2,7,1,3,0,1,EXEC_MAGIC,0,0,0,0]
    raw=[[2,1,100,7,3,1000,2000,0,1|(5<<8)|(476<<16)]]
    af=[[2,3,111,7,3,10,0,99,0],[4,2,112,7,3,3000,0,0,0],
        [6,4,113,7,3,1,10,3000,0x10001]]
    return header,raw,af

class ReaderTests(unittest.TestCase):
    def test_same_tick_keeps_independent_streams_and_rejects_wrong_command_writer(self):
        h,raw,af=fixture();h[8]=1;control=[[2,6,112,7,3,1,500,500,110]]
        r=decode(h,raw,af,control)
        self.assertEqual(r['controlRecords'][0]['stream'],'control')
        self.assertEqual(r['afRecords'][1]['observedTick'],r['controlRecords'][0]['observedTick'])
        self.assertNotIn('combinedRecords',r)
        control[0][5]=0
        with self.assertRaisesRegex(ValueError,'writer mismatch'):decode(h,raw,af,control)
        h,raw,af=fixture();h[4]=4;af.append([8,6,112,7,3,1,500,500,110])
        with self.assertRaisesRegex(ValueError,'writer mismatch'):decode(h,raw,af)
    def test_changing_control_counter_rejects_snapshot_without_retry(self):
        c,io,l,j,r,h=staged();l.install(r,h,RELOC,BLOB)
        new=NativeContract(FARM,nonce=j.record['bootstrapNonce'])
        s=Snapshot(new,io,j.record,RELOC,BLOB);original=io.read;start=RELOC['symbols']['nc_capture'];seen=[]
        def changing(a):
            v=original(a)
            if a==start:
                seen.append(a)
                if len(seen)==2:io.cpu.put(start+32,1)
            return v
        io.read=changing
        with self.assertRaisesRegex(RuntimeError,'changed during'):s.read()
        self.assertEqual(len(seen),2)
    def test_native_value_pairing_never_claims_physical_timestamp_or_frame(self):
        r=decode(*fixture());p=r['nativePairs'][0]
        self.assertTrue(p['nativeFifoValuesMatched']);self.assertEqual(p['rawCandidateCount'],1)
        self.assertEqual(p['rawObservedTick'],100);self.assertEqual(p['lensSequence'],99)
        self.assertIsNone(p['sampleTick']);self.assertEqual(p['algorithmMetadataFlags'],0)
        self.assertFalse(p['physicalFrameAlignmentVerified']);self.assertFalse(r['predictionCalibrationAvailable'])
    def test_duplicate_cv_is_ambiguous_instead_of_nearest_time_selection(self):
        h,raw,af=fixture();h[3]=2;raw.append([4,1,105,7,3,1000,2000,0,0])
        p=decode(h,raw,af)['nativePairs'][0]
        self.assertEqual(p['rawCandidateCount'],2);self.assertIsNone(p['rawSequence'])
        self.assertIsNone(p['rawObservedTick'])
    def test_missing_mismatched_or_other_generation_rows_are_not_joined(self):
        h,raw,af=fixture();af[0][5]=11
        p=decode(h,raw,af)['nativePairs'][0];self.assertFalse(p['nativeFifoValuesMatched'])
        h,raw,af=fixture();raw[0][3]=6
        p=decode(h,raw,af)['nativePairs'][0];self.assertEqual(p['rawCandidateCount'],0)
    def test_torn_commit_and_out_of_range_fifo_are_rejected(self):
        h,raw,af=fixture();raw[0][0]=3
        with self.assertRaisesRegex(ValueError,'torn'):decode(h,raw,af)
        h,raw,af=fixture();af[-1][-1]=0x50001
        with self.assertRaisesRegex(ValueError,'head bounds'):decode(h,raw,af)
    def test_fixed_snapshot_reads_only_after_valid_installation_and_preserves_hardware_state(self):
        c,io,l,j,r,h=staged();l.install(r,h,RELOC,BLOB)
        header,raw,af=fixture();start=RELOC['symbols']['nc_capture']
        io.cpu.u.mem_write(start,struct.pack('<12I',*header))
        io.cpu.u.mem_write(start+48,struct.pack('<9I',*raw[0]))
        for i,row in enumerate(af):io.cpu.u.mem_write(start+48+64*36+i*36,struct.pack('<9I',*row))
        new=NativeContract(FARM,nonce=j.record['bootstrapNonce'])
        before=io.writes;requests=io.requests
        report=Snapshot(new,io,j.record,RELOC,BLOB).read()
        self.assertEqual(io.writes,before);self.assertGreater(io.requests,requests)
        self.assertEqual(len(report['nativePairs']),1);self.assertTrue(report['allHandlesClosed'])
        self.assertEqual(report['hardwareRequests'],0)
    def test_stale_installation_nonce_is_rejected_before_record_collection(self):
        c,io,l,j,r,h=staged();l.install(r,h,RELOC,BLOB)
        new=NativeContract(FARM,nonce=j.record['bootstrapNonce']);s=Snapshot(new,io,j.record,RELOC,BLOB)
        io.cpu.put(c.request+8,777)
        with self.assertRaisesRegex(RuntimeError,'nonce/allocation'):s.read()
    def test_busy_or_changing_capture_has_no_automatic_retry(self):
        c,io,l,j,r,h=staged();l.install(r,h,RELOC,BLOB)
        new=NativeContract(FARM);s=Snapshot(new,io,j.record,RELOC,BLOB)
        io.cpu.put(0x6bb46c,3)
        with self.assertRaisesRegex(RuntimeError,'idle'):s.read()
        io.cpu.put(0x6bb46c,0);original=io.read;start=RELOC['symbols']['nc_capture'];seen=[]
        def changing(a):
            v=original(a)
            if a==start:
                seen.append(a)
                if len(seen)==2:io.cpu.put(start+8,1)
            return v
        io.read=changing
        with self.assertRaisesRegex(RuntimeError,'changed during'):s.read()
        self.assertEqual(len(seen),2)
    def test_read_client_rejects_writes_without_opening_transport(self):
        c=NativeContract(FARM);io=CaptureReadIO(c)
        with self.assertRaisesRegex(ValueError,'read-only'):io.exchange('write',c.control,2)
        self.assertEqual(io.requests,0)
    def test_durable_journal_recovers_chain_and_marks_incomplete_tail(self):
        parent=HERE/'build/native-capture-r1/journal-tests';parent.mkdir(parents=True,exist_ok=True)
        folder=Path(tempfile.mkdtemp(prefix='case-',dir=parent));path=folder/'journal.json';identity='a'*64
        journal=InstallJournal(path,identity,backend='offline_packet_model')
        journal.begin('test',('write',0x2b2800,0));journal.complete()
        journal.begin('test',('wake_read',0x2b37b8,0));journal.close()
        r=InstallJournal.read_record(path,identity)
        self.assertIsNotNone(r['inFlight']);self.assertEqual(r['sequence'],2)
        self.assertFalse(r['journalAudit']['incompleteTail'])
        with journal.events_path.open('ab') as f:f.write(b'{"partial":')
        r=InstallJournal.read_record(path,identity);self.assertTrue(r['journalAudit']['incompleteTail'])
        with self.assertRaises(RuntimeError):InstallJournal(path,identity,backend='offline_packet_model')

if __name__=='__main__':
    start=time.perf_counter();result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ReaderTests))
    report={'tests':result.testsRun,'passed':result.wasSuccessful(),'failures':len(result.failures),'errors':len(result.errors),
        'seconds':time.perf_counter()-start,'hardwareRequests':0,'baselineSha256':FARM.sha256,
        'payloadSha256':RELOC['payload_sha256'],'testSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'scope':'读取合同与解析、跨轮/奇数commit/重复CV/错配/忙状态负例；持久事件链和不完整尾部',
        'limitations':['读取传输为报文模型；样本是固定标量输入，不代表实机标定']}
    (HERE/'build/native-capture-r1/reader-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False));raise SystemExit(not result.wasSuccessful())
