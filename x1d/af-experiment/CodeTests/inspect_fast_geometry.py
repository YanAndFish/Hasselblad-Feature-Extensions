"""固定X1D 1.25.0裁剪寄存器编码和AF框算术；仅隔离内存，无设备接口。"""
import json,struct
import inspect_fast_window as W
from unicorn.arm_const import *

class GeometryCase(W.ConfigCase):
    def __init__(self,farm):
        super().__init__(farm)
        self.u.mem_map(0x6cc000,0x1000)
        self.u.mem_map(0x6d9000,0x1000)
        self.u.mem_write(0x6d93a2,b'\x01')
    def code(self,u,a,size,data):
        if any(lo<=a<hi for lo,hi in ((0x2341f4,0x234578),(0x2348f4,0x2349e0),
               (0x1f0090,0x1f0558),(0x1cd584,0x1cd614),(0x21facc,0x21faf4),(0x21f67c,0x21f6a0))):
            self.executed.add(a);return
        super().code(u,a,size,data)
    def write(self,u,access,a,size,v,data):
        if 0x6cc59c<=a and a+size<=0x6cc5a4:
            self.writes.append((a,size));return
        super().write(u,access,a,size,v,data)
    def call(self,address,*args):
        u=self.u
        for r,v in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),args):u.reg_write(r,v)
        u.reg_write(UC_ARM_REG_SP,0x100f000);u.reg_write(UC_ARM_REG_LR,0x100f800)
        if len(args)>4:u.mem_write(0x100f000,struct.pack('<'+'I'*(len(args)-4),*args[4:]))
        u.emu_start(address,0x100f800,count=100000,timeout=1000000)
        assert u.reg_read(UC_ARM_REG_PC)==0x100f800 and u.reg_read(UC_ARM_REG_SP)==0x100f000
        return u.reg_read(UC_ARM_REG_R0)
    def crop_registers(self):
        assert self.call(0x2341f4,0x1002000,self.cfg,0x29cc48+8*8,6200,0x6db2e8)==0
        regs=bytes(self.u.mem_read(0x6db2e8,0x100))
        return {'enabled':regs[1]&3,'rawRowOrigin':regs[0x11]|((regs[0x12]&63)<<8),
                'outputRows':regs[0x13]|((regs[0x14]&63)<<8),'registerBuffer':regs.hex()}
    def roi(self,width,height,center=(5000,5000),size=(900,1200)):
        # 合成的正常用户框输入；执行原厂getter和取整，未修改真实设置。
        self.u.mem_write(0x2add4e,struct.pack('<4H',*center,*size))
        assert self.call(0x1f0090,width,height)==0x6cc59c
        y,x,w,h=struct.unpack('<4H',self.u.mem_read(0x6cc59c,8))
        return {'x':x,'y':y,'width':w,'height':h}

def main():
    farm=W.FarmApplication();cases=[]
    for mode,rows in ((5,None),(7,None),(5,160)):
        c=GeometryCase(farm);cfg=c.run(mode,rows);regs=c.crop_registers()
        roi=c.roi(cfg['outputWidth']-8,cfg['outputHeight']-8)
        cases.append({'config':cfg,'crop':regs,'defaultNormalizedRoi':roi})
    regular,preset,af160=cases
    a=bytes.fromhex(preset['config']['configBytes']);b=bytes.fromhex(af160['config']['configBytes'])
    assert [i for i,(x,y) in enumerate(zip(a,b)) if x!=y]==[1]
    assert preset['crop']==af160['crop']
    roi=regular['defaultNormalizedRoi'];crop=af160['crop']
    assert crop['enabled']==1 and crop['outputRows']==160
    raw_step=13;normal_origin=116
    assert (crop['rawRowOrigin']-normal_origin)%raw_step==0
    shift=(crop['rawRowOrigin']-normal_origin)//raw_step
    adjusted={**roi,'y':roi['y']-shift}
    # 两种输出之间只平移AF框；不能沿用归一化高度而使原56行缩成18行。
    assert adjusted['y']>=4 and adjusted['y']+adjusted['height']<=152-4
    assert adjusted['width']==248 and adjusted['height']==56
    assert adjusted['y']*13+crop['rawRowOrigin']==roi['y']*13+normal_origin
    result={'farmSha256':farm.sha256,'cases':cases,'originalRoi':roi,'translatedRoi':adjusted,
            'verticalShiftInStatisticsRows':shift,'hardwareRequests':0,
            'scope':'原生配置、裁剪寄存器编码、AF框算术；未执行传感器下发、显示或动态切换'}
    out=W.ROOT/'x1d/af-experiment/build/fast-window';out.mkdir(parents=True,exist_ok=True)
    (out/'geometry.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='cases'},ensure_ascii=False,indent=2))
    print(json.dumps([{k:v for k,v in c['crop'].items() if k!='registerBuffer'} for c in cases]))
if __name__=='__main__':main()
