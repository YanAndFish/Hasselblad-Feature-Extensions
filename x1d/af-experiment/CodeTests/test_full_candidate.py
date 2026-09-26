"""全程候选的原生ARM/Thumb执行、闭环运动替身与失败/取消验证。无USB。"""
import sys,json,struct,ctypes,unittest,math,random
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[1]
sys.path[:0]=[str(ROOT/"x1d/tools"),str(ROOT/".research-cache/x1d-1.25.0/python")]
from farm_diagnostic_binary import FarmApplication
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import *
BUILD=HERE/"build/full-owned"
M=json.loads((BUILD/"manifest.json").read_text(encoding="utf-8"));FARM=FarmApplication()
assert FARM.sha256==M["baseline_sha256"]
U32=ctypes.c_uint32;I32=ctypes.c_int32
class Trace(ctypes.LittleEndianStructure):
    _fields_=[("tick",U32),("phase",U32),("command",I32),("position",I32),("cv",U32)]
class State(ctypes.LittleEndianStructure):
    _fields_=[(n,U32) for n in "magic abi armed until generation phase reason calls reversals confirmations owned started leg_started seen waiting_reset skip samples up down".split()]
    _fields_ += [(n,I32) for n in "direction command origin last_position best_index".split()]
    _fields_ += [(n,U32) for n in "best_cv noise roi0 roi1 rate configured pending_error".split()]
    _fields_ += [(n,I32) for n in "fine_start fine_end coarse_peak target command_target".split()]
    _fields_ += [(n,U32) for n in "move_started reply_seen reply_status reply_tick corrections position_tolerance".split()]
    _fields_ += [("physical",I32)]
    _fields_ += [(n,U32) for n in "position_tick position_seq raw_cv raw_tick raw_seq verify_seq verify_points stopped_tick position_baseline blocked_commands send_returns trace_count trace_overflow".split()]
    _fields_ += [("positions",I32*64),("cvs",U32*64),("trace",Trace*12),("canary",U32)]
assert ctypes.sizeof(State)==M["stateBytes"]

class Case:
    def __init__(self,far=False,start=100,origin=0):
        self.u=Uc(UC_ARCH_ARM,UC_MODE_ARM);self.u.mem_map(0x100000,0x600000)
        self.u.mem_write(0x100000,FARM.data);self.u.mem_map(0x900000,0x10000)
        self.u.mem_write(M["base"],(BUILD/"candidate.bin").read_bytes())
        # 明确的ARM bx lr替身；实际执行返回指令，不依赖代码回调改PC跳过函数。
        for a in (0x1e80d0,0x236a14,0x19dd70,0x1a502c,0x1a5318,0x189e4c):
            self.u.mem_write(a,bytes.fromhex("1eff2fe1"))
        for a,old,new in M["hooks"]:assert FARM.word(a)==old;self.w(a,new)
        for a,old,new in M["speed_words"]:self.w(a,new)
        self.u.mem_write(0x2adc78,bytes((1 if far else 0,18,0,0)))
        self.u.mem_write(0x2adc8c,b"\0");self.addr=M["symbols"]["af_state"]
        self.w(self.addr+8,2);self.w(0x6badd0,start)
        self.sends=[];self.targets=[];self.results=[];self.disables=0;self.native_search=[]
        self.position=origin;self.time=start;self.accepted=[];self.move_target=None;self.move_sent_at=0
        self.wait_result=0;self.wait_timeout=None;self.resume=None;self.offset=0;self.tolerance=12
        self.u.hook_add(UC_HOOK_CODE,self.hook)
        self.run("af_reset_owned",0x19bbf0)
    def w(self,a,v):self.u.mem_write(a,struct.pack("<I",v&0xffffffff))
    def h(self,a,v):self.u.mem_write(a,struct.pack("<H",v&65535))
    def state(self):return State.from_buffer_copy(bytes(self.u.mem_read(self.addr,ctypes.sizeof(State))))
    def set(self,name,value):self.w(self.addr+getattr(State,name).offset,value)
    def return_value(self,u,value=0):u.reg_write(UC_ARM_REG_R0,value)
    def hook(self,u,a,size,_):
        if a==0x1e80d0:
            msg=bytes(u.mem_read(u.reg_read(UC_ARM_REG_R0),8));kind=struct.unpack_from("<H",msg)[0]
            if kind==0xcd:
                command=struct.unpack_from("<h",msg,4)[0];self.sends.append(command)
                if command:self.move_target=None
            elif kind==0xcf:
                self.move_target=struct.unpack_from("<h",msg,4)[0];self.targets.append(self.move_target);self.move_sent_at=self.time
            elif kind==0xae:self.disables+=1
            else:raise AssertionError("unexpected native packet "+hex(kind))
            self.return_value(u,1)
        elif a==0x236a14:self.return_value(u)
        elif a==0x19dd70:self.results.append(u.reg_read(UC_ARM_REG_R0));self.return_value(u)
        elif a==0x1a502c:self.return_value(u,self.offset)
        elif a==0x1a5318:self.return_value(u,self.tolerance)
        elif a==0x189e4c:
            self.wait_timeout=u.reg_read(UC_ARM_REG_R3)
            if self.wait_result:self.w(u.reg_read(UC_ARM_REG_R2),self.wait_result)
            self.return_value(u,int(bool(self.wait_result)))
        elif a in (0x19d198,0x19bb98,0x1a4954,0x1a1cdc,0x1a1a9c,0x1a0ec0,0x1a049c,0x1a06e8):
            self.resume=a;u.emu_stop()
        elif M["base"]<=a<M["end"] or a in {x[0] for x in M["hooks"]} or 0x1a0244<=a<0x1a0498 or 0x199ccc<=a<0x199d04:pass
        else:
            self.native_search.append(a);raise AssertionError("unexpected original code "+hex(a))
    def run(self,name,*args,lr=0x900000,dispatch=False):
        u=self.u;address=M["symbols"].get(name,name) if isinstance(name,str) else name
        u.reg_write(UC_ARM_REG_CPSR,0x1f);u.reg_write(UC_ARM_REG_C1_C0_2,0xf<<20);u.reg_write(UC_ARM_REG_FPEXC,1<<30)
        u.reg_write(UC_ARM_REG_SP,0x90fdf0);u.reg_write(UC_ARM_REG_LR,lr)
        for r,v in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),args):u.reg_write(r,v&0xffffffff)
        preserved=(UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11)
        for j,r in enumerate(preserved):u.reg_write(r,0x12345000+j)
        if dispatch:u.reg_write(UC_ARM_REG_R11,0x90ff00)
        self.resume=None;u.emu_start(address,lr,count=100000)
        if self.resume is None:
            assert u.reg_read(UC_ARM_REG_PC)==lr,(name,hex(u.reg_read(UC_ARM_REG_PC)))
            assert u.reg_read(UC_ARM_REG_SP)==0x90fdf0
            assert all(u.reg_read(r)==0x12345000+j for j,r in enumerate(preserved))
        assert self.state().canary==M["canary"]
        return u.reg_read(UC_ARM_REG_R0)
    def position_message(self,position):
        self.position=position;msg=bytearray(12);struct.pack_into("<h",msg,5,position)
        self.u.mem_write(0x900040,bytes(msg));self.run("af_observe_position",0x900040)
    def cv_message(self,cv):
        self.u.mem_write(0x900040,b"\xcc\x00\x01\x03"+struct.pack("<I",cv))
        self.run("af_observe_cv",0x900040)
    def reply(self,status=0):
        self.u.mem_write(0x900040,b"\xcf\x00\x01\x03"+bytes((status,0,0,0)))
        self.run("af_position_reply",0x900040)
    def start(self):
        self.position_message(self.position);self.u.mem_write(0x6bb46c,b"\x03")
        self.run("speed_entry",20000,lr=0x1a1f68)
    def event(self,mask=16,dispatch=False):
        addr=0x90ff00-0x94 if dispatch else 0x900020
        self.w(addr,mask)
        result=self.run("dispatch_entry",dispatch=True) if dispatch else self.run("af_event",addr)
        if dispatch:assert self.resume==0x19d198
        return result
    def feed(self,position,cv,dt=10,accepted=True,dispatch=True):
        self.time=(self.time+dt)&0xffffffff;self.w(0x6badd0,self.time)
        self.position_message(position);self.cv_message(cv)
        command=struct.unpack("<h",bytes(self.u.mem_read(0x6bb5a0,2)))[0]
        previous=struct.unpack("<h",bytes(self.u.mem_read(0x6bb5a2,2)))[0]
        if (command>0)!=(previous>0):self.accepted=[];self.h(0x6bc954,0);self.h(0x6bb5a2,command)
        if accepted and command:
            self.accepted.append((position,cv));n=len(self.accepted);assert n<=500
            self.h(0x6bc954,n);self.u.mem_write(0x6bbd9c,struct.pack("<"+"h"*n,*[p for p,_ in self.accepted]))
            self.u.mem_write(0x6bb5cc,struct.pack("<"+"I"*n,*[v for _,v in self.accepted]))
        return self.event() if dispatch else None
    def simulate(self,curve,steps=300,lag=0,intervals=(10,)):
        pending=[];acks=0
        for step in range(steps):
            dt=intervals[step%len(intervals)]
            state=self.state()
            if state.phase in (8,9):break
            command=state.command
            if self.move_target is not None:
                delta=self.move_target-self.position
                position=self.position+max(-6*dt,min(6*dt,delta))
            else:position=self.position+int(command*dt/1000)
            pending.append(curve(position));cv=pending[max(0,len(pending)-1-lag)]
            self.feed(position,max(1,round(cv)),dt=dt,accepted=command!=0)
            if self.move_target is not None and position==self.move_target and len(self.targets)>acks:
                acks=len(self.targets);self.reply()
        return self.state()

class NativeCompletionCase(Case):
    """执行原厂结果封包和元数据写入；RTOS、时钟、FPGA关闭及链路为固定替身。"""
    STUBS=(0x18a594,0x1f0b04,0x198568,0x15ada8,0x1f1094,0x1f10b8,0x15ae34,0x1efdcc,0x226974)
    def __init__(self,**kwargs):
        super().__init__(**kwargs);self.u.mem_write(0x19dd70,FARM.read(0x19dd70,4))
        for a in self.STUBS:self.u.mem_write(a,bytes.fromhex("1eff2fe1"))
        self.w(0x6bcb78,1);self.sync_stops=0;self.timer_cancels=0
    def hook(self,u,a,size,data):
        if a in self.STUBS:
            if a==0x1f0b04:self.sync_stops+=1
            elif a==0x18a594:
                assert u.reg_read(UC_ARM_REG_R1)==3;self.timer_cancels+=1
            elif a==0x1efdcc:self.w(u.reg_read(UC_ARM_REG_R0),0)
            elif a==0x226974:
                assert u.reg_read(UC_ARM_REG_R2)==0xb4
                u.mem_write(u.reg_read(UC_ARM_REG_R0),bytes(0xb4))
            self.return_value(u,0);u.reg_write(UC_ARM_REG_R1,0);return
        if a==0x1e80d0:
            msg=bytes(u.mem_read(u.reg_read(UC_ARM_REG_R0),8))
            if struct.unpack_from("<H",msg)[0]==0x2e9:
                assert msg[2:5]==b"\x01\x05\x00"
                self.results.append(msg[5]);self.return_value(u,1);return
        if 0x19dd70<=a<0x19e2a8 or 0x1a3f78<=a<0x1a42d0 or 0x19b960<=a<0x19bb94 or 0x1a9e2c<=a<0x1a9e80:return
        super().hook(u,a,size,data)

class FullTests(unittest.TestCase):
    def test_smooth_peak_both_initial_directions_and_wrong_initial_direction(self):
        for far in (False,True):
            for peak in (-150,150):
                c=Case(far);c.start();s=c.simulate(lambda p:10000*math.exp(-.5*((p-peak)/200)**2))
                self.assertEqual(s.phase,8,(far,peak,s.phase,s.reason,s.samples,s.noise,c.sends,c.targets))
                self.assertLessEqual(abs(s.target-peak),15);self.assertEqual(c.results,[0]);self.assertEqual(c.disables,1)
                self.assertEqual(c.sends[-1],0);self.assertFalse(c.native_search)
    def test_broad_gradual_peak(self):
        c=Case();c.start();s=c.simulate(lambda p:1000*math.exp(-.5*((p+200)/1000)**2))
        self.assertEqual(s.phase,8,(s.phase,s.reason,s.samples,s.noise,c.sends,c.targets))
        self.assertLessEqual(abs(s.target+200),60);self.assertEqual(c.results,[0])
    def test_flat_or_oscillating_contrast_stops_without_native_fallback(self):
        for curve in (lambda p:1000,lambda p:1000+(1 if (p//120)%2 else -1)):
            c=Case();c.start();s=c.simulate(curve)
            self.assertEqual(s.phase,9);self.assertEqual(c.results,[1]);self.assertEqual(c.sends[-1],0)
            self.assertFalse(c.native_search)
    def test_missing_first_position_and_pending_error_are_bounded(self):
        c=Case();c.u.mem_write(0x6bb46c,b"\x03");c.w(0x6badd0,c.time+500);c.event(0)
        self.assertEqual(c.state().reason,2);self.assertEqual(c.results,[1]);self.assertEqual(c.sends,[0])
        c=Case();c.u.mem_write(0x6bb46c,b"\x03");c.set("pending_error",1);c.event(0)
        self.assertEqual(c.state().reason,1);self.assertEqual(c.results,[1])
    def test_cancel_during_start_and_scan(self):
        for started in (False,True):
            c=Case()
            if started:c.start()
            c.u.mem_write(0x6bb46c,b"\x07");c.event(0)
            self.assertEqual(c.state().reason,12);self.assertEqual(c.state().phase,9);self.assertEqual(c.results,[])
    def test_profile_change_and_feedback_loss_stop(self):
        c=Case();c.start();c.w(0x2adc2c,5000);c.event()
        self.assertEqual(c.state().reason,1);self.assertEqual(c.sends[-1],0)
        c=Case();c.start();c.w(0x6badd0,c.time+100);c.event(0)
        self.assertEqual(c.state().reason,2);self.assertEqual(c.sends[-1],0)
    def test_foreign_motion_blocked_and_zero_allowed(self):
        c=Case();c.start();n=len(c.sends)
        c.run("speed_entry",-20000);c.run("position_entry",200)
        self.assertEqual(len(c.sends),n);self.assertEqual(c.targets,[])
        self.assertEqual(c.state().blocked_commands,2)
        c.run("speed_entry",0);self.assertEqual(c.sends[-1],0)
    def test_real_protocol_positive_negative_and_zero(self):
        c=Case();c.set("owned",0)
        for v in (20000,-20000,3000,-3000,0):c.run("speed_entry",v)
        self.assertEqual(c.sends,[20000,-20000,3000,-3000,0])
        c.run("position_entry",-1234);self.assertEqual(c.targets,[-1234])
    def test_tick_wait_preserves_cancel_and_uses_twenty(self):
        c=Case();c.start();c.w(0x900020,0xffffffff)
        self.assertEqual(c.run("af_wait",0,0xffffffff,0x900020,500),1)
        self.assertEqual(c.wait_timeout,20);self.assertEqual(bytes(c.u.mem_read(0x900020,4)),bytes(4))
        c.wait_result=0x20000;c.run("af_wait",0,0xffffffff,0x900020,500)
        self.assertEqual(struct.unpack("<I",bytes(c.u.mem_read(0x900020,4)))[0],0x20000)
    def test_dispatch_hook_skips_native_search(self):
        c=Case();c.start();c.event(0,dispatch=True);self.assertFalse(c.native_search)
    def test_boundary_and_lens_error_have_no_search_retry(self):
        c=Case();c.start();c.run("near_entry");c.event(0)
        self.assertEqual(c.state().reason,8);self.assertEqual(c.results,[1]);self.assertEqual(c.sends[-1],0)
        c=Case();c.start();c.event(0x100)
        self.assertEqual(c.state().reason,9);self.assertEqual(c.results,[1])
    def test_clock_wrap(self):
        c=Case(start=0xfffffff0);c.start();c.time=0x100;c.w(0x6badd0,c.time);c.position_message(0);c.event(0)
        self.assertEqual(c.state().reason,3)

    def test_old_direction_burst_is_not_consumed_after_reversal(self):
        c=Case();c.start()
        for i,cv in enumerate((1100,1000,950,900,850,800,750,700,650,600)):
            c.feed((i+1)*120,cv,dispatch=False)
        c.event();s=c.state()
        self.assertEqual(s.reversals,1);self.assertEqual(s.samples,0)
        self.assertEqual(s.phase,3);self.assertEqual(s.command,-20000)
        c.event();self.assertEqual(c.state().samples,0)
        c.feed(1080,650);c.feed(960,700)
        self.assertEqual(c.state().samples,1);self.assertEqual(c.state().positions[0],960)

    def test_no_new_samples_and_duplicate_positions_are_bounded(self):
        for duplicate in (False,True):
            c=Case();c.start()
            for i in range(26):
                if c.state().phase==9:break
                c.feed(0,1000+i,accepted=duplicate)
            self.assertEqual(c.state().phase,9);self.assertEqual(c.state().reason,3)
            self.assertEqual(c.results,[1]);self.assertEqual(c.sends[-1],0)

    def test_changed_roi_rate_bad_count_and_range_reject(self):
        for address,value in ((0x6cc59c,1),(0x6cc5a0,1),(0x6bcb44,1)):
            c=Case();c.start();c.feed(120,1000);c.feed(240,1100)
            c.w(address,value);c.feed(360,1200)
            self.assertEqual(c.state().reason,1);self.assertEqual(c.sends[-1],0)
        c=Case();c.start();c.feed(120,1000);c.h(0x6bc954,501);c.event()
        self.assertEqual(c.state().reason,7)
        c=Case();c.start();c.feed(8200,1000);self.assertEqual(c.state().reason,4)
        for cv in (0,0x20000000,0xffffffff):
            c=Case();c.start();c.feed(120,1000);c.feed(240,cv)
            self.assertEqual(c.state().reason,6);self.assertEqual(c.results,[1])

    def test_consecutive_af_cycles_and_negative_calibration(self):
        c=Case(origin=-2000);c.offset=-7
        for generation,peak in ((1,-1700),(2,-1900)):
            if generation==2:
                c.event(0);self.assertEqual(c.state().owned,0)
                c.u.mem_write(0x6bb46c,b"\x00");c.h(0x6bc954,0);c.accepted=[]
                c.run("af_reset_owned",0x19bbf0);c.move_target=None
            c.start();s=c.simulate(lambda p:10000*math.exp(-.5*((p-peak)/200)**2))
            self.assertEqual(s.phase,8,(generation,s.reason,c.targets))
            self.assertEqual(s.generation,generation);self.assertLessEqual(abs(s.target-(peak-7)),15)
        self.assertEqual(c.results,[0,0]);self.assertFalse(c.native_search)

    def test_inactive_entry_replays_original_prologues(self):
        c=Case();c.set("armed",0);c.run("af_reset_owned",0x19bbf0)
        for entry,resume,stack_words in (("reset_entry",0x1a4954,2),("position_observer_entry",0x1a1cdc,3),
                ("cv_observer_entry",0x1a1a9c,2),("position_reply_entry",0x1a0ec0,4),
                ("near_entry",0x1a049c,2),("far_entry",0x1a06e8,2)):
            c.run(entry,0x900040)
            self.assertEqual(c.resume,resume);self.assertEqual(c.u.reg_read(UC_ARM_REG_SP),0x90fdf0-stack_words*4)
            self.assertEqual(c.u.reg_read(UC_ARM_REG_R0),0x900040)
        c.run("dispatch_entry",dispatch=True);self.assertEqual(c.resume,0x19bb98)
        self.assertEqual(c.u.reg_read(UC_ARM_REG_R3),0xb46c)
        c.run("af_wait",0,0xffffffff,0x900020,500);self.assertEqual(c.wait_timeout,500)

    def test_missing_position_reply_does_not_claim_focus(self):
        c=Case();c.start()
        for i in range(240):
            s=c.state()
            if s.phase==9:break
            p=c.move_target if c.move_target is not None else c.position+int(s.command/100)
            c.feed(p,max(1,round(10000*math.exp(-.5*((p-150)/200)**2))))
        self.assertEqual(c.state().phase,9);self.assertEqual(c.results,[1]);self.assertEqual(c.sends[-1],0)

    def test_irregular_intervals_have_bounded_outcome(self):
        outcomes={"success":0,"failure":0}
        for intervals in ((10,),(6,14),(5,5,20),(8,12,9,11)):
            for sigma in (200,500,1000):
                for far in (False,True):
                    for peak in (-150,300):
                        c=Case(far);c.start();s=c.simulate(lambda p:10000*math.exp(-.5*((p-peak)/sigma)**2),intervals=intervals)
                        self.assertIn(s.phase,(8,9));self.assertEqual(c.sends[-1],0);self.assertFalse(c.native_search)
                        self.assertLessEqual((c.time-s.started)&0xffffffff,2420)
                        if s.phase==8:
                            self.assertLessEqual(abs(s.target-peak),max(15,sigma/10),(intervals,sigma,far,peak,s.target))
                            outcomes["success"]+=1
                        else:outcomes["failure"]+=1
        self.assertGreater(outcomes["success"],0)
        print("irregular interval model outcomes",outcomes)

    def test_noise_does_not_report_a_false_peak(self):
        for amplitude in (1,20,100,200):
            for seed in range(24):
                rng=random.Random(seed);c=Case();c.start()
                s=c.simulate(lambda p:1000+rng.randint(-amplitude,amplitude))
                self.assertEqual(s.phase,9,(amplitude,seed,s.target,s.best_cv,s.noise));self.assertEqual(c.results,[1])

    def test_smooth_peak_with_small_sensor_noise(self):
        for seed in range(12):
            rng=random.Random(seed);c=Case();c.start()
            s=c.simulate(lambda p:10000*math.exp(-.5*((p+150)/200)**2)+rng.randint(-10,10))
            self.assertEqual(s.phase,8,(seed,s.reason));self.assertLessEqual(abs(s.target+150),15)

    def test_original_result_packet_and_normal_cancel_path(self):
        for curve,expected in ((lambda p:10000*math.exp(-.5*((p+150)/200)**2),0),(lambda p:1000,1)):
            c=NativeCompletionCase();c.start();c.simulate(curve)
            self.assertEqual(c.results,[expected]);self.assertEqual(c.disables,1)
            self.assertEqual(c.timer_cancels,1);self.assertEqual(c.sync_stops,1);self.assertFalse(c.native_search)
        c=NativeCompletionCase();c.start();c.w(0x90ff00-0x94,0x20000)
        c.run(0x19b960,dispatch=True)
        self.assertEqual(c.results,[5]);self.assertEqual(c.disables,1)
        self.assertEqual(c.state().owned,0);self.assertEqual(c.state().reason,12)

    def test_user_image_proxy_curves_including_weak_initial_signal(self):
        fixture=json.loads((HERE/"CodeTests/Fixtures/SyntheticAfCurves.json").read_text(encoding="utf-8"))
        tested=0
        for item in fixture["curves"]:
            for units in (50,100,200):
                for peak in (-300,300):
                    for far in (False,True):
                        def curve(p):
                            x=abs(p-peak)/units*4;values=item["values"]
                            i=min(int(x),len(values)-1)
                            value=values[i] if i==len(values)-1 else values[i]+(values[i+1]-values[i])*(x-i)
                            return max(1,round(value*fixture["cvScale"]))
                        c=Case(far);c.start();s=c.simulate(curve)
                        self.assertEqual(s.phase,8,(item["scene"],item["roi"],item["metric"],units,peak,far,s.reason))
                        self.assertLessEqual(abs(s.target-peak),max(15,units*.25))
                        self.assertLessEqual(s.reversals,1);self.assertEqual(c.sends[-1],0);self.assertFalse(c.native_search)
                        tested+=1
        self.assertEqual(tested,96);print("user image proxy closed-loop cases",tested)

if __name__=="__main__":unittest.main()
