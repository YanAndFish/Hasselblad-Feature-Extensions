"""第二版原生ARM回归；保留同一内存的原厂启动/完成/下一轮，端点故障复现。"""
import sys,json,struct,math,unittest,random
sys.dont_write_bytecode=True
import test_full_candidate as T
T.BUILD=T.HERE/'build/full-r2'
T.M=json.loads((T.BUILD/'manifest.json').read_text(encoding='utf-8'))
from test_full_candidate import Case,State,NativeCompletionCase

class LifecycleCase(NativeCompletionCase):
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.set('generation',0);self.set('owned',0);self.set('phase',0)
        self.lifecycle=True;self.query_count=0;self.enables=0;self.timer_ops=[]
        self.u.mem_write(0x6bb46c,b'\0')
        for a in (0x198778,0x1f0a1c):self.u.mem_write(a,bytes.fromhex('1eff2fe1'))
    def hook(self,u,a,size,data):
        if getattr(self,'lifecycle',False):
            if a==0x198778:self.return_value(u,0);return
            if a==0x1f0a1c:self.return_value(u,0);return
            if a==0x18a594:
                operation=u.reg_read(T.UC_ARM_REG_R1);self.timer_ops.append(operation)
                if operation==3:self.timer_cancels+=1
                self.return_value(u,0);return
            if a==0x1e80d0:
                msg=bytes(u.mem_read(u.reg_read(T.UC_ARM_REG_R0),8));kind=struct.unpack_from('<H',msg)[0]
                if kind in (0x377,0xb0):
                    if kind==0x377:self.query_count+=1
                    else:self.enables+=1
                    self.return_value(u,1);return
            if (0x19bb98<=a<0x19bfb4 or 0x19d040<=a<0x19d198 or
                0x1a4954<=a<=0x1a4aa4 or 0x1a42d8<=a<=0x1a4388 or
                0x199c94<=a<0x199ccc):return
        super().hook(u,a,size,data)
    def native_event(self,mask):
        self.w(0x90ff00-0x94,mask)
        self.run(0x19bb94,dispatch=True)
        assert self.resume==0x19d198
    def next_cycle(self,position=None):
        # 实际7态关闭确认后回0，随后真实1/2/4事件启动；不手写清任何原厂队列。
        if self.u.mem_read(0x6bb46c,1)[0]==7:self.native_event(8)
        assert self.u.mem_read(0x6bb46c,1)[0]==0
        self.native_event(1);assert self.u.mem_read(0x6bb46c,1)[0]==1
        assert self.state().phase==1 and self.state().pending_error==0
        assert struct.unpack('<H',self.u.mem_read(0x6bc954,2))[0]==0
        assert all(self.u.mem_read(a,4)==bytes(4) for a in (0x6bc984,0x6bc998))
        self.accepted=[];self.move_target=None
        self.native_event(2);assert self.u.mem_read(0x6bb46c,1)[0]==2
        self.native_event(4);assert self.u.mem_read(0x6bb46c,1)[0]==3
        self.position_message(self.position if position is None else position)
        # 固定初始镜头回报链在1a1f40先写CMD，再调用speed_entry。
        self.h(0x6bb5a0,20000)
        self.run('speed_entry',20000,lr=0x1a1f68)
    def boundary(self,direction):self.run('near_entry' if direction>0 else 'far_entry');self.event(0)

class R2Tests(T.FullTests):
    def test_user_image_proxy_curves_including_weak_initial_signal(self):
        fixture=json.loads((T.HERE/'CodeTests/Fixtures/SyntheticAfCurves.json').read_text(encoding='utf-8'))
        rows=[]
        for item in fixture['curves']:
            for units in (50,100,200):
                for peak in (-300,300):
                    for far in (False,True):
                        def curve(p):
                            x=abs(p-peak)/units*4;values=item['values'];i=min(int(x),len(values)-1)
                            value=values[i] if i==len(values)-1 else values[i]+(values[i+1]-values[i])*(x-i)
                            return max(1,round(value*fixture['cvScale']))
                        c=Case(far);c.start();s=c.simulate(curve)
                        self.assertEqual(s.phase,8,(item['scene'],item['roi'],item['metric'],units,peak,far,s.reason))
                        # 8000/10tick模型步距为80，单次三点拟合精度要求为四分之一步距。
                        # 不沿用3000/10tick版的固定15单位门限来声称相同精度。
                        error=abs(s.target-peak)
                        self.assertLessEqual(error,max(15,T.M['fineSpeed']*.010/4,units*.25))
                        self.assertLessEqual(s.reversals,1);self.assertEqual(c.sends[-1],0);self.assertFalse(c.native_search)
                        rows.append(dict(scene=item['scene'],roi=item['roi'],metric=item['metric'],units=units,peak=peak,far=far,error=error,ticks=(c.time-s.started)&0xffffffff))
        self.assertEqual(len(rows),96)
        (T.BUILD/'image-proxy-results.json').write_text(json.dumps({'payloadSha256':T.M['payload_sha256'],'physicalAfVerified':False,'cases':rows},indent=2)+'\n',encoding='utf-8')
        print('8000 image proxy cases',len(rows),'max position error',max(r['error'] for r in rows))

    def test_additional_noise_seeds_after_fine_noise_change(self):
        for amplitude in (20,100,200,400):
            for seed in range(24,88):
                rng=random.Random(seed);c=Case();c.start()
                s=c.simulate(lambda p:1000+rng.randint(-amplitude,amplitude))
                self.assertEqual(s.phase,9,(amplitude,seed,s.target,s.best_cv,s.noise))
                self.assertEqual(c.results,[1])

    def test_original_payload_repeats_observed_endpoint_failure(self):
        saved_build,saved_manifest=T.BUILD,T.M
        try:
            T.BUILD=T.HERE/'build/full-owned';T.M=json.loads((T.BUILD/'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(T.M['payload_sha256'],'0273fd5771d34eb3884681fdfbeb2a04b26f2237574a3bcc6b0fa5f562a78f55')
            c=LifecycleCase(origin=3454)
            for generation in range(1,4):
                c.next_cycle();self.assertEqual(c.sends[-1],20000);c.boundary(1)
                self.assertEqual((c.state().generation,c.state().phase,c.state().reason),(generation,9,8))
                self.assertEqual(c.state().samples,0)
            self.assertEqual(c.results,[1,1,1])
        finally:T.BUILD,T.M=saved_build,saved_manifest

    def test_boundary_and_lens_error_have_no_search_retry(self):
        # 新版端点在粗扫中允许唯一折返；位置移动错误仍有界失败。
        c=Case();c.start();c.run('near_entry');c.event(0)
        self.assertEqual(c.state().reversals,1);self.assertEqual(c.sends[-1],-20000)
        c.run('far_entry');c.event(0)
        self.assertEqual(c.state().reason,8);self.assertEqual(c.results,[1])
        c=Case();c.start();c.set('phase',4);c.reply(1);c.event(0)
        self.assertEqual(c.state().reason,9);self.assertEqual(c.results,[1])

    def test_observed_endpoint_then_valid_peak_and_next_two_cycles(self):
        c=LifecycleCase(origin=3454)
        c.next_cycle();self.assertEqual(c.sends[-1],20000)
        c.boundary(1)
        self.assertEqual((c.state().phase,c.state().pending_error,c.state().reversals),(3,0,1))
        self.assertEqual(c.sends[-1],-20000)
        c.boundary(1) # 迟到重复的原端点不能把向内运动再次判失败。
        self.assertEqual(c.sends[-1],-20000)
        c.simulate(lambda p:10000*math.exp(-.5*((p-2500)/300)**2))
        self.assertEqual(c.state().phase,8,(c.state().reason,c.targets))
        for peak in (2200,2700):
            c.next_cycle();c.simulate(lambda p:10000*math.exp(-.5*((p-peak)/300)**2))
            self.assertEqual(c.state().phase,8,(c.state().generation,c.state().reason,c.targets))
        self.assertEqual(c.results,[0,0,0]);self.assertEqual(c.query_count,3)
        self.assertFalse(c.native_search)

    def test_first_bounded_failure_does_not_poison_next_peak(self):
        for mode in ('flat','double_endpoint','no_position','no_reply','cancel','reset_other'):
            with self.subTest(mode=mode):
                c=LifecycleCase();c.next_cycle()
                if mode=='flat':c.simulate(lambda p:1000)
                elif mode=='double_endpoint':c.boundary(1);c.boundary(-1)
                elif mode=='no_position':c.time+=100;c.w(0x6badd0,c.time);c.event(0)
                elif mode=='no_reply':
                    for i in range(250):
                        s=c.state()
                        if s.phase==9:break
                        p=c.move_target if c.move_target is not None else c.position+int(s.command/100)
                        c.feed(p,max(1,round(10000*math.exp(-.5*((p-300)/300)**2))))
                elif mode=='cancel':
                    c.w(0x90ff00-0x94,0x20000);c.run(0x19b960,dispatch=True)
                elif mode=='reset_other':c.run('af_reset_owned',0x199ef4);c.event(0)
                self.assertEqual(c.state().phase,9,(mode,c.state().reason))
                for i in range(2):
                    peak=c.position+(-300 if mode=='double_endpoint' else 300)
                    c.next_cycle();s=c.simulate(lambda p:10000*math.exp(-.5*((p-peak)/300)**2))
                    self.assertEqual(s.phase,8,(mode,i,s.reason,c.sends,c.targets))
                    self.assertEqual(s.pending_error,0);self.assertEqual(s.generation,i+2)
                self.assertEqual(c.results[-2:],[0,0]);self.assertFalse(c.native_search)

    def test_endpoint_hint_survives_only_as_position_qualified_direction(self):
        c=LifecycleCase(origin=3454);c.next_cycle();c.boundary(1);c.boundary(-1)
        self.assertEqual(c.state().phase,9)
        c.next_cycle();self.assertEqual(c.sends[-1],20000)
        c.boundary(1);c.boundary(-1)
        self.assertEqual(c.state().phase,9)
        c.next_cycle(position=3000);self.assertEqual(c.sends[-1],20000)

    def test_late_position_ack_and_terminal_feedback_do_not_poison_next_cycle(self):
        c=LifecycleCase();c.next_cycle();c.run('af_reset_owned',0x199ef4);c.event(0)
        before=bytes(c.u.mem_read(c.addr,T.M['stateBytes']))
        c.reply(1);c.position_message(17);c.cv_message(7)
        self.assertEqual(before,bytes(c.u.mem_read(c.addr,T.M['stateBytes'])))
        c.native_event(8);c.native_event(1);c.reply(1)
        self.assertEqual(c.state().pending_error,0)

    def test_endpoint_cannot_override_configuration_and_motion_guards(self):
        for invalid in ('config','state','travel','stale'):
            c=Case();c.start();c.run('near_entry')
            if invalid=='config':c.u.mem_write(0x2adc8c,b'\1')
            elif invalid=='state':c.u.mem_write(0x6bb46c,b'\4')
            elif invalid=='travel':c.set('physical',9000)
            elif invalid=='stale':c.w(0x6badd0,c.time+100)
            c.event(0);self.assertEqual(c.state().phase,9);self.assertEqual(c.sends[-1],0)
            self.assertEqual(c.state().reversals,0)

if __name__=='__main__':unittest.main()
