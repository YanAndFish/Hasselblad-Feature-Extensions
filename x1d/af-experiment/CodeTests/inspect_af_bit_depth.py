"""离线核对普通/短帧AF位深与10 bit原厂编码；不修改R3候选、不访问设备。"""
import sys,json,struct
sys.dont_write_bytecode=True
from inspect_fast_window import ConfigCase,FarmApplication,ROOT
from unicorn import UC_PROT_ALL
from unicorn.arm_const import *

class SensorIfCase(ConfigCase):
    """只运行sensorif配置/应用，MMIO访问用字典；校准状态为显式替身。"""
    def __init__(self,farm):
        super().__init__(farm);self.mmio={0x4200001c:0xa4};self.mmio_writes=[]
        self.u.mem_protect(0x2b1000,0x1000,UC_PROT_ALL)
        for a in (0x238820,0x23899c,0x1f1ba0,0x21f67c):
            self.u.mem_write(a,bytes.fromhex('1eff2fe1'))
    def code(self,u,a,size,data):
        args=[u.reg_read(r) for r in (UC_ARM_REG_R0,UC_ARM_REG_R1)]
        if a in (0x238820,0x23899c):
            assert args[0] in (0x42000004,0x42000008,0x4200000c,0x42000018,0x4200001c,0x42000024)
            if a==0x238820:
                self.mmio[args[0]]=args[1];self.mmio_writes.append((args[0],args[1]))
                u.reg_write(UC_ARM_REG_R0,0)
            else:u.reg_write(UC_ARM_REG_R0,self.mmio.get(args[0],0))
            return
        if a in (0x1f1ba0,0x21f67c):
            # 没有校准窗口、机型分支不进入额外接收选项；不模拟真实板级状态。
            u.reg_write(UC_ARM_REG_R0,0);return
        if 0x21368c<=a<0x213b94:self.executed.add(a);return
        super().code(u,a,size,data)
    def write(self,u,access,a,size,value,data):
        if 0x2b1990<=a and a+size<=0x2b19a8:return
        super().write(u,access,a,size,value,data)
    def call(self,a,*args):
        u=self.u
        for r,v in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),args):u.reg_write(r,v)
        u.mem_write(0x100ef00,struct.pack('<I',args[4] if len(args)>4 else 0))
        u.reg_write(UC_ARM_REG_SP,0x100ef00);u.reg_write(UC_ARM_REG_LR,0x100f800)
        u.emu_start(a,0x100f800,count=10000)
        assert u.reg_read(UC_ARM_REG_PC)==0x100f800 and u.reg_read(UC_ARM_REG_SP)==0x100ef00
        return u.reg_read(UC_ARM_REG_R0)
    def apply(self,bit_depth,h,v):
        encoding=self.call(0x21368c,bit_depth)
        self.call(0x213af4,0,bit_depth,v,h,0)
        self.call(0x213834)
        assert self.mmio[0x4200001c]==0xa4|encoding
        assert self.mmio[0x4200000c]==h and self.mmio[0x42000008]==v
        return dict(bitDepth=bit_depth,receiverEncoding=encoding,
            hPeriod=self.mmio[0x4200000c],vPeriod=self.mmio[0x42000008],
            mmioModel={hex(a):value for a,value in self.mmio.items()})

def main():
    farm=FarmApplication();rows=[]
    assert farm.word(0x2302e4)==0xe3a0200c
    for mode in (0,5,6,7):
        c=ConfigCase(farm);result=c.run(mode)
        result['bitDepth']=bytes.fromhex(result['configBytes'])[0x7c]
        assert result['bitDepth']==(14 if mode in (0,6) else 12)
        rows.append(result)
    variants=[]
    for mode in (5,7):
        c=ConfigCase(farm)
        # 仅模拟器里把构造器立即数12换10，继续运行同一原厂构造/编码/检查。
        c.u.mem_write(0x2302e4,(0xe3a0200a).to_bytes(4,'little'))
        result=c.run(mode);cfg=bytes.fromhex(result['configBytes'])
        assert cfg[0x7c]==10
        base=next(r for r in rows if r['internalMode']==mode)
        assert all(result[k]==base[k] for k in ('hPeriod','vPeriod','nominalFpsField','outputWidth','outputHeight'))
        a,b=bytes.fromhex(base['registerBuffer']),bytes.fromhex(result['registerBuffer'])
        changes=[dict(offset=i,before=x,after=y) for i,(x,y) in enumerate(zip(a,b)) if x!=y]
        assert changes==[dict(offset=0x35,before=0x9a,after=0x98),dict(offset=0x47,before=0x80,after=0)]
        variants.append(dict(internalMode=mode,bitDepth=10,hPeriod=result['hPeriod'],vPeriod=result['vPeriod'],
            nominalFpsField=result['nominalFpsField'],registerChanges=changes,returnValue=result['return']))
    receiver=[]
    for bit_depth,encoding in ((10,0),(12,1),(14,2),(16,3)):
        row=SensorIfCase(farm).apply(bit_depth,1132,488)
        assert row['receiverEncoding']==encoding
        receiver.append(row)
    clock=struct.unpack('<f',farm.read(0x2305cc,4))[0]
    assert clock==54000000
    output=dict(farmSha256=farm.sha256,hardwareRequests=0,nominalTimingClock=clock,
        baseline=[{k:r[k] for k in ('internalMode','sensorMode','bitDepth','outputWidth','outputHeight',
             'hPeriod','vPeriod','nominalFpsField')} for r in rows],tenBitVariants=variants,
        receiverNativeCases=receiver,
        limitations=['只执行原厂配置运算与寄存器缓冲编码，未发送寄存器',
            'FPGA接收端10/12/14/16编码为原指令结果，MMIO和校准状态为模型，不证明物理接收成功',
            '未验证10 bit最低合法行周期、实际传感器时序、完整图像管线或AF效果',
            '更改位深字段不会自动缩短原厂行周期；没有据此宣称提速',
            'R3候选仍保持原厂12 bit，不包含10 bit实验'])
    path=ROOT/'x1d/af-experiment/build/fast-window/bit-depth.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(output,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
