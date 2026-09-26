"""实际 ARM 观察桥回放：正常发布、失效、寄存器/标志和陈旧缓存。无设备访问。"""
import unittest
import test_r6_candidate as c
from unicorn.arm_const import *

class Identity(unittest.TestCase):
    def test_eight_dynamic_parameter_success_and_failure_factory_slice(self):
        # Reference keys/speeds are supplied fixtures. This test verifies body
        # handling, not the lens query or an entire boot sequence.
        for fields,speed in (((49,49,1),59),((62,62,1),62),((39,39,3),45),((73,73,1),50),
                             ((35,35,1),25),((79,79,2),45),((47,83,1),60),((28,47,1),60)):
            for status in (0,1):
                m=c.Machine();u=m.u;fp=0x908000
                u.reg_write(UC_ARM_REG_FP,fp);u.reg_write(UC_ARM_REG_SP,fp-0x2b8)
                u.mem_write(0x2adc79,b'\x13');u.mem_write(0x6bcb7d,bytes([0,*fields[:2]]))
                for off,value in zip((0x2a5,0x2a6,5),fields):u.mem_write(fp-off,bytes([value]))
                response=bytearray(18);__import__('struct').pack_into('<HH',response,4,speed,speed)
                response[17]=status;u.mem_write(fp-0x188,bytes(response))
                def stop(uc,a,size,data):
                    if a in (0x199220,0x199194):uc.emu_stop()
                hook=u.hook_add(c.UC_HOOK_CODE,stop);u.emu_start(0x198d20,0,count=10000);u.hook_del(hook)
                self.assertEqual(u.mem_read(0x2adc79,1)[0],19 if status else 18)
                self.assertEqual(bool(m.run('af_identity_token',0)),not status)
                if not status:self.assertEqual(m.run('af_reported_start_speed'),speed*100)
    def bridge(self,m,address,end,fields):
        u=m.u;fp=0x908000;sp=fp-0x2b8
        u.reg_write(UC_ARM_REG_CPSR,0xa000001f)
        regs=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,
              UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,
              UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_R12,UC_ARM_REG_LR]
        for i,r in enumerate(regs):u.reg_write(r,0x12340000+i)
        u.reg_write(UC_ARM_REG_FP,fp);u.reg_write(UC_ARM_REG_SP,sp)
        u.reg_write(UC_ARM_REG_R2,18 if address==0x1990f8 else 19)
        u.reg_write(UC_ARM_REG_R3,0x2adc79)
        for off,v in zip((0x2a5,0x2a6,5),fields):u.mem_write(fp-off,bytes([v]))
        before=[u.reg_read(r) for r in regs]
        u.emu_start(address,end,count=10000)
        self.assertEqual(u.reg_read(UC_ARM_REG_PC),end)
        self.assertEqual([u.reg_read(r) for r in regs],before)
        self.assertEqual(u.reg_read(UC_ARM_REG_SP),sp)
        self.assertEqual(u.reg_read(UC_ARM_REG_CPSR)&0xf000003f,0xa000001f)
    def ready(self,fields):
        m=c.Machine();lo,hi,_=fields
        m.u.mem_write(0x6bcb7d,bytes([0,lo,hi]))
        m.u.mem_write(0x2ad998+18*36+5,bytes([lo,hi]))
        self.bridge(m,0x19890c,0x198910,fields)
        self.assertEqual(m.run('af_identity_token',0),0)
        self.bridge(m,0x1990f8,0x1990fc,fields)
        return m
    def test_eight_keys_capture_actual_success_store(self):
        for fields in ((49,49,1),(62,62,1),(39,39,3),(73,73,1),(35,35,1),(79,79,2),(47,83,1),(28,47,1)):
            m=self.ready(fields);token=m.run('af_identity_token',0x901000)
            self.assertNotEqual(token,0)
            self.assertEqual(c.words(m.u.mem_read(0x901000,4))[0],fields[0]|fields[1]<<8|fields[2]<<16)
            self.bridge(m,0x19890c,0x198910,fields)
            self.assertEqual(m.u.mem_read(0x2adc79,1)[0],19)
            self.assertEqual(m.run('af_identity_token',0),0)
    def test_stale_cache_model_and_focal_fail_closed(self):
        for a,v in ((0x2adc79,b'\x13'),(0x6bcb7e,b'\x01'),(0x2ad998+18*36+12,c.pack(999))):
            m=self.ready((73,73,1));m.u.mem_write(a,v)
            self.assertEqual(m.run('af_identity_token',0),0)
    def test_no_observed_publication_and_in_progress_fail_closed(self):
        m=c.Machine();self.assertEqual(m.run('af_identity_token',0),0)
        m=self.ready((73,73,1));a=c.M['symbols']['af_identity'];m.u.mem_write(a,c.pack(5))
        self.assertEqual(m.run('af_identity_token',0),0)

if __name__=='__main__':unittest.main(verbosity=2)
