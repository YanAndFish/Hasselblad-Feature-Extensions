"""执行编译后的 ARM 辅助与固定原厂判向/越峰函数；链路和日志为替身，无 USB。"""
import ctypes as C
import hashlib,json,math,random,struct,sys,time,unittest
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[1]
assert Path.cwd().resolve()==ROOT.resolve()
sys.path[:0]=[str(ROOT/'x1d/tools'),str(ROOT/'.research-cache/x1d-1.25.0/python')]
from farm_diagnostic_binary import FarmApplication
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import *
THUMB='--thumb' in sys.argv
if THUMB:sys.argv.remove('--thumb')
CAPTURE='--capture' in sys.argv
if CAPTURE:sys.argv.remove('--capture')
BUILD=HERE/('build/native-capture-r1/00800000' if CAPTURE else ('build/native-camera-r1' if THUMB else 'build/native-af-r1'))
PAYLOAD=BUILD/('candidate.bin' if THUMB or CAPTURE else 'offline.bin')
M=json.loads((BUILD/('capture-manifest.json' if CAPTURE else ('layout-manifest.json' if THUMB else 'offline-manifest.json'))).read_text(encoding='utf-8'))
FARM=FarmApplication();assert FARM.sha256==M['baseline_sha256']
assert hashlib.sha256(PAYLOAD.read_bytes()).hexdigest()==M['payload_sha256']
for p,h in M['source_sha256'].items():assert hashlib.sha256((HERE/p).read_bytes()).hexdigest()==h
U=C.c_uint32;I=C.c_int32;F=C.c_float
class Sample(C.LittleEndianStructure):
    _fields_=[('position',I)]+[(n,U) for n in 'cv sample_tick receive_tick frame_id generation flags native_count secondary_cv'.split()]
class Timing(C.LittleEndianStructure):
    _fields_=[(n,U) for n in 'now processing_ticks command_ticks calibrated'.split()]+[('braking_per_tick2',F)]
    _fields_ += [('command_in_flight',U),('commanded_velocity_bound',F),('command_sequence',U)]
class Result(C.LittleEndianStructure):
    _fields_=[(n,U) for n in 'direction_valid prediction_valid reason used prediction_kind'.split()]
    _fields_ += [(n,F) for n in 'direction_metric velocity_per_tick frame_ticks age_ticks residual peak_position peak_distance lead_distance required_distance safe_speed_ratio position_step prediction_velocity_per_tick'.split()]
class Adapter(C.LittleEndianStructure):
    _fields_=[(n,U) for n in 'generation count allow_actuation previous_valid last_slow_count previous_count config_status'.split()]
    _fields_ += [('previous_kind',U),('command_sequence',U),('last_command',I)]
    _fields_ += [('previous_peak',F),('timing',Timing),('samples',Sample*5),('result',Result)]
class Config(C.LittleEndianStructure):
    _fields_=[(n,U) for n in 'magic abi lens revision probe fast fine flags checksum'.split()]
class Bank(C.LittleEndianStructure):
    _fields_=[('sequence',U),('generation',U),('pending',Config),('active',Config)]
def config(revision=2,probe=0,fast=0,fine=0,new=True):
    c=Config(0x31435441,1,75,revision,probe,fast,fine,int(new),0);h=2166136261
    for b in bytes(c)[:32]:h=((h^b)*16777619)&0xffffffff
    c.checksum=h;return c

def samples(positions=(0,20,40,60,80),ticks=None,curve=None,delay=4,generation=1):
    if ticks is None:ticks=[100+10*i for i in range(len(positions))]
    if curve is None:curve=lambda p:20000-(p-120)**2
    return [Sample(p,max(1,round(curve(p))),t&0xffffffff,(t+delay)&0xffffffff,i+1,generation,7,i+1) for i,(p,t) in enumerate(zip(positions,ticks))]

class Case:
    def __init__(self,patched=True):
        self.u=Uc(UC_ARCH_ARM,UC_MODE_ARM);self.u.mem_map(0x100000,0x600000)
        self.u.mem_write(0x100000,FARM.data);self.u.mem_map(0x800000,0x10000);self.u.mem_map(0x900000,0x10000)
        self.u.mem_write(M['base'],PAYLOAD.read_bytes())
        if patched:
            for a,old,new in M['emulatorOnlyHooks']:assert FARM.word(a)==old;self.w(a,new)
        # 原厂 helper、state3、state4、速度封包实际执行；外部链路/日志/event queue 用 bx lr 替身。
        self.stubs={0x1e80d0,0x236a14,0x1a4890,0x199b50,0x1a9e9c,0x198778}
        for a in self.stubs:self.u.mem_write(a,bytes.fromhex('1eff2fe1'))
        self.u.hook_add(UC_HOOK_CODE,self.hook);self.sends=[];self.events=[];self.visited=set()
        self.addr=M['symbols']['na_adapter'];self.w(0x6bcb7c,1);self.w(0x2ad9a8,500)
        self.run('na_config_reset');self.publish(config())
        self.run('na_begin',1)
    def w(self,a,v):self.u.mem_write(a,struct.pack('<I',v&0xffffffff))
    def h(self,a,v):self.u.mem_write(a,struct.pack('<H',v&65535))
    def byte(self,a,v):self.u.mem_write(a,bytes((v,)))
    def state(self):return Adapter.from_buffer_copy(bytes(self.u.mem_read(self.addr,C.sizeof(Adapter))))
    def bank(self):return Bank.from_buffer_copy(bytes(self.u.mem_read(M['symbols']['na_config_bank'],C.sizeof(Bank))))
    def publish(self,c):
        self.u.mem_write(0x904000,bytes(c));return self.run('na_config_publish',0x904000)
    def hook(self,u,a,size,_):
        if not(0x100000<=a<0x700000 or M['base']<=a<M['end']):raise AssertionError('unexpected pc '+hex(a))
        self.visited.add(a)
        if a==0x1e80d0:
            msg=bytes(u.mem_read(u.reg_read(UC_ARM_REG_R0),6));assert msg[:4]==bytes.fromhex('cd000103')
            self.sends.append(struct.unpack_from('<h',msg,4)[0]);u.reg_write(UC_ARM_REG_R0,1)
        elif a==0x236a14:u.reg_write(UC_ARM_REG_R0,0)
        elif a==0x1a4890:self.events.append(u.reg_read(UC_ARM_REG_R0));u.reg_write(UC_ARM_REG_R0,0)
        elif a==0x199b50:u.reg_write(UC_ARM_REG_R0,50)
        elif a in (0x1a9e9c,0x198778):u.reg_write(UC_ARM_REG_R0,0)
    def run(self,address,*args):
        u=self.u;address=M['symbols'].get(address,address)
        u.reg_write(UC_ARM_REG_CPSR,0x1f);u.reg_write(UC_ARM_REG_C1_C0_2,0xf<<20);u.reg_write(UC_ARM_REG_FPEXC,1<<30)
        u.reg_write(UC_ARM_REG_SP,0x90fdf0);u.reg_write(UC_ARM_REG_LR,0x900000)
        preserved=[UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11]
        for j,r in enumerate(preserved):u.reg_write(r,0x12345000+j)
        for j in range(8,16):u.reg_write(globals()['UC_ARM_REG_D'+str(j)],0x0123456700000000+j)
        for r,v in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),args):u.reg_write(r,v&0xffffffff)
        u.emu_start(address,0x900000,count=250000)
        assert u.reg_read(UC_ARM_REG_PC)==0x900000,hex(u.reg_read(UC_ARM_REG_PC))
        assert u.reg_read(UC_ARM_REG_SP)==0x90fdf0
        assert all(u.reg_read(r)==0x12345000+j for j,r in enumerate(preserved))
        assert all(u.reg_read(globals()['UC_ARM_REG_D'+str(j)])==0x0123456700000000+j for j in range(8,16))
        return u.reg_read(UC_ARM_REG_R0)
    def core(self,ss,timing=None):
        if timing is None:timing=Timing(ss[-1].receive_tick,2,2,1,0.2)
        self.u.mem_write(0x901000,bytes((Sample*len(ss))(*ss)));self.u.mem_write(0x902000,bytes(timing))
        self.run('na_assess',0x901000,len(ss),0x902000,0x903000)
        return Result.from_buffer_copy(bytes(self.u.mem_read(0x903000,C.sizeof(Result))))
    def native(self,ss,phase=3,command=2000,supply=True,actuate=False):
        self.byte(0x6bb46c,phase);self.h(0x6bc954,len(ss));self.h(0x6bb5a0,command);self.h(0x6bb5a2,command)
        self.w(0x6bb5bc,min(s.cv for s in ss));self.w(0x6badd0,ss[-1].receive_tick)
        self.u.mem_write(0x6bb5cc,struct.pack('<'+'I'*len(ss),*[s.cv for s in ss]))
        self.u.mem_write(0x6bbd9c,struct.pack('<'+'h'*len(ss),*[s.position for s in ss]))
        if supply:
            for s in ss:self.u.mem_write(0x901000,bytes(s));self.run('na_supply',0x901000)
        self.u.mem_write(self.addr+Adapter.timing.offset,bytes(Timing(ss[-1].receive_tick,2,2,1,0.2)))
        self.w(self.addr+Adapter.allow_actuation.offset,int(actuate))
    def metric(self):
        v=self.run('na_direction',0x902000)
        return struct.unpack('<f',struct.pack('<I',v))[0]

class CoreTests(unittest.TestCase):
    def test_auxiliary_small_quantization_does_not_hide_strong_primary_trend(self):
        c=Case()
        for sign in (-1,1):
            for aux in ([2000,1996,2300],[2000,2300,2296],[2000,2000,2300]):
                ss=samples((0,20,40))
                for i,s in enumerate(ss):
                    s.flags=15;s.cv=2000+sign*300*i;s.secondary_cv=3000+sign*(aux[i]-2000)
                r=c.core(ss);self.assertTrue(r.direction_valid)
                self.assertGreater(sign*r.direction_metric,0)
    def test_auxiliary_real_reversal_or_weak_evidence_still_abstains(self):
        c=Case()
        for primary,aux in [([1000,1300,1600],[2000,1900,2300]),
                            ([1000,1300,1600],[2000,2300,2200]),
                            ([1000,1300,1600],[2000,2001,2002]),
                            ([1000,1001,1600],[2000,2000,2600]),
                            ([1000,1400,1300],[2000,2000,2600])]:
            for sign in (-1,1):
                ss=samples((0,20,40))
                for s,p,a in zip(ss,primary,aux):
                    s.flags=15;s.cv=3000+sign*(p-1000);s.secondary_cv=4000+sign*(a-2000)
                self.assertFalse(c.core(ss).direction_valid)
    def test_three_frames_need_correlated_secondary_agreement(self):
        c=Case();ss=samples((0,20,40),curve=lambda p:1000+15*p)
        self.assertFalse(c.core(ss).direction_valid)
        for s in ss:s.flags=15;s.secondary_cv=2*s.cv
        self.assertTrue(c.core(ss).direction_valid)
        ss[2].secondary_cv=500;self.assertFalse(c.core(ss).direction_valid)
    def test_secondary_disagreement_and_spike_are_not_a_direction(self):
        c=Case()
        for values in ([1000,1001,4000],[1000,600,1400],[1000,1300,1600]):
            ss=samples((0,20,40))
            for s,v,aux in zip(ss,values,[2000,1600,1200]):s.cv=v;s.flags=15;s.secondary_cv=aux
            self.assertFalse(c.core(ss).direction_valid)
    def test_curve_predicts_known_peak_and_measured_speed(self):
        c=Case();r=c.core(samples())
        self.assertTrue(r.prediction_valid);self.assertAlmostEqual(r.peak_position,120,delta=.02)
        self.assertAlmostEqual(r.velocity_per_tick,2,places=4);self.assertEqual(r.frame_ticks,10)
        self.assertAlmostEqual(r.required_distance,66,places=3)
        self.assertGreater(r.safe_speed_ratio,0);self.assertLess(r.safe_speed_ratio,1)
    def test_actual_velocity_changes_anticipation(self):
        c=Case();rows=samples();slow=c.core(rows)
        fast=c.core(samples(ticks=[100,105,110,115,120]))
        self.assertAlmostEqual(fast.velocity_per_tick,2*slow.velocity_per_tick,places=3)
        self.assertGreater(fast.required_distance,slow.required_distance)
        self.assertLess(fast.safe_speed_ratio,slow.safe_speed_ratio)
    def test_feedback_age_processing_and_command_budget_each_count(self):
        c=Case();ss=samples();base=c.core(ss)
        for t in [Timing(148,2,2,1,.2),Timing(144,6,2,1,.2),Timing(144,2,6,1,.2)]:
            r=c.core(ss,t);self.assertTrue(r.prediction_valid)
            self.assertAlmostEqual(r.required_distance-base.required_distance,8,delta=.001)
        # 相同速度、相同曲线，不同反馈间隔会改变预判距离。
        a=c.core(samples((20,30,40,50,60),[100,105,110,115,120]))
        b=c.core(samples((20,40,60,80,100),[100,110,120,130,140]))
        self.assertAlmostEqual(a.velocity_per_tick,b.velocity_per_tick,places=4)
        self.assertGreater(b.required_distance,a.required_distance)
    def test_mirrored_motion_and_peak(self):
        c=Case();r=c.core(samples(tuple(-20*i for i in range(5)),curve=lambda p:20000-(p+120)**2))
        self.assertTrue(r.prediction_valid);self.assertAlmostEqual(r.peak_position,-120,delta=.02)
        self.assertLess(r.velocity_per_tick,0);self.assertLess(r.direction_metric,0)
    def test_first_three_wait_four_direction_five_prediction(self):
        c=Case();ss=samples()
        self.assertFalse(c.core(ss[:3]).direction_valid)
        self.assertTrue(c.core(ss[:4]).direction_valid)
        self.assertEqual(c.core(ss[:4]).prediction_kind,1)
        self.assertTrue(c.core(ss).prediction_valid)
    def test_flat_noise_and_single_outlier_do_not_predict(self):
        c=Case()
        for cvs in ([1000]*5,[1000,1001,999,1000,1001],[1000,1001,999,1000,1600]):
            ss=samples()
            for s,v in zip(ss,cvs):s.cv=v
            r=c.core(ss);self.assertFalse(r.prediction_valid);self.assertFalse(r.direction_valid)
    def test_monotonic_convex_curve_direction_does_not_use_extrapolated_derivative(self):
        c=Case();ss=samples((0,20,40),curve=lambda p:1000/(1+p/20))
        for s in ss:s.flags=15;s.secondary_cv=s.cv*2
        self.assertTrue(c.core(ss).direction_valid);self.assertLess(c.core(ss).direction_metric,0)
    def test_pending_fast_command_uses_future_velocity_bound(self):
        c=Case();ss=samples();base=c.core(ss)
        fast=c.core(ss,Timing(144,2,20,1,.2,1,8,9))
        self.assertTrue(fast.prediction_valid);self.assertEqual(fast.prediction_velocity_per_tick,8)
        self.assertGreater(fast.required_distance,base.required_distance)
        self.assertLess(fast.safe_speed_ratio,base.safe_speed_ratio)
        self.assertFalse(c.core(ss,Timing(144,2,20,1,.2,1,0,9)).prediction_valid)
    def test_invalid_alignment_clock_and_motion_rejected(self):
        c=Case()
        mutations=[lambda s:setattr(s[2],'flags',1),lambda s:setattr(s[2],'generation',2),
                   lambda s:setattr(s[2],'frame_id',9),lambda s:setattr(s[2],'native_count',10),
                   lambda s:setattr(s[2],'sample_tick',s[1].sample_tick),lambda s:setattr(s[2],'receive_tick',0),
                   lambda s:setattr(s[2],'position',s[1].position),lambda s:setattr(s[2],'position',-50),
                   lambda s:setattr(s[2],'position',2147483647),lambda s:setattr(s[2],'cv',0)]
        for f in mutations:
            ss=samples();f(ss);r=c.core(ss)
            self.assertFalse(r.prediction_valid);self.assertFalse(r.direction_valid)
    def test_wrap_and_irregular_intervals(self):
        c=Case();r=c.core(samples(ticks=[0xffffffe0,0xffffffea,0xfffffff4,0xfffffffe,8]))
        self.assertTrue(r.prediction_valid);self.assertAlmostEqual(r.peak_position,120,delta=.02)
        ss=samples((0,16,40,58,80),[100,108,120,129,140]);r=c.core(ss)
        self.assertTrue(r.prediction_valid);self.assertAlmostEqual(r.velocity_per_tick,2,places=4)
    def test_uncalibrated_stale_and_accelerating_no_actuation(self):
        c=Case();ss=samples()
        for t in [Timing(144,2,2,0,.2),Timing(144,2,2,1,0),Timing(144,2,2,1,float('nan')),Timing(200,2,2,1,.2)]:
            self.assertFalse(c.core(ss,t).prediction_valid)
        self.assertFalse(c.core(samples((0,20,40,60,80),[100,110,120,130,132])).prediction_valid)
    def test_scale_and_position_translation_do_not_change_ratio(self):
        c=Case();a=c.core(samples());b=c.core(samples(tuple(1000+20*i for i in range(5)),curve=lambda p:10*(20000-(p-1120)**2)))
        self.assertAlmostEqual(a.safe_speed_ratio,b.safe_speed_ratio,places=4)
        self.assertAlmostEqual(b.peak_position-a.peak_position,1000,delta=.05)

class NativeTests(unittest.TestCase):
    def test_toggle_off_really_executes_original_direction_with_other_controls(self):
        c=Case();self.assertEqual(c.publish(config(3,3000,8000,5000,new=False)),0);c.run('na_begin',2)
        c.w(M['symbols']['na_speed_overrides'],1)
        ss=samples((0,20,40));
        for s,v in zip(ss,[1000,850,700]):s.cv=v;s.generation=2
        c.native(ss);c.visited.clear();c.run(0x19d19c)
        self.assertEqual(c.events,[32]);self.assertEqual(c.sends,[-8000])
        self.assertIn(0x19e47c,c.visited);self.assertNotIn(M['symbols']['na_assess'],c.visited)
    def test_no_provider_preserves_original_state3(self):
        for sign in (-1,1):
            ss=samples(tuple(sign*20*i for i in range(5)),curve=lambda p:1000+100*sign*p)
            a=Case(False);b=Case()
            for c in (a,b):c.native(ss,command=sign*2000,supply=False);c.run(0x19d19c)
            self.assertEqual(a.sends,b.sends);self.assertEqual(a.events,b.events);self.assertEqual(b.events,[32])
            self.assertIn(0x19e47c,b.visited);self.assertIn(0x19d3cc,b.visited)
    def test_native_helper_metric_does_not_normalize_distance(self):
        values=[1000,1200,1500,1900,2400];metrics=[]
        for step in (1,100):
            c=Case(False);ss=samples(tuple(step*i for i in range(5)))
            for s,v in zip(ss,values):s.cv=v
            c.native(ss,supply=False);v=c.run(0x19e47c,0x902000)
            metrics.append(struct.unpack('<f',struct.pack('<I',v))[0])
        self.assertAlmostEqual(metrics[0],.9,places=5);self.assertEqual(*metrics)
    def test_noisy_initial_run_is_held_inside_original_framework(self):
        a=Case(False);b=Case();ss=samples()
        for s,v in zip(ss,[1000,1001,999,1000,1600]):s.cv=v
        for c in (a,b):c.native(ss);c.run(0x19d19c)
        self.assertEqual(a.events,[32]);self.assertEqual(b.events,[]);self.assertEqual(b.sends,[])
        self.assertIn(0x19e47c,b.visited);self.assertIn(0x19d5c0,b.visited)
    def test_stable_direction_still_uses_original_events_and_speed(self):
        c=Case();ss=samples(curve=lambda p:1000+100*p);c.native(ss);c.run(0x19d19c)
        self.assertEqual(c.events,[32]);self.assertEqual(c.sends,[2000])
        self.assertIn(0x1a0240,c.visited);self.assertIn(0x19e47c,c.visited)
    def test_incremental_first_frames_cannot_escape_before_noise_gate(self):
        a=Case(False);b=Case();ss=samples((0,20,40,60),curve=lambda p:1000+15*p)
        for n in range(1,4):
            for c in (a,b):
                c.native(ss[:n],supply=False)
                c.u.mem_write(0x901000,bytes(ss[n-1]));c.run('na_supply',0x901000);c.run(0x19d19c)
        self.assertEqual(a.events,[32]);self.assertEqual(b.events,[])
        b.native(ss,supply=False);b.u.mem_write(0x901000,bytes(ss[-1]));b.run('na_supply',0x901000);b.run(0x19d19c)
        self.assertEqual(b.events,[32]);self.assertEqual(b.sends,[2000])
    def test_initial_false_decline_is_not_allowed_to_commit_at_third_frame(self):
        a=Case(False);b=Case();ss=samples((0,20,40,60))
        for s,v in zip(ss,[1000,850,700,1200]):s.cv=v
        for n in range(1,5):
            for c in (a,b):
                c.native(ss[:n],supply=False)
                c.u.mem_write(0x901000,bytes(ss[n-1]));c.run('na_supply',0x901000);c.run(0x19d19c)
        self.assertIn(-2000,a.sends);self.assertEqual(b.sends,[]);self.assertEqual(b.events,[])
    def test_unaligned_provider_falls_back_to_original(self):
        a=Case(False);b=Case();ss=samples(curve=lambda p:1000+100*p);ss[2].flags=1
        for c in (a,b):c.native(ss);c.run(0x19d19c)
        self.assertEqual(a.events,b.events);self.assertEqual(a.sends,b.sends)
    def test_past_peak_event_and_flags_are_native(self):
        for sign in (-1,1):
            a=Case(False);b=Case();ss=samples(curve=lambda p:10000-50*p)
            for c in (a,b):
                c.native(ss,phase=4,command=sign*2000);c.byte(0x6bb59c,int(sign>0));c.byte(0x6bb59d,int(sign<0));c.run(0x19d5c8)
            self.assertEqual(a.events,b.events);self.assertEqual(b.events,[64]);self.assertEqual(b.sends,[])
            self.assertEqual(bytes(b.u.mem_read(0x6bb59c,2)),b'\x01\x01')
    def test_default_prediction_cannot_send_or_post_event(self):
        c=Case();c.native(samples(),phase=4);c.run(0x19d5c8);c.run(0x19d5c8)
        self.assertTrue(c.state().result.prediction_valid);self.assertEqual(c.sends,[]);self.assertEqual(c.events,[])
    def test_cancel_reset_wrong_phase_and_array_mismatch_bypass(self):
        ss=samples()
        for phase in (0,1,2,5,6,7):
            c=Case();c.native(ss,phase=phase,actuate=True);c.run('na_before_peak');c.run('na_before_peak')
            self.assertEqual(c.sends,[])
        c=Case();c.native(ss,phase=4,actuate=True);c.run('na_begin',2);c.run('na_before_peak');self.assertEqual(c.sends,[])
        c=Case();c.native(ss,phase=4,actuate=True);c.h(0x6bbd9c,999);c.run('na_before_peak');self.assertEqual(c.sends,[])
    def test_calibrated_simulation_limits_through_original_speed_packet(self):
        c=Case();c.native(samples(),phase=4,actuate=True);c.run(0x19d5c8);self.assertEqual(c.sends,[])
        c.run(0x19d5c8);self.assertEqual(c.sends,[]) # 同一帧重入不算两次独立拟合。
        ss=samples((0,20,40,60,80,90),[100,110,120,130,140,145])
        c.native(ss,phase=4,supply=False,actuate=True)
        c.u.mem_write(0x901000,bytes(ss[-1]));c.run('na_supply',0x901000);c.run(0x19d5c8)
        self.assertEqual(len(c.sends),1);self.assertGreaterEqual(c.sends[0],500);self.assertLess(c.sends[0],2000)
        self.assertEqual(c.events,[]);self.assertIn(0x19d5cc,c.visited);self.assertIn(0x1a0240,c.visited)
        c.run(0x19d5c8);self.assertEqual(len(c.sends),1)

class ConfigurationTests(unittest.TestCase):
    def test_cycle_reset_preserves_native_clears_and_latches_whole_new_config(self):
        a=Case(False);b=Case()
        for c in (a,b):
            # 固定时钟和原厂辅助登记为替身；0x1a4950 的字段清理实际执行。
            c.u.mem_write(0x198568,bytes.fromhex('7b00a0e30010a0e31eff2fe1'))
            c.u.mem_write(0x1a42d8,bytes.fromhex('1eff2fe1'))
            c.native(samples(),phase=4,actuate=True)
            c.u.mem_write(0x6bb59c,bytes([1,1,1,1]));c.w(0x6bc958,55)
            c.publish(config(3,1000,8000,2000,new=False))
        a.run(0x1a4950);b.run('na_cycle_reset')
        self.assertIn(0x1a4950,b.visited)
        self.assertEqual(bytes(a.u.mem_read(0x6bb000,0x1a00)),bytes(b.u.mem_read(0x6bb000,0x1a00)))
        self.assertEqual(b.state().count,0);self.assertEqual(b.state().allow_actuation,0)
        self.assertEqual(b.state().generation,2);self.assertEqual(b.bank().active.revision,3)
        self.assertEqual(bytes(b.bank().active),bytes(config(3,1000,8000,2000,new=False)))
    def test_default_is_original_direction_and_original_speeds(self):
        c=Case();c.run('na_config_reset');self.assertEqual(c.bank().active.flags,0)
        for stage in range(3):self.assertEqual(c.run('na_config_command',stage,5000),5000)
    def test_every_speed_option_for_each_independent_stage(self):
        c=Case();revision=2
        for probe in (0,1000,2000,3000,5000,8000,12000):
            for fast in (0,1000,2000,3000,5000,8000,12000):
                for fine in (0,1000,2000,3000,5000,8000,12000):
                    revision+=1;self.assertEqual(c.publish(config(revision,probe,fast,fine)),0);c.run('na_begin',revision)
                    for stage,value in enumerate((probe,fast,fine)):
                        for sign in (-1,1):
                            self.assertEqual(C.c_int32(c.run('na_config_command',stage,sign*2000)).value,sign*(value or 2000))
                        self.assertEqual(c.run('na_config_command',stage,0),0)
    def test_pending_changes_only_apply_at_next_af_start(self):
        c=Case();self.assertEqual(c.publish(config(3,3000,12000,5000,new=False)),0)
        self.assertEqual(c.bank().active.revision,2);self.assertEqual(c.bank().pending.revision,3)
        c.run('na_begin',1);self.assertEqual(c.bank().active.revision,2)
        c.run('na_begin',2);self.assertEqual(c.bank().active.revision,3)
        self.assertEqual(c.run('na_config_command',1,2000),12000)
        self.assertEqual(c.publish(config(4,5000,8000,3000,new=True)),0)
        self.assertEqual(c.bank().active.flags,0);self.assertEqual(c.run('na_config_command',1,2000),12000)
    def test_invalid_lens_speed_flags_checksum_and_stale_are_rejected(self):
        c=Case();before=bytes(c.bank().pending)
        for field,value,code in [('lens',55,2),('fast',3800,3),('flags',2,1),('magic',0,1),('checksum',0,4)]:
            row=config(3);setattr(row,field,value);self.assertEqual(c.publish(row),code)
            self.assertEqual(bytes(c.bank().pending),before)
        self.assertEqual(c.publish(config(2)),5)
    def test_busy_publication_cannot_latch_mixed_revision(self):
        c=Case();before=bytes(c.bank().active);c.w(M['symbols']['na_config_bank'],3)
        self.assertEqual(c.run('na_config_latch',2),6);self.assertEqual(bytes(c.bank().active),before)
        self.assertEqual(c.publish(config(3)),6)
    def test_stage_helpers_use_latched_values_and_native_packets(self):
        c=Case();c.publish(config(3,3000,8000,5000));c.run('na_begin',2);c.w(M['symbols']['na_speed_overrides'],1)
        for name,value in [('na_probe_speed',3000),('na_fast_speed',8000),('na_fine_speed',5000)]:
            c.run(name,-2000);self.assertEqual(c.sends[-1],-value)
        c.publish(config(4,12000,12000,12000));c.run('na_fast_speed',2000);self.assertEqual(c.sends[-1],8000)

if __name__=='__main__':
    started=time.perf_counter();suite=unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    r=unittest.TextTestRunner(verbosity=2).run(suite)
    report={'tests':r.testsRun,'failures':len(r.failures),'errors':len(r.errors),'seconds':time.perf_counter()-started,
            'passed':r.wasSuccessful(),'hardwareRequests':0,'experimentalInstallReady':False,
            'baseline_sha256':FARM.sha256,'payload_sha256':M['payload_sha256'],
            'test_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'scope':'ARM离线计算与原厂state3/state4/速度封包；不证明物理合焦、帧同步或真实制动能力'}
    (BUILD/'tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False));sys.exit(0 if r.wasSuccessful() else 1)
