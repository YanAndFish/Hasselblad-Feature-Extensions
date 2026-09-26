"""AF与视频请求生命周期：执行R3 ARM，视频任务响应及帧时序为明确替身。无硬件。"""
import sys,ctypes,struct,math,json,unittest
sys.dont_write_bytecode=True
from test_full_r3 import MotionCase,T
from test_r3_fast_video import VideoState

class JointCase(MotionCase):
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.vaddr=T.M['symbols']['fast_video_state'];self.transitions=[];self.delivery=[]
        self.mode=5;self.service_delay=2;self.pending_at=None;self.fail_target=0
        self.mipi_ends=0;self.freeze_mipi=False
        self.vset('enabled',2);self.vset('observed_width',640);self.vset('observed_height',360)
        self.u.mem_write(0x6c176c,b'\x01');self.u.mem_write(0x6c1778,b'\x05')
        self.w(0x6cc59c,206|(1250<<16));self.w(0x6cc5a0,248|(56<<16));self.w(0x6bcb44,1120108861)
    def video(self):return VideoState.from_buffer_copy(bytes(self.u.mem_read(self.vaddr,ctypes.sizeof(VideoState))))
    def vset(self,name,value):self.w(self.vaddr+getattr(VideoState,name).offset,value)
    def hook(self,u,a,size,data):
        if 0x1fd1a4<=a<0x1fd1d4:return
        if a==0x23899c and u.reg_read(T.UC_ARM_REG_R0)==0x43000174:
            self.return_value(u,self.mipi_ends);u.reg_write(T.UC_ARM_REG_PC,u.reg_read(T.UC_ARM_REG_LR));return
        super().hook(u,a,size,data)
    def service_model(self):
        v=self.video()
        if v.request==v.ack:self.pending_at=None;return
        if self.pending_at is None:self.pending_at=self.time
        if (self.time-self.pending_at)&0xffffffff<self.service_delay:return
        target=v.target
        if not v.session or v.external_epoch!=v.request_epoch:result=1
        elif target==self.fail_target:result=5
        else:
            result=0;self.mode=target
            self.u.mem_write(0x6c1778,bytes((target,)))
            self.w(0x6cc59c,(v.roi0&0xffff0000)|((v.roi0&65535)-(158 if target==7 else 0)))
            self.w(0x6cc5a0,v.roi1)
            self.vset('ready_rate',1132920832 if target==7 else v.full_rate)
            self.vset('ready_tick',self.time)
        self.vset('dirty',int(result!=0 or target==7))
        self.vset('result',result);self.vset('ack',v.request)
        if result and target==5:self.vset('need_recovery',1)
        self.transitions.append(dict(t=self.time,target=target,result=result,phase=self.state().phase))
        self.pending_at=None
    def simulate_joint(self,curve,steps=1000,lag=0):
        history=[]
        for i in range(steps):
            s=self.state()
            if s.phase>=8:break
            dt=4 if self.mode==7 else 10
            if self.move_target is not None and self.position!=self.move_target:
                delta=self.move_target-self.position;dx=max(-6*dt,min(6*dt,delta));position=self.position+dx
                self.velocity=dx/dt if position!=self.move_target else 0.
            elif s.command:
                self.velocity=s.command/1000.;position=round(self.position+self.velocity*dt)
            else:
                old=self.velocity;self.velocity=old*max(0.,1-dt/self.coast)
                if abs(self.velocity)<.5:self.velocity=0.
                position=round(self.position+(old+self.velocity)*dt/2)
            self.time=(self.time+dt)&0xffffffff;self.w(0x6badd0,self.time)
            self.service_model()
            # MIPI picture-end为独立明示硬件替身；可冻结而继续产生AF统计。
            if self.mode==5 and not self.freeze_mipi:self.mipi_ends=(self.mipi_ends+1)&255
            # 故意把160模式CV乘7，检测任何跨模式峰值/确认比较。
            cv=max(1,round(curve(position)*(7 if self.mode==7 else 1)))
            history.append((cv,self.make_frame(cv),self.mode))
            cv,packet,mode=history[max(0,len(history)-1-lag)]
            before=self.state();self.feed(position,cv,dt=0,packet=packet)
            after=self.state()
            if after.samples>before.samples:self.delivery.append((mode,after.cv_profile,after.phase))
            if self.move_target is not None and position==self.move_target and len(self.targets)>self.ack_count:
                self.ack_count=len(self.targets);self.reply()
        return self.state()
    def start_fine(self):
        self.next_cycle()
        assert self.video().session==self.state().generation
        self.set('phase',4);self.set('probe_active',0);self.set('direction',1)
        self.set('stop_pending',2);self.set('stable_points',3)
        self.set('stable_tick',self.time-30);self.set('fine_end',1000)
        self.position_message(self.position);self.event()
        assert self.state().video_state==1 and self.video().target==7

class VideoFlowTests(unittest.TestCase):
    def test_joint_curves_never_mix_scaled_profiles_and_restore_before_success(self):
        rows=[]
        for far in (False,True):
            for peak in (-300,300):
                for width in (200,400,1000):
                    c=JointCase(far=far);c.next_cycle()
                    s=c.simulate_joint(lambda p:10000*math.exp(-.5*((p-peak)/width)**2))
                    rows.append(dict(far=far,peak=peak,width=width,phase=s.phase,reason=s.reason,
                        target=s.target,ticks=c.time-s.started,transitions=c.transitions))
                    self.assertFalse(c.rejects)
                    self.assertTrue(all(mode==(7 if profile else 5) for mode,profile,_ in c.delivery),c.delivery)
        (T.BUILD/'video-flow-curves.json').write_text(json.dumps({'artifactSha256':T.M['artifact_sha256'],
            'hardwareRequests':0,'videoAckModelDelay':2,'fullStatInterval':10,'shortStatInterval':4,
            'physicalFrameCompletionVerified':False,'cases':rows},indent=2)+'\n',encoding='utf-8')
        self.assertEqual([r for r in rows if r['phase']!=8 or abs(r['target']-r['peak'])>20],[])
        self.assertTrue(all(r['transitions'] for r in rows))
        self.assertTrue(all(r['transitions'][-1]['target']==5 for r in rows))

    def test_cancel_before_short_ack_does_not_overwrite_pending_target(self):
        c=JointCase();c.start_fine();seq=c.video().request
        c.w(0x90ff00-0x94,0x20000);c.run('early_entry',dispatch=True)
        self.assertEqual(c.results,[]);self.assertEqual((c.video().target,c.video().request),(7,seq))
        self.assertEqual(c.state().finish_pending,13)
        s=c.simulate_joint(lambda p:1000)
        self.assertEqual((s.phase,s.reason),(9,12));self.assertEqual(c.results,[1])
        self.assertEqual([r['target'] for r in c.transitions],[7,5]);self.assertEqual(c.video().dirty,0)

    def test_all_native_termination_masks_restore_before_closure(self):
        for mask in (0x20000,0x200,0x800):
            c=JointCase();c.start_fine();c.service_delay=0;c.service_model();c.event()
            c.w(0x90ff00-0x94,mask);c.run('early_entry',dispatch=True)
            self.assertEqual(c.results,[])
            s=c.simulate_joint(lambda p:1000)
            self.assertEqual(s.phase,9);self.assertEqual(c.results,[1]);self.assertEqual(c.mode,5)

    def test_full_restore_failure_blocks_next_fast_session(self):
        c=JointCase();c.start_fine();c.event(0x20000);c.fail_target=5
        s=c.simulate_joint(lambda p:1000)
        self.assertEqual(s.phase,9);self.assertEqual(c.video().need_recovery,1)
        self.assertEqual(c.run('fast_video_request',7),0)
        before=len(c.targets);c.next_cycle();c.event()
        self.assertEqual((c.state().phase,c.state().reason),(9,14))
        self.assertEqual(len(c.targets),before)

    def test_pending_timeout_invalidates_session_before_possible_late_service(self):
        c=JointCase();c.start_fine();c.service_delay=10000
        s=c.simulate_joint(lambda p:1000)
        self.assertEqual((s.phase,s.reason),(9,14));self.assertEqual(c.video().session,0)
        self.assertEqual(c.video().need_recovery,1)
        c.service_delay=0;c.service_model();self.assertEqual(c.mode,5);self.assertEqual(c.video().result,1)

    def test_lost_position_during_switch_cannot_resume_scan(self):
        c=JointCase();c.start_fine();before=len(c.sends)
        c.time+=120;c.w(0x6badd0,c.time);c.service_delay=0;c.service_model();c.event()
        self.assertEqual(c.state().finish_pending,3)
        s=c.simulate_joint(lambda p:1000)
        self.assertEqual((s.phase,s.reason),(9,2))
        self.assertTrue(all(v==0 for v in c.sends[before:]))
        self.assertEqual(c.mode,5)

    def test_delayed_packets_across_switches_fail_or_preserve_profile_and_localization(self):
        rows=[]
        for lag in (1,2,4):
            for peak in (-300,300):
                c=JointCase();c.next_cycle()
                s=c.simulate_joint(lambda p:10000*math.exp(-.5*((p-peak)/400)**2),lag=lag)
                self.assertIn(s.phase,(8,9));self.assertFalse(c.rejects)
                if s.phase==8:self.assertLessEqual(abs(s.target-peak),20)
                self.assertTrue(all(mode==(7 if profile else 5) for mode,profile,_ in c.delivery),c.delivery)
                self.assertEqual(c.mode,5)
                rows.append(dict(lag=lag,peak=peak,phase=s.phase,reason=s.reason,target=s.target))
        (T.BUILD/'video-flow-delays.json').write_text(json.dumps({'artifactSha256':T.M['artifact_sha256'],
            'hardwareRequests':0,'cases':rows},indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':unittest.main(verbosity=2)
