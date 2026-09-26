"""执行原生IRQ分发、缓存helper和EOI顺序；所有MMIO与缓存效果只在模拟器内。"""
import sys,json,struct,unittest
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import full_loader_r3 as L
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *

class NativeSgiCase:
    def __init__(self,farm,callback,argument,blob,descriptor=None,iar=0x40f):
        self.u=u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
        u.mem_map(0x100000,0x200000);u.mem_write(0x100000,farm.data)
        u.mem_map(0x6ba000,0x4000);u.mem_map(0x900000,0x10000)
        u.mem_map(0xf8f00000,0x4000)
        u.mem_write(L.SCRATCH,blob);self.word(L.CB,callback);self.word(L.ARG,argument)
        self.word(0x2ad78c,0x2a4ffc);self.word(0xf8f0010c,iar)
        if descriptor is not None:
            for index,value in enumerate(descriptor):self.word(L.DESC+index*4,value)
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
        if not any(lo<=a<hi for lo,hi in ranges):raise AssertionError('unexpected IRQ path '+hex(a))
    def write(self,u,access,a,size,value,data):
        if a==0xf8f00110:
            assert self.returned and self.barriers==[0x1007d8,0x1007dc] and value==self.iar
            self.mmio.append((a,value));return
        if a>=0xf8f00000:
            assert a in (0xf8f02740,0xf8f02770,0xf8f027b0,0xf8f027f0)
            self.mmio.append((a,value));return
        assert 0x90f000<=a<0x910000 or a in (L.DESC,L.DESC+12,0x6bacc4)
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
    @classmethod
    def setUpClass(cls):
        cls.farm=L.FarmApplication();assert cls.farm.sha256==L.M['baseline_sha256']
        assert cls.farm.word(0x27b824)==0xf8f0010c and cls.farm.word(0x27b828)==0xf8f00110
    def test_native_probe_ack_precedes_barriers_and_eoi_preserves_source_cpu(self):
        for iar in (15,0x40f):
            c=NativeSgiCase(self.farm,L.SCRATCH,L.DESC,L.PROBE,iar=iar).run()
            self.assertEqual(c.word(L.DESC),L.MAGIC)
            self.assertIn(0x18b090,c.code);self.assertEqual(c.cache_lines,[])
    def test_native_clean_and_invalidate_ranges_visit_exact_aligned_lines_before_ack(self):
        for fn,site in ((L.CLEAN_RANGE,0x10a2a0),(L.INVALIDATE_RANGE,0x10a390)):
            c=NativeSgiCase(self.farm,L.SCRATCH,L.DESC,L.THUNK,
                descriptor=(L.BASE,len(L.BLOB)+len(L.WAKE_BLOB),fn,0)).run()
            self.assertEqual(c.word(L.DESC+12),1)
            self.assertEqual(c.cache_lines,[(site,a) for a in range(L.BASE,L.BASE+192,32)])
            self.assertLess(c.code.index(L.SCRATCH+20),c.code.index(0x1007cc))
    def test_native_bootstrap_line_helpers_return_before_irq_eoi(self):
        for fn,site in ((L.CLEAN,0x10a2f0),(L.INVALIDATE,0x10a344)):
            c=NativeSgiCase(self.farm,fn,L.SCRATCH,L.PROBE).run()
            self.assertEqual(c.cache_lines,[(site,L.SCRATCH)])
            self.assertEqual(c.word(L.DESC),0)
    @classmethod
    def tearDownClass(cls):
        (L.BUILD/'loader-sgi-native.json').write_text(json.dumps({
            'artifactSha256':L.ARTIFACT,'farmSha256':cls.farm.sha256,'hardwareRequests':0,
            'nativeIrqEntry':0x1007a8,'nativeDispatcher':0x18b034,'eoiInstruction':0x1007e8,
            'completionOrder':['callback ACK/write completes','callback returns','DSB','ISB','EOI'],
            'scope':'原生ARM流程，CP15缓存效果与GIC为模拟器替身',
            'limitations':['不模拟物理中断到达延迟或真实缓存一致性',
                '实机必须完成本轮探针和每段ACK，并检查SGI pending/active均清除']},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':unittest.main(verbosity=2)
