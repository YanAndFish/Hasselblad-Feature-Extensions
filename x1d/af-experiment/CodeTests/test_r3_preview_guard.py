"""原厂MIPI结束getter与AF恢复屏障；计数/像素/物理设备为明确替身。"""
import sys,unittest,json
sys.dont_write_bytecode=True
from test_r3_video_flow import JointCase,T

class PreviewGuardTests(unittest.TestCase):
    def full_wait(self,start=0):
        c=JointCase();c.mipi_ends=start;c.freeze_mipi=True
        c.start_fine();c.event(0x20000)
        for _ in range(30):
            c.simulate_joint(lambda p:1000,steps=1)
            if c.mode==5 and c.state().video_state==2:break
        self.assertEqual((c.mode,c.state().video_state),(5,2))
        self.assertEqual(c.results,[])
        return c

    def tick(self,c):
        return c.feed(c.position,1000,dt=10)

    def test_native_getter_returns_only_picture_end_low_byte(self):
        c=JointCase()
        for value in (0,0x12882201,0x34abcdfe,0xffffffff):
            c.mipi_ends=value
            self.assertEqual(c.run(0x1fd1a4),value&255)
        # 原厂格式和实参顺序：pixel/byte, picture-start, end, headers。
        self.assertTrue(T.FARM.read(0x252580,80).startswith(
            b'%syuv-pixels OR bytes: %lu, picture-start: %lu, end: %lu, headers: %lu'))

    def test_stats_alone_or_one_end_cannot_complete_full_restore(self):
        for initial in (0,254,255):
            c=self.full_wait(initial)
            for _ in range(6):self.tick(c)
            self.assertEqual(c.results,[]);self.assertEqual(c.state().video_state,2)
            c.mipi_ends=(initial+1)&255;self.tick(c)
            self.assertEqual(c.results,[])
            c.mipi_ends=(initial+2)&255;self.tick(c)
            self.assertEqual((c.state().phase,c.state().reason),(9,12))
            self.assertEqual(c.results,[1]);self.assertEqual(c.video().need_recovery,0)

    def test_frozen_mipi_fails_bounded_even_with_fresh_af_stats(self):
        c=self.full_wait();before=len(c.sends)
        s=c.simulate_joint(lambda p:1000)
        self.assertEqual((s.phase,s.reason),(9,14))
        self.assertEqual(c.video().need_recovery,1)
        self.assertTrue(all(v==0 for v in c.sends[before:]))
        self.assertLessEqual(c.time-c.state().video_started,360)

    def test_backwards_or_implausible_jump_does_not_satisfy_guard(self):
        c=self.full_wait(20)
        for value in (19,18,200):
            c.mipi_ends=value;self.tick(c)
            self.assertEqual(c.results,[])
        c.mipi_ends=22;self.tick(c)
        self.assertEqual((c.state().phase,c.state().reason),(9,12))

if __name__=='__main__':unittest.main(verbosity=2)
