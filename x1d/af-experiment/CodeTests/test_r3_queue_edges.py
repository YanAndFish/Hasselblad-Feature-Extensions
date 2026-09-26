"""候选ARM队列的容量、回绕与显式中途覆盖；设备请求为零。"""
import sys,ctypes,unittest
sys.dont_write_bytecode=True
from test_r3_native_messages import NativeMessages,R,T
from unicorn import UC_HOOK_MEM_READ

class QueueTests(unittest.TestCase):
    def scan(self,sequence=0,time=1000):
        c=NativeMessages(startup_cv=0);c.time=time;c.w(0x6badd0,time);c.next_cycle()
        c.set('phase',3);c.set('probe_active',0);c.set('command',20000);c.set('skip',0)
        c.set('frame_seq',sequence);c.set('frame_consumed',sequence);c.set('seen',sequence)
        return c

    def burst(self,c,count):
        for i in range(count):c.feed((i+1)*32,1000+i*32,dt=1,dispatch=False)
        c.event(0)

    def test_burst_eight_drained_nine_or_ten_fail_before_accepting_torn_records(self):
        for count in (8,9,10):
            c=self.scan();self.burst(c,count);s=c.state()
            if count==8:
                self.assertEqual((s.phase,s.samples),(3,8))
                self.assertEqual(list(s.positions[:8]),list(range(32,257,32)))
                self.assertEqual(list(s.cvs[:8]),list(range(1000,1256,32)))
            else:
                self.assertEqual(s.phase,9);self.assertIn(s.reason,(2,7));self.assertEqual(s.samples,0)
                self.assertEqual(c.sends[-1],0)

    def test_tag_zero_skip_and_uint32_wrap(self):
        for sequence in (65532,0xfffffffc):
            c=self.scan(sequence);self.burst(c,7);s=c.state()
            self.assertEqual((s.phase,s.samples),(3,7))
            self.assertEqual(s.frame_seq,(sequence+8)&0xffffffff)
            # 跳过零会在这一批八个实际记录中重复槽位，必须报丢失，不能错配。
            c=self.scan(sequence);self.burst(c,8)
            self.assertEqual((c.state().phase,c.state().reason),(9,2))
            c=self.scan(sequence)
            for i in range(16):c.feed((i+1)*16,1000+i*16,dt=1)
            self.assertEqual((c.state().phase,c.state().samples),(3,16))

    def test_tick_wrap_keeps_fresh_frame_and_rejects_100_tick_old_frame(self):
        c=self.scan(time=0xfffffff0)
        for i in range(3):c.feed((i+1)*32,1000+i*32,dt=10)
        self.assertEqual((c.state().phase,c.state().samples),(3,3))
        packet=c.make_frame(1200);c.time=(c.time+100)&0xffffffff;c.w(0x6badd0,c.time)
        self.assertFalse(c.deliver_frame(packet));c.event(0)
        self.assertEqual((c.state().phase,c.state().reason),(9,2))

    def test_overwrite_mid_observer_and_mid_drain_fails_closed(self):
        for where in ('observer','drain'):
            c=self.scan();packet=c.make_frame(1000);seq=c.state().frame_seq
            slot=T.M['symbols']['af_state']+R.State.frames.offset+(seq&7)*ctypes.sizeof(R.Frame)
            c.position_message(32)
            if where=='drain':self.assertTrue(c.deliver_frame(packet))
            hits=[]
            def interleave(u,access,address,size,value,data):
                if not hits and address==slot+(4 if where=='observer' else 12):
                    hits.append(address)
                    # 对应生产者已经清除发布序号、正在写字段而尚未发布新序号。
                    c.w(slot,0);c.w(slot+20,0);c.w(slot+12,2000)
            hook=c.u.hook_add(UC_HOOK_MEM_READ,interleave)
            if where=='observer':self.assertFalse(c.deliver_frame(packet))
            c.event(0);c.u.hook_del(hook)
            self.assertEqual(len(hits),1)
            self.assertEqual((c.state().phase,c.state().reason,c.state().samples),(9,2,0))

if __name__=='__main__':unittest.main(verbosity=2)
