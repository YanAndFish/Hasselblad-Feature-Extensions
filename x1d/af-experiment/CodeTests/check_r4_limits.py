"""R4有界限位运动模型与现有R3回归；独立运行，加载新产物，不访问USB。"""
import sys,json,math,unittest,ctypes,time
sys.dont_write_bytecode=True
import test_full_r3 as AF
import test_r3_video_flow as FLOW
import test_r3_joint_native as NATIVE
T=AF.T
RESULTS=[]

class LimitedCase(FLOW.JointCase):
    low=-3454
    high=3454
    def __init__(self,**kwargs):
        self.limits=[]
        super().__init__(**kwargs)

    def simulate_limits(self,curve,steps=1000):
        for _ in range(steps):
            s=self.state()
            if s.phase>=8:break
            dt=4 if self.mode==7 else 10
            target=self.move_target
            rejected=target is not None and not self.low<=target<=self.high
            boundary=0
            if rejected:
                position=self.position;self.velocity=0.
            elif target is not None and self.position!=target:
                dx=max(-6*dt,min(6*dt,target-self.position));position=self.position+dx
                self.velocity=dx/dt if position!=target else 0.
            elif s.command:
                self.velocity=s.command/1000.;position=round(self.position+self.velocity*dt)
                if position>self.high:position=self.high;boundary=1
                if position<self.low:position=self.low;boundary=-1
            else:
                old=self.velocity;self.velocity=old*max(0.,1-dt/self.coast)
                if abs(self.velocity)<.5:self.velocity=0.
                position=max(self.low,min(self.high,round(self.position+(old+self.velocity)*dt/2)))
            self.time=(self.time+dt)&0xffffffff;self.w(0x6badd0,self.time)
            self.service_model()
            if self.mode==5:self.mipi_ends=(self.mipi_ends+1)&255
            cv=max(1,round(curve(position)*(7 if self.mode==7 else 1)))
            self.feed(position,cv,dt=0)
            if rejected and target==self.move_target and self.time-self.move_sent_at>=30:
                status=1 if target>self.high else 2
                self.limits.append({'target':target,'status':status,'position':position,'generation':s.generation})
                self.move_target=None;self.ack_count=len(self.targets)
                self.reply(status);self.event()
            elif self.move_target is not None and position==self.move_target and len(self.targets)>self.ack_count:
                self.ack_count=len(self.targets);self.reply()
            if boundary:
                self.velocity=0.;self.boundary(boundary)
        return self.state()

class LimitTests(unittest.TestCase):
    def test_qualification_reason_mask_is_recorded_for_exact_generation(self):
        cases=(
            (1,lambda c:c.vset('dirty',1)),
            (1,lambda c:c.vset('request',1)),
            (2,lambda c:c.vset('enabled',0)),
            (4,lambda c:c.vset('need_recovery',1)),
            (8,lambda c:c.u.mem_write(0x6bb46c,b'\x04')),
            (16,lambda c:c.u.mem_write(0x6c176c,b'\x00')),
            (32,lambda c:c.u.mem_write(0x6c1778,b'\x02')),
            (128,lambda c:c.vset('observed_width',0)),
            (256,lambda c:c.w(0x6c173c,0x40000000)),
            (512,lambda c:c.w(0x6cc59c,100|(1250<<16))))
        import struct
        for expected,configure in cases:
            c=LimitedCase();c.next_cycle();configure(c)
            roi0,roi1=(struct.unpack('<I',c.u.mem_read(a,4))[0] for a in (0x6cc59c,0x6cc5a0))
            self.assertEqual(c.run('fast_video_begin',17,roi0,roi1,1120108861),0)
            status,generation=(struct.unpack('<I',c.u.mem_read(T.M['symbols'][n],4))[0]
                for n in ('fast_video_begin_status','fast_video_begin_generation'))
            self.assertEqual((status,generation),(expected,17))
        c=LimitedCase();c.next_cycle()
        self.assertEqual(struct.unpack('<I',c.u.mem_read(T.M['symbols']['fast_video_begin_status'],4))[0],0)
        self.assertEqual(struct.unpack('<I',c.u.mem_read(T.M['symbols']['fast_video_begin_generation'],4))[0],1)

    def first_request(self,c):
        c.next_cycle()
        for _ in range(30):
            c.feed(c.position,16000)
            if c.targets:return c.targets[-1]
        self.fail('no initial CF')

    def test_near_and_far_limit_reach_160_and_complete(self):
        for direction in (1,-1):
            origin=3454*direction;peak=origin-354*direction
            c=LimitedCase(origin=origin,far=direction<0);c.next_cycle()
            s=c.simulate_limits(lambda p:10000*math.exp(-.5*((p-peak)/300)**2))
            self.assertEqual((s.phase,s.reason),(8,0),(direction,s.phase,s.reason,c.targets,c.limits))
            self.assertEqual(c.limits,[dict(target=origin+64*direction,status=1 if direction>0 else 2,position=origin,generation=1)])
            self.assertEqual(s.reversals,1)
            self.assertTrue(any(x['target']==7 for x in c.transitions))
            self.assertEqual(c.transitions[-1]['target'],5)
            self.assertTrue(all(c.low<=p<=c.high for p in c.targets[1:]))
            RESULTS.append({'case':'near' if direction>0 else 'far','phase':s.phase,'reason':s.reason,
                'targets':c.targets,'limits':c.limits,'transitions':c.transitions,'targetError':abs(s.target-peak)})

    def test_next_cycles_remember_limit_without_outward_request(self):
        c=LimitedCase(origin=3454)
        for _ in range(3):
            c.next_cycle(position=3454)
            s=c.simulate_limits(lambda p:10000*math.exp(-.5*((p-3100)/300)**2))
            self.assertEqual((s.phase,s.reason),(8,0))
        self.assertEqual(len(c.limits),1)
        self.assertEqual(c.targets.count(3518),1)

    def test_flat_and_peak_outside_range_stop_without_repeating_limit(self):
        for direction in (1,-1):
            origin=3454*direction
            for curve in (lambda p:16000,lambda p:10000*math.exp(-.5*((p-(origin+100*direction))/300)**2)):
                c=LimitedCase(origin=origin,far=direction<0);c.next_cycle()
                s=c.simulate_limits(curve)
                self.assertEqual(s.phase,9)
                self.assertEqual(c.results,[1]);self.assertLessEqual(s.reversals,1)
                self.assertEqual(len(c.limits),1)
                self.assertLessEqual(len(c.targets),5)
                self.assertTrue(all(c.low<=p<=c.high for p in c.targets[1:]))

    def test_jam_other_errors_and_opposite_limit_are_failure(self):
        for status in (2,3,4,5,8,255):
            c=LimitedCase(origin=3454);self.assertEqual(self.first_request(c),3518)
            c.reply(status);c.event()
            self.assertEqual((c.state().phase,c.state().reason),(9,9),status)
            self.assertEqual(c.state().until,0)

    def test_duplicate_limit_and_second_limit_are_bounded(self):
        c=LimitedCase(origin=3454);self.first_request(c)
        c.reply(1);c.reply(1);c.event()
        self.assertEqual(c.state().reversals,1)
        self.assertEqual(c.state().reason,0)
        for _ in range(10):
            c.feed(3454,16000)
            if len(c.targets)>1:break
        self.assertEqual(c.targets,[3518,3390])
        c.reply(2);c.event()
        self.assertEqual((c.state().phase,c.state().reason),(9,8))
        self.assertEqual(c.state().reversals,1)

def main():
    T.BUILD=T.HERE/'build/full-r4'
    T.M=json.loads((T.BUILD/'manifest.json').read_text(encoding='utf-8'))
    assert T.M['stateBytes']==ctypes.sizeof(T.State)
    loader=unittest.TestLoader()
    suite=unittest.TestSuite(loader.loadTestsFromTestCase(cls) for cls in
        (LimitTests,AF.R3Tests,FLOW.VideoFlowTests,NATIVE.JointNativeTests))
    started=time.monotonic();result=unittest.TextTestRunner(verbosity=2).run(suite)
    report={'artifactSha256':T.M['artifact_sha256'],'tests':result.testsRun,'passed':result.wasSuccessful(),
        'seconds':time.monotonic()-started,'hardwareRequests':0,'cases':RESULTS,
        'limitations':['ARM候选执行真实指令，镜头边界、惯性、CV曲线及视频调度为替身',
            '模型通过不代表真实镜头合焦或160切换耗时已验证','R4尚未装载或完成安装审查']}
    (T.BUILD/'limit-regression.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(not result.wasSuccessful())

if __name__=='__main__':main()
