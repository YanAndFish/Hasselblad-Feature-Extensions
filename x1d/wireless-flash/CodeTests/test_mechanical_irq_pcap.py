"""原厂 PCAP 下载函数的实际 ARM 指令回放；所有外设均为显式模型。"""
from pathlib import Path
import hashlib
import json
import struct
import sys

HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'.research-cache/x1d-1.25.0/python'))
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_WRITE, UC_HOOK_MEM_READ
from unicorn import arm_const as arm

FARM_SHA='317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca'
OUT=HERE/'build/mechanical-irq-candidate'
REG=0xf8007000
STACK=0x3000000
STOP=0x3200000
INSTANCE=0x6db300
PL_POINTER=0x2400000 # 仅模型值；不是已读出的实机地址。
PL_BYTES=5979936

class Model:
    def __init__(self,farm,mode='success'):
        assert hashlib.sha256(farm).hexdigest()==FARM_SHA
        self.u=u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
        u.mem_map(0x100000,(len(farm)+4095)&~4095); u.mem_write(0x100000,farm)
        for a,n in ((0x6b0000,0x40000),(STACK,0x4000),(0x2129000,0x1000),(REG,0x1000)):
            u.mem_map(a,n)
        self.mmio=[]; self.calls=[]; self.tick=0; self.mode=mode
        self.ctrl=0x40000000; self.status=0x40000010; self.interrupts=0; self.dma_started=False
        self.visits={}
        for a,v in ((0x6db2e4,INSTANCE),(INSTANCE+4,REG),(INSTANCE+8,0x11111111),
                    (0x2129004,PL_BYTES),(0x2129008,PL_POINTER)):
            self.put(a,v)
        self.put(REG+0x80,0x100)

        def code(uc,a,n,_):
            self.visits[a]=self.visits.get(a,0)+1
            if a in (0x2209f4,0x10a1f8): raise AssertionError('原厂断言 '+hex(a))
            if a in (0x236a14,0x187bd8,0x188624):
                self.calls.append(a)
                if a==0x188624:
                    self.tick+=100; result=self.tick
                else: result=0 # 日志关闭、等待仅记录。
                uc.reg_write(arm.UC_ARM_REG_R0,result)
                uc.reg_write(arm.UC_ARM_REG_PC,uc.reg_read(arm.UC_ARM_REG_LR))

        def read(uc,access,a,n,v,_):
            if a>=0x40000000:
                assert REG<=a<REG+0x84 and n==4,hex(a)
                if a==REG: self.put(a,self.ctrl)
                if a==REG+0xc: self.put(a,self.interrupts)
                if a==REG+0x14: self.put(a,self.status)

        def write(uc,access,a,n,v,_):
            if a>=0x40000000:
                assert a in (REG,REG+0xc,REG+0x18,REG+0x1c,REG+0x20,REG+0x24,REG+0x80) and n==4,hex(a)
                self.mmio.append((a,v))
                if a==REG:
                    self.ctrl=v
                    if self.mode!='init-stuck':
                        self.status=(self.status&~0x10)|(0x10 if v&0x40000000 else 0)
                elif a==REG+0xc: self.interrupts&=~v
                elif a==REG+0x24:
                    self.dma_started=True
                    if self.mode=='success': self.interrupts|=0x2004
                    elif self.mode=='dma-error': self.interrupts|=0x400000
                return
            assert STACK<=a<STACK+0x4000 or a==0x6ee998 or a in getattr(self,'allowed_state_writes',()),hex(a)

        u.hook_add(UC_HOOK_CODE,code); u.hook_add(UC_HOOK_MEM_READ,read); u.hook_add(UC_HOOK_MEM_WRITE,write)

    def put(self,a,v): self.u.mem_write(a,struct.pack('<I',v))
    def run(self,limit=40000):
        self.u.reg_write(arm.UC_ARM_REG_CPSR,0x60000153)
        self.u.reg_write(arm.UC_ARM_REG_SP,STACK+0x3000)
        self.u.reg_write(arm.UC_ARM_REG_LR,STOP)
        self.u.emu_start(0x22b800,STOP,count=limit)
        self.returned=self.u.reg_read(arm.UC_ARM_REG_PC)==STOP
        self.result=self.u.reg_read(arm.UC_ARM_REG_R0)
        return self

def run(farm):
    assert Path.cwd().resolve()==ROOT
    results=[]
    for mode in ('success','dma-error','dma-timeout','init-stuck'):
        m=Model(farm,mode).run()
        if mode=='success':
            assert m.returned and m.result==0 and m.dma_started
            assert [(a-REG,v) for a,v in m.mmio if 0x18<=a-REG<=0x24]==[
                (0x18,PL_POINTER|1),(0x1c,0xffffffff),(0x20,PL_BYTES//4),(0x24,PL_BYTES//4)]
        elif mode in ('dma-error','dma-timeout'):
            assert m.returned and m.result!=0 and m.dma_started
        else:
            assert not m.returned and not m.dma_started
            assert m.visits.get(0x22b6c0,0)>100
        control=[v for a,v in m.mmio if a==REG]
        assert any(not v&0x40000000 for v in control)
        results.append({'mode':mode,'returned':m.returned,'result':m.result if m.returned else None,
            'dmaStarted':m.dma_started,'mmioWrites':[[hex(a),hex(v)] for a,v in m.mmio],
            'instructionsExecuted':sum(m.visits.values())})
    report={'passed':True,'firmwareSha256':FARM_SHA,'hardwareRequests':0,'installed':False,
        'originalInstructionsExecuted':True,'peripheralsModeled':True,'plPointerIsSynthetic':True,
        'entry':'0x22b800','cachedSourceGetter':'0x21f5d4','cachedSourceDescriptor':'0x02129000',
        'fullPlResetConfirmed':True,'resetHandshakeUnboundedLoopConfirmed':True,
        'safeLiveLoaderImplemented':False,'cases':results,
        'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (OUT/'pcap-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report

if __name__=='__main__':
    sys.path.insert(0,str(ROOT/'x1d/tools'))
    from farm_diagnostic_binary import FarmApplication
    print(json.dumps(run(FarmApplication().data),ensure_ascii=False))
