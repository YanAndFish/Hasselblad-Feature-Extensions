"""两阶段起步实际 ARM/FARM 返回路径；无设备。"""
import struct,unittest
import test_r6_candidate as c
import test_r6_flow
class StartTests(unittest.TestCase):
    dispatch=test_r6_flow.FlowTests.dispatch
    def start(self,n=3,speed=1000,probe=17000,flags=2):
        m=c.Machine();m.u.mem_write(0x1a4890,bytes.fromhex('1eff2fe1'))
        m.u.mem_write(0x199b50,bytes.fromhex('0000a0e31eff2fe1'))
        self.assertEqual(c.words(m.process(c.request(2,1,c.config(flags=flags,probe=probe,start_speed=speed,start_samples=n)))[24:28]),(0,))
        m.run('na_begin',2);m.u.mem_write(0x6bb46c,b'\x03');m.run('na_stage_speed',0,6123)
        self.assertEqual(self.command(m),-speed if flags&2 else speed)
        m.sends.clear();return m
    def command(self,m):return struct.unpack('<h',m.sends[-1][-2:])[0]
    def accepted(self,m,count):m.run('nc_accepted',count)
    def undecided(self,m):
        m.native([1000,1000,1000]);self.dispatch(m,3,0x10)
    def test_n_boundary_and_duplicate_evaluation_count_no_samples(self):
        for n in (1,3,5,500):
            m=self.start(n)
            self.undecided(m);self.assertFalse(m.sends)
            for i in range(1,n):self.accepted(m,i)
            self.undecided(m);self.assertFalse(m.sends)
            self.accepted(m,n);self.undecided(m)
            self.assertEqual(self.command(m),-17000)
            before=len(m.sends)
            for _ in range(3):self.undecided(m)
            self.accepted(m,1);self.undecided(m);self.assertEqual(len(m.sends),before)
    def test_direction_before_and_on_n_wins_without_extra_high_command(self):
        for n in (3,10):
            m=self.start(n)
            for i in (1,2,3):self.accepted(m,i)
            m.native([1000,1300,1700]);self.dispatch(m,3,0x10)
            self.assertEqual(len(m.sends),1);self.assertEqual(self.command(m),20000)
            self.assertEqual(m.events,[0x20])
            for i in range(4,12):self.accepted(m,i)
            self.undecided(m);self.assertEqual(len(m.sends),1)
    def test_endpoint_sign_preserved_count_continues_and_no_rearm(self):
        m=self.start(3);self.accepted(m,1);m.run(0x1a06e4)
        self.assertEqual(self.command(m),1000);m.sends.clear()
        self.accepted(m,1);self.undecided(m);self.assertFalse(m.sends)
        self.accepted(m,2);self.undecided(m);self.assertEqual(self.command(m),17000)
        m.run('na_stage_speed',0,6123);self.assertEqual(self.command(m),-17000)
        m.run('na_begin',3);m.run('na_stage_speed',0,6123);self.assertEqual(self.command(m),-1000)
    def test_factory_high_restores_original_amplitude_with_current_sign(self):
        m=self.start(1,probe=0);m.run(0x1a06e4);self.accepted(m,1);self.undecided(m)
        self.assertEqual(self.command(m),6123)
    def test_fast_retry_state3_never_restarts_low(self):
        m=self.start(3);m.run('na_stage_speed',1,-6000)
        m.u.mem_write(0x6bb46c,b'\x04');m.u.mem_write(0x6bb59d,b'\x01');m.run(0x1a06e4)
        self.assertEqual(self.dispatch(m,4,0x4000),3)
        m.sends.clear()
        for i in range(1,6):self.accepted(m,i)
        self.undecided(m);self.assertFalse(m.sends)
    def test_invalid_config_and_old_wire_rejected(self):
        for speed,n in ((999,3),(6000,3),(1000,0),(1000,501)):
            m=c.Machine();before=m.bank();r=m.process(c.request(2,1,c.config(start_speed=speed,start_samples=n)))
            self.assertNotEqual(c.words(r[24:28])[0],0);self.assertEqual(before,m.bank())
        m=c.Machine();p=c.request();p[8:12]=c.pack(3);p[251:]=c.pack(c.checksum(p[:251]))
        self.assertNotEqual(c.words(m.process(p)[24:28])[0],0)
    def test_disabled_and_wrong_lens_never_arm(self):
        for lens in (18,19):
            m=c.Machine();m.u.mem_write(0x2adc79,bytes([lens]));m.run('na_stage_speed',0,6123);m.sends.clear()
            for i in (1,2,3):self.accepted(m,i)
            m.u.mem_write(0x6bb46c,b'\x03');m.run('na_after_direction');self.assertFalse(m.sends)
if __name__=='__main__':unittest.main(verbosity=2)
