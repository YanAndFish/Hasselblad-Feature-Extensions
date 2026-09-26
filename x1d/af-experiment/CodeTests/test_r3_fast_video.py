"""原厂视频入口/退出与160行串行构件：寄存器发送、设备、RTOS为显式替身。"""
import sys,struct,json,ctypes,unittest
sys.dont_write_bytecode=True
from inspect_fast_pipeline import PipelineCase,W
from inspect_fast_sensor_program import SensorProgramCase
from unicorn import UC_PROT_ALL
from unicorn.arm_const import *
BUILD=W.ROOT/'x1d/af-experiment/build/fast-video-r3'
M=json.loads((BUILD/'manifest.json').read_text(encoding='utf-8'));FARM=W.FarmApplication()
TRANSITIONS=[]
class VideoState(ctypes.LittleEndianStructure):
    _fields_=[(n,ctypes.c_uint32) for n in '''magic abi enabled session request ack target result applying dirty need_recovery
        external_epoch session_epoch request_epoch observed_width observed_height width height roi0 roi1 full_rate
        pipeline_calls pipeline_result spi_calls spi_result spi_bytes ready_tick ready_rate switches canary'''.split()]
assert ctypes.sizeof(VideoState)==M['stateBytes']

class VideoCase(PipelineCase,SensorProgramCase):
    SIMPLE={0x1dc638:0,0x1c3848:0,0x1ef448:0,0x1efd70:0,0x1e479c:0,0x1cf574:0,0x1a6308:0,
        0x213fcc:0,0x2101dc:0,0x214550:0,0x202d8c:0,0x1fd694:0,0x1a9e2c:0,0x1a9e64:0,
        0x214980:0,0x214a64:0,0x1c2cbc:0,0x21f964:0,0x1cda34:1,0x1fd098:0,0x20faa4:0,
        0x1a9dc0:0,0x21d510:1,0x21d8b8:0,0x1ef9c0:0,0x21d5e8:0,0x213af4:0,
        0x23543c:0,0x23555c:0,0x21f658:15,0x186500:1,0x2017c8:0x1003000}
    def __init__(self):
        super().__init__(FARM);u=self.u
        u.reg_write(UC_ARM_REG_C1_C0_2,0xf<<20);u.reg_write(UC_ARM_REG_FPEXC,1<<30)
        u.mem_protect(0x2b1000,0x1000,UC_PROT_ALL)
        u.mem_map(0x300000,0x10000);u.mem_write(M['base'],(BUILD/'candidate.bin').read_bytes())
        u.mem_map(0x6c0000,0x6000);u.mem_map(0x6ba000,0x3000)
        self.addr=M['symbols']['fast_video_state'];self.set('enabled',2)
        u.mem_write(0x6bb46c,b'\x03');self.word(0x6badd0,1000);self.word(0x6c1768,0x1234)
        self.word(0x6c14e8,0x5678)
        # 合成已初始化的SPC传输状态；不把固件静态0xff默认值当运行态。
        u.mem_write(0x2b2450,b'\x00')
        self.native_calls=[];self.resources=set();self.queue=[];self.spi_status=0;self.pipeline_status=0
        self.mutex_fail=False;self.fail_resource=None;self.interrupt_after_spi=None
        self.configs={mode:bytes.fromhex(W.ConfigCase(FARM).run(mode)['configBytes']) for mode in (5,7)}
        for a in set(self.SIMPLE)|{0x186b70,0x22daac,0x22e1a8,0x235758}:u.mem_write(a,bytes.fromhex('1eff2fe1'))
        for a,old,new in M['hooks']:assert FARM.word(a)==old;self.word(a,new)
    def word(self,a,v):self.u.mem_write(a,struct.pack('<I',v&0xffffffff))
    def state(self):return VideoState.from_buffer_copy(bytes(self.u.mem_read(self.addr,ctypes.sizeof(VideoState))))
    def set(self,name,v):self.word(self.addr+getattr(VideoState,name).offset,v)
    def call_named(self,name,*args):return self.call(M['symbols'][name],*args)
    def write(self,u,access,a,size,v,data):
        if any(lo<=a and a+size<=hi for lo,hi in ((0x300000,0x310000),(0x6c0000,0x6c6000),
              (0x6ba000,0x6bd000),(0x6d92c0,0x6d93a0),(0x2b1da8,0x2b1dc8))):return
        super().write(u,access,a,size,v,data)
    def code(self,u,a,size,data):
        args=[u.reg_read(r) for r in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)]
        def ret(value=0):u.reg_write(UC_ARM_REG_R0,value)
        if a in self.SIMPLE:
            self.native_calls.append((a,args));ret(self.SIMPLE[a]);return
        if a==0x186b70:
            self.native_calls.append((a,args))
            if args[0]==0x1234:ret(0 if self.mutex_fail else 1)
            else:
                assert args[0]==0x5678 and args[1]==0x6c14ec
                assert self.queue,'test must supply bounded queue outcomes'
                result=self.queue.pop(0);ret(result)
            return
        if a==0x235758:
            assert args[0] in (5,7) and args[2]==0x6c1690
            u.mem_write(args[2],self.configs[args[0]]);ret();return
        if a==0x22daac:
            key=args[0];self.native_calls.append((a,args))
            if key==self.fail_resource:ret(1);return
            assert key not in self.resources,('duplicate resource acquisition',key)
            self.resources.add(key);ret();return
        if a==0x22e1a8:
            key=args[0];self.native_calls.append((a,args))
            assert key in self.resources,('release unowned resource',key)
            self.resources.remove(key);ret();return
        if a==0x234c64:
            super().code(u,a,size,data);ret(self.spi_status)
            if self.interrupt_after_spi:self.interrupt_after_spi(self)
            return
        if a==0x202a0c and self.pipeline_status:
            # 原管线返回值失败注入；仍执行其真实尺寸计算与资源配置。
            u.reg_write(UC_ARM_REG_R3,self.pipeline_status)
        if M['base']<=a<M['end']:return
        if any(lo<=a<hi for lo,hi in ((0x1c9614,0x1ca1f4),(0x1c3978,0x1c3ac4),
                (0x21e5e8,0x21e720),(0x21eb68,0x21edc8),(0x2357fc,0x2358a8),
                (0x1f0a1c,0x1f0c20),(0x21f1a0,0x21f1c4),(0x22da78,0x22daac))):return
        super().code(u,a,size,data)
    def start(self):
        self.call_named('fast_videoon',5,640,360,0)
        assert self.u.mem_read(0x6c176c,1)==b'\x01'
        assert self.call_named('fast_video_begin',1,206|(1250<<16),248|(56<<16),1120108861)==1
    def switch(self,target):
        assert self.call_named('fast_video_request',target)==1
        self.call_named('fast_video_service')
        s=self.state()
        TRANSITIONS.append({'target':target,'state':{name:getattr(s,name) for name,_ in VideoState._fields_},
            'resources':sorted(self.resources),'afSetup':self.af_setup[-1:]})
        return s

class FastVideoTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        (BUILD/'transition-cases.json').write_text(json.dumps({'artifactSha256':M['sha256'],
            'farmSha256':FARM.sha256,'hardwareRequests':0,'physicalFrameCompletionVerified':False,
            'simulatorOnly':True,'transitions':TRANSITIONS,
            'limitations':['RTOS资源、SPI、MIPI、前端控制和颜色参数为替身',
                '本套测试的235758使用原厂模式构造结果，21d8b8为替身；另有原生曝光测试',
                'status0不能独立证明每字节传输成功或传感器锁存','此文件只验证视频构件；AF整合与显示物理完成另列']},
            ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def test_native_fast_and_full_switch_programs_complete_buffer_and_retains_af(self):
        c=VideoCase();c.start();self.assertEqual(c.resources,{11,14,15})
        s=c.switch(7)
        self.assertEqual((s.result,s.ack,s.request),(0,1,1))
        self.assertEqual(c.resources,{14,15})
        self.assertEqual(c.af_setup[-1],{'width':2748,'height':152})
        self.assertEqual(list(struct.unpack('<4H',c.u.mem_read(0x6cc59c,8))),[48,1250,248,56])
        self.assertEqual((s.spi_calls,s.spi_bytes,s.pipeline_calls),(1,256,1))
        self.assertEqual(c.u.mem_read(0x6c1778,1),b'\x07')
        s=c.switch(5)
        self.assertEqual((s.result,s.dirty,s.need_recovery),(0,0,0))
        self.assertEqual(c.resources,{11,14,15})
        self.assertEqual(c.af_setup[-1],{'width':2748,'height':468})
        self.assertEqual(list(struct.unpack('<4H',c.u.mem_read(0x6cc59c,8))),[206,1250,248,56])
        self.assertEqual(c.programs[-1]['bytes'],256)

    def test_sensor_failure_is_not_success_despite_updated_software_cache(self):
        c=VideoCase();c.start();c.spi_status=1;s=c.switch(7)
        self.assertEqual((s.result,s.dirty,s.need_recovery),(5,1,0))
        self.assertEqual(c.u.mem_read(0x6c176c,1),b'\x00')
        self.assertEqual(bytes(c.u.mem_read(0x2b214c,256)),bytes(c.u.mem_read(0x6db2e8,256)))
        c.spi_status=0;s=c.switch(5)
        self.assertEqual((s.result,s.dirty,s.need_recovery),(0,0,0))
        self.assertEqual(c.programs[-1]['bytes'],256)

    def test_failed_full_restore_blocks_new_session(self):
        c=VideoCase();c.start();c.switch(7);c.spi_status=1;s=c.switch(5)
        self.assertEqual((s.result,s.dirty,s.need_recovery),(5,1,1))
        self.assertEqual(c.call_named('fast_video_request',7),0)
        self.assertEqual(c.call_named('fast_video_begin',2,206|(1250<<16),248|(56<<16),1120108861),0)

    def test_pipeline_failure_detected_even_when_native_videoon_sets_active(self):
        c=VideoCase();c.start();c.pipeline_status=2;s=c.switch(7)
        self.assertEqual((s.result,s.dirty),(4,1))
        self.assertEqual(c.u.mem_read(0x6c176c,1),b'\x01')
        c.pipeline_status=0;s=c.switch(5)
        self.assertEqual((s.result,s.dirty,s.need_recovery),(0,0,0))

    def test_resource_and_mutex_failures_are_not_success(self):
        for key in (14,15,16,'mutex'):
            c=VideoCase();c.start()
            if key=='mutex':c.mutex_fail=True
            else:c.fail_resource=key
            s=c.switch(7)
            self.assertIn(s.result,(2,3));self.assertEqual(s.ack,s.request)
            c.fail_resource=None;c.mutex_fail=False;s=c.switch(5)
            self.assertEqual((s.result,s.dirty,s.need_recovery),(0,0,0),(key,s.result))
            self.assertEqual(c.resources,{11,14,15})

    def test_pending_target_is_immutable_and_full_frame_request_follows_ack(self):
        c=VideoCase();c.start();self.assertEqual(c.call_named('fast_video_request',7),1)
        self.assertEqual(c.call_named('fast_video_request',5),0)
        self.assertEqual(c.state().target,7)
        c.call_named('fast_video_service');self.assertEqual(c.state().result,0)
        s=c.switch(5);self.assertEqual((s.result,s.request,s.ack,s.dirty),(0,2,2,0))

    def test_off_center_roi_rejected_before_any_switch_request(self):
        for y,height in ((0,56),(150,56),(260,56),(206,120)):
            c=VideoCase();c.call_named('fast_videoon',5,640,360,0);before=len(c.programs)
            self.assertEqual(c.call_named('fast_video_begin',1,y|(1250<<16),248|(height<<16),1120108861),0)
            self.assertEqual(c.call_named('fast_video_request',7),0)
            self.assertEqual(len(c.programs),before)

    def test_invalid_new_session_cannot_reuse_previous_roi(self):
        c=VideoCase();c.start();c.switch(7);c.switch(5)
        self.assertEqual(c.call_named('fast_video_begin',2,0|(1250<<16),248|(56<<16),1120108861),0)
        self.assertEqual(c.state().session,0);self.assertEqual(c.call_named('fast_video_request',7),0)

    def test_native_videooff_supersedes_pending_request(self):
        c=VideoCase();c.start();self.assertEqual(c.call_named('fast_video_request',7),1)
        # 正常AF结束本身先停止AF统计，再调用原厂视频退出。
        c.call(0x1f0b04);c.call_named('fast_videooff',0);before=len(c.programs)
        c.call_named('fast_video_service')
        self.assertEqual(c.state().result,1);self.assertEqual(len(c.programs),before)
        self.assertEqual(c.u.mem_read(0x6c176c,1),b'\x00')

    def test_external_entry_always_advances_epoch_even_if_apply_flag_is_set(self):
        c=VideoCase();c.start();epoch=c.state().external_epoch
        c.call(0x1f0b04);c.set('applying',1);c.call_named('fast_videooff',0)
        self.assertEqual(c.state().external_epoch,epoch+1)
        c.set('applying',0)

    def test_queue_real_message_priority_and_no_synthetic_packet(self):
        c=VideoCase();c.start();c.call_named('fast_video_request',7)
        marker=bytes(range(16));c.u.mem_write(0x6c14ec,marker);c.queue=[1]
        self.assertEqual(c.call_named('fast_video_wait',0x5678,0x6c14ec,0xffffffff,0),1)
        self.assertEqual(c.state().ack,0)
        c.queue=[0,1]
        self.assertEqual(c.call_named('fast_video_wait',0x5678,0x6c14ec,0xffffffff,0),1)
        self.assertEqual(c.state().result,0);self.assertEqual(c.u.mem_read(0x6c14ec,16),marker)

if __name__=='__main__':unittest.main(verbosity=2)
