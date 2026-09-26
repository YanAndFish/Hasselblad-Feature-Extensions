"""R3开发回归：运行候选ARM，显式模拟惯性、回包延迟和CF拒绝。无USB。"""
import sys,json,ctypes,struct,math,unittest,random
sys.dont_write_bytecode=True
import test_full_r2 as R
T=R.T
OLD_STATE=T.State
class Frame(ctypes.LittleEndianStructure):
    _fields_=[(n,T.U32) for n in 'seq tick generation cv'.split()]+[('position',T.I32),('accepted_seq',T.U32)]
class State(ctypes.LittleEndianStructure):
    _fields_=OLD_STATE._fields_[:56]+[("positions",ctypes.c_int16*32),("cvs",T.U32*32),("trace",T.Trace*8)]
    _fields_ += [(n,T.U32) for n in "stop_pending stable_tick stable_seq stable_points".split()]
    _fields_ += [("stable_position",T.I32),("predictions",T.U32),("brake_distance",T.U32),("probe_active",T.U32)]
    _fields_ += [("frame_seq",T.U32),("frame_consumed",T.U32),("frames",Frame*8)]
    _fields_ += [("probe_origin",T.I32),("refinements",T.U32)]
    _fields_ += [(n,T.U32) for n in 'cv_profile video_state video_started video_raw video_fresh video_preview last_full_tick finish_pending'.split()]
    _fields_ += [("video_command",T.I32),("video_mipi",T.U32),("canary",T.U32)]
T.BUILD=T.HERE/'build/full-r3'
T.M=json.loads((T.BUILD/'manifest.json').read_text(encoding='utf-8'))
T.State=State
assert ctypes.sizeof(State)==T.M['stateBytes'],(ctypes.sizeof(State),T.M['stateBytes'])

class MotionCase(R.LifecycleCase):
    def __init__(self,**kwargs):
        self.velocity=0.;self.coast=20;self.rejects=[];self.timeline=[];self.ack_count=0
        self.request_far=kwargs.get('far',False)
        super().__init__(**kwargs)
        for seg in T.M['segments']:self.u.mem_write(seg['base'],(T.BUILD/seg['file']).read_bytes())
        self.u.mem_write(0x1a4890,bytes.fromhex('1eff2fe1'))
        self.allow_native_dispatch=False
    def cv_message(self,cv):
        return self.deliver_frame(self.make_frame(cv))
    def make_frame(self,cv):
        return struct.pack('<HHI',0xcc,self.run('af_tag_frame',cv),cv)
    def deliver_frame(self,packet):
        self.u.mem_write(0x900040,packet)
        before=self.state().raw_seq;self.run('af_observe_cv',0x900040)
        return self.state().raw_seq!=before
    def feed(self,position,cv,dt=10,accepted=True,dispatch=True,packet=None):
        self.time=(self.time+dt)&0xffffffff;self.w(0x6badd0,self.time)
        self.position_message(position)
        self.cv_message(cv) if packet is None else self.deliver_frame(packet)
        return self.event() if dispatch else None
    def next_cycle(self,position=None):
        if self.u.mem_read(0x6bb46c,1)[0]==7:self.native_event(8)
        assert self.u.mem_read(0x6bb46c,1)[0]==0
        self.native_event(1);self.native_event(2);self.native_event(4)
        assert self.u.mem_read(0x6bb46c,1)[0]==3
        assert self.u.mem_read(0x6bc954,2)==bytes(2)
        self.accepted=[];self.move_target=None
        self.position_message(self.position if position is None else position)
        # 原厂reset会设默认方向；这里只合成用户选择的另一初始方向覆盖分支。
        self.u.mem_write(0x2adc78,bytes((int(self.request_far),)))
        self.h(0x6bb5a0,20000);self.run('speed_entry',20000,lr=0x1a1f68)
    def hook(self,u,a,size,data):
        if a==0x1a4890:self.return_value(u);return
        if any(s['base']<=a<s['end'] for s in T.M.get('segments',[])):return
        if getattr(self,'allow_native_dispatch',False) and 0x19bb98<=a<0x19d198:return
        if a==0x1e80d0:
            msg=bytes(u.mem_read(u.reg_read(T.UC_ARM_REG_R0),8));kind=struct.unpack_from('<H',msg)[0]
            if kind in (0xcd,0xcf):
                value=struct.unpack_from('<h',msg,4)[0]
                self.timeline.append(dict(t=self.time,kind=kind,value=value,position=self.position,velocity=self.velocity))
                if kind==0xcf and abs(self.velocity)>.01:
                    self.rejects.append((self.time,self.velocity));self.return_value(u,1);return
        super().hook(u,a,size,data)
    def simulate_motion(self,curve,steps=400,lag=0,intervals=(10,)):
        history=[]
        for i in range(steps):
            s=self.state()
            if s.phase>=8:break
            dt=intervals[i%len(intervals)]
            if self.move_target is not None and self.position!=self.move_target:
                delta=self.move_target-self.position;dx=max(-6*dt,min(6*dt,delta));position=self.position+dx
                self.velocity=dx/dt if position!=self.move_target else 0.
            elif s.command:
                self.velocity=s.command/1000.;position=round(self.position+self.velocity*dt)
            else:
                old=self.velocity;self.velocity=old*max(0.,1-dt/self.coast)
                if abs(self.velocity)<.5:self.velocity=0.
                position=round(self.position+(old+self.velocity)*dt/2)
            cv=max(1,round(curve(position)))
            self.time=(self.time+dt)&0xffffffff;self.w(0x6badd0,self.time)
            history.append((cv,self.make_frame(cv)))
            # 帧在产生时打标；延迟的是整条已产生消息，不能在送达时重新打标。
            cv,packet=history[max(0,len(history)-1-lag)]
            self.feed(position,cv,dt=0,accepted=s.command!=0,packet=packet)
            if self.move_target is not None and position==self.move_target and len(self.targets)>self.ack_count:
                self.ack_count=len(self.targets);self.reply()
            if self.rejects:
                self.reply(5);self.event(0)
        return self.state()

class R3Tests(unittest.TestCase):
    def test_unowned_all_native_search_states_close_without_movement(self):
        for state in (3,4,5,6):
            for mask in (0,16,32,64,128,0x400):
                c=MotionCase();c.next_cycle();c.set('armed',0);c.set('owned',0)
                c.u.mem_write(0x6bb46c,bytes((state,)));c.allow_native_dispatch=True
                c.native_event(mask)
                self.assertEqual((c.state().phase,c.state().reason),(9,13))
                self.assertEqual(c.u.mem_read(0x6bb46c,1),b'\x07')
                self.assertEqual(c.results,[1]);self.assertEqual(c.targets,[])
                self.assertTrue(all(command==0 for command in c.sends))
    def test_unarmed_fallback_hits_guard_and_closes_without_overlay_fallthrough(self):
        c=MotionCase();c.next_cycle();c.set('armed',0);c.set('owned',0)
        c.allow_native_dispatch=True;c.native_event(16)
        self.assertEqual((c.state().phase,c.state().reason),(9,13))
        self.assertEqual(c.u.mem_read(0x6bb46c,1),b'\x07')
        self.assertEqual(c.results,[1]);self.assertEqual(c.sends[-1],0)
    def test_stop_barrier_requires_new_stable_positions_not_old_ack(self):
        c=MotionCase();c.next_cycle();c.set('phase',4);c.set('command',0);c.set('target',700)
        c.set('command_target',700);c.set('move_started',c.time);c.set('stop_pending',1)
        c.set('stable_tick',c.time);c.set('stable_seq',c.state().position_seq)
        c.set('stable_position',0);c.reply(5)
        self.assertEqual(c.state().pending_error,0)
        for p in (150,220,250,260,270):c.feed(p,1000,accepted=False)
        self.assertEqual(c.targets,[])
        for _ in range(2):c.feed(270,1000,accepted=False)
        self.assertEqual(c.targets,[])
        c.feed(270,1000,accepted=False)
        self.assertEqual(c.targets,[700]);self.assertEqual(c.state().stop_pending,0)

    def test_native_closure_and_coasting_both_directions(self):
        rows=[]
        for far in (False,True):
            for peak in (-300,300):
                for width in (200,400,1000):
                    c=MotionCase(far=far);c.next_cycle()
                    s=c.simulate_motion(lambda p:10000*math.exp(-.5*((p-peak)/width)**2))
                    rows.append(dict(far=far,peak=peak,width=width,phase=s.phase,reason=s.reason,
                                     target=s.target,noise=s.noise,predictions=s.predictions,ticks=c.time-s.started,
                                     commands=c.timeline))
                    self.assertFalse(c.rejects,(far,peak,width,c.rejects))
        (T.BUILD/'motion-development.json').write_text(json.dumps(rows,indent=2)+'\n',encoding='utf-8')
        failed=[{k:v for k,v in r.items() if k!='commands'} for r in rows if r['phase']!=8 or abs(r['target']-r['peak'])>60]
        self.assertEqual(failed,[])

    def test_flat_and_noise_do_not_complete_successfully(self):
        for amplitude in (0,20,100,400):
            for seed in range(12):
                rng=random.Random(seed);c=MotionCase();c.next_cycle()
                s=c.simulate_motion(lambda p:1000+rng.randint(-amplitude,amplitude))
                self.assertEqual(s.phase,9,(amplitude,seed,s.target,s.noise))

    def test_recorded_r2_leg_brakes_earlier(self):
        record=json.loads((T.HERE/'recovery/full-diagnostic-r2-20260910-235937.json').read_text(encoding='utf-8'))
        c=MotionCase(far=True,origin=3129);c.next_cycle();c.set('probe_active',0);c.set('phase',3);c.set('skip',0)
        c.set('command',-20000);c.h(0x6bb5a0,-20000)
        for item in record['state']['samplesData']:
            c.feed(item['position'],item['cv'])
            if c.state().stop_pending:break
        s=c.state()
        self.assertEqual((s.phase,s.stop_pending),(4,2),(s.phase,s.reason,s.samples))
        self.assertGreaterEqual(s.physical,707)
        self.assertLessEqual(abs(s.fine_start-s.coarse_peak),320)
        self.assertEqual(c.targets,[])

if __name__=='__main__':unittest.main(verbosity=2)
