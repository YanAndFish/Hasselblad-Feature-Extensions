"""执行原厂CV生产和位置启动/计时器前段，验证自有消息队列；RTOS/FPGA为替身。无USB。"""
import sys,struct,unittest,math,json
sys.dont_write_bytecode=True
import test_full_r3 as R
T=R.T

class NativeMessages(R.MotionCase):
    MESSAGE_STUBS=(0x1f0c20,0x1867e4,0x186b70,0x1a4890,0x23899c,0x17bd50,0x19e404)
    def __init__(self,**kwargs):
        self.startup_cv=kwargs.pop('startup_cv',2)
        self.message_native=False
        super().__init__(**kwargs)
        self.message_native=True;self.produced=[];self.native_masks=[];self.fpga_cv=0;self.fpga_status=0
        self.router_packet=None;self.router_received=False;self.router_count=0
        for a in self.MESSAGE_STUBS:self.u.mem_write(a,bytes.fromhex('1eff2fe1'))
        self.u.mem_write(0x6bcb44,struct.pack('<f',100.0))
    def hook(self,u,a,size,data):
        if getattr(self,'message_native',False):
            r0=u.reg_read(T.UC_ARM_REG_R0)
            if a==0x19b294 and self.router_received:
                self.resume=a;u.emu_stop();return
            if a==0x1f0c20:
                assert u.reg_read(T.UC_ARM_REG_R1)==1
                self.w(r0,self.fpga_cv);self.return_value(u,self.fpga_status);return
            if a==0x1867e4:
                # 原厂1a443c..4448创建8项、每项0x11f字节的共享消息队列。
                self.produced.append(bytes(u.mem_read(u.reg_read(T.UC_ARM_REG_R1),0x11f)))
                self.w(u.reg_read(T.UC_ARM_REG_R2),0);self.return_value(u,1);return
            if a==0x186b70:
                assert self.router_packet is not None and u.reg_read(T.UC_ARM_REG_R1)==0x6bb478
                assert len(self.router_packet)==0x11f
                u.mem_write(0x6bb478,self.router_packet);self.router_received=True;self.router_count+=1
                self.return_value(u,1);return
            if a==0x1a4890:self.native_masks.append(r0);self.return_value(u);return
            if a==0x23899c:assert r0==0x442c0060;self.return_value(u);return
            if a==0x17bd50:
                value=struct.unpack('<d',struct.pack('<II',r0,u.reg_read(T.UC_ARM_REG_R1)))[0]
                lo,hi=struct.unpack('<II',struct.pack('<d',float(math.ceil(value))))
                u.reg_write(T.UC_ARM_REG_R0,lo);u.reg_write(T.UC_ARM_REG_R1,hi);return
            if a==0x19e404:self.return_value(u);return
            if a==0x198778:self.return_value(u,18);return
            if any(lo<=a<hi for lo,hi in ((0x1986d8,0x198778),(0x19b284,0x19b710),(0x1a9e64,0x1a9e9c),(0x1a1a98,0x1a22c4),
                    (0x1a2a30,0x1a3170),(0x1a3eb4,0x1a3ef4))):return
        super().hook(u,a,size,data)
    def make_frame(self,cv):
        self.fpga_cv=cv;before=len(self.produced);self.run(0x1986d8,0)
        assert len(self.produced)==before+1
        return self.produced[-1]
    def deliver_frame(self,packet):
        before=self.state().raw_seq;self.router_packet=packet;self.router_received=False
        self.run(0x19b284,0)
        self.router_packet=None;self.router_received=False
        return self.state().raw_seq!=before
    def position_message(self,position):
        if not self.message_native:return super().position_message(position)
        self.position=position;msg=bytearray(12);struct.pack_into('<h',msg,5,position)
        self.u.mem_write(0x900040,bytes(msg));self.run('position_observer_entry',0x900040)
    def next_cycle(self,position=None):
        if self.u.mem_read(0x6bb46c,1)[0]==7:self.native_event(8)
        assert self.u.mem_read(0x6bb46c,1)[0]==0
        self.native_event(1);self.native_event(2);self.native_event(4)
        assert self.u.mem_read(0x6bb46c,1)[0]==3
        self.move_target=None
        self.u.mem_write(0x2adc78,bytes((int(self.request_far),)))
        # 显式合成CV先到的已对齐启动：首帧被原厂跳过，第二帧等候位置。
        # 尚无实机共同帧标记，另测0/1/3帧的顺序反例，不把这当唯一真实顺序。
        for _ in range(self.startup_cv):self.cv_message(1000)
        self.position_message(self.position if position is None else position)
        assert self.state().phase==2
    def feed(self,position,cv,dt=10,accepted=True,dispatch=True,packet=None):
        self.time=(self.time+dt)&0xffffffff;self.w(0x6badd0,self.time)
        self.position_message(position)
        self.cv_message(cv) if packet is None else self.deliver_frame(packet)
        # 不手写COUNT/CV/POS；本轮自有CV队列，原厂双FIFO在owned期间被两个入口一并隔离。
        mask=0
        for value in self.native_masks:mask|=value
        self.native_masks=[]
        return self.event(mask) if dispatch else None

class MessageTests(unittest.TestCase):
    def test_alternative_native_consumer_rejects_tagging_and_focus_cycle(self):
        c=NativeMessages();c.next_cycle();c.u.mem_write(0x6bb598,b'\x01')
        self.assertEqual(c.run('af_tag_frame',1000),0)
        c.event(0);self.assertEqual((c.state().phase,c.state().reason),(9,1))

    def test_original_producer_preserves_packet_and_failed_read_sends_nothing(self):
        c=NativeMessages();c.next_cycle();packet=c.make_frame(0x12345678)
        self.assertEqual(len(packet),0x11f)
        self.assertEqual(struct.unpack_from('<HHI',packet),(0xcc,3,0x12345678))
        self.assertEqual(c.state().frames[3].tick,c.time)
        before=len(c.produced);c.fpga_status=1;c.run(0x1986d8,0)
        self.assertEqual(len(c.produced),before)

    def test_old_duplicate_reordered_overwritten_and_aged_packets_rejected(self):
        c=NativeMessages();c.next_cycle();p1=c.make_frame(1000);p2=c.make_frame(1100)
        self.assertTrue(c.deliver_frame(p2));count=c.state().raw_seq
        self.assertFalse(c.deliver_frame(p1));self.assertFalse(c.deliver_frame(p2))
        self.assertEqual(c.state().raw_seq,count)
        old=c.make_frame(1200)
        for i in range(8):c.make_frame(1300+i)
        self.assertFalse(c.deliver_frame(old))
        aged=c.make_frame(1500);c.time+=100;c.w(0x6badd0,c.time)
        self.assertFalse(c.deliver_frame(aged))
        old=c.make_frame(1000)
        c.run('af_reset_owned',0x199ef4);c.event(0);c.next_cycle()
        fresh=c.make_frame(1000)
        self.assertFalse(c.deliver_frame(old));self.assertTrue(c.deliver_frame(fresh))

    def test_micro_settle_uses_production_time_and_new_positions(self):
        c=R.MotionCase();c.next_cycle();packets=[]
        for i in range(5):packets.append(c.make_frame(1000+i))
        for p in packets:c.feed(0,0,dt=10,accepted=False,packet=p)
        self.assertEqual(c.state().samples,0)
        self.assertEqual(c.state().verify_points,0)
        for i in range(5):c.feed(0,1000+i,dt=10,accepted=False)
        self.assertEqual(c.state().samples,1)
        self.assertEqual(c.targets,[64])

    def test_verify_rejects_pre_settle_frames_even_when_received_later(self):
        c=R.MotionCase();c.next_cycle();c.set('phase',7);c.set('stopped_tick',c.time)
        c.set('target',0);c.set('position_tolerance',12);c.set('best_cv',1000)
        p=c.make_frame(1000)
        c.feed(0,0,dt=60,accepted=False,packet=p)
        self.assertEqual(c.state().verify_points,0)
        for i in range(3):c.feed(0,1000,accepted=False)
        self.assertEqual(c.state().phase,8)

    def test_native_message_path_completes_gaussian_without_original_pairer(self):
        c=NativeMessages();c.next_cycle()
        s=c.simulate_motion(lambda p:10000*math.exp(-.5*((p-300)/400)**2))
        self.assertFalse(c.rejects)
        self.assertEqual((s.phase,s.reason),(8,0),(s.phase,s.reason,s.samples,c.timeline))
        self.assertLessEqual(abs(s.target-300),60)
        self.assertEqual(c.results,[0])
        self.assertEqual(c.u.mem_read(0x6bc954,2),bytes(2))

if __name__=='__main__':unittest.main(verbosity=2)
