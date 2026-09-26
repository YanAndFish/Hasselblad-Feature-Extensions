"""普通诊断任务→一次性事件发布→原生AF等待返回→独立屏障。仅离线。"""
import sys,json,struct,hashlib,unittest
sys.dont_write_bytecode=True
from test_r4_install_barrier import (FarmApplication,BASE,COUNT,HOOK,LOOP,BLOB,
    branch,M,BUILD,Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE)
from unicorn import UC_HOOK_INTR
from unicorn.arm_const import *

WAKE_BASE=BASE+len(BLOB)
WAKE_HOOK=0x1e2224
READ_HANDLER=0x1e1768
SENT=COUNT+4

def wake_blob():
    # r0仅为已由原队列分发到F4的消息指针。其他地址沿用原内存读取。
    # 固定COUNT请求且AF idle时，先占用一次性标志，再发布事件16。
    # 原请求仍交给原厂校验与回复；这里不跳过读取权限检查。
    words=[0xe92d4001,0xe5901004,0,0xe1510002,0,
           0xe5921004,0xe3510000,0,0,0xe5d11000,0xe3510000,0,
           0xe3a01001,0xe5821004,0xf57ff05b,0xe3a00010,0,
           0xe8bd4001,0,COUNT,0x6bb46c]
    for index,target,reg in ((2,19,2),(8,20,1)):
        words[index]=0xe59f0000|(reg<<12)|(4*(target-index)-8)
    for index in (4,7,11):
        words[index]=(branch(WAKE_BASE+4*index,WAKE_BASE+4*17)&0x0fffffff)|0x10000000
    words[16]=branch(WAKE_BASE+64,0x1a4890)|0x01000000
    words[18]=branch(WAKE_BASE+72,READ_HANDLER)
    blob=struct.pack('<%dI'%len(words),*words)
    assert WAKE_BASE+len(blob)<=COUNT and SENT+4<=0x2b4000
    return blob

WAKE_BLOB=wake_blob()

class TaskWakeCase:
    AF=0x920000;HOST=0x920100;CURRENT=0x6baccc;MSG=0x6c37f4
    # RTOS锁/链表、队列投递、回复构造与传输、地址校验/实际读取为显式替身。
    # 事件发布0x18a020、事件等待0x189e4c及AF/诊断分发执行原始指令。
    STUBS={0x1854bc,0x185520,0x185fa0,0x185e48,0x186b70,
           0x236a14,0x1e0a50,0x238ef8,0x23899c,0x1e80d0}
    def __init__(self,farm,state=0,active_gate=True):
        self.u=u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
        u.mem_map(0x100000,0x200000);u.mem_write(0x100000,farm.data)
        u.mem_map(0x6ba000,0xb000);u.mem_map(0x900000,0x30000)
        u.mem_write(BASE,BLOB);u.mem_write(WAKE_BASE,WAKE_BLOB)
        if active_gate:self.word(HOOK,branch(HOOK,BASE))
        self.word(WAKE_HOOK,branch(WAKE_HOOK,WAKE_BASE)|0x01000000)
        self.word(0x6bb46c,state);self.word(0x6bb470,self.AF)
        self.word(self.AF+0x2c,8);self.word(self.HOST+0x2c,3)
        self.word(0x6c37f0,0x920200)
        self.events=[];self.replies=[];self.waits=[];self.svcs=[];self.executed=[]
        self.context=None;self.phase=None;self.stop=None
        u.hook_add(UC_HOOK_CODE,self.code);u.hook_add(UC_HOOK_INTR,self.intr)
    def word(self,a,value=None):
        if value is None:return struct.unpack('<I',self.u.mem_read(a,4))[0]
        self.u.mem_write(a,struct.pack('<I',value))
    def ret(self,value=0):
        self.u.reg_write(UC_ARM_REG_R0,value)
        self.u.reg_write(UC_ARM_REG_PC,self.u.reg_read(UC_ARM_REG_LR))
    def code(self,u,a,size,data):
        self.executed.append((self.phase,a))
        if self.phase=='af' and a==LOOP:
            self.stop='barrier';u.emu_stop();return
        if self.phase=='host' and a==0x1e23ec:
            self.stop='reply_done';u.emu_stop();return
        if a==0x18a020:
            values=tuple(u.reg_read(r) for r in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3))
            assert self.phase=='host' and self.word(self.CURRENT)==self.HOST
            assert self.word(HOOK)==branch(HOOK,BASE)
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
        ranges=((BASE,COUNT),(0x1e2088,0x1e23f0),(0x1e1768,0x1e1888),
                (0x1a4890,0x1a4950),(0x18a020,0x18a210),(0x189e4c,0x18a020),
                (0x19b718,0x19b75c),(HOOK,HOOK+4))
        if not any(lo<=a<hi for lo,hi in ranges):raise AssertionError('unexpected native path '+hex(a))
    def intr(self,u,number,data):
        pc=u.reg_read(UC_ARM_REG_PC)
        assert number==2 and (self.phase,pc) in (('af',0x189f7c),('host',0x18a1fc))
        self.svcs.append((self.phase,pc));self.stop='svc';u.emu_stop()
    def run(self,pc):
        self.stop=None;self.u.emu_start(pc,0,count=2000)
        assert self.stop is not None
        return self.stop
    def block_af(self):
        u=self.u;self.phase='af';self.word(self.CURRENT,self.AF)
        u.reg_write(UC_ARM_REG_CPSR,0x1f);u.reg_write(UC_ARM_REG_R11,0x90fd00)
        u.reg_write(UC_ARM_REG_SP,0x90fb00)
        assert self.run(0x19b718)=='svc' and self.word(self.AF+0x6c)&255==1
        self.context=u.context_save()
    def resume_af(self):
        assert self.context is not None
        u=self.u;u.context_restore(self.context);self.phase='af';self.word(self.CURRENT,self.AF)
        assert self.run(u.reg_read(UC_ARM_REG_PC))=='barrier'
        assert self.word(0x90fd00-0x94)==16 and self.word(self.AF+0x68)==0
        assert self.word(self.AF+0x6c)&255==0 and self.word(COUNT)==1
    def request(self,address=COUNT,schedule_at_svc=False):
        self.address=address;u=self.u;self.phase='host';self.word(self.CURRENT,self.HOST)
        u.reg_write(UC_ARM_REG_CPSR,0x1f);u.reg_write(UC_ARM_REG_R11,0x91fd00)
        u.reg_write(UC_ARM_REG_SP,0x91fb00)
        u.mem_write(self.MSG,bytes.fromhex('f4000801')+struct.pack('<I',address))
        stop=self.run(0x1e2088)
        if stop=='svc':
            context=u.context_save()
            if schedule_at_svc:self.resume_af()
            u.context_restore(context);self.phase='host';self.word(self.CURRENT,self.HOST)
            stop=self.run(u.reg_read(UC_ARM_REG_PC))
        assert stop=='reply_done' and u.reg_read(UC_ARM_REG_SP)==0x91fb00
        assert u.reg_read(UC_ARM_REG_R11)==0x91fd00
        return self.replies[-1]

class TaskWakeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.farm=FarmApplication();assert cls.farm.sha256==M['baseline_sha256']
        assert cls.farm.word(WAKE_HOOK)==branch(WAKE_HOOK,READ_HANDLER)|0x01000000
        assert cls.farm.word(0x1e20a8)==branch(0x1e20a8,0x186b70)|0x01000000
        assert cls.farm.word(0x1e23ec)==branch(0x1e23ec,0x1e2088)

    def test_blocked_af_resumes_through_native_wait_before_reply(self):
        c=TaskWakeCase(self.farm);c.block_af()
        self.assertEqual(c.request(schedule_at_svc=True),1)
        self.assertEqual(c.events,[(c.AF,16,1,0)])
        self.assertEqual(c.svcs,[('af',0x189f7c),('host',0x18a1fc)])

    def test_delayed_schedule_requires_observation_and_duplicate_does_not_republish(self):
        c=TaskWakeCase(self.farm);c.block_af();self.assertEqual(c.request(),0)
        self.assertEqual(c.word(COUNT),0);self.assertEqual(c.word(SENT),1)
        self.assertEqual(c.request(),0);self.assertEqual(len(c.events),1)
        c.resume_af();self.assertEqual(c.request(),1);self.assertEqual(len(c.events),1)

    def test_other_address_and_non_idle_states_keep_original_read_without_events(self):
        c=TaskWakeCase(self.farm);c.word(COUNT+8,0x87654321)
        self.assertEqual(c.request(COUNT+8),0x87654321)
        self.assertEqual(c.events,[]);self.assertEqual(c.word(SENT),0)
        for state in range(1,9):
            c=TaskWakeCase(self.farm,state=state);self.assertEqual(c.request(),0)
            self.assertEqual(c.events,[]);self.assertEqual(c.word(SENT),0)

    @classmethod
    def tearDownClass(cls):
        result={'artifactSha256':M['artifact_sha256'],'farmSha256':cls.farm.sha256,
            'wakeBase':WAKE_BASE,'wakeEnd':WAKE_BASE+len(WAKE_BLOB),'wakeHex':WAKE_BLOB.hex(),
            'wakeSha256':hashlib.sha256(WAKE_BLOB).hexdigest(),'wakeHook':WAKE_HOOK,
            'counterAddress':COUNT,'sentAddress':SENT,'eventMask':16,
            'nativeEventAndWait':True,'rtosContextSwitch':'explicit emulator scheduling',
            'stubAddresses':sorted(TaskWakeCase.STUBS),'hardwareRequests':0,'installReady':False,
            'limitations':['读COUNT在临时hook生效期间会产生一次任务通知，不再是无副作用读取',
                '须先完成屏障与唤醒代码缓存同步，后发布唤醒hook；最终开放前恢复该hook',
                '调度与外设仍为电脑模型，尚未接入USB、SGI完成证明及持久化恢复',
                '已装入后必须保留两个helper到手动重启，不能因hook恢复即擦除']}
        (BUILD/'installation-task-wake.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':unittest.main(verbosity=2)
