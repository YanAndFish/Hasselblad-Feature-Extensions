"""实际固定 FARM 状态分支与速度封包；队列、亮度下限、精扫交接结果、镜头 getter 为替身。"""
import json,struct,unittest
from pathlib import Path
import test_r6_candidate as c
from unicorn.arm_const import *
HERE=Path(__file__).resolve().parents[1]
class FlowTests(unittest.TestCase):
    def machine(self):
        m=c.Machine();m.u.mem_write(0x1a4890,bytes.fromhex('1eff2fe1'))
        m.u.mem_write(0x199b50,bytes.fromhex('0000a0e31eff2fe1')) # 亮度门限已满足，模型只核状态分支
        m.process(c.request(2,1,c.config(flags=2)));m.run('na_begin',2)
        m.run('na_stage_speed',0,5000);m.sends.clear();m.events.clear()
        return m
    def dispatch(self,m,state,bits):
        u=m.u;u.mem_write(0x6bb46c,bytes([state]));u.mem_write(0x90e000-0x94,c.pack(bits))
        u.reg_write(UC_ARM_REG_SP,0x90d000);u.reg_write(UC_ARM_REG_FP,0x90e000)
        u.emu_start(0x19bfb4 if state==3 else 0x19c310,0x19d0ec,count=300000)
        self.assertEqual(u.reg_read(UC_ARM_REG_PC),0x19d0ec)
        return u.mem_read(0x6bb46c,1)[0]
    def test_failed_first_window_keeps_probe_then_later_window_sends_fast_before_state4(self):
        m=self.machine()
        m.native([1000,1100,1050]);self.assertEqual(self.dispatch(m,3,0x10),3)
        self.assertFalse(m.events);self.assertFalse(m.sends)
        self.assertEqual(struct.unpack('<h',m.u.mem_read(0x6bb5a0,2))[0],-9000)
        m.native([1000,1100,1050,1200,1500]);self.assertEqual(self.dispatch(m,3,0x10),3)
        self.assertEqual(m.events,[0x20]);self.assertEqual(m.sends[-1][-2:],struct.pack('<h',20000))
        self.assertEqual(self.dispatch(m,3,0x20),4)
    def test_far_endpoint_in_state3_reverses_same_probe_magnitude_and_rejoins_fast(self):
        m=self.machine();m.u.mem_write(0x6bb46c,b'\x03');m.run(0x1a06e4)
        self.assertEqual(m.events,[]);self.assertEqual(m.sends[-1][-2:],struct.pack('<h',9000))
        self.assertEqual(m.u.mem_read(0x6bb46c,1),b'\x03')
        m.native([1000,1300,1700]);self.dispatch(m,3,0x10)
        self.assertEqual(m.events,[0x20]);self.assertEqual(m.sends[-1][-2:],struct.pack('<h',20000))
    def test_final_direction_failure_goes_to_cleanup_not_fine(self):
        m=self.machine();m.u.mem_write(0x199ccc,bytes.fromhex('1eff2fe1'))
        m.u.mem_write(0x19dd70,bytes.fromhex('1eff2fe1'))
        self.assertEqual(self.dispatch(m,3,0x2000),7)
        self.assertFalse(m.sends)
    def test_state4_peak_event_enters_factory_fine_only_after_handoff_checks(self):
        m=self.machine();m.native([2000,1900,1800,1700]);m.u.mem_write(0x6bb59c,b'\x01')
        self.assertEqual(self.dispatch(m,4,0x10),4);self.assertEqual(m.events,[0x40])
        # 交接结果9明确表示暂不转state5；结果由替身指定，不推断未提供的峰位元数据。
        m.u.mem_write(0x19e7f0,bytes.fromhex('0900a0e31eff2fe1'))
        self.assertEqual(self.dispatch(m,4,0x40),4);self.assertFalse(m.sends)
        # 隔离替代峰位验证结果与镜头 getter；0x19d87c/速度封包/状态分支实际执行。
        m.u.mem_write(0x19e7f0,bytes.fromhex('0000a0e31eff2fe1'));m.u.ctl_remove_cache(0x19e7f0,0x19e7f8)
        m.u.mem_write(0x1a3ef4,bytes.fromhex('0000a0e31eff2fe1'))
        m.u.mem_write(0x1a3e08,c.pack(0xe3a00efa,0xe12fff1e)) # 2000，实际选档覆盖为5000
        self.assertEqual(self.dispatch(m,4,0x40),5)
        self.assertEqual(m.sends[-1][-2:],struct.pack('<h',5000))
    def test_failed_fast_far_endpoint_reduces_current_speed_then_returns_state3(self):
        m=self.machine();m.u.mem_write(0x6bb46c,b'\x04');m.u.mem_write(0x6bb59d,b'\x01')
        m.u.mem_write(0x6bb5a0,struct.pack('<h',-18000));m.run(0x1a06e4)
        self.assertEqual(m.events,[0x4000]);self.assertEqual(m.sends[-1][-2:],struct.pack('<h',12000))
        self.assertEqual(self.dispatch(m,4,0x4000),3)
        # 原厂恢复试探状态时保留减速后的当前命令，未重发 UI 的9000试探选择。
        self.assertEqual(struct.unpack('<h',m.u.mem_read(0x6bb5a0,2))[0],12000)
if __name__=='__main__':unittest.main(verbosity=2)
