"""双 IRQ 装入/解除、白名单、原 ARM thunk 及每步故障停止；没有设备访问。"""
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
import mechanical_irq_loader as m
FARM=None

class FakeIO:
    offline_model=True
    def __init__(self,fail=None,after=False):
        self.requests=self.writes=0; self.closed=True; self.failed=False
        self.memory={a:0 for a in m.READ_SET}
        for a in m.old.CACHE_CODE+m.old.HOOK_LINES+m.old.AF_CODE+(0x214110,0x233c7c):
            self.memory[a]=struct.unpack_from('<I',FARM,a-0x100000)[0]
        for a,(_,v) in m.old.IRQ_GUARDS.items(): self.memory[a]=v
        for a in m.old.AF_SPEEDS: self.memory[a]=4500
        for a,v in ((0x2a52cc,m.ORIG_CB),(0x2a52d0,m.ORIG_ARG),(0x2a52d4,m.ORIG_CB),(0x2a52d8,m.ORIG_ARG),
                    (0xf8f01458,0x88776655),(0xf8f01858,0x04030201),(0xf8f01c14,0x55555555),(0xf8f00108,2)):
            self.memory[a]=v
        self.fail,self.after=fail,after
        self.trace=[]; self.calls=[]

    def exchange(self,kind,address=None,value=None):
        m.request(kind,address,value)
        if self.failed: raise AssertionError('operation after uncertain failure')
        self.requests+=1
        if kind=='version': return m.pre.VERSION
        if kind=='read': return self.memory[address]
        self.writes+=1
        if self.writes==self.fail and not self.after:
            self.failed=True; raise RuntimeError('synthetic before-write failure')
        self.trace.append((address,value))
        if address!=m.SGIR: self.memory[address]=value
        elif self.memory[m.CB]==m.BASE:
            code=b''.join(struct.pack('<I',self.memory[m.BASE+i]) for i in range(0,32,4))
            arg=self.memory[m.ARG]
            if code.startswith(m.PROBE): self.memory[arg]=m.PROBE_MAGIC
            elif code.startswith(m.THUNK):
                assert self.memory[arg+8] in (m.CLEAN_RANGE,m.INVALIDATE_RANGE)
                self.memory[arg+12]=1
            else:
                assert code==m.CALL_THUNK and arg==m.DESC
                self.invoke(self.memory[arg+8]); self.memory[arg+12]=1; self.memory[arg+16]=1
        if self.writes==self.fail and self.after:
            self.failed=True; raise RuntimeError('synthetic after-write failure')
        return 0

    def invoke(self,fn):
        self.calls.append(fn); r=m.RECORD
        if fn==m.SYMBOLS['mechanical_irq_setup']:
            for off,a,mask in ((80,0xf8f01458,0xffff0000),(84,0xf8f01858,0xffff0000),(88,0xf8f01c14,0xf00000)):
                self.memory[r+off]=self.memory[a]&mask
            for off,a in ((92,0x2a52cc),(96,0x2a52d0),(100,0x2a52d4),(104,0x2a52d8)):
                self.memory[r+off]=self.memory[a]
            for a,mask,value in ((0xf8f01458,0xffff0000,0xa0a00000),(0xf8f01858,0xffff0000,0x01010000),(0xf8f01c14,0xf00000,0xa00000)):
                self.memory[a]=(self.memory[a]&~mask)|value
            for a,v in ((0x2a52cc,m.SYMBOLS['mechanical_irq_hold']),(0x2a52d4,m.SYMBOLS['mechanical_irq_idle']),
                        (0x2a52d0,r),(0x2a52d8,r),(r+76,m.MAGIC)): self.memory[a]=v
        elif fn==m.SYMBOLS['mechanical_sync_cancel_old']:
            self.memory[r+8]=0
            for a in (0xf8f01108,0xf8f01208): self.memory[a]&=~m.BOTH
        elif fn==m.SYMBOLS['mechanical_irq_restore']:
            for off,a,mask in ((80,0xf8f01458,0xffff0000),(84,0xf8f01858,0xffff0000),(88,0xf8f01c14,0xf00000)):
                self.memory[a]=(self.memory[a]&~mask)|self.memory[r+off]
            for off,a in ((92,0x2a52cc),(96,0x2a52d0),(100,0x2a52d4),(104,0x2a52d8)):
                self.memory[a]=self.memory[r+off]
            self.memory[r+76]=0
        else: raise AssertionError('unexpected native target')

    def read(self,a): return self.exchange('read',a)

class Loader(m.Loader):
    def save(self): self.saved_copy=copy.deepcopy(self.record)

def prepare(fail=None,after=False):
    loader=Loader(FakeIO(fail,after))
    loader.prepare(FARM,HERE/'build/irq-model-only-no-file-written.json')
    return loader

def install(fail=None,after=False):
    loader=prepare(fail,after); loader.probe(); loader.install_disarmed()
    return loader

class Tests(unittest.TestCase):
    def test_offline_identity_checks_precede_first_io(self):
        io=FakeIO();loader=Loader(io)
        with self.assertRaises(RuntimeError):loader.prepare(b'wrong firmware',HERE/'build/unused.json')
        self.assertEqual(io.requests,0)
        with patch.object(m,'payload',side_effect=ValueError('changed candidate')):
            with self.assertRaises(ValueError):loader.prepare(FARM,HERE/'build/unused.json')
        self.assertEqual(io.requests,0)

    def test_no_live_transport_and_no_fpga_write_scope(self):
        with self.assertRaises(RuntimeError): m.Loader(object())
        for a,v in ((0xf8007000,0x40000000),(0x2129008,0),(0x42000010,3),(m.RECORD+8,1),(0x2a52cc,0)):
            with self.assertRaises(ValueError): m.request('write',a,v)

    def test_used_irqs_or_old_resident_reject_before_writes(self):
        for a,v in ((0xf8f01108,m.BOTH),(0xf8f01208,m.BOTH),(0xf8f01308,m.BOTH),
                    (0x2a52cc,0),(0xf8f00108,3),(m.PAYLOAD_START,1)):
            io=FakeIO(); io.memory[a]=v; loader=Loader(io)
            with self.assertRaises(RuntimeError): loader.prepare(FARM,HERE/'build/irq-model-only-no-file-written.json')
            self.assertEqual(io.writes,0)

    def test_install_requires_fpga_evidence_before_arm(self):
        loader=install(); self.assertTrue(loader.record['installed'])
        self.assertEqual(loader.io.memory[m.RECORD+4],0)
        with self.assertRaises(RuntimeError): loader.arm()
        self.assertFalse(loader.io.memory[0xf8f01108]&m.BOTH)
        self.assertEqual(loader.io.calls,[m.SYMBOLS['mechanical_irq_setup']])

    def test_code_precedes_slots_and_hooks_and_restore_keeps_arena(self):
        loader=install(); io=loader.io
        for a,value in m.NEW_HOOKS.items():
            index=io.trace.index((a,value))
            for off in range(0,m.PAYLOAD_BYTES,4):
                expected=struct.unpack_from('<I',m.payload(),off)[0]
                self.assertIn((m.PAYLOAD_START+off,expected),io.trace[:index])
        loader.record['fpga_configured']=True # 仅模型输入；不代表已有实机证据。
        loader.arm(); loader.unhook()
        self.assertEqual(io.memory[m.RECORD+4],0)
        self.assertEqual({a:io.memory[a] for a in m.ORIGINAL_HOOKS},m.ORIGINAL_HOOKS)
        self.assertEqual(io.memory[0xf8f01458],0x88776655)
        self.assertEqual(io.memory[0xf8f01858],0x04030201)
        self.assertEqual(io.memory[0xf8f01c14],0x55555555)
        self.assertEqual(io.memory[m.CB],m.ORIG_CB); self.assertEqual(io.memory[m.ARG],m.ORIG_ARG)
        self.assertTrue(all(io.memory[a]==0 for a in range(m.BASE,m.BASE+64,4)))
        self.assertFalse(loader.record['safe_to_overwrite_payload_without_restart'])
        self.assertEqual([io.memory[a] for a in m.old.AF_SPEEDS],[4500]*3)

    def test_actual_arm_return_thunk_and_setup_match_model(self):
        spec=importlib.util.spec_from_file_location('irq_native_loader_check',HERE/'CodeTests/test_mechanical_irq_capture.py')
        native=importlib.util.module_from_spec(spec); spec.loader.exec_module(native)
        native.FARM=FARM; native.ELF_PATH=m.OUT/'irq-target.elf'
        machine=native.Machine(real_queue=False,patched=False)
        machine.symbols['loader_thunk']=m.BASE
        machine.extra_writable={m.DESC+12,m.DESC+16}
        fake=install().io
        for name in ('mechanical_irq_setup','mechanical_sync_cancel_old','mechanical_irq_restore'):
            machine.u.mem_write(m.BASE,m.CALL_THUNK)
            for a,v in ((m.DESC,m.RECORD),(m.DESC+4,0),(m.DESC+8,m.SYMBOLS[name]),(m.DESC+12,0),(m.DESC+16,0)):
                machine.put(a,v)
            machine.call('loader_thunk',m.DESC)
            self.assertEqual(machine.word(m.DESC+16),1)
            if name!='mechanical_sync_cancel_old': self.assertEqual(machine.word(m.DESC+12),1)
            if name=='mechanical_irq_setup':
                for a in (*m.EXTRA_READ,*range(m.RECORD+76,m.RECORD+108,4)):
                    self.assertEqual(machine.word(a),fake.memory[a],hex(a))

    def test_each_write_failure_stops_without_retry(self):
        loader=install(); loader.record['fpga_configured']=True; loader.arm(); loader.unhook()
        total=loader.io.writes
        # 每个候选写入前/后发生不确定失败都不能自动继续或清理。
        for after in (False,True):
            for step in range(1,total+1):
                item=prepare(step,after)
                with self.assertRaises(RuntimeError):
                    item.probe(); item.install_disarmed(); item.record['fpga_configured']=True; item.arm(); item.unhook()
                self.assertTrue(item.io.failed); self.assertEqual(item.io.writes,step)
                self.assertIsNotNone(item.saved_copy['in_flight'])
        self.__class__.failure_positions=total*2

def run(farm):
    global FARM
    FARM=farm
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    report={'passed':result.wasSuccessful(),'tests':result.testsRun,'hardwareRequests':0,'installed':False,
        'liveLoaderEnabled':False,'fpgaLoaderIncluded':False,'actualArmThunkChecked':True,
        'failurePositions':getattr(Tests,'failure_positions',0),'firmwareSha256':hashlib.sha256(FARM).hexdigest(),
        'payloadSha256':hashlib.sha256(m.payload()).hexdigest(),
        'sourceHashes':{str(p.relative_to(HERE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
            (Path(__file__),HERE/'research/mechanical_irq_loader.py',HERE/'CodeTests/test_mechanical_irq_capture.py')}}
    (m.OUT/'irq-loader-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report

if __name__=='__main__':
    sys.path.insert(0,str(m.ROOT/'x1d/tools'))
    from farm_diagnostic_binary import FarmApplication
    print(run(FarmApplication().data))
