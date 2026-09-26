"""真实 ARM 峰值入口回放；观察时序预算，不是物理曝光/实机精度证明。"""
import struct,unittest
import test_r6_candidate as c
class AdvanceWindow(unittest.TestCase):
    def machine(self,ms):
        m=c.Machine();m.u.mem_write(0x1a4890,c.pack(0xe12fff1e))
        self.assertEqual(c.words(m.process(c.request(2,1,c.config(time=ms)))[24:28]),(0,))
        m.run('na_begin',2);m.u.mem_write(0x6bb46c,b'\x04');m.u.mem_write(0x6bb59c,b'\x01\x00')
        return m
    def sample(self,m,n,cv,tick):
        m.u.mem_write(0x6bb5cc+(n-1)*4,c.pack(cv));m.u.mem_write(0x6bc954,struct.pack('<H',n))
        m.u.mem_write(0x6badd0,c.pack(tick));m.run('na_start_accepted',n)
    def test_100ms_advances_same_event_by_two_50ms_samples(self):
        first=[]
        for ms in (0,100):
            m=self.machine(ms)
            for n,cv in enumerate((100,150,200,190,180,170),1):
                self.sample(m,n,cv,n*50);m.run(0x19d5c8)
                if m.events: first.append((ms,n*50));break
            self.assertEqual(m.events,[0x40]);self.assertEqual(m.sends,[])
            self.assertEqual(bytes(m.u.mem_read(0x6bb59c,2)),b'\x01\x01')
        self.assertEqual(first,[(0,300),(100,200)])
    def test_zero_and_factory_sentinel_match_unpatched_peak(self):
        for ms in (0,65534):
            for values in ((100,200,300,400),(400,300,200,100),(100,200,200,190),(100,200,190,180)):
                patched=self.machine(ms);original=self.machine(ms)
                original.u.mem_write(0x19d5c8,c.pack(0xe92d4800));original.u.ctl_remove_cache(0x19d5c8,0x19d5cc)
                for m in (patched,original):
                    for n,cv in enumerate(values,1):self.sample(m,n,cv,n*50)
                    m.run(0x19d5c8)
                self.assertEqual(patched.events,original.events)
                self.assertEqual(bytes(patched.u.mem_read(0x6bb59c,4)),bytes(original.u.mem_read(0x6bb59c,4)))
    def test_duplicates_new_cycle_missing_flags_unknown_lens_and_no_fall(self):
        for mode in ('duplicate','reset','flags','lens','rising','unready'):
            m=self.machine(100)
            for n,cv in enumerate((100,150,200,190 if mode!='rising' else 210),1):self.sample(m,n,cv,n*50)
            if mode=='duplicate':m.run(0x19d5c8);m.events.clear()
            if mode=='reset':m.run('na_begin',3)
            if mode=='flags':m.u.mem_write(0x6bb59c,b'\x00\x00')
            if mode=='lens':m.u.mem_write(0x2adc79,b'\x13')
            if mode=='unready':m.u.mem_write(c.M['symbols']['af_window'],c.pack(9))
            m.run(0x19d5c8);self.assertEqual(m.events,[],mode)
    def test_firmware_millisecond_conversion_actual_arm(self):
        from unicorn.arm_const import UC_ARM_REG_FP,UC_ARM_REG_SP,UC_ARM_REG_R1
        for ms in (0,1,50,100,1000):
            m=c.Machine();u=m.u;fp=0x908000
            u.reg_write(UC_ARM_REG_FP,fp);u.reg_write(UC_ARM_REG_SP,fp-0x24);u.reg_write(UC_ARM_REG_R1,1234)
            u.mem_write(fp-0x1c,c.pack(ms));u.emu_start(0x11d728,0x11d760,count=100)
            self.assertEqual(c.words(u.mem_read(fp-0xc,4)),(1234+ms,))
if __name__=='__main__':unittest.main(verbosity=2)
