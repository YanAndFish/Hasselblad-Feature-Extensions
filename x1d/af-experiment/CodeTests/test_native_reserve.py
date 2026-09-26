"""独立块申请原型与原厂分配器联合执行；只在电脑上构造堆状态。"""
import hashlib,json,struct,time,unittest
from pathlib import Path
from test_native_memory import Heap,FARM,HERE,BUILD
from unicorn.arm_const import *
M=json.loads((BUILD/'reserve-manifest.json').read_text(encoding='utf-8'))
BLOB=(BUILD/'reserve.bin').read_bytes()
assert hashlib.sha256(BLOB).hexdigest()==M['payloadSha256']
for p,h in M['sourceSha256'].items():assert hashlib.sha256((HERE/p).read_bytes()).hexdigest()==h
DESC=0x80f000

class Reservation(Heap):
    def __init__(self):
        super().__init__();self.u.mem_map(0x900000,0x10000);self.u.mem_write(M['base'],BLOB)
        self.put(0x6bb470,0x6c0000);self.put(0x6baccc,0x6c0000)
        p=self.alloc(64);self.free(p) # 已初始化的模拟原厂堆，原型禁止自行初始化。
        self.malloc_calls=0;self.request()
    def hook(self,u,a,size,_):
        if a==0x184a60 and hasattr(self,'malloc_calls'):self.malloc_calls+=1
        if M['base']<=a<M['end']:return
        super().hook(u,a,size,_)
    def put(self,address,v):self.u.mem_write(address,struct.pack('<I',v))
    def request(self,size=16384,remaining=131072,sequence=1):
        fields=[0x31524e41,1,sequence,size,remaining];checksum=0x6c871ae5
        for v in fields:checksum^=v
        self.u.mem_write(DESC,struct.pack('<13I',*fields,checksum,1,0,0,0,0,0,0))
    def reserve(self,mode=31):
        u=self.u;u.reg_write(UC_ARM_REG_CPSR,mode);u.reg_write(UC_ARM_REG_SP,0x80dff0)
        u.reg_write(UC_ARM_REG_R0,DESC);u.reg_write(UC_ARM_REG_LR,0x800000)
        for i in range(4,12):u.reg_write(globals()['UC_ARM_REG_R'+str(i)],0xabcd0000+i)
        u.emu_start(M['symbols']['nr_reserve'],0x800000,count=500000)
        assert u.reg_read(UC_ARM_REG_PC)==0x800000 and u.reg_read(UC_ARM_REG_SP)==0x80dff0
        assert all(u.reg_read(globals()['UC_ARM_REG_R'+str(i)])==0xabcd0000+i for i in range(4,12))
        assert self.critical==0 and self.word(0x6badec)==0
        return list(struct.unpack('<13I',u.mem_read(DESC,52)))

class ReservationTests(unittest.TestCase):
    def test_independent_allocation_is_aligned_and_duplicate_is_no_op(self):
        c=Reservation();r=c.reserve();self.assertEqual(r[6:8],[3,0])
        self.assertEqual(r[9]%32,0);self.assertGreaterEqual(r[10]-8,16384)
        self.assertGreaterEqual(r[12],131072);self.assertEqual(c.malloc_calls,1)
        self.assertEqual(c.reserve(),r);self.assertEqual(c.malloc_calls,1)
        self.assertEqual(c.failed,0)
    def test_interrupt_wrong_task_and_active_af_never_call_allocator(self):
        for mode,current,state in [(18,0x6c0000,0),(17,0x6c0000,0),(19,0x6c0000,0),
                                   (31,0x6c1000,0),(31,0x6c0000,4)]:
            c=Reservation();c.put(0x6baccc,current);c.put(0x6bb46c,state);before=c.free_bytes()
            self.assertEqual(c.reserve(mode)[6:8],[4,1]);self.assertEqual(c.free_bytes(),before)
            self.assertEqual(c.malloc_calls,0)
    def test_incomplete_publication_invalid_bounds_and_bad_checksum_reject(self):
        for field,value in [(0,0),(1,9),(2,0),(3,4095),(3,32769),(4,0),(5,0)]:
            c=Reservation();c.put(DESC+4*field,value)
            self.assertEqual(c.reserve()[6:8],[4,2]);self.assertEqual(c.malloc_calls,0)
        c=Reservation();c.put(DESC+24,0);self.assertEqual(c.reserve()[6],0);self.assertEqual(c.malloc_calls,0)
    def test_corrupt_heap_and_uninitialized_heap_reject_without_allocator(self):
        for a,v in [(0x6baca8,0xffffffff),(0x6baca8,0x2baca9),(0x2baca8,0x2baca8),
                     (0x2bacac,0x80000040),(0x6bacb0,0),(0x6bacb4,1),
                     (0x6bacbc,0),(0x6bacac,8)]:
            c=Reservation();c.put(a,v);self.assertEqual(c.reserve()[6:8],[4,3])
            self.assertEqual(c.malloc_calls,0);self.assertEqual(c.failed,0)
    def test_minimum_remaining_rejects_before_native_failure_hook(self):
        c=Reservation();a=c.alloc(1400000);b=c.alloc(1400000);c.alloc(1300000)
        c.free(a);c.free(b)
        # 只剩下低于最小剩余预算的内存时，申请失败且不进入原厂 malloc 失败钩子。
        c.alloc(2800000);c.malloc_calls=0;c.request(32768,131072)
        self.assertEqual(c.reserve()[6:8],[4,4]);self.assertEqual(c.malloc_calls,0);self.assertEqual(c.failed,0)
    def test_fragmentation_rejects_even_when_total_free_is_sufficient(self):
        c=Reservation();blocks=[c.alloc(32768) for _ in range(127)]
        self.assertTrue(all(blocks))
        for i in range(0,126,2):c.free(blocks[i])
        self.assertGreater(c.free_bytes(),2000000);c.malloc_calls=0;c.request(32768,131072)
        self.assertEqual(c.reserve()[6:8],[4,4]);self.assertEqual(c.malloc_calls,0);self.assertEqual(c.failed,0)

if __name__=='__main__':
    start=time.perf_counter();result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ReservationTests))
    report={'tests':result.testsRun,'passed':result.wasSuccessful(),'failures':len(result.failures),'errors':len(result.errors),
            'seconds':time.perf_counter()-start,'baselineSha256':FARM.sha256,'payloadSha256':M['payloadSha256'],
            'hardwareRequests':0,'allocatedCameraRange':None,'testSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'scope':'原型与原厂 heap_4 联合执行；不含真实任务hook/缓存/USB事务，CPU临界区与失败钩子为替身'}
    (BUILD/'reserve-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False));raise SystemExit(not result.wasSuccessful())
