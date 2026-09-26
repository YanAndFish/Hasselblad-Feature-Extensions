"""R5局部峰修复：实测字段播种、量化位置、噪声反例与原有原生回归。无硬件。"""
import sys,json,struct,math,random,unittest,time
sys.dont_write_bytecode=True
from check_r4_limits import LimitedCase,LimitTests,AF,FLOW,NATIVE,T
from test_r3_matrix import MatrixTests
from test_r3_preview_guard import PreviewGuardTests
ROWS=[]

def seeded(noise=274341,refinements=1):
    c=LimitedCase(origin=1953);c.next_cycle()
    c.vset('session',0)
    for name,value in {'origin':1829,'probe_origin':1889,'refinements':refinements,
                       'samples':2,'noise':noise,'best_cv':2501727,'best_index':1}.items():c.set(name,value)
    for i,(p,cv) in enumerate(((1825,1822560),(1889,2501727))):
        c.u.mem_write(c.addr+T.State.positions.offset+2*i,struct.pack('<h',p))
        c.w(c.addr+T.State.cvs.offset+4*i,cv)
    return c

class PeakTests(unittest.TestCase):
    def test_recorded_disjoint_intervals_reach_peak_and_verify(self):
        c=seeded()
        for _ in range(30):
            c.feed(1953,1700509)
            if c.targets:break
        self.assertEqual(c.state().phase,6)
        self.assertLessEqual(abs(c.targets[0]-1889),4)
        target=c.targets[0]
        c.position_message(target);c.reply()
        for _ in range(35):
            c.feed(target,2450000)
            if c.state().phase>=8:break
        self.assertEqual((c.state().phase,c.state().reason),(8,0))
        self.assertEqual(c.results,[0])
        ROWS.append({'case':'recorded_point_state_with_disjoint_intervals','target':target,
                     'phase':c.state().phase,'hardwareRequests':0})

    def test_overlapping_intervals_do_not_force_success_and_do_not_repeat_quantized_position(self):
        c=seeded(noise=500000)
        for _ in range(30):
            c.feed(1953,1700509)
            if c.targets:break
        self.assertEqual(c.targets,[2017])
        c.position_message(2018);c.reply()
        for _ in range(40):
            c.feed(2018,961567)
            if len(c.targets)>1 or c.state().phase>=8:break
        self.assertEqual(c.targets,[2017,1761])
        c.position_message(1761);c.reply()
        for _ in range(40):
            c.feed(1761,1700000)
            if c.state().phase>=8:break
        self.assertEqual((c.state().phase,c.state().reason),(9,11))
        self.assertEqual(c.targets.count(2017),1)
        ROWS.append({'case':'overlapping_intervals_with_quantized_reply','targets':c.targets,
                     'phase':c.state().phase,'reason':c.state().reason})

    def test_reached_reply_without_distinct_probe_position_is_not_a_new_point(self):
        c=LimitedCase(origin=0);c.next_cycle()
        for _ in range(30):
            c.feed(0,1000)
            if c.targets:break
        c.set('target',0);c.set('command_target',0)
        c.reply()
        for _ in range(40):
            c.feed(0,1000)
            if c.state().phase>=8:break
        self.assertEqual((c.state().phase,c.state().reason),(9,10))
        self.assertEqual(c.state().samples,1)

    def test_noisy_flat_curves_do_not_become_success(self):
        failures=[]
        for amplitude in (100,1000,3000,9000):
            for seed in range(64):
                rng=random.Random(seed);c=LimitedCase();c.next_cycle()
                s=c.simulate_limits(lambda p:10000+rng.randint(-amplitude,amplitude))
                if s.phase!=9 or c.results!=[1]:failures.append((amplitude,seed,s.phase,s.reason))
        self.assertEqual(failures,[])
        ROWS.append({'case':'uncorrelated_noisy_flat','cases':256,'falseSuccesses':len(failures)})

    def test_native_error_mask_is_bound_to_cycle_and_resets(self):
        c=LimitedCase();c.next_cycle();c.event(0x100)
        def word(name):return struct.unpack('<I',c.u.mem_read(T.M['symbols'][name],4))[0]
        self.assertEqual((word('af_error_events'),word('af_error_generation')),(0x100,1))
        c.next_cycle()
        self.assertEqual((word('af_error_events'),word('af_error_generation')),(0,2))

def main():
    T.BUILD=T.HERE/'build/full-r5';T.M=json.loads((T.BUILD/'manifest.json').read_text())
    suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(c) for c in
        (PeakTests,LimitTests,AF.R3Tests,FLOW.VideoFlowTests,NATIVE.JointNativeTests,MatrixTests,PreviewGuardTests))
    start=time.monotonic();result=unittest.TextTestRunner(verbosity=2).run(suite)
    record={'artifactSha256':T.M['artifact_sha256'],'tests':result.testsRun,'passed':result.wasSuccessful(),
        'seconds':time.monotonic()-start,'hardwareRequests':0,'cases':ROWS,
        'limitations':['实测字段仅用于播种，后续CV/位置是明确模型输入',
            '不能把通过范围有限的噪声反例当成实机合焦率','R5尚未安装或实机验证']}
    (T.BUILD/'peak-regression.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(not result.wasSuccessful())

if __name__=='__main__':main()
