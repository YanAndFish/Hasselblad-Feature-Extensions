"""执行新 AF idle 引导、原厂分配器和 F4 唤醒分支；不连接相机。"""
import hashlib,json,struct,time,unittest
from pathlib import Path
from test_native_memory import Heap,FARM,HERE
from unicorn.arm_const import *
BUILD=HERE/'build/native-bootstrap-r1';M=json.loads((BUILD/'bootstrap-manifest.json').read_text(encoding='utf-8'))
BLOB=(BUILD/'bootstrap.bin').read_bytes();S=M['symbols'];REQUEST=S['nr_request'];CONTROL=S['nr_gate_control']
assert hashlib.sha256(BLOB).hexdigest()==M['payloadSha256'] and FARM.sha256==M['baselineSha256']
for p,h in M['sourceSha256'].items():assert hashlib.sha256((HERE/p).read_bytes()).hexdigest()==h
class Bootstrap(Heap):
    def __init__(self,state=0):
        super().__init__();self.u.mem_write(M['base'],BLOB)
        for a,old,new in M['emulatorOnlyHooks']:
            assert FARM.word(a)==old;self.put(a,new)
        self.put(0x6bb470,0x6c0000);self.put(0x6baccc,0x6c0000);self.put(0x6bb46c,state)
        p=self.alloc(128);self.free(p)
        self.malloc_calls=0;self.endpoint=None;self.events=[];self.reads=[]
    def put(self,a,v):self.u.mem_write(a,struct.pack('<I',v))
    def request(self):return list(struct.unpack('<13I',self.u.mem_read(REQUEST,52)))
    def hook(self,u,a,size,_):
        if a==0x184a60 and hasattr(self,'malloc_calls'):self.malloc_calls+=1
        if a in (0x19d198,0x19b964):self.endpoint=a;u.emu_stop();return
        if a==0x1a4890:
            self.events.append(u.reg_read(UC_ARM_REG_R0));u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR));return
        if a==0x1e1768:
            self.reads.append(u.reg_read(UC_ARM_REG_R0));self.endpoint=a;u.emu_stop();return
        if M['base']<=a<M['end']:self.visited.add(a);return
        super().hook(u,a,size,_)
    def registers(self):
        u=self.u;u.reg_write(UC_ARM_REG_CPSR,0xa800001f)
        for i in range(13):u.reg_write(globals()['UC_ARM_REG_R'+str(i)],0x12345000+i)
        u.reg_write(UC_ARM_REG_LR,0x800000);u.reg_write(UC_ARM_REG_SP,0x80c000);u.reg_write(UC_ARM_REG_R11,0x80c100)
        u.reg_write(UC_ARM_REG_C1_C0_2,0xf<<20);u.reg_write(UC_ARM_REG_FPEXC,1<<30)
        for i in range(32):u.reg_write(globals()['UC_ARM_REG_D'+str(i)],0x1234567800000000+i)
        self.put(0x80c100-0x94,0x20011)
        self.before={r:u.reg_read(r) for r in [*[globals()['UC_ARM_REG_R'+str(i)] for i in range(13)],UC_ARM_REG_SP,UC_ARM_REG_LR]}
    def gate(self):
        self.registers();self.endpoint=None;self.u.emu_start(0x19b960,0,count=500000)
        assert self.endpoint in (0x19d198,0x19b964)
        assert self.u.reg_read(UC_ARM_REG_CPSR)&0xf8000000==0xa8000000
        for r,v in self.before.items():
            expected=0x20011 if r==UC_ARM_REG_R3 and self.endpoint==0x19b964 else v
            assert self.u.reg_read(r)==expected,(r,hex(self.u.reg_read(r)),hex(expected))
        assert all(self.u.reg_read(globals()['UC_ARM_REG_D'+str(i)])==0x1234567800000000+i for i in range(32))
        return self.endpoint
    def wake(self,address=None):
        if address is None:address=CONTROL+4
        self.registers();self.endpoint=None
        message=0x80e000;self.u.mem_write(message,bytes.fromhex('f4000801')+struct.pack('<I',address))
        self.u.reg_write(UC_ARM_REG_R0,message)
        self.u.emu_start(S['nr_wake'],0,count=10000)
        assert self.endpoint==0x1e1768 and self.reads[-1]==message
        assert self.u.reg_read(UC_ARM_REG_SP)==0x80c000 and self.u.reg_read(UC_ARM_REG_LR)==0x800000

class BootstrapTests(unittest.TestCase):
    def test_idle_gate_allocates_once_acks_and_retains_original_flags_registers(self):
        c=Bootstrap();before=bytes(c.u.mem_read(0x2b2880,0xb80))
        self.assertEqual(c.gate(),0x19d198);r=c.request();self.assertEqual(r[6:8],[3,0])
        self.assertEqual(c.word(CONTROL+4),1);self.assertEqual(c.malloc_calls,1)
        self.assertEqual(c.gate(),0x19d198);self.assertEqual(c.request(),r)
        self.assertEqual(c.word(CONTROL+4),2);self.assertEqual(c.malloc_calls,1)
        self.assertEqual(bytes(c.u.mem_read(0x2b2880,0xb80)),before)
    def test_active_native_af_is_not_frozen_or_allocated(self):
        for state in range(1,9):
            c=Bootstrap(state);self.assertEqual(c.gate(),0x19b964)
            self.assertEqual(c.malloc_calls,0);self.assertEqual(c.word(CONTROL+4),0)
    def test_known_allocation_failure_keeps_gate_held_until_explicit_release(self):
        c=Bootstrap();c.put(0x6bacb4,0)
        self.assertEqual(c.gate(),0x19d198);self.assertEqual(c.request()[6:8],[4,3])
        self.assertEqual(c.malloc_calls,0);self.assertEqual(c.failed,0)
        c.put(CONTROL,2);self.assertEqual(c.gate(),0x19b964)
    def test_release_restores_native_event_dispatch_without_reallocation(self):
        c=Bootstrap();c.gate();p=c.request()[8];c.put(CONTROL,2)
        self.assertEqual(c.gate(),0x19b964);self.assertEqual(c.request()[8],p)
        self.assertEqual(c.malloc_calls,1)
    def test_only_fixed_ack_read_posts_once_and_always_returns_to_original_reader(self):
        c=Bootstrap();c.wake(CONTROL);self.assertEqual(c.events,[])
        c.wake();self.assertEqual(c.events,[16]);self.assertEqual(c.word(CONTROL+8),1)
        c.wake();self.assertEqual(c.events,[16]);self.assertEqual(len(c.reads),3)
        for state in range(1,9):
            c=Bootstrap(state);c.wake();self.assertEqual(c.events,[]);self.assertEqual(c.word(CONTROL+8),0)

if __name__=='__main__':
    start=time.perf_counter();result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(BootstrapTests))
    report={'tests':result.testsRun,'passed':result.wasSuccessful(),'failures':len(result.failures),'errors':len(result.errors),
            'seconds':time.perf_counter()-start,'baselineSha256':FARM.sha256,'payloadSha256':M['payloadSha256'],
            'hardwareRequests':0,'allocatedCameraRange':None,'testSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'scope':'新 ARM gate/wake 与原厂分配器执行，F4 reader/event publication 在本组为边界替身；尚无完整任务等待/唤醒/USB事务'}
    (BUILD/'tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False));raise SystemExit(not result.wasSuccessful())
