"""在真实编译指令的发布中点切换上下文，复现旧覆盖并验证三写者分环。"""
import hashlib,json,struct,sys,time,unittest
from pathlib import Path
sys.dont_write_bytecode=True
from test_native_capture import CaptureCase,M,FARM,BUILD,CAP,records
from unicorn import UC_HOOK_MEM_WRITE,UC_HOOK_CODE
from unicorn.arm_const import *

HERE=Path(__file__).resolve().parents[1]
OLD=HERE/'build/native-capture-r1/pre-concurrency-audit/build/native-capture-r1/00800000'
OLD_M=json.loads((OLD/'capture-manifest.json').read_text(encoding='utf-8'))
OLD_BLOB=(OLD/'candidate.bin').read_bytes()
assert hashlib.sha256(OLD_BLOB).hexdigest()==OLD_M['payload_sha256']=='205724bf23863a5ecbe287e95fef20429a35e06c9212f7c09f90a0a3ac51dddf'

class Interleaved:
    def __init__(self,legacy=False):
        self.c=CaptureCase();self.u=self.c.u;self.m=OLD_M if legacy else M;self.legacy=legacy
        if legacy:self.u.mem_write(self.m['base'],OLD_BLOB)
        self.cap=self.m['symbols']['nc_capture'];self.c.w(self.cap+8,7)
        self.header=32 if legacy else 48
    def execute(self,name,args,stack):
        u=self.u;u.reg_write(UC_ARM_REG_CPSR,0x1f);u.reg_write(UC_ARM_REG_SP,stack)
        u.reg_write(UC_ARM_REG_LR,0x900000)
        for r,v in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2),args):u.reg_write(r,v&0xffffffff)
        u.emu_start(self.m['symbols'][name],0x900000,count=100000)
    def preempt(self,outer,outer_args,inner,inner_args,control_outer=False,irq=False):
        # 在外层写者发布奇数 commit 后切换，不借助 Python 重写任一记录。
        slot=self.cap+self.header+(64+128 if control_outer and not self.legacy else 64)*36
        stopped=[]
        def pause(u,access,address,size,value,data):
            if address==slot and value==3 and not stopped:stopped.append(address);u.emu_stop()
        hook=self.u.hook_add(UC_HOOK_MEM_WRITE,pause)
        self.execute(outer,outer_args,0x90fd00);self.u.hook_del(hook)
        assert stopped and self.u.reg_read(UC_ARM_REG_PC)!=0x900000
        context=self.u.context_save()
        self.execute(inner,inner_args,0x90dd00);assert self.u.reg_read(UC_ARM_REG_PC)==0x900000
        if irq:self.execute('nc_raw',(111,222,0),0x90bd00)
        self.u.context_restore(context)
        pc=self.u.reg_read(UC_ARM_REG_PC)|(1 if self.u.reg_read(UC_ARM_REG_CPSR)&32 else 0)
        self.u.emu_start(pc,0x900000,count=100000)
        assert self.u.reg_read(UC_ARM_REG_PC)==0x900000
    def legacy_af(self):
        n=self.c.word(self.cap+16);base=self.cap+32+64*36
        return [struct.unpack('<9I',self.u.mem_read(base+i*36,36)) for i in range(n)]
    def interleave_commands(self):
        stopped=[]
        def pause(u,a,size,data):
            if a==0x1a02dc and not stopped:stopped.append(a);u.emu_stop()
        hook=self.u.hook_add(UC_HOOK_CODE,pause)
        self.execute('nc_fast_speed',(500,),0x90fd00);self.u.hook_del(hook)
        assert stopped and self.c.sends==[500]
        context=self.u.context_save()
        self.execute('nc_probe_speed',(2000,),0x90dd00)
        self.u.context_restore(context)
        self.u.emu_start(self.u.reg_read(UC_ARM_REG_PC),0x900000,count=100000)
        assert self.u.reg_read(UC_ARM_REG_PC)==0x900000

class ConcurrencyTests(unittest.TestCase):
    def test_command_record_binds_local_packet_argument_after_other_task_sends(self):
        old=Interleaved(True);old.interleave_commands()
        self.assertEqual(old.c.sends,[500,2000])
        self.assertEqual(old.legacy_af()[-1][5:8],(1,500,2000))
        c=Interleaved();c.interleave_commands()
        self.assertEqual(c.c.sends,[500,2000])
        self.assertEqual(records(c.c)[0][5:8],(0,2000,2000))
        self.assertEqual(records(c.c,control=True)[0][5:8],(1,500,500))
    def test_old_verified_payload_reproduces_control_record_loss(self):
        c=Interleaved(True);c.preempt('nc_cv_fifo',(3000,0),'nc_fast_speed',(500,))
        self.assertEqual(c.c.word(c.cap+16),1)
        self.assertEqual([r[1] for r in c.legacy_af()],[2])
        self.assertEqual(c.c.sends,[500]) # 原厂命令已发送，但旧共用环把它的记录覆盖了。
    def test_data_publication_survives_control_task_and_irq_preemption(self):
        c=Interleaved();c.preempt('nc_cv_fifo',(3000,0),'nc_fast_speed',(500,),irq=True)
        self.assertEqual(records(c.c)[0][1],2);self.assertEqual(records(c.c)[0][5:7],(3000,0))
        self.assertEqual(records(c.c,control=True)[0][1],6)
        self.assertEqual(records(c.c,control=True)[0][5:],(1,500,500,1000))
        self.assertEqual(records(c.c,raw=True)[0][5:7],(111,222))
        self.assertEqual([c.c.word(CAP+off) for off in (12,16,32)],[1,1,1])
    def test_control_publication_survives_data_task_preemption(self):
        c=Interleaved();c.preempt('nc_fine_speed',(-500,),'nc_position_fifo',(-12,0,99),control_outer=True)
        self.assertEqual(records(c.c)[0][1],3);self.assertEqual(records(c.c)[0][5:8],(0xfffffff4,0,99))
        self.assertEqual(records(c.c,control=True)[0][1],6)
        self.assertEqual(records(c.c,control=True)[0][5:7],(2,0xfffffe0c))
    def test_independent_wrap_counters_cannot_replace_other_task_records(self):
        c=CaptureCase()
        for i in range(140):c.run('nc_cv_fifo',1000+i,i%5)
        data=records(c)
        for i in range(40):c.run('nc_fast_speed',500+i)
        self.assertEqual(records(c),data);self.assertEqual(len(records(c,control=True)),32)
        self.assertEqual(records(c,control=True)[0][0],18)
        self.assertEqual(c.word(CAP+16),140);self.assertEqual(c.word(CAP+32),40)

if __name__=='__main__':
    start=time.perf_counter();r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ConcurrencyTests))
    report={'passed':r.wasSuccessful(),'tests':r.testsRun,'failures':len(r.failures),'errors':len(r.errors),
        'seconds':time.perf_counter()-start,'baselineSha256':FARM.sha256,'payloadSha256':M['payload_sha256'],
        'testSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'hardwareRequests':0,
        'legacyPayloadSha256':OLD_M['payload_sha256'],'legacyRaceReproduced':r.wasSuccessful(),
        'scope':'编译 ARM/Thumb 指令在奇数 commit 发布点的显式任务/IRQ上下文交错；旧镜像覆盖复现与三独立环回绕',
        'limitations':['上下文切换由仿真器安排；不证明实际任务调度、物理时间或算法提供器并发正确']}
    (BUILD/'concurrency-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False));raise SystemExit(not r.wasSuccessful())
