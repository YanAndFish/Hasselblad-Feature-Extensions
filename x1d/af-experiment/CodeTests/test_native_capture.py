"""原厂 CV 读数、FIFO 和接受点的旁路记录；不提供伪造的同帧标志。"""
import hashlib,json,struct,sys,time,unittest
from pathlib import Path
sys.dont_write_bytecode=True
sys.argv.append('--capture')
from test_native_af import Case,M,BUILD,FARM,PAYLOAD
from unicorn.arm_const import *

S=M['symbols'];CAP=S['nc_capture'];RECORD_BYTES=36
def records(c,raw=False,control=False):
    seq=c.word(CAP+(12 if raw else (32 if control else 16)));capacity=64 if raw else (32 if control else 128)
    start=CAP+48+(0 if raw else ((64+128)*RECORD_BYTES if control else 64*RECORD_BYTES));out=[]
    for n in range(max(1,seq-capacity+1),seq+1):
        fields=struct.unpack('<9I',c.u.mem_read(start+((n-1)&(capacity-1))*RECORD_BYTES,RECORD_BYTES))
        assert fields[0]==n*2;out.append(fields)
    return out

class CaptureCase(Case):
    def __init__(self,patched=True):
        self.capture_patched=patched;self.inline_end=None;self.block_pair=False
        self.bus={0x442c0000:1,0x442c000c:0};self.channels=(3000,4000);self.bus_reads=[];self.bus_writes=[];self.messages=[]
        super().__init__(patched)
        self.capture_stubs={0x21facc,0x23899c,0x238820,0x1867e4,0x18a594}
        for a in self.capture_stubs:self.u.mem_write(a,bytes.fromhex('1eff2fe1'))
        self.byte(0x6bb46c,3);self.w(CAP+8,7);self.w(0x6badd0,1000)
    def word(self,a):return struct.unpack('<I',self.u.mem_read(a,4))[0]
    def hook(self,u,a,size,data):
        if a==self.inline_end or (self.block_pair and a==0x1a2a30):u.emu_stop();return
        if a==0x21facc:u.reg_write(UC_ARM_REG_R0,1);return
        if a==0x23899c:
            address=u.reg_read(UC_ARM_REG_R0);self.bus_reads.append(address)
            if address==0x442c0068:value=self.channels[bool(self.bus[0x442c000c]&0x1000)]
            else:value=self.bus[address]
            u.reg_write(UC_ARM_REG_R0,value);return
        if a==0x238820:
            address=u.reg_read(UC_ARM_REG_R0);value=u.reg_read(UC_ARM_REG_R1)
            assert address==0x442c000c
            self.bus_writes.append((address,value));self.bus[address]=value;u.reg_write(UC_ARM_REG_R0,0);return
        if a==0x1867e4:
            assert u.reg_read(UC_ARM_REG_R0)==0x904800
            self.messages.append(bytes(u.mem_read(u.reg_read(UC_ARM_REG_R1),8)))
            u.reg_write(UC_ARM_REG_R0,1);return
        if a==0x18a594:u.reg_write(UC_ARM_REG_R0,0);return
        super().hook(u,a,size,data)
    def inline(self,entry,end,prepare):
        u=self.u;self.inline_end=end
        u.reg_write(UC_ARM_REG_CPSR,0xa800001f);u.reg_write(UC_ARM_REG_C1_C0_2,0xf<<20);u.reg_write(UC_ARM_REG_FPEXC,1<<30)
        for i in range(13):u.reg_write(globals()['UC_ARM_REG_R'+str(i)],0x13570000+i)
        u.reg_write(UC_ARM_REG_R11,0x90fd00);u.reg_write(UC_ARM_REG_SP,0x90fb00);u.reg_write(UC_ARM_REG_LR,0x900000)
        for i in range(32):u.reg_write(globals()['UC_ARM_REG_D'+str(i)],0x1234000000000000+i)
        prepare(self)
        registers=[*[globals()['UC_ARM_REG_R'+str(i)] for i in range(13)],UC_ARM_REG_SP,UC_ARM_REG_LR]
        before={r:u.reg_read(r) for r in registers}
        u.emu_start(entry,0,count=30000);assert u.reg_read(UC_ARM_REG_PC)==end
        if entry==0x1f0d2c:before[UC_ARM_REG_R3]=2
        assert all(u.reg_read(r)==v for r,v in before.items())
        assert u.reg_read(UC_ARM_REG_CPSR)&0xf8000000==0xa8000000
        assert all(u.reg_read(globals()['UC_ARM_REG_D'+str(i)])==0x1234000000000000+i for i in range(32))
        self.inline_end=None

class CaptureTests(unittest.TestCase):
    def test_four_inline_hooks_replay_original_memory_and_preserve_all_registers(self):
        cases=[(0x1f0d2c,0x1f0d30,lambda c:(c.w(0x90fcf0,301),c.w(0x90fcec,402),c.byte(0x90fce7,2)),True,(301,402,2,0)),
            (0x1a1b48,0x1a1b4c,lambda c:(c.u.reg_write(UC_ARM_REG_R1,12345),c.u.reg_write(UC_ARM_REG_R2,3),c.u.reg_write(UC_ARM_REG_R3,0x6bc96c)),False,(12345,3,0,0)),
            (0x1a2130,0x1a2134,lambda c:(c.u.reg_write(UC_ARM_REG_R2,65513),c.u.reg_write(UC_ARM_REG_R3,0x6bc988),c.w(0x90fcd8,0),c.byte(0x90fcdd,99)),False,(0xffffffe9,0,99,0)),
            (0x1a3068,0x1a306c,lambda c:(c.u.reg_write(UC_ARM_REG_R2,2),c.u.reg_write(UC_ARM_REG_R3,0x6bc954),c.h(0x6bbd9e,55),c.w(0x6bb5d0,999)),False,(2,55,999,0))]
        for entry,end,prepare,raw,expected in cases:
            c=CaptureCase();c.inline(entry,end,prepare)
            row=records(c,raw)[-1];self.assertEqual(row[2:5],(1000,7,3));self.assertEqual(row[5:],expected)
            if entry==0x1a1b48:self.assertEqual(c.word(0x6bc978),12345)
            elif entry==0x1a2130:self.assertEqual(bytes(c.u.mem_read(0x6bc988,2)),struct.pack('<h',-23))
            elif entry==0x1a3068:self.assertEqual(c.word(0x6bc954)&65535,2)
    def test_original_fpga_modes_have_identical_results_and_bus_accesses(self):
        for mode,expected in [(0,7000),(1,4000),(2,5000),(3,3000),(4,4000)]:
            before=CaptureCase(False);after=CaptureCase()
            for c in (before,after):
                self.assertEqual(c.run(0x1f0c20,0x904000,mode),0)
                self.assertEqual(c.word(0x904000),expected)
            self.assertEqual(before.bus_reads,after.bus_reads);self.assertEqual(before.bus_writes,after.bus_writes)
            self.assertEqual(records(after,True)[-1][5:],(3000,4000,mode,0))
    def test_not_ready_has_no_raw_capture_and_original_failure_is_preserved(self):
        c=CaptureCase();c.bus[0x442c0000]=0
        self.assertEqual(c.run(0x1f0c20,0x904000,0),1)
        self.assertEqual(records(c,True),[]);self.assertEqual(c.bus_writes,[])
    def test_original_irq_message_is_unchanged_by_raw_capture(self):
        a=CaptureCase(False);b=CaptureCase()
        for c in (a,b):c.w(0x6bb474,0x904800);c.run(0x1986d8,0)
        self.assertEqual(a.messages,b.messages);self.assertEqual(len(b.messages),1)
        self.assertEqual(b.messages[0][:2],bytes.fromhex('cc00'))
        self.assertEqual(records(b,True)[-1][5:7],b.channels)
    def test_ring_wrap_publication_sequence_and_generation_are_explicit(self):
        c=CaptureCase()
        for i in range(70):c.w(0x6badd0,1000+i);c.run('nc_raw',i,i+1,2)
        rows=records(c,True);self.assertEqual(len(rows),64);self.assertEqual(rows[0][0],14)
        self.assertEqual(rows[-1][0],140);self.assertEqual(rows[-1][2:5],(1069,7,3))
        self.assertEqual(rows[-1][5:],(69,70,2,0))
    def test_original_fifos_pair_wrap_and_speed_filter_are_unchanged(self):
        a=CaptureCase(False);b=CaptureCase()
        for c in (a,b):
            c.w(0x6bcb78,0x904800);c.w(0x6bcb44,0x42480000)
            c.h(0x6bb5a0,500);c.h(0x6bb5a2,500)
            c.bus[0x442c0060]=0 # 固定外设输入；不解释其物理含义。
        positions=[10,20,30,40,50,60,70,80,90,100,300,310,320]
        for i,position in enumerate(positions):
            for c in (a,b):
                c.w(0x6badd0,1000+i*20)
                c.u.mem_write(0x904000,bytes.fromhex('0000000000')+struct.pack('<h',position)+bytes((0,0,(91+i)%100)))
                c.run(0x1a1cd8,0x904000)
                c.w(0x904000,0xcc);c.w(0x904004,11000+i*1000)
                c.run(0x1a1a98,0x904000);c.run(0x1a2a30)
            self.assertEqual(bytes(a.u.mem_read(0x6bb46c,0x1500)),bytes(b.u.mem_read(0x6bb46c,0x1500)))
        accepted=records(b);accepted=[r for r in accepted if r[1]==4]
        self.assertEqual(len(accepted),b.word(0x6bc954)&65535)
        self.assertGreater(len(accepted),5);self.assertLess(len(accepted),len(positions))
        self.assertEqual(a.events,b.events);self.assertEqual(a.sends,b.sends)
        self.assertIn(0,[r[7] for r in records(b) if r[1]==3])
    def test_first_discard_and_missing_counterpart_remain_native(self):
        c=CaptureCase();c.byte(0x6bc95c,1)
        c.w(0x904000,0xcc);c.w(0x904004,12345)
        c.run(0x1a1a98,0x904000);self.assertEqual(records(c),[])
        c.run(0x1a1a98,0x904000);self.assertEqual(records(c)[-1][1],2)
        c.run(0x1a2a30)
        self.assertEqual(c.word(0x6bc954)&65535,0)
        self.assertEqual(c.state().count,0)
    def test_invalid_indices_are_rejected_and_no_algorithm_metadata_is_manufactured(self):
        c=CaptureCase();before=bytes(c.u.mem_read(S['na_adapter'],340))
        c.run('nc_cv_fifo',123,5);c.run('nc_position_fifo',12,0,100)
        c.run('nc_accepted',0);c.run('nc_accepted',501)
        self.assertEqual(c.word(CAP+20),4);self.assertEqual(records(c),[])
        c.run('nc_raw',1000,2000,1);c.run('nc_cv_fifo',1500,0)
        self.assertEqual(bytes(c.u.mem_read(S['na_adapter'],340)),before)
        self.assertEqual(c.sends,[]);self.assertEqual(c.events,[])
    def test_video_mode_is_observed_and_stage_command_start_is_not_receive_time(self):
        c=CaptureCase();c.byte(0x6c176c,1);c.byte(0x6c1778,5);c.h(0x6c169a,476)
        c.run('nc_raw',123,456,2)
        self.assertEqual(records(c,True)[-1][8],1|(5<<8)|(476<<16))
        # 模拟原厂发送封装自身消耗 7 tick，起点与返回时刻应分别保留。
        from unicorn import UC_HOOK_CODE
        # 独立时钟 hook 只在原厂发送边界更新一次，现有设备替身继续执行。
        def clock_tick(u,a,size,data):
            if a==0x1e80d0:c.w(0x6badd0,c.word(0x6badd0)+7)
        handle=c.u.hook_add(UC_HOOK_CODE,clock_tick)
        c.run('nc_fast_speed',500);c.u.hook_del(handle)
        row=records(c,control=True)[-1];self.assertEqual(row[1],6)
        self.assertEqual(row[2],1007);self.assertEqual(row[5:],(1,500,500,1000))
    def test_observer_stage_wrappers_and_cycle_preserve_native_state_and_packets(self):
        for wrapper in ('nc_probe_speed','nc_fast_speed','nc_fine_speed'):
            for speed in (-40000,-2000,0,2000,40000):
                a=CaptureCase(False);b=CaptureCase()
                a.run(0x1a0240,speed);b.run(wrapper,speed)
                self.assertEqual(a.sends,b.sends);self.assertEqual(a.events,b.events)
                self.assertEqual(records(b,control=wrapper!='nc_probe_speed')[-1][7],a.sends[-1]&0xffffffff)
                self.assertEqual(bytes(a.u.mem_read(0x6bb000,0x1a00)),bytes(b.u.mem_read(0x6bb000,0x1a00)))
        a=CaptureCase(False);b=CaptureCase()
        for c in (a,b):
            c.u.mem_write(0x198568,bytes.fromhex('7b00a0e30010a0e31eff2fe1'))
            c.u.mem_write(0x1a42d8,bytes.fromhex('1eff2fe1'))
            c.u.mem_write(0x6bb59c,bytes([1,1,1,1]));c.w(0x6bc958,55)
        a.run(0x1a4950);b.run('nc_cycle_reset')
        self.assertEqual(bytes(a.u.mem_read(0x6bb000,0x1a00)),bytes(b.u.mem_read(0x6bb000,0x1a00)))
        self.assertEqual(b.word(CAP+8),8);self.assertEqual(records(b,control=True)[-1][1],5)
        self.assertEqual(b.state().allow_actuation,0);self.assertEqual(b.state().count,0)

if __name__=='__main__':
    start=time.perf_counter();result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CaptureTests))
    report={'tests':result.testsRun,'passed':result.wasSuccessful(),'failures':len(result.failures),'errors':len(result.errors),
        'seconds':time.perf_counter()-start,'baselineSha256':FARM.sha256,'payloadSha256':M['payload_sha256'],
        'hardwareRequests':0,'testSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'scope':'四个原厂 inline 入口及全部GPR/NZCVQ/VFP保存；原厂 FPGA 双通道读取和 IRQ 消息发布；外设/队列为替身',
        'limitations':['没有证明物理帧对应、采样时间、当前镜头固件或实际执行延迟','记录不会向算法伪造 NA_REQUIRED 或 calibrated 标志']}
    (BUILD/'capture-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False));raise SystemExit(not result.wasSuccessful())
