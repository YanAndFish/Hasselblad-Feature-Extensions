"""新引导与原厂 F4、任务通知、AF 等待及堆申请联合执行；没有硬件接口。"""
import hashlib,json,struct,time,unittest
from pathlib import Path
from test_native_memory import Heap,FARM,HERE
from unicorn import UC_HOOK_INTR
from unicorn.arm_const import *

BUILD=HERE/'build/native-bootstrap-r1'
M=json.loads((BUILD/'bootstrap-manifest.json').read_text(encoding='utf-8'))
BLOB=(BUILD/'bootstrap.bin').read_bytes();S=M['symbols']
REQUEST=S['nr_request'];CONTROL=S['nr_gate_control'];COUNT=CONTROL+4;SENT=CONTROL+8
assert hashlib.sha256(BLOB).hexdigest()==M['payloadSha256']
assert FARM.sha256==M['baselineSha256']
for p,h in M['sourceSha256'].items():assert hashlib.sha256((HERE/p).read_bytes()).hexdigest()==h

class NativeWake(Heap):
    AF=0x920000;HOST=0x920100;CURRENT=0x6baccc;MSG=0x6c37f4
    STUBS={0x1854bc,0x185520,0x185fa0,0x185e48,0x186b70,
           0x236a14,0x1e0a50,0x238ef8,0x23899c,0x1e80d0}
    def __init__(self,state=0):
        self.phase='heap_init';super().__init__()
        p=self.alloc(128);self.free(p)
        self.u.mem_map(0x900000,0x30000);self.u.mem_write(M['base'],BLOB)
        for a,old,new in M['emulatorOnlyHooks']:
            assert FARM.word(a)==old;self.put(a,new)
        self.put(0x6bb46c,state);self.put(0x6bb470,self.AF)
        self.put(self.AF+0x2c,8);self.put(self.HOST+0x2c,3)
        self.put(0x6c37f0,0x920200)
        self.events=[];self.replies=[];self.waits=[];self.svcs=[];self.malloc_calls=0
        self.context=None;self.stop=None;self.phase=None
        self.u.hook_add(UC_HOOK_INTR,self.intr)
    def put(self,a,v):self.u.mem_write(a,struct.pack('<I',v))
    def ret(self,v=0):
        self.u.reg_write(UC_ARM_REG_R0,v)
        self.u.reg_write(UC_ARM_REG_PC,self.u.reg_read(UC_ARM_REG_LR))
    def hook(self,u,a,size,data):
        if self.phase=='heap_init':return super().hook(u,a,size,data)
        self.visited.add(a)
        if self.phase=='af' and a in (0x19d198,0x19b964):
            self.stop='held' if a==0x19d198 else 'released';u.emu_stop();return
        if self.phase=='host' and a==0x1e23ec:
            self.stop='reply_done';u.emu_stop();return
        if a==0x184a60:
            assert self.phase=='af' and self.word(self.CURRENT)==self.AF
            self.malloc_calls+=1
        if a==0x18a020:
            values=tuple(u.reg_read(r) for r in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3))
            assert self.phase=='host' and self.word(self.CURRENT)==self.HOST
            assert values==(self.AF,16,1,0) and self.word(SENT)==1
            self.events.append(values)
        if a==0x189e4c:
            values=tuple(u.reg_read(r) for r in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3))
            assert self.phase=='af' and values[0:2]==(0,0xffffffff) and values[3]==0xffffffff
            self.waits.append(values)
        if a in self.STUBS:
            r0=u.reg_read(UC_ARM_REG_R0);r1=u.reg_read(UC_ARM_REG_R1);r2=u.reg_read(UC_ARM_REG_R2)
            if a==0x186b70:
                assert self.phase=='host' and (r0,r1,r2)==(0x920200,self.MSG,0xffffffff)
                self.ret(1)
            elif a==0x1e0a50:
                assert r0==self.MSG and r2==0xf5
                u.mem_write(r1,bytes.fromhex('f5000108')+bytes(8));self.ret()
            elif a==0x238ef8:
                assert r0==self.address and r1==4;self.ret(1)
            elif a==0x23899c:
                assert r0==self.address;self.ret(self.word(r0))
            elif a==0x1e80d0:
                raw=bytes(u.mem_read(r0,12));assert raw[:4]==bytes.fromhex('f5000108') and raw[8]==0
                self.replies.append(struct.unpack_from('<I',raw,4)[0]);self.ret()
            else:self.ret()
            return
        ranges=((M['base'],M['end']),(0x1e2088,0x1e23f0),(0x1e1768,0x1e1888),
                (0x1a4890,0x1a4950),(0x18a020,0x18a210),(0x189e4c,0x18a020),
                (0x19b718,0x19b75c),(0x19b960,0x19b964),
                (0x184a60,0x1850e4),(0x188370,0x1883a0),(0x188424,0x188630))
        if not any(lo<=a<hi for lo,hi in ranges):raise AssertionError('unexpected native path '+hex(a))
    def intr(self,u,number,data):
        pc=u.reg_read(UC_ARM_REG_PC)
        assert number==2 and (self.phase,pc) in (('af',0x189f7c),('host',0x18a1fc))
        self.svcs.append((self.phase,pc));self.stop='svc';u.emu_stop()
    def execute(self,pc):
        self.stop=None;self.u.emu_start(pc,0,count=200000)
        assert self.stop is not None
        return self.stop
    def block_af(self):
        u=self.u;self.phase='af';self.put(self.CURRENT,self.AF)
        u.reg_write(UC_ARM_REG_CPSR,0x1f);u.reg_write(UC_ARM_REG_R11,0x90fd00)
        u.reg_write(UC_ARM_REG_SP,0x90fb00)
        assert self.execute(0x19b718)=='svc' and self.word(self.AF+0x6c)&255==1
        self.context=u.context_save()
    def resume_af(self):
        assert self.context is not None
        u=self.u;u.context_restore(self.context);self.phase='af';self.put(self.CURRENT,self.AF)
        assert self.execute(u.reg_read(UC_ARM_REG_PC))=='held'
        assert self.word(0x90fd00-0x94)==16 and self.word(self.AF+0x68)==0
        assert self.word(self.AF+0x6c)&255==0 and self.word(COUNT)==1
        assert self.word(0x6badec)==0
    def request(self,address=COUNT,schedule_at_svc=False):
        self.address=address;u=self.u;self.phase='host';self.put(self.CURRENT,self.HOST)
        u.reg_write(UC_ARM_REG_CPSR,0x1f);u.reg_write(UC_ARM_REG_R11,0x91fd00)
        u.reg_write(UC_ARM_REG_SP,0x91fb00)
        u.mem_write(self.MSG,bytes.fromhex('f4000801')+struct.pack('<I',address))
        stop=self.execute(0x1e2088)
        if stop=='svc':
            context=u.context_save()
            if schedule_at_svc:self.resume_af()
            u.context_restore(context);self.phase='host';self.put(self.CURRENT,self.HOST)
            stop=self.execute(u.reg_read(UC_ARM_REG_PC))
        assert stop=='reply_done' and u.reg_read(UC_ARM_REG_SP)==0x91fb00
        assert u.reg_read(UC_ARM_REG_R11)==0x91fd00
        return self.replies[-1]

class NativeWakeTests(unittest.TestCase):
    def test_actual_event_and_wait_allocate_in_af_task_before_reply(self):
        c=NativeWake();before=c.free_bytes();c.block_af()
        self.assertEqual(c.request(schedule_at_svc=True),1)
        self.assertEqual(c.word(REQUEST+24),3);self.assertEqual(c.malloc_calls,1)
        self.assertLess(c.free_bytes(),before)
        self.assertEqual(c.events,[(c.AF,16,1,0)])
        self.assertEqual(c.svcs,[('af',0x189f7c),('host',0x18a1fc)])
    def test_delayed_schedule_must_observe_ack_and_does_not_allocate_in_host(self):
        c=NativeWake();c.block_af();self.assertEqual(c.request(),0)
        self.assertEqual(c.malloc_calls,0);self.assertEqual(c.word(REQUEST+24),1)
        self.assertEqual(c.request(),0);self.assertEqual(len(c.events),1)
        c.resume_af();self.assertEqual(c.request(),1)
        self.assertEqual(c.malloc_calls,1);self.assertEqual(c.word(REQUEST+24),3)
    def test_failed_heap_preflight_reports_rejection_without_native_failed_hook(self):
        c=NativeWake();c.put(0x6bacb4,0);c.block_af()
        self.assertEqual(c.request(schedule_at_svc=True),1)
        self.assertEqual(c.word(REQUEST+24),4);self.assertEqual(c.word(REQUEST+28),3)
        self.assertEqual(c.malloc_calls,0);self.assertNotIn(0x2209ac,c.visited)
    def test_other_addresses_and_busy_states_do_not_post_or_allocate(self):
        c=NativeWake();self.assertEqual(c.request(REQUEST),0x31524e41)
        self.assertEqual(c.events,[]);self.assertEqual(c.malloc_calls,0)
        for state in range(1,9):
            c=NativeWake(state);self.assertEqual(c.request(),0)
            self.assertEqual(c.events,[]);self.assertEqual(c.word(SENT),0)
    def test_allocated_block_is_retained_across_future_diagnostic_reads(self):
        c=NativeWake();c.block_af();c.request(schedule_at_svc=True)
        pointer=c.word(REQUEST+32);free=c.free_bytes()
        self.assertTrue(c.word(pointer-4)&0x80000000)
        for address in (COUNT,REQUEST+32,REQUEST+36,COUNT):c.request(address)
        self.assertEqual(c.malloc_calls,1);self.assertEqual(c.free_bytes(),free)

if __name__=='__main__':
    start=time.perf_counter();result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(NativeWakeTests))
    report={'tests':result.testsRun,'passed':result.wasSuccessful(),'failures':len(result.failures),'errors':len(result.errors),
        'seconds':time.perf_counter()-start,'baselineSha256':FARM.sha256,'payloadSha256':M['payloadSha256'],
        'hardwareRequests':0,'testSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'scope':'新引导+原厂 F4 分发/reader、任务事件发布/等待、AF任务内堆申请与挂起/恢复',
        'stubAddresses':sorted(NativeWake.STUBS),'contextSwitch':'显式仿真调度',
        'limitations':['不模拟 CPU 实际上下文切换、硬件缓存或 USB 传输；地址对齐检查和底层队列/链表仍为替身',
                       'ACK 只证明当前空闲入口已经过，不代表其他代码已装载或预测可启用']}
    (BUILD/'task-wake-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False));raise SystemExit(not result.wasSuccessful())
