"""实机适配的报文白名单、一次发送和异常关闭；传输完全为替身。"""
from pathlib import Path
import hashlib,json,sys,unittest
from unittest.mock import patch
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE/'research'))
import mechanical_irq_live as m
class Native:
    instances=[];fail=False
    def __init__(self,*args):
        self.args=args;self.sent=False;self.usb=1;self.winusb=self;self.closed=False;self.instances.append(self)
    def open(self):return None
    def prepare(self):pass
    def WinUsb_SetPipePolicy(self,*args):return 1
    def check(self,result,label):assert result
    def write_query(self,size):
        assert len(m.packet(*self.args,size))==size;self.sent=True;return size
    def read_reply(self,size):
        if self.fail:raise RuntimeError('synthetic ambiguous reply')
        return bytes.fromhex('1c02010803')+bytes(size-5)
    def close(self):self.closed=True;return {'file':True,'interface':True}
class Tests(unittest.TestCase):
    def setUp(self):
        # 仅隔离报文测试的入口校验；不修改磁盘隔离标记、不开放真实设备。
        self.validation_patch=patch.object(m,'validate',return_value={'offlineFixture':True})
        self.validation_patch.start();self.addCleanup(self.validation_patch.stop)
    def test_live_quarantine_precedes_device_open(self):
        self.validation_patch.stop()
        Native.instances=[]
        original=Path.read_text
        def read(path,*args,**kwargs):
            return '{"active":true}' if path==m.s.OUT/'live-quarantine.json' else original(path,*args,**kwargs)
        with patch.object(m,'Native',Native),patch.object(Path,'read_text',read):
            with self.assertRaisesRegex(RuntimeError,'暂停'):m.IO('offline quarantine test')
        self.assertEqual(Native.instances,[])
    def test_previous_stage_release_precedes_device_open(self):
        self.validation_patch.stop();Native.instances=[]
        original=Path.read_text
        def read(path,*args,**kwargs):
            return '{"active":false,"release":{"approvedStageSha256":"old-stage"}}' if path==m.s.OUT/'live-quarantine.json' else original(path,*args,**kwargs)
        with patch.object(m,'Native',Native),patch.object(Path,'read_text',read):
            with self.assertRaisesRegex(RuntimeError,'候选已变化'):m.IO('offline changed-stage test')
        self.assertEqual(Native.instances,[])
    def test_standard_read_and_write_replies(self):
        self.assertEqual(m.reply('read',bytes.fromhex('f50001087856341200')+bytes(503),512),0x12345678)
        self.assertEqual(m.reply('write',bytes.fromhex('f300010800')+bytes(507),512),0)
    def test_control_scope(self):
        for phase,kind,a,v in (('capture','power-down',None,None),('stage','power-down',None,1),
                               ('stage','write',0x2b20cc,0),('stage','write',0xf8007000,0)):
            with self.assertRaises(ValueError):m.packet(phase,kind,a,v)
        for raw in (bytes(512),bytes.fromhex('1c02010802')+bytes(507),bytes.fromhex('1c02010803')):
            with self.assertRaises(ValueError):m.reply('power-down',raw,512)
        with self.assertRaises(ValueError):m.reply('stage',bytes.fromhex('1c02010803')+bytes(507),512)
    def test_one_shutdown_and_closed_handle(self):
        Native.instances=[];Native.fail=False
        with patch.object(m,'Native',Native),patch.object(m.usb,'validate_interface',return_value=512):
            io=m.IO('offline transport test')
            self.assertEqual(io.exchange('power-down'),3)
            with self.assertRaises(RuntimeError):io.exchange('power-down')
        self.assertEqual(len(Native.instances),1);self.assertTrue(Native.instances[0].closed)
        self.assertEqual((io.requests,io.writes,io.closed,io.failed),(1,1,True,False))
    def test_uncertain_failure_stops_all_followups(self):
        Native.instances=[];Native.fail=True
        with patch.object(m,'Native',Native),patch.object(m.usb,'validate_interface',return_value=512):
            io=m.IO('offline transport failure test')
            with self.assertRaises(RuntimeError):io.exchange('power-down')
            with self.assertRaises(RuntimeError):io.exchange('version')
        self.assertEqual(len(Native.instances),1);self.assertTrue(io.failed and io.closed)
        Native.fail=False
    def test_capture_requires_finished_stage(self):
        io=m.IO('offline stage gate test')
        with self.assertRaises(RuntimeError):m.Capture(io)
        class Stage:pass
        st=Stage();st.io=io;st.record={}
        with self.assertRaises(RuntimeError):io.begin_capture(st)
        self.assertEqual(io.phase,'stage')
if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    if not result.wasSuccessful():raise SystemExit(1)
    files=(Path(__file__),HERE/'research/mechanical_irq_live.py')
    report={'passed':True,'tests':result.testsRun,'hardwareRequests':0,'transportIsStub':True,
            'sourceHashes':{str(p.relative_to(HERE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    (m.s.OUT/'irq-live-adapter-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
