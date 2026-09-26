"""执行原厂 heap_4 的申请/释放/合并；CPU 临界区为替身，不证明实机可安装。"""
import hashlib,json,struct,time,unittest
from pathlib import Path
from inspect_native_memory import FARM,HERE,BUILD
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import *

class Heap:
    def __init__(self):
        self.u=Uc(UC_ARCH_ARM,UC_MODE_ARM);self.u.mem_map(0x100000,0x600000)
        self.u.mem_write(0x100000,FARM.data);self.u.mem_map(0x800000,0x10000)
        self.critical=0;self.failed=0;self.visited=set()
        for address in (0x1854bc,0x185520,0x2209ac):self.u.mem_write(address,bytes.fromhex('1eff2fe1'))
        self.u.hook_add(UC_HOOK_CODE,self.hook)
    def word(self,address):return struct.unpack('<I',self.u.mem_read(address,4))[0]
    def hook(self,u,address,size,_):
        self.visited.add(address)
        if address==0x2209f4:raise AssertionError('原厂断言被触发')
        if address==0x2209ac:self.failed+=1
        if address==0x1854bc:self.critical+=1
        if address==0x185520:self.critical-=1
        if not 0x100000<=address<0x240000:raise AssertionError(hex(address))
    def run(self,address,arg):
        u=self.u;u.reg_write(UC_ARM_REG_CPSR,0x1f);u.reg_write(UC_ARM_REG_SP,0x80fff0)
        u.reg_write(UC_ARM_REG_LR,0x800000);u.reg_write(UC_ARM_REG_R0,arg)
        for i in range(4,12):u.reg_write(globals()['UC_ARM_REG_R'+str(i)],0xabcd0000+i)
        u.emu_start(address,0x800000,count=200000)
        assert u.reg_read(UC_ARM_REG_PC)==0x800000 and u.reg_read(UC_ARM_REG_SP)==0x80fff0
        assert all(u.reg_read(globals()['UC_ARM_REG_R'+str(i)])==0xabcd0000+i for i in range(4,12))
        assert self.critical==0 and self.word(0x6badec)==0
        return u.reg_read(UC_ARM_REG_R0)
    def alloc(self,size):return self.run(0x184a60,size)
    def free(self,p):self.run(0x184d0c,p)
    def free_bytes(self):return self.word(0x6bacb4)
    def block(self,p):return self.word(p-4)&0x7fffffff

class MemoryTests(unittest.TestCase):
    def test_native_allocation_preserves_flash_and_is_not_reused_while_owned(self):
        h=Heap();before=bytes(h.u.mem_read(0x2b26a0,0x1960))
        first=h.alloc(16000);af=h.alloc(16384);later=h.alloc(20000)
        self.assertEqual(first,0x2bacb0)
        self.assertTrue(first+h.block(first)<=af and af+h.block(af)<=later)
        self.assertTrue(h.word(af-4)&0x80000000);self.assertEqual(h.word(af-8),0)
        h.u.mem_write(af,b'AF owned memory'+bytes(16384-15));h.free(first)
        reused=h.alloc(10000);self.assertEqual(reused,first)
        self.assertEqual(bytes(h.u.mem_read(af,15)),b'AF owned memory')
        self.assertEqual(bytes(h.u.mem_read(0x2b26a0,0x1960)),before)
        self.assertTrue({0x188370,0x188424,0x184e2c,0x184f90}.issubset(h.visited))
        self.assertEqual(h.failed,0)
    def test_free_and_coalesce_restore_exact_original_capacity(self):
        h=Heap();first=h.alloc(1);capacity=h.free_bytes()+h.block(first);h.free(first)
        addresses=[h.alloc(s) for s in (4096,8192,16384,32,12345)]
        self.assertTrue(all(p and p%8==0 for p in addresses))
        for i in (2,0,4,1,3):h.free(addresses[i])
        self.assertEqual(h.free_bytes(),capacity)
        self.assertEqual(h.word(0x6baca8),0x2baca8)
        self.assertEqual(h.word(0x2bacac),0x400000-8)
    def test_fragmentation_requires_contiguous_space_not_only_total_free(self):
        h=Heap();a=h.alloc(1400000);b=h.alloc(1400000);c=h.alloc(1390000)
        self.assertTrue(a and b and c);h.free(a);h.free(c)
        self.assertGreater(h.free_bytes(),2000000)
        self.assertEqual(h.alloc(2000000),0)
        self.assertEqual(h.failed,1) # 原厂失败钩子实际到达，只有其正文用替身。
        h.free(b);self.assertNotEqual(h.alloc(2000000),0)
    def test_unallocated_heap_is_part_of_original_bss_and_not_static_padding(self):
        self.assertEqual(FARM.word(0x10a188),0x2b9800)
        self.assertEqual(FARM.word(0x10a18c),0x6ee9a8)
        self.assertTrue(0x2b9800<=0x2baca8<0x6baca8<0x6ee9a8)
        self.assertTrue(all(FARM.word(0x2b4000+s*4)&3==2 for s in range(2,7)))
    def test_native_diagnostic_helper_checks_alignment_and_is_not_an_access_policy(self):
        h=Heap()
        for address in (0,0x2bacb0,0x400000,0x6bac9c,0xf8f01f00):
            h.u.reg_write(UC_ARM_REG_R1,4)
            self.assertEqual(h.run(0x238ef8,address),1)
            h.u.reg_write(UC_ARM_REG_R1,4)
            self.assertEqual(h.run(0x238ef8,address+1),0)

if __name__=='__main__':
    start=time.perf_counter();result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(MemoryTests))
    report={'tests':result.testsRun,'passed':result.wasSuccessful(),'failures':len(result.failures),'errors':len(result.errors),
            'seconds':time.perf_counter()-start,'baselineSha256':FARM.sha256,'hardwareRequests':0,
            'allocatedCameraRange':None,'testSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'scope':'原厂分配/释放/合并、无待调度任务的挂起/恢复执行；临界区和失败钩子为替身，未验证实际并发/缓存/装载'}
    BUILD.mkdir(parents=True,exist_ok=True)
    (BUILD/'tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False));raise SystemExit(not result.wasSuccessful())
