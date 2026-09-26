"""视频整链补上原厂曝光选择：AE/ISO/光圈输入、log/pow为显式数学替身。"""
import sys,struct,math,unittest,json
sys.dont_write_bytecode=True
from test_r3_fast_video import VideoCase,FARM,BUILD,M
from unicorn.arm_const import *

class ExposureCase(VideoCase):
    SIMPLE={a:v for a,v in VideoCase.SIMPLE.items() if a!=0x21d8b8}
    def __init__(self):
        super().__init__();self.ev12=120;self.iso=100;self.aperture12=48
        for a in (0x1efdcc,0x235e9c,0x1cd334,0x1cd390,0x1cd3b8,0x17c210,0x17c4f8):
            self.u.mem_write(a,bytes.fromhex('1eff2fe1'))
    def code(self,u,a,size,data):
        r=[u.reg_read(k) for k in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)]
        def ret(value):u.reg_write(UC_ARM_REG_R0,value&0xffffffff)
        if a==0x1efdcc:self.word(r[0],self.ev12);ret(0);return
        if a in (0x235e9c,0x1cd334):ret(self.iso);return
        if a==0x1cd3b8:ret(self.aperture12);return
        if a==0x1cd390:ret(1000000);u.reg_write(UC_ARM_REG_R1,0);return
        if a in (0x17c210,0x17c4f8):
            x=struct.unpack('<d',struct.pack('<II',*r[:2]))[0]
            value=math.log(x) if a==0x17c210 else math.pow(x,struct.unpack('<d',struct.pack('<II',*r[2:]))[0])
            lo,hi=struct.unpack('<II',struct.pack('<d',value));ret(lo);u.reg_write(UC_ARM_REG_R1,hi);return
        if any(lo<=a<hi for lo,hi in ((0x21d8b8,0x21dd4c),(0x21e7c0,0x21ea4c),
            (0x235e1c,0x235e9c),(0x22ec14,0x22ed88),(0x235ee8,0x235f30),
            (0x236238,0x2363b8),(0x15ada8,0x15afc0))):return
        super().code(u,a,size,data)
    def exposure(self):
        b=bytes(self.u.mem_read(0x6c1690,0xd0))
        return dict(mode=b[1],maximum=struct.unpack_from('<Q',b,0x80)[0],
            exposure=struct.unpack_from('<Q',b,0xa0)[0],gain_code=struct.unpack_from('<I',b,0xa8)[0],
            digital_gain=struct.unpack_from('<f',b,0xac)[0],fps=struct.unpack_from('<f',b,0x9c)[0])

class VideoExposureTests(unittest.TestCase):
    def test_native_exposure_selector_runs_for_fast_and_restored_full(self):
        rows=[]
        for ev in (72,120,168):
            c=ExposureCase();c.ev12=ev;c.start();full=c.exposure()
            s=c.switch(7);self.assertEqual(s.result,0);short=c.exposure()
            s=c.switch(5);self.assertEqual(s.result,0);restored=c.exposure()
            self.assertEqual(restored,full)
            self.assertGreater(short['exposure'],0);self.assertLessEqual(short['exposure'],short['maximum'])
            if ev>=120:self.assertEqual(short['exposure'],full['exposure'])
            else:self.assertGreater(short['gain_code'],full['gain_code'])
            rows.append(dict(ev12=ev,full=full,short=short,restored=restored))
        (BUILD/'native-exposure-cases.json').write_text(json.dumps({'farmSha256':FARM.sha256,
            'artifactSha256':M['sha256'],'hardwareRequests':0,'cases':rows,'limitations':['AE/ISO/光圈是固定输入','log/pow为数学替身',
            'SPI/MIPI/RTOS/FPGA仍为模型，不是实测曝光或帧率']},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

    def test_weak_light_retains_full_mode_instead_of_shorter_exposure(self):
        c=ExposureCase();c.ev12=24;c.call_named('fast_videoon',5,640,360,0)
        full=c.exposure();self.assertGreater(full['digital_gain'],1)
        self.assertEqual(c.call_named('fast_video_begin',1,206|(1250<<16),248|(56<<16),1120108861),0)
        self.assertEqual(c.call_named('fast_video_request',7),0)
        self.assertEqual(c.exposure(),full)

if __name__=='__main__':unittest.main(verbosity=2)
