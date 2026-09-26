"""原生POST配置路由和尺寸检查。外部模块为显式成功替身，不代表全链已通过。"""
import json,struct
from inspect_fast_geometry import GeometryCase,W
from unicorn import UC_PROT_ALL
from unicorn.arm_const import *

# 这些调用只保存参数、返回成功；不能把它们称为验证过的FPGA行为。
STUBS={0x2011bc:'post_control',0x20127c:'post_buffer_mode',0x2010e4:'post_mode',
 0x200fcc:'hotpixel_size',0x1fc300:'demosaic',0x200120:'round_control',0x2000e8:'gamma_control',
 0x1ffba4:'whitebalance',0x200e68:'yuv_control',0x21dff0:'color_space',0x200c78:'color_transform',
 0x203b38:'display_format',0x1fb1e4:'display_setup',0x1ef5ec:'non_af_statistics',
 0x204110:'scaler_control',0x204960:'output_control',0x204cd4:'output_size',
 0x204b54:'output_flush',0x203b70:'display_control',0x2038b4:'display_enable',
 0x1ffb78:'post_latch',0x21e2f0:'exposure_state',0x1efe98:'lens_filter',
 0x203df0:'scaler_coefficients',0x204028:'scaler_apply_coefficients',
 0x203d78:'scaler_input',0x203d00:'scaler_latch',0x203c08:'scaler_dimensions',0x203cbc:'scaler_finish'}
class PipelineCase(GeometryCase):
    def __init__(self,farm):
        super().__init__(farm);u=self.u
        self.calls=[];self.mmio={};self.af_setup=[];self.scaler_setup=[];self.frontend=[]
        self.translate_roi=False;self.use_crop_dimensions=False
        u.mem_map(0x6d0000,0x1000);u.mem_protect(0x2ae000,0x1000,UC_PROT_ALL)
        u.mem_write(0x6d08b8,struct.pack('<H',8192))
        for mode in (5,7):
            cfg=bytes.fromhex(W.ConfigCase(farm).run(mode)['configBytes'])
            u.mem_write(0x6d93a8+mode*0xd0,cfg)
        u.mem_write(0x2add4e,struct.pack('<4H',5000,5000,900,1200))
        u.mem_write(0x1003000,struct.pack('<III',0xffc,0x1003100,0x3f800000)+bytes(0x28))
        u.mem_write(0x1003100,struct.pack('<3f',1,1,1))
        for a in STUBS:u.mem_write(a,bytes.fromhex('1eff2fe1'))
        for a in (0x238820,0x23899c):u.mem_write(a,bytes.fromhex('1eff2fe1'))
    def write(self,u,access,a,size,v,data):
        if any(lo<=a and a+size<=hi for lo,hi in ((0x6d08f8,0x6d0924),(0x2ae068,0x2ae078))):
            self.writes.append((a,size));return
        super().write(u,access,a,size,v,data)
    def code(self,u,a,size,data):
        args=[u.reg_read(r) for r in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)]
        if a in STUBS:
            self.calls.append({'function':STUBS[a],'address':hex(a),'args':args})
            if a==0x21e2f0:
                assert 0x100e000<=args[0] and args[0]+20<0x100f000
                u.mem_write(args[0],bytes(20))
            u.reg_write(UC_ARM_REG_R0,0);return
        if a in (0x238820,0x23899c):
            assert (0x44230000<=args[0]<0x44230100 or 0x442c0000<=args[0]<0x442c0100)
            if a==0x238820:self.mmio[args[0]]=args[1];u.reg_write(UC_ARM_REG_R0,0)
            else:u.reg_write(UC_ARM_REG_R0,self.mmio.get(args[0],0))
            return
        if a==0x2209f4:raise RuntimeError('native assertion, caller '+hex(u.reg_read(UC_ARM_REG_LR)))
        if a==0x201324 and self.use_crop_dimensions:
            # 候选补偿：仅这次POST几何计算使用当前传感器实际输入尺寸。
            ptr=args[0];cfg=struct.unpack('<I',u.mem_read(ptr,4))[0]
            b=bytes(u.mem_read(cfg,0xd0))
            u.mem_write(0x6d93a8+5*0xd0,b)
        if a==0x1ff7c8:self.frontend.append({'width':args[0],'height':args[1],
            'crop':list(struct.unpack('<4I',u.mem_read(args[2],16)))})
        if a==0x1f0558:self.af_setup.append({'width':args[1],'height':args[2]})
        if a==0x1f0e6c and self.translate_roi and self.af_setup[-1]['height']==152:
            u.mem_write(0x6cc59c,struct.pack('<4H',48,1250,248,56))
        if a==0x204244:self.scaler_setup.append(args)
        if any(lo<=a<hi for lo,hi in ((0x201e44,0x202a18),(0x201324,0x2014e0),
                (0x201964,0x201e44),(0x21f6a0,0x21f820),(0x21faf4,0x21fb70),
                (0x20f2b0,0x20f300),(0x20ed0c,0x20ee90),(0x214448,0x2144c4),
                (0x1ff430,0x1ff714),(0x1ff7c8,0x1ff82c),(0x1f0558,0x1f0a1c),
                (0x1f0e6c,0x1f0fc8),(0x204244,0x204578))):
            self.executed.add(a);return
        super().code(u,a,size,data)
    def pipeline(self,mode,override,pipeline,display,translate_roi=False,use_crop_dimensions=False):
        cfg=self.run(mode,override);self.translate_roi=translate_roi;self.use_crop_dimensions=use_crop_dimensions
        ret=self.call(0x201e44,self.cfg,pipeline,*display,0x1003000)
        roi=list(struct.unpack('<4H',self.u.mem_read(0x6cc59c,8)))
        return {'mode':mode,'cropRows':override,'pipeline':pipeline,'display':display,'return':ret,
                'translateRoi':translate_roi,'useCurrentDimensions':use_crop_dimensions,'frontend':self.frontend,
                'afSetup':self.af_setup,'roiYXWH':roi,'scalerInputOutput':self.scaler_setup,
                'mmioModel':{hex(a):v for a,v in self.mmio.items()},'stubbedCalls':self.calls}

def main():
    farm=W.FarmApplication();cases=[]
    for spec in ((5,None,2,(640,360),False,False),(5,160,2,(640,360),False,False),
                 (7,None,6,(64,64),False,False),(7,None,2,(640,360),True,False),
                 (7,None,2,(640,96),True,False),(5,160,2,(640,96),True,True)):
        cases.append(PipelineCase(farm).pipeline(*spec))
    out=W.ROOT/'x1d/af-experiment/build/fast-window/pipeline-routing.json'
    out.write_text(json.dumps({'farmSha256':farm.sha256,'cases':cases,'hardwareRequests':0,
          'limitation':'显式成功替身覆盖非几何模块；未验证DMA、传感器下发或帧切换'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps([{k:v for k,v in c.items() if k not in ('stubbedCalls','mmioModel')} for c in cases],indent=2))
if __name__=='__main__':main()
