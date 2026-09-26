"""阶段主机装入、任务退出边界和双 IRQ 交接；全部使用内存替身。"""
from pathlib import Path
import copy
import hashlib
import importlib.util
import json
import struct
import sys
import unittest
from unittest.mock import patch
HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE/'research'))
import mechanical_irq_stage_loader as s
spec=importlib.util.spec_from_file_location('stage_capture_fixture',HERE/'CodeTests/test_mechanical_irq_loader.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)

class IO(base.FakeIO):
    def __init__(self,power=0,barrier=1,close_result=0):
        super().__init__();self.ops=[];self.barrier=barrier;self.retired=False
        self.close_result=close_result
        for a in s.READ_SET:self.memory.setdefault(a,0)
        for a in s.HOOK_WORDS+s.ORIGINAL_CALL_WORDS:self.memory[a]=struct.unpack_from('<I',base.FARM,a-0x100000)[0]
        self.memory.update({0x2129004:s.PLAN['bytes'],0x2129008:0x2129040,0x6db2c4:0x6e0000,0x2b20cc:power})
        for n in range(0x21,0x27):self.memory[0x2b4000+n*4]=n<<20|0xc02
    def exchange(self,kind,address=None,value=None):
        s.request(kind,address,value)
        if kind!='stage':
            with patch.object(s.capture,'request',s.request):return super().exchange(kind,address,value)
        self.ops.append(value);self.requests+=1
        if self.retired:return self.barrier
        r=s.RECORD
        self.memory.update({r:0x32504749,r+4:value,r+8:0,r+24:self.memory[0x2b20cc]})
        if value==0xa0:self.memory.update({r+12:0,r+16:0,r+20:0})
        elif value==0xa1:
            if self.close_result:
                self.memory[r+8]=self.close_result;return 1
            self.memory.update({r+12:1,r+16:1,s.DOWNLOAD:2})
        elif value==0xa3:self.memory.update(s.ORIGINAL_HOOKS);self.retired=True
        else:raise AssertionError('unexpected private operation')
        return 0

class Stager(s.Stager):
    def save(self):self.saved_copy=copy.deepcopy(self.record)

def prepare(**kwargs):
    st=Stager(IO(**kwargs));st.prepare(base.FARM,HERE/'build/model-no-file.json');return st
def installed(**kwargs):
    st=prepare(**kwargs);st.probe();st.install_disarmed();return st

class Tests(unittest.TestCase):
    def test_install_configure_retire_then_capture(self):
        st=installed();self.assertTrue(st.configure());st.retire_and_clear()
        self.assertEqual(st.io.ops,[0xa0,0xa1,0xa3,0xaf])
        self.assertTrue(st.record['irq_capture_may_follow'])
        self.assertTrue(st.record['task_barrier_confirmed'])
        self.assertFalse(st.record['installed'])
        # 切换固定白名单；同一 RAM 模型保留阶段结束后的真实内存状态。
        io=base.FakeIO();io.memory.update(st.io.memory)
        cap=base.Loader(io);cap.prepare(base.FARM,HERE/'build/model-capture-no-file.json')
        cap.probe();cap.install_disarmed();cap.verify(0)
        self.assertFalse(cap.record.get('armed',False))
    def test_native_close_decides_powered_resources_without_host_power_down(self):
        st=installed(power=1,close_result=25)
        before=st.io.memory[s.DOWNLOAD]
        self.assertFalse(st.configure())
        self.assertEqual(st.io.ops,[0xa0,0xa1]);self.assertEqual(st.io.memory[s.DOWNLOAD],before)
        self.assertFalse(st.record['fpga_configured'])
        self.assertFalse(st.record['requires_restart'])
        self.assertFalse(any(address==0x22dbb0 for address,value in st.io.trace))
    def test_missing_barrier_never_clears_stage(self):
        st=installed(barrier=0)
        with self.assertRaises(RuntimeError):st.retire_and_clear()
        self.assertTrue(st.record['task_retired']);self.assertFalse(st.record['arena_cleared'])
        self.assertTrue(any(st.io.memory[s.START+i] for i in range(0,s.SIZE,4)))
    def test_changed_original_close_precedes_private_command(self):
        st=installed();st.io.memory[0x22e3d4]^=1
        with self.assertRaisesRegex(RuntimeError,'关闭或睡眠入口'):st.configure()
        self.assertEqual(st.io.ops,[])
    def test_rejects_live_transport_and_unlisted_hardware_writes(self):
        with self.assertRaises(RuntimeError):s.Stager(object())
        with self.assertRaises(ValueError):s.request('write',s.ENTRIES['mechanical_irq_guard_active'],1)
        for a,v in ((0xf8007000,0x40000000),(0x2129040,0),(0x42000010,3)):
            with self.assertRaises(ValueError):s.request('write',a,v)
        for op in (0,1,2,0xff):
            with self.assertRaises(ValueError):s.request('stage',None,op)
    def test_identity_failures_precede_io(self):
        io=IO();st=Stager(io)
        with self.assertRaises(RuntimeError):st.prepare(b'wrong',HERE/'build/no-file.json')
        self.assertEqual(io.requests,0)
        with patch.object(s,'payload',side_effect=RuntimeError('changed source')):
            with self.assertRaises(RuntimeError):st.prepare(base.FARM,HERE/'build/no-file.json')
        self.assertEqual(io.requests,0)

def run(farm):
    base.FARM=farm
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    if not result.wasSuccessful():raise AssertionError('stage loader model failed')
    report={'passed':True,'tests':result.testsRun,'hardwareRequests':0,'installed':False,
        'stageSha256':s.BUILD['sha256'],'taskAndRegistersAreExplicitModels':True,
        'stageToDisarmedCaptureHandoffPassed':True,'physicalConfigurationValidated':False,
        'sourceHashes':{str(p.relative_to(HERE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),HERE/'research/mechanical_irq_stage_loader.py')}}
    (s.OUT/'irq-stage-loader-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report

if __name__=='__main__':
    sys.path.insert(0,str(HERE.parents[1]/'x1d/tools'))
    from farm_diagnostic_binary import FarmApplication
    print(json.dumps(run(FarmApplication().data),ensure_ascii=False))
