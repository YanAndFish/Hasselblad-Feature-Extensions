"""固定IMX161模式/裁剪构造的原生离线执行。未映射设备寄存器，无硬件模块。"""
import sys,json,struct,hashlib
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'x1d/tools'),str(ROOT/'.research-cache/x1d-1.25.0/python')]
from farm_diagnostic_binary import FarmApplication
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE,UC_HOOK_MEM_WRITE,UC_PROT_READ,UC_PROT_EXEC
from unicorn.arm_const import *
FARM_SHA='317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca'
class ConfigCase:
    def __init__(self,farm):
        assert farm.sha256==FARM_SHA
        self.farm=farm;self.u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u=self.u
        u.mem_map(0x100000,(len(farm.data)+4095)&~4095,UC_PROT_READ|UC_PROT_EXEC);u.mem_write(0x100000,farm.data)
        # 禁用日志输出的固定替身，配置和检查仍运行原指令。
        u.mem_write(0x236a14,bytes.fromhex('1eff2fe1'))
        u.mem_map(0x6db000,0x1000);u.mem_map(0x1000000,0x10000)
        self.cfg=0x1001000;self.executed=set();self.writes=[];self.override=None
        u.hook_add(UC_HOOK_CODE,self.code);u.hook_add(UC_HOOK_MEM_WRITE,self.write)
    def code(self,u,a,size,_):
        if a==0x236a14:u.reg_write(UC_ARM_REG_R0,0);return
        allowed=((0x22f49c,0x2305cc),(0x226974,0x226b90),(0x15ed40,0x15eed4),
                 (0x234578,0x2348f4),(0x233c84,0x2341f4),(0x21f9e0,0x21fa20),
                 (0x15a3dc,0x15a690))
        if not any(lo<=a<hi for lo,hi in allowed):raise RuntimeError('unreviewed code '+hex(a))
        self.executed.add(a)
        if a==0x230408 and self.override is not None:
            # 只在合成配置上替换候选输出高，继续跑原厂裁剪算术与断言。
            u.mem_write(self.cfg+0xc8,struct.pack('<I',self.override))
    def write(self,u,access,a,size,v,_):
        if not any(lo<=a and a+size<=hi for lo,hi in ((self.cfg,self.cfg+0xd0),(0x6db2e8,0x6db3e8),(0x100e000,0x100f000))):
            raise RuntimeError('unexpected write '+hex(a))
        self.writes.append((a,size))
    def run(self,mode,override=None):
        self.override=override;u=self.u
        for r,v in ((UC_ARM_REG_C1_C0_2,0xf<<20),(UC_ARM_REG_FPEXC,1<<30),(UC_ARM_REG_R0,mode),(UC_ARM_REG_R1,0),
                    (UC_ARM_REG_R2,self.cfg),(UC_ARM_REG_SP,0x100f000),(UC_ARM_REG_LR,0x100f800)):u.reg_write(r,v)
        u.emu_start(0x22f9f0,0x100f800,count=100000,timeout=1000000)
        assert u.reg_read(UC_ARM_REG_PC)==0x100f800 and u.reg_read(UC_ARM_REG_SP)==0x100f000
        cfg=bytes(u.mem_read(self.cfg,0xd0));regs=bytes(u.mem_read(0x6db2e8,0x100))
        h=lambda off:struct.unpack_from('<H',cfg,off)[0]
        w=lambda off:struct.unpack_from('<I',cfg,off)[0]
        return {'internalMode':mode,'overrideOutputRows':override,'sensorMode':cfg[2],
                'configBytes':cfg.hex(),'registerBuffer':regs.hex(),'inputWidth':h(4),'inputHeight':h(6),
                'outputWidth':h(8),'outputHeight':h(10),'hPeriod':w(0x70),'extra':w(0x74),'vPeriod':w(0x78),
                'cropOutputHeight':w(0xc8),'nominalFpsField':struct.unpack_from('<f',cfg,0x9c)[0],
                'return':u.reg_read(UC_ARM_REG_R0),'nativeInstructions':len(self.executed),'hardwareRequests':0}
def main():
    farm=FarmApplication()
    results=[ConfigCase(farm).run(mode) for mode in range(12)]
    out=ROOT/'x1d/af-experiment/build/fast-window';out.mkdir(parents=True,exist_ok=True)
    (out/'native-configs.json').write_text(json.dumps({'farmSha256':farm.sha256,'cases':results},indent=2)+'\n',encoding='utf-8')
    print(json.dumps([{k:v for k,v in result.items() if k not in ('configBytes','registerBuffer')} for result in results],indent=2))
if __name__=='__main__':main()
