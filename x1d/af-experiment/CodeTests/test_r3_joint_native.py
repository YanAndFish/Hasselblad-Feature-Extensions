"""同一ARM内存执行AF与实际视频服务/曝光/配置；设备和任务调度仍显式模拟。"""
import sys,math,json,unittest
sys.dont_write_bytecode=True
from test_r3_video_flow import JointCase,T
from test_r3_video_exposure import ExposureCase
from inspect_fast_pipeline import STUBS

class JointNativeCase(JointCase):
    def __init__(self,**kwargs):
        self.video_engine=None
        super().__init__(**kwargs)
        engine=ExposureCase();template=engine.u
        # 复制同版本离线配置/RTOS初值；不复制独立候选的0x300000代码。
        for lo,hi,_ in template.mem_regions():
            if 0x600000<=lo<0x700000:self.u.mem_write(lo,bytes(template.mem_read(lo,hi-lo+1)))
            elif lo==0x1000000:
                self.u.mem_map(lo,hi-lo+1);self.u.mem_write(lo,bytes(template.mem_read(lo,hi-lo+1)))
        for a,n in ((0x2add4e,8),(0x2b2450,1),(0x2b214c,256),(0x2b1da8,32)):
            self.u.mem_write(a,bytes(template.mem_read(a,n)))
        for a in set(engine.SIMPLE)|set(STUBS)|{0x186b70,0x22daac,0x22e1a8,0x235758,0x234c64,
                0x238820,0x23899c,0x1efdcc,0x235e9c,0x1cd334,0x1cd390,0x1cd3b8,0x17c210,0x17c4f8}:
            self.u.mem_write(a,bytes(template.mem_read(a,4)))
        # 这些公共函数在旧AF模块测试中为替身；这里两条链都执行原指令。
        for a in (0x1f0a1c,0x1f0b04,0x15ada8,0x15ae34,0x226974):self.u.mem_write(a,T.FARM.read(a,4))
        engine.u=self.u;engine.addr=self.vaddr;self.video_engine=engine
        self.u.mem_write(0x6bb46c,b'\x00');self.w(0x6badd0,self.time)
        self.w(0x6bcb78,1)
        for a,old,new in T.M['speed_words']:self.w(a,new)
        self.run('fast_videoon',5,640,360,0)
        self.w(0x6bcb44,int.from_bytes(self.u.mem_read(0x6c172c,4),'little'))
        assert self.u.mem_read(0x6c176c,1)==b'\x01' and engine.resources=={11,14,15}

    def hook(self,u,a,size,data):
        engine=getattr(self,'video_engine',None)
        if engine:
            if 0x1fd1a4<=a<0x1fd1d4 or (a==0x23899c and u.reg_read(T.UC_ARM_REG_R0)==0x43000174):
                super().hook(u,a,size,data);return
            if a==0x21e2f0:
                # 与独立视频测试相同的颜色/曝光状态替身，使用本AF模拟器的栈。
                ptr=u.reg_read(T.UC_ARM_REG_R0);assert 0x900000<=ptr<0x910000
                u.mem_write(ptr,bytes(20));self.return_value(u);return
            if not (T.M['base']<=a<T.M['end'] or any(s['base']<=a<s['end'] for s in T.M['segments'])):
                try:engine.code(u,a,size,data);return
                except RuntimeError as error:
                    if not str(error).startswith('unreviewed code '):raise
        super().hook(u,a,size,data)

    def service_model(self):
        v=self.video()
        if v.request==v.ack:self.pending_at=None;return
        if self.pending_at is None:self.pending_at=self.time
        if (self.time-self.pending_at)&0xffffffff<self.service_delay:return
        self.video_engine.spi_status=int(v.target==self.fail_target)
        self.run('fast_video_service')
        done=self.video();assert done.ack==done.request
        self.mode=self.u.mem_read(0x6c1778,1)[0]
        self.transitions.append(dict(t=self.time,target=v.target,result=done.result,phase=self.state().phase))
        self.pending_at=None

    def pause_native_video_at_spi_return(self):
        """显式VideoTask寄存器/独立栈，在SPI替身完成后暂停；不是RTOS调度器。"""
        u=self.u;paused=[]
        def pause(engine):
            paused.append(u.reg_read(T.UC_ARM_REG_LR));u.emu_stop()
        self.video_engine.interrupt_after_spi=pause
        u.reg_write(T.UC_ARM_REG_CPSR,0x1f);u.reg_write(T.UC_ARM_REG_SP,0x90bdf0)
        u.reg_write(T.UC_ARM_REG_LR,0x900000)
        u.emu_start(T.M['symbols']['fast_video_service'],0x900000,count=100000)
        assert len(paused)==1 and self.video().applying==1
        self.video_context=u.context_save();self.video_return=paused[0]
        self.video_engine.interrupt_after_spi=None

    def resume_native_video(self):
        u=self.u;u.context_restore(self.video_context)
        # SPI替身已返回结果，从保存的LR恢复，不能重复执行一次SPI。
        u.emu_start(self.video_return,0x900000,count=100000)
        assert u.reg_read(T.UC_ARM_REG_PC)==0x900000 and u.reg_read(T.UC_ARM_REG_SP)==0x90bdf0
        assert self.video().request==self.video().ack and self.video().applying==0
        self.mode=u.mem_read(0x6c1778,1)[0]

class JointNativeTests(unittest.TestCase):
    def test_same_memory_native_af_video_exposure_and_next_cycle(self):
        c=JointNativeCase();rows=[]
        for peak in (300,-300,300):
            c.next_cycle();s=c.simulate_joint(lambda p:10000*math.exp(-.5*((p-peak)/400)**2))
            self.assertEqual((s.phase,s.reason),(8,0));self.assertLessEqual(abs(s.target-peak),20)
            self.assertFalse(c.rejects);self.assertEqual(c.mode,5);self.assertEqual(c.video().dirty,0)
            self.assertEqual(c.video_engine.resources,{11,14,15})
            rows.append(dict(peak=peak,target=s.target,ticks=c.time-s.started,generation=s.generation))
        self.assertTrue(c.video_engine.programs)
        self.assertTrue(all(x['bytes']==256 for x in c.video_engine.programs))
        (T.BUILD/'joint-native-cases.json').write_text(json.dumps({'artifactSha256':T.M['artifact_sha256'],
            'hardwareRequests':0,'cases':rows,'transitions':c.transitions,'limitations':[
                '视频任务调用调度与时钟为模型，未仿真原RTOS并发','SPI/MIPI/硬件/镜头反馈是替身',
                '原厂配置构造结果作为235758输入；AE/ISO/光圈与log/pow为替身',
                '未验证物理短帧或Linux/Qt帧完成']},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

    def test_cancel_waits_for_native_full_restore(self):
        c=JointNativeCase();c.start_fine();c.event(0x20000)
        s=c.simulate_joint(lambda p:1000)
        self.assertEqual((s.phase,s.reason),(9,12));self.assertEqual(c.mode,5)
        self.assertEqual(c.results,[1]);self.assertEqual(c.video().dirty,0)
        self.assertEqual(c.video_engine.resources,{11,14,15})

    def test_cancel_while_native_video_is_inflight_waits_then_restores(self):
        c=JointNativeCase();c.start_fine();seq=c.video().request
        c.pause_native_video_at_spi_return();programs=len(c.video_engine.programs)
        c.event(0x20000)
        self.assertEqual(c.results,[]);self.assertEqual(c.video().request,seq)
        self.assertEqual(c.video().target,7);self.assertEqual(c.video().applying,1)
        c.resume_native_video();self.assertEqual(len(c.video_engine.programs),programs)
        s=c.simulate_joint(lambda p:1000)
        self.assertEqual((s.phase,s.reason),(9,12));self.assertEqual(c.mode,5)
        self.assertEqual(c.video_engine.resources,{11,14,15})

    def test_timeout_while_native_video_is_inflight_invalidates_before_closure(self):
        c=JointNativeCase();c.start_fine();c.pause_native_video_at_spi_return()
        before=len(c.sends);c.time+=400;c.w(0x6badd0,c.time);c.position_message(c.position);c.event(0)
        self.assertEqual(c.results,[]);self.assertLess(c.state().phase,8)
        self.assertEqual((c.video().session,c.video().need_recovery),(0,1))
        c.resume_native_video();self.assertEqual(c.video().result,1)
        c.event(0)
        self.assertEqual((c.state().phase,c.state().reason),(9,14))
        self.assertEqual(c.results,[1]);self.assertTrue(all(v==0 for v in c.sends[before:]))

    def test_external_epoch_change_while_applying_cannot_close_live_stack(self):
        c=JointNativeCase();c.start_fine();c.pause_native_video_at_spi_return()
        # 明示外部生命周期发布的epoch输入，视频与AF两套原生栈仍实际执行。
        c.vset('external_epoch',c.video().external_epoch+1);c.event(0)
        self.assertEqual(c.results,[]);self.assertLess(c.state().phase,8)
        c.resume_native_video();self.assertEqual(c.video().result,1);c.event(0)
        self.assertEqual((c.state().phase,c.state().reason),(9,14))
        self.assertEqual(c.video().need_recovery,1)

if __name__=='__main__':unittest.main(verbosity=2)
