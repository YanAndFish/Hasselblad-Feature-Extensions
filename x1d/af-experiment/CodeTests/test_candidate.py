"""编译后ARM候选的离线行为/ABI测试；原厂电机封包运行于Unicorn，传输为替身。"""
import sys,json,struct,ctypes,unittest,os
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[1]
sys.path[:0]=[str(ROOT/"x1d/tools"),str(ROOT/".research-cache/x1d-1.25.0/python")]
from farm_diagnostic_binary import FarmApplication
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import *
BUILD=Path(os.environ.get("AF_TEST_BUILD",str(HERE/"build"))).resolve()
assert BUILD.is_relative_to((HERE/"build").resolve())
M=json.loads((BUILD/"manifest.json").read_text())
SPEED=M["speed_words"][0][2]
FARM=FarmApplication()
assert FARM.sha256==M["baseline_sha256"]
class Trace(ctypes.LittleEndianStructure):
    _fields_=[("tick",ctypes.c_uint32),("cmd",ctypes.c_int32),("measured",ctypes.c_int32),("returned",ctypes.c_uint32)]
class State(ctypes.LittleEndianStructure):
    _fields_=[(n,ctypes.c_uint32) for n in "magic abi armed until generation phase reason calls reversals confirmations started physical_set seen waiting_reset".split()]
    _fields_ += [(n,ctypes.c_int32) for n in "direction out_speed first_physical anchor_pos turn_pos step".split()]
    _fields_ += [(n,ctypes.c_uint32) for n in "anchor_cv turn_cv noise points return_points return_previous".split()]
    _fields_ += [("last_pos",ctypes.c_int32),("cv",ctypes.c_uint32*5),("meta",ctypes.c_uint32*12),("trace_count",ctypes.c_uint32),("trace_overflow",ctypes.c_uint32),("trace",Trace*24),("canary",ctypes.c_uint32)]
assert ctypes.sizeof(State)==572
class Case:
    def __init__(self,direction=1,start=100):
        self.u=Uc(UC_ARCH_ARM,UC_MODE_ARM);self.u.mem_map(0x100000,0x600000);self.u.mem_write(0x100000,FARM.data)
        self.u.mem_map(0x900000,0x10000);self.u.mem_write(M["base"],(BUILD/"candidate.bin").read_bytes())
        for a,old,new in M["hooks"]:assert FARM.word(a)==old;self.w(a,new)
        for a,old,new in M["speed_words"]:self.w(a,new)
        self.u.mem_write(0x2adc79,b"\x12");self.u.mem_write(0x2adc8c,b"\0")
        self.addr=M["symbols"]["af_state"];self.sends=[];self.events=[];self.original=None
        self.w(0x6badd0,start);self.w(self.addr+State.armed.offset,1);self.w(self.addr+State.until.offset,(start+30000)&0xffffffff)
        self.u.hook_add(UC_HOOK_CODE,self.hook)
        self.run("af_reset",0x19bbf0)
        self.u.mem_write(0x6bb46c,b"\x03")
        self.u.mem_write(0x6bb5a0,struct.pack("<hh",direction*SPEED,direction*SPEED))
    def w(self,a,v):self.u.mem_write(a,struct.pack("<I",v&0xffffffff))
    def state(self):return State.from_buffer_copy(bytes(self.u.mem_read(self.addr,ctypes.sizeof(State))))
    def hook(self,u,a,size,_):
        if a==0x1e80d0:
            msg=bytes(u.mem_read(u.reg_read(UC_ARM_REG_R0),6))
            assert msg[:4]==bytes.fromhex("cd000103")
            self.sends.append(struct.unpack_from("<h",msg,4)[0]);u.reg_write(UC_ARM_REG_R0,1);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
        elif a==0x236a14:u.reg_write(UC_ARM_REG_R0,0);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
        elif a==0x1a4890:self.events.append(u.reg_read(UC_ARM_REG_R0));u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
        elif a in (0x19d1a0,0x1a4954):self.original=a;u.emu_stop()
        elif not(M["base"]<=a<M["end"] or 0x1a0240<=a<0x1a0378):raise AssertionError("unexpected ARM pc "+hex(a))
    def run(self,name,arg=0,lr=0x900000):
        self.u.reg_write(UC_ARM_REG_CPSR,0x1f);self.u.reg_write(UC_ARM_REG_SP,0x90fff0);self.u.reg_write(UC_ARM_REG_LR,lr);self.u.reg_write(UC_ARM_REG_R0,arg)
        regs=(UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11)
        for j,r in enumerate(regs):self.u.reg_write(r,0x12345000+j)
        self.original=None;self.u.emu_start(M["symbols"][name] if isinstance(name,str) else name,0x900000,count=30000)
        if self.original is None:
            assert self.u.reg_read(UC_ARM_REG_PC)==0x900000
            assert self.u.reg_read(UC_ARM_REG_SP)==0x90fff0
            assert all(self.u.reg_read(r)==0x12345000+j for j,r in enumerate(regs))
        assert self.state().canary==0x52463541
        return self.u.reg_read(UC_ARM_REG_R0)
    def feed(self,cvs,positions,t,old=None):
        assert len(cvs)==len(positions)
        self.u.mem_write(0x6bc954,struct.pack("<H",len(cvs)))
        if cvs:
            self.u.mem_write(0x6bb5cc,struct.pack("<"+"I"*len(cvs),*cvs))
            self.u.mem_write(0x6bbd9c,struct.pack("<"+"h"*len(positions),*positions))
            self.u.mem_write(0x6bb5b4,struct.pack("<h",positions[-1]))
        if old is not None:self.u.mem_write(0x6bb5a2,struct.pack("<h",old))
        self.w(0x6badd0,t);return self.run("af_decide")
class NativeTests(unittest.TestCase):
    def outbound(self,sgn=1):
        c=Case(sgn);seq=[1000,995,980,955,920]
        for n in range(1,6):c.feed(seq[:n],[sgn*x for x in range(n)],100+n*10)
        self.assertEqual(c.sends,[-sgn*SPEED]);self.assertEqual(c.events,[])
        self.assertEqual(c.state().phase,2);return c
    def test_both_directions_and_return_confirmation(self):
        for sgn in (-1,1):
            c=self.outbound(sgn)
            for n in range(1,4):c.feed([955,980,995][:n],[sgn*x for x in [3,2,1]][:n],160+n*10,old=-sgn*SPEED)
            self.assertEqual(c.events,[32]);self.assertEqual(c.state().confirmations,1)
            self.assertEqual(c.state().reversals,1);self.assertEqual(c.state().trace[0].returned,1)
            self.assertEqual(bytes(c.u.mem_read(0x6bb59c,2)),b"\x01\0" if sgn<0 else b"\0\x01")
    def test_five_points_required_and_linear_decline(self):
        c=Case()
        for n in range(1,6):
            c.feed([1000-10*i for i in range(n)],list(range(n)),100+n*10)
            self.assertEqual(len(c.sends),int(n==5))
    def test_later_evidence_within_same_travel_budget(self):
        c=Case();seq=[1000,1000,999,995,990,980,965,945]
        for n in range(1,9):
            c.feed(seq[:n],list(range(n)),100+n*10)
            self.assertEqual(len(c.sends),int(n==8))
    def test_single_outlier_and_rising_preserve_original(self):
        for seq in ([1000,1001,999,1000,600],[700,710,730,750,800]):
            c=Case()
            for n in range(1,6):self.assertEqual(c.feed(seq[:n],list(range(n)),100+n*10),0)
            self.assertEqual(c.sends,[]);self.assertEqual(c.events,[])
    def test_invalid_samples_keep_time_budget(self):
        c=Case();c.feed([],[],100);self.assertEqual(c.feed([],[],350),0);self.assertEqual(c.state().reason,6)
    def test_metadata_change_cancels(self):
        c=self.outbound();c.w(0x2b1da4,123);self.assertEqual(c.feed([955],[3],170,old=-SPEED),0);self.assertEqual(c.events,[])
    def test_old_direction_samples_do_not_confirm(self):
        c=self.outbound();c.feed([955,980,995],[5,6,7],180,old=-SPEED)
        self.assertEqual(c.events,[]);self.assertEqual(c.state().return_points,0)
    def test_waiting_for_direction_reset_is_bounded(self):
        c=self.outbound();c.feed([1000,995,980,955,920],list(range(5)),399)
        self.assertEqual(c.state().phase,2)
        self.assertEqual(c.feed([],[],400),0);self.assertEqual(c.state().reason,6)
    def test_wraparound_budget(self):
        c=Case(start=0xffffff80);c.feed([],[],0xfffffff0);self.assertEqual(c.feed([],[],0x100),0)
        self.assertEqual(c.state().reason,6)
    def test_internal_reset_does_not_rearm(self):
        c=self.outbound();c.run("af_reset",0x199ef4);self.assertEqual(c.state().phase,0)
    def test_retained_trial_still_has_per_af_budget(self):
        c=Case();c.w(c.addr+State.armed.offset,2)
        c.feed([1000],[0],40000)
        self.assertEqual(c.state().phase,1)
        c.feed([1000],[0],40250)
        self.assertEqual(c.state().reason,6)
        c.run(0x1a0240,SPEED);self.assertEqual(c.state().trace_count,1)
        c.w(c.addr+State.armed.offset,0);c.run("af_reset",0x19bbf0)
        self.assertEqual(c.state().phase,0)
    def test_bad_count_and_cv_overflow(self):
        c=Case();c.u.mem_write(0x6bc954,struct.pack("<H",501));c.run("af_decide");self.assertEqual(c.state().reason,3)
        c=Case();c.feed([0xffffffff],[0],110);self.assertEqual(c.state().reason,10)
    def test_speed_profile_required(self):
        c=Case();c.w(0x2adc2c,5000);self.assertEqual(c.feed([1000],[0],110),0);self.assertEqual(c.state().reason,2)
    def test_each_inconsistent_speed_word_disables_candidate(self):
        for address,_,_ in M["speed_words"]:
            c=Case();c.w(address,SPEED//2)
            self.assertEqual(c.feed([1000],[0],110),0)
            self.assertEqual(c.state().reason,2);self.assertEqual(c.sends,[])
    def test_stock_entry_abi_when_unarmed(self):
        c=Case();c.w(c.addr+State.armed.offset,0)
        c.run("state3_entry");self.assertEqual(c.original,0x19d1a0);self.assertEqual(c.u.reg_read(UC_ARM_REG_SP),0x90fff0-12)
        c.run("reset_entry",lr=0x19bbf0);self.assertEqual(c.original,0x1a4954);self.assertEqual(c.u.reg_read(UC_ARM_REG_SP),0x90fff0-8)
    def test_target_negative_relative_reduction_and_stop_wire_values(self):
        c=Case()
        for v in (SPEED,-SPEED,SPEED//2,-SPEED//2,0):c.run(0x1a0240,v)
        self.assertEqual(c.sends,[SPEED,-SPEED,SPEED//2,-SPEED//2,0])
        self.assertEqual([c.state().trace[i].cmd for i in range(5)],c.sends)
if __name__=="__main__":unittest.main()
