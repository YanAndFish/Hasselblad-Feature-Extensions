"""新 AF 引导/堆取指探针经过原厂 IRQ/SGI 分发；CP15 与 GIC 为替身。"""
import hashlib,json,struct,sys,time,unittest
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import native_install as L
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
from test_native_memory import FARM
BUILD=HERE/'build/native-capture-r1'
M=json.loads((BUILD/'002bacc0/capture-manifest.json').read_text(encoding='utf-8'))
BLOB=(BUILD/'002bacc0/candidate.bin').read_bytes()
assert hashlib.sha256(BLOB).hexdigest()==M['payload_sha256'] and FARM.sha256==M['baseline_sha256']
for n,h in M['source_sha256'].items():assert hashlib.sha256((HERE/n).read_bytes()).hexdigest()==h

class NativeSgiCase:
    def __init__(self,farm,callback,argument,blob,descriptor=None,iar=0x40f,owned=None):
        self.u=u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
        u.mem_map(0x100000,0x200000);u.mem_write(0x100000,farm.data)
        u.mem_map(0x6ba000,0x4000);u.mem_map(0x900000,0x10000)
        u.mem_map(0xf8f00000,0x4000)
        u.mem_write(L.SCRATCH,blob);self.word(L.CB,callback);self.word(L.ARG,argument)
        self.word(0x2ad78c,0x2a4ffc);self.word(0xf8f0010c,iar)
        if descriptor is not None:
            for index,value in enumerate(descriptor):self.word(L.DESC+index*4,value)
        self.owned=owned
        if owned is not None:u.mem_write(owned[0],owned[1])
        self.callback=callback;self.iar=iar;self.cache_lines=[];self.code=[];self.mmio=[]
        self.barriers=[];self.returned=False;self.done=False
        instructions=farm.instructions(0x10a270,0x13c)
        self.cp15={i.address for i in instructions if i.mnemonic=='mcr'}
        u.hook_add(UC_HOOK_CODE,self.execute);u.hook_add(UC_HOOK_MEM_WRITE,self.write)
    def word(self,a,value=None):
        if value is None:return struct.unpack('<I',self.u.mem_read(a,4))[0]
        self.u.mem_write(a,struct.pack('<I',value))
    def execute(self,u,a,size,data):
        self.code.append(a)
        if a==0x1007cc:self.returned=True
        if a in (0x1007d8,0x1007dc):
            assert self.returned;self.barriers.append(a)
        if a==0x1007ec:self.done=True;u.emu_stop();return
        if a in self.cp15:
            # CP15维护效果是明确替身；循环、参数计算、DSB/ISB和IRQ返回顺序保持原指令。
            registers={0x10a2a0:UC_ARM_REG_R4,0x10a2f0:UC_ARM_REG_R3,
                0x10a344:UC_ARM_REG_R4,0x10a390:UC_ARM_REG_R0}
            if a in registers:self.cache_lines.append((a,u.reg_read(registers[a])))
            u.reg_write(UC_ARM_REG_PC,a+4);return
        ranges=((0x1007a8,0x1007ec),(0x18b034,0x18b09c),(0x10a270,0x10a3ac),
                (0x10acac,0x10acb4),(L.SCRATCH,L.SCRATCH+len(L.THUNK)))
        if self.owned is not None and self.owned[0]<=a<self.owned[0]+len(self.owned[1]):return
        if not any(lo<=a<hi for lo,hi in ranges):raise AssertionError('unexpected IRQ path '+hex(a))
    def write(self,u,access,a,size,value,data):
        if a==0xf8f00110:
            assert self.returned and self.barriers==[0x1007d8,0x1007dc] and value==self.iar
            self.mmio.append((a,value));return
        if a>=0xf8f00000:
            assert a in (0xf8f02740,0xf8f02770,0xf8f027b0,0xf8f027f0)
            self.mmio.append((a,value));return
        assert 0x90f000<=a<0x910000 or a in (L.DESC,L.DESC+12,0x6bacc4) or (self.owned is not None and a==self.owned[2])
    def run(self):
        u=self.u;u.reg_write(UC_ARM_REG_CPSR,0x93)
        u.reg_write(UC_ARM_REG_SP,0x90fd00);u.reg_write(UC_ARM_REG_R1,0)
        u.reg_write(UC_ARM_REG_R3,0x6bacc4)
        # 从原IRQ保存VFP寄存器后的入口开始；IAR仅由模拟器提供，没有主机IAR请求。
        u.emu_start(0x1007a8,0,count=30000)
        assert self.done and self.mmio[-1]==(0xf8f00110,self.iar)
        assert u.reg_read(UC_ARM_REG_SP)==0x90fd00
        return self

class NativeSgiTests(unittest.TestCase):
    def test_native_probe_ack_precedes_barriers_and_source_cpu_eoi(self):
        for iar in (15,0x40f):
            c=NativeSgiCase(FARM,L.SCRATCH,L.DESC,L.PROBE,iar=iar).run()
            self.assertEqual(c.word(L.DESC),L.MAGIC)
            self.assertIn(0x18b090,c.code);self.assertEqual(c.cache_lines,[])
    def test_exact_bootstrap_and_owned_code_ranges_are_maintained(self):
        for start,size in ((0x2b3400,960),(M['base'],len(BLOB))):
            for fn,site in ((L.CLEAN_RANGE,0x10a2a0),(L.INVALIDATE_RANGE,0x10a390)):
                c=NativeSgiCase(FARM,L.SCRATCH,L.DESC,L.THUNK,descriptor=(start,size,fn,0)).run()
                self.assertEqual(c.word(L.DESC+12),1)
                self.assertEqual(c.cache_lines,[(site,a) for a in range(start,start+size,32)])
                self.assertLess(c.code.index(L.SCRATCH+20),c.code.index(0x1007cc))
    def test_native_single_line_helpers_return_before_eoi(self):
        for fn,site in ((L.CLEAN,0x10a2f0),(L.INVALIDATE,0x10a344)):
            c=NativeSgiCase(FARM,fn,L.SCRATCH,L.PROBE).run()
            self.assertEqual(c.cache_lines,[(site,L.SCRATCH)])
    def test_thumb_heap_callback_runs_through_original_dispatch_and_returns_to_arm(self):
        ack=M['symbols']['nc_capture']+28;fn=M['symbols']['nc_execution_probe']
        self.assertEqual(fn&1,1)
        for iar in (15,0x40f):
            c=NativeSgiCase(FARM,fn,ack,L.THUNK,iar=iar,owned=(M['base'],BLOB,ack)).run()
            self.assertEqual(c.word(ack),L.EXEC_MAGIC)
            self.assertIn(fn&~1,c.code);self.assertFalse(c.u.reg_read(UC_ARM_REG_CPSR)&32)
            self.assertEqual(c.cache_lines,[])
    def test_owned_probe_rejects_wrong_ack_pointer(self):
        ack=M['symbols']['nc_capture']+28;fn=M['symbols']['nc_execution_probe']
        c=NativeSgiCase(FARM,fn,L.DESC,L.THUNK,owned=(M['base'],BLOB,ack)).run()
        self.assertEqual(c.word(ack),0);self.assertEqual(c.word(L.DESC),0)

if __name__=='__main__':
    start=time.perf_counter();result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(NativeSgiTests))
    report={'tests':result.testsRun,'passed':result.wasSuccessful(),'failures':len(result.failures),'errors':len(result.errors),
        'seconds':time.perf_counter()-start,'hardwareRequests':0,'baselineSha256':FARM.sha256,
        'payloadSha256':M['payload_sha256'],'testSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'completionOrder':['callback ACK','callback returns','DSB','ISB','EOI including source CPU'],
        'scope':'原厂 IRQ 分发、缓存循环/屏障、重定位 Thumb 取指探针与 EOI 实际指令；CP15维护效果/GIC 为替身',
        'limitations':['从 IRQ 完成寄存器保存之后开始；不模拟物理中断到达或真实缓存一致性',
            '实机仍必须观察本轮探针 ACK 与 pending/active 清除']}
    (BUILD/'sgi-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False));raise SystemExit(not result.wasSuccessful())
