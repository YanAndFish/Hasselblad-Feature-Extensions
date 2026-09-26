"""原厂IMX161寄存器编程缓冲：下发函数为记录替身，绝不调用设备。"""
import sys,json,struct
sys.dont_write_bytecode=True
from inspect_fast_geometry import GeometryCase,W
from unicorn import UC_PROT_ALL
from unicorn.arm_const import *

class SensorProgramCase(GeometryCase):
    def __init__(self,farm):
        super().__init__(farm);self.programs=[]
        self.u.mem_protect(0x2b2000,0x1000,UC_PROT_ALL)
        self.u.mem_write(0x234c64,bytes.fromhex('1eff2fe1'))
    def code(self,u,a,size,data):
        if a==0x234c64:
            kind,offset,count,pointer=[u.reg_read(r) for r in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)]
            assert kind==2 and offset==0 and 0<count<=256 and pointer==0x6db2e8
            self.programs.append({'kind':kind,'offset':offset,'bytes':count,'buffer':bytes(u.mem_read(pointer,count)).hex()})
            u.reg_write(UC_ARM_REG_R0,0);return
        if any(lo<=a<hi for lo,hi in ((0x2305d0,0x23096c),(0x22ed88,0x22f49c),(0x233a4c,0x233c84),
                (0x15ae34,0x15afc0),(0x15c6d8,0x15d054),(0x15f190,0x15f220))):
            self.executed.add(a);return
        super().code(u,a,size,data)
    def write(self,u,access,a,size,v,data):
        if 0x2b214c<=a and a+size<=0x2b224c:self.writes.append((a,size));return
        if 0x6db3e8<=a and a+size<=0x6db4b8:self.writes.append((a,size));return
        super().write(u,access,a,size,v,data)
    def program(self,rows):
        cfg=self.run(5,rows)
        result=self.call(0x2305d0,self.cfg+0xa0,self.cfg,0x2b2450)
        assert result==0 and len(self.programs)==1
        return {'rows':rows,'result':result,'config':cfg,'program':self.programs[0]}

def main():
    farm=W.FarmApplication();rows=[]
    for height in (None,160):rows.append(SensorProgramCase(farm).program(height))
    a,b=[bytes.fromhex(x['program']['buffer']) for x in rows]
    result={'farmSha256':farm.sha256,'hardwareRequests':0,'cases':rows,
        'changedBytes':[{'offset':i,'full':x,'short':y} for i,(x,y) in enumerate(zip(a,b)) if x!=y],
        'limitations':['配置曝光字段为原厂构造默认值，非当前相机设置','SUC寄存器发送、回包、传感器和帧完成均未执行']}
    (W.ROOT/'x1d/af-experiment/build/fast-window/sensor-program.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='cases'},indent=2,ensure_ascii=False))
if __name__=='__main__':main()
