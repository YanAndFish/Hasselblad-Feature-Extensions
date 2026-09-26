"""R3离线反例矩阵。图像只作CV代理；不声称实机准确度或时长。"""
import sys,unittest,math,json,random,struct
sys.dont_write_bytecode=True
from test_r3_native_messages import NativeMessages,R,T

def save(name,rows):
    (T.BUILD/name).write_text(json.dumps({'artifactSha256':T.M['artifact_sha256'],
        'hardwareRequests':0,'physicalAfVerified':False,'cases':rows},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

class MatrixTests(unittest.TestCase):
    def test_delayed_irregular_frames_success_requires_localization(self):
        rows=[]
        for lag in (0,1,2,4,8):
            for intervals in ((10,),(7,13,9,11),(4,4,12)):
                for peak in (-300,300):
                    c=R.MotionCase();c.next_cycle()
                    s=c.simulate_motion(lambda p:10000*math.exp(-.5*((p-peak)/400)**2),lag=lag,intervals=intervals)
                    rows.append(dict(lag=lag,intervals=intervals,peak=peak,phase=s.phase,reason=s.reason,
                        error=abs(s.target-peak),ticks=(c.time-s.started)&0xffffffff,rejects=c.rejects))
        save('delay-matrix.json',rows)
        self.assertFalse([r for r in rows if r['rejects'] or r['phase']==8 and r['error']>20])
        self.assertTrue(all(r['phase']==8 for r in rows if r['lag']<=1))
        self.assertTrue(all(r['phase']==9 for r in rows if r['lag']==8))

    def test_native_pairing_startup_orders(self):
        rows=[]
        for early in (0,1,2,3):
            for far in (False,True):
                for peak in (-300,300):
                    for width in (200,400,1000):
                        c=NativeMessages(startup_cv=early,far=far);c.next_cycle()
                        s=c.simulate_motion(lambda p:10000*math.exp(-.5*((p-peak)/width)**2))
                        rows.append(dict(early=early,far=far,peak=peak,width=width,phase=s.phase,reason=s.reason,
                            error=abs(s.target-peak),ticks=c.time-s.started,rejects=c.rejects))
        save('native-message-matrix.json',rows)
        self.assertFalse([r for r in rows if r['rejects'] or r['phase']==8 and r['error']>20])
        self.assertTrue(all(r['phase']==8 for r in rows))

    def test_user_images_with_coasting(self):
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
                        c=R.MotionCase(far=far);c.next_cycle();s=c.simulate_motion(curve)
                        rows.append(dict(scene=item['scene'],roi=item['roi'],metric=item['metric'],units=units,
                            peak=peak,far=far,phase=s.phase,reason=s.reason,error=abs(s.target-peak),ticks=c.time-s.started))
        save('user-image-matrix.json',rows)
        self.assertFalse([r for r in rows if r['phase']!=8 or r['error']>max(20,r['units']*.25)])

    def test_failures_cancel_and_late_packets_do_not_poison_following_cycles(self):
        for kind in ('flat','cancel','wrong_reset','no_positions','lens_status5'):
            c=R.MotionCase();c.next_cycle()
            if kind=='flat':c.simulate_motion(lambda p:1000)
            elif kind=='cancel':
                c.w(0x90ff00-0x94,0x20000);c.run(0x19b960,dispatch=True)
            elif kind=='wrong_reset':c.run('af_reset_owned',0x199ef4);c.event(0)
            elif kind=='no_positions':c.time+=100;c.w(0x6badd0,c.time);c.event(0)
            elif kind=='lens_status5':
                for _ in range(7):c.feed(0,1000,accepted=False)
                c.reply(5);c.event(0)
            self.assertEqual(c.state().phase,9,(kind,c.state().phase,c.state().reason))
            for i in range(3):
                old=c.make_frame(1000);c.next_cycle();self.assertFalse(c.deliver_frame(old))
                peak=c.position+(300 if i%2 else -300)
                s=c.simulate_motion(lambda p:10000*math.exp(-.5*((p-peak)/400)**2))
                self.assertEqual((s.phase,s.reason),(8,0),(kind,i,s.phase,s.reason))
                self.assertLessEqual(abs(s.target-peak),20);self.assertFalse(c.rejects)

if __name__=='__main__':unittest.main(verbosity=2)
