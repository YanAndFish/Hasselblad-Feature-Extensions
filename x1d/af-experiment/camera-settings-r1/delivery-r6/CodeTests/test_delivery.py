"""真实 AF Python 流程/原厂 ARM 分配器；USB、时钟与缓存由替身提供。"""
import ctypes, hashlib, json, sys, tempfile, unittest
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1]
AF=HERE.parent
sys.path[:0]=[str(HERE),str(AF/'CodeTests')]
from runtime import *
from test_upgrade import Model, NewHoldPacket, Journal, FARM, OUT
from test_native_loader import Packet
from rollback import AfOnlyRollbackContract, AfOnlyRollbackLoader
from af_only_install import read_json, old
from read_usb_link_once import UsbFailure, U32

class MemoryTrace:
    def __init__(self):self.events=[]
    def append(self,item):self.events.append(item)

class R3Model(TracedIO,Model):
    is_hardware=False
    def __init__(self,c,trace):
        super().__init__(c,trace)
        self.now=0.;self.clock=lambda:self.now
        self.delay=0.;self.read_calls=0;self.policy=[];self.corrupt=False
    def transport(self,kind,a,v):
        packet=Packet(self,kind,a,v)
        base_read=packet.read_reply
        owner=self
        def read(timeout):
            owner.read_calls+=1
            owner.now+=min(owner.delay,timeout/1000)
            if owner.delay>timeout/1000:raise UsbFailure('USB_READ',121)
            raw=base_read(512)
            return b'bad' if owner.corrupt else raw
        packet.read_reply=lambda size:read(2000)
        class WinUsb:
            def WinUsb_SetPipePolicy(self,usb,endpoint,policy,size,pointer):
                assert (endpoint,policy,size)==(0x82,3,4)
                self.timeout=ctypes.cast(pointer,ctypes.POINTER(U32)).contents.value
                owner.policy.append(self.timeout)
                return 1
            def WinUsb_ReadPipe(self,usb,endpoint,buffer,size,count,overlapped):
                assert (endpoint,size,overlapped)==(0x82,512,None)
                raw=read(self.timeout)
                ctypes.memmove(buffer,raw,len(raw))
                ctypes.cast(count,ctypes.POINTER(U32)).contents.value=len(raw)
                return 1
        packet.winusb=WinUsb();packet.usb=None
        packet.check=lambda ok,code:None if ok else (_ for _ in ()).throw(UsbFailure(code,121))
        return self.wrap(packet,self.read_timeout,True)
    def hold_transport(self,packet,token):
        return self.wrap(NewHoldPacket(self,packet,token),20000,False)

def prepare(trace=None):
    c=AfOnlyContract(FARM,nonce=41)
    io=R3Model(c,trace or MemoryTrace())
    return c,io,AfOnlyLoader(c,io)

class DeliveryTests(unittest.TestCase):
    def test_first_reply_extended_once_and_normal_timeout(self):
        c,io,l=prepare();l.hold_initial();io.delay=3
        self.assertEqual(io.exchange('version'),old.VERSIONS)
        self.assertEqual(io.read_calls,1);self.assertEqual(io.policy,[20000])
        with self.assertRaises(UsbFailure):io.read(old.CB)
        self.assertTrue(io.failed);self.assertEqual(io.read_calls,2)
        self.assertEqual(io.trace.events[-1]['win32'],121)
        self.assertEqual(io.trace.events[-1]['timeoutMs'],2000)
        count=io.requests
        with self.assertRaises(RuntimeError):io.read(old.CB)
        self.assertEqual(io.requests,count);self.assertTrue(io.closed)

    def test_timeout_segment_cap_and_no_retry(self):
        c,io,l=prepare();l.hold_initial();io.segment_deadline=io.now+5;io.delay=6
        with self.assertRaises(UsbFailure):io.exchange('version')
        self.assertEqual(io.policy,[5000]);self.assertEqual(io.read_calls,1)
        self.assertTrue(io.failed);self.assertEqual(io.opens,io.closes)

    def test_exact_preflight_address_survives_usb_failure(self):
        c,io,l=prepare()
        original=io.transport
        def at_address(kind,a,v):
            io.delay=21 if a==0x19da54 else 0
            return original(kind,a,v)
        io.transport=at_address
        with self.assertRaises(UsbFailure):l.preflight()
        event=io.trace.events[-1]
        self.assertEqual(event['address'],'0x19da54')
        self.assertEqual(event['nextRequest'],3234)
        self.assertEqual(event['timeoutMs'],20000)
        self.assertEqual(event['win32'],121)
        self.assertEqual(io.writes,0);self.assertIsNone(io.journal)

    def test_failed_hold_does_not_issue_farm_read(self):
        c,io,l=prepare()
        io.fault=lambda phase,kind,a,v:'before' if kind=='hold_check' else None
        with self.assertRaises(OSError):l.preflight()
        self.assertEqual(io.read_calls,0);self.assertFalse(io.after_hold)
        self.assertTrue(io.failed);self.assertTrue(io.closed)

    def test_wrong_reply_not_drained_or_accepted(self):
        c,io,l=prepare();l.hold_initial();io.corrupt=True
        with self.assertRaises(ValueError):io.exchange('version')
        self.assertEqual(io.read_calls,1);self.assertTrue(io.closed)
        self.assertFalse(io.trace.events[-1]['ok'])

    def test_durable_trace_preflight_failure_and_torn_tail(self):
        folder=HERE/'CodeTests/output';folder.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=folder) as directory:
            path=Path(directory)/'trace.jsonl'
            c=AfOnlyContract(FARM,nonce=42);trace=Trace(path,c.identity)
            io=R3Model(c,trace);l=AfOnlyLoader(c,io);io.delay=21
            with self.assertRaises(UsbFailure):l.preflight()
            trace.close();audit=Trace.inspect(path)
            last=audit['events'][-1]
            self.assertTrue(audit['completeTail']);self.assertEqual(last['win32'],121)
            self.assertEqual(last['kind'],'version');self.assertEqual(last['writes'],0)
            self.assertTrue(last['allHandlesClosed']);self.assertIsNone(io.journal)
            with path.open('ab') as f:f.write(b'{"partial":')
            self.assertFalse(Trace.inspect(path)['completeTail'])

    def test_trace_write_failure_blocks_dispatch(self):
        class Broken:
            def append(self,data):raise OSError('trace disk failure')
        c,io,l=prepare(Broken())
        with self.assertRaises(OSError):l.preflight()
        self.assertEqual(io.requests,0);self.assertTrue(io.failed)

    def test_complete_preflight_identical_and_no_ram_writes(self):
        c,io,l=prepare();l.preflight()
        self.assertEqual((io.requests,io.writes,io.hold_requests),(7905,0,31))
        self.assertEqual(len(io.policy),31)
        self.assertIsNone(io.journal);self.assertTrue(io.closed)
        self.assertEqual(l.phase,'prepared')
        for a,v in c.factory_flash_expected.items():self.assertEqual(io.cpu.word(a),v)

    def test_full_install_and_rollback_unchanged_checks(self):
        c,io,l=prepare();l.preflight();j=Journal();l.attach(j);l.probe()
        result,header=l.stage()
        out=HERE/'build'/f'{result[9]:08x}'
        l.install(result,header,read_json(out/'capture-manifest.json'),(out/'candidate.bin').read_bytes())
        self.assertEqual(l.phase,'installed_settings_until_restart')
        self.assertEqual(io.cpu.malloc_calls,1);self.assertTrue(io.closed)
        self.assertNotEqual((out/'candidate.bin').read_bytes(),(OUT/'candidate.bin').read_bytes())
        self.assertEqual(c.offline['source_sha256'],read_json(out/'capture-manifest.json')['source_sha256'])
        rc=AfOnlyRollbackContract(j.record,FARM)
        rio=R3Model(rc,MemoryTrace());rio.cpu=io.cpu;rio.cpu.block_af()
        rio.clean,rio.visible=io.clean,io.visible
        rl=AfOnlyRollbackLoader(rc,rio);rl.preflight();rj=Journal();rl.attach(rj)
        retained=bytes(rio.cpu.u.mem_read(rc.candidate['base'],len(rc.candidate_blob)))
        free=rio.cpu.free_bytes();rl.probe();rl.stage();rl.restore()
        self.assertEqual(rl.phase,'rolled_back_until_restart')
        self.assertEqual(rio.cpu.malloc_calls,1);self.assertEqual(rio.cpu.free_bytes(),free)
        self.assertEqual(bytes(rio.cpu.u.mem_read(rc.candidate['base'],len(rc.candidate_blob))),retained)
        for a,v in {**rc.restore_bootstrap,**rc.restored_hooks,**rc.factory_flash_expected}.items():
            self.assertEqual(rio.cpu.word(a),v)
        self.assertTrue(rio.closed);self.assertEqual(rio.opens,rio.closes)

    def test_ambiguous_write_stops_with_durable_pending(self):
        for timing in ('before','after'):
            c,io,l=prepare();l.preflight();j=Journal();l.attach(j)
            io.fault=lambda phase,kind,a,v:timing if kind=='write' else None
            with self.assertRaises(OSError):l.probe()
            self.assertIsNotNone(j.record['inFlight']);self.assertTrue(io.failed)
            self.assertTrue(io.closed);count=io.requests
            with self.assertRaises(RuntimeError):io.read(old.CB)
            self.assertEqual(io.requests,count)

if __name__=='__main__':unittest.main(verbosity=2)
