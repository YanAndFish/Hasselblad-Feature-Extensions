"""执行新 Thumb 代码及原播放准备指令；PHY 寄存器与 ROM 为显式替身。"""
from pathlib import Path
import hashlib,json,struct,sys

HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'.research-cache/x1d-1.25.0/python'))
import unicorn
from unicorn import arm_const as arm

OUT=HERE/'build/mechanical-hw-ready-candidate'
PI,REGS,STACK,STOP=0x300000,0x310000,0x410000,0x400000
STATE,CONTEXT=0x2147e0,0x217f00
manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
firmware=(OUT/'hardware-ready-wltest.bin').read_bytes()
assert hashlib.sha256(firmware).hexdigest()==manifest['sha256']

class Machine:
    def __init__(self,busy_reads=2):
        self.u=unicorn.Uc(unicorn.UC_ARCH_ARM,unicorn.UC_MODE_THUMB)
        for base,size in [(0,0x10000),(0x180000,0x100000),(PI,0x20000),(STOP,0x20000)]: self.u.mem_map(base,size)
        self.u.mem_write(0x180000,firmware)
        self.u.mem_write(STOP,b'\x00\xbe')
        self.put32(PI+0x100,REGS); self.put16(PI+0x10e,0x1002)
        self.put16(REGS+0x492,2); self.put16(REGS+0x55a,0x1111); self.put16(REGS+0x55c,0x2222)
        self.u.mem_write(STATE,struct.pack('<8I',1,0x0e77be41,1,0,1,0,0,0))
        self.phy={0x471:0x1240,0x400:0x80,0x19e:0x20}
        self.busy_reads=busy_reads; self.remaining=0
        self.events=[]; self.depth=0; self.rf=0; self.fail_after_start=False
        self.u.hook_add(unicorn.UC_HOOK_CODE,self.code)
        self.u.hook_add(unicorn.UC_HOOK_MEM_WRITE,self.write,begin=REGS,end=REGS+0x1000)

    def put16(self,a,v): self.u.mem_write(a,struct.pack('<H',v))
    def put32(self,a,v): self.u.mem_write(a,struct.pack('<I',v))
    def word(self,a): return struct.unpack('<I',self.u.mem_read(a,4))[0]
    def half(self,a): return struct.unpack('<H',self.u.mem_read(a,2))[0]
    def ret(self,value=0):
        for r in (arm.UC_ARM_REG_R1,arm.UC_ARM_REG_R2,arm.UC_ARM_REG_R3,arm.UC_ARM_REG_R12): self.u.reg_write(r,0xbad00000+r)
        self.u.reg_write(arm.UC_ARM_REG_R0,value)
        self.u.reg_write(arm.UC_ARM_REG_PC,self.u.reg_read(arm.UC_ARM_REG_LR))

    def write(self,u,access,address,size,value,data):
        if address==REGS+0x492 and value==0x1802:
            assert size==2
            self.rf+=1; self.events.append(('start',self.rf))
            if self.fail_after_start: self.busy_reads=-1

    def code(self,u,address,size,data):
        if address==STOP: u.emu_stop(); return
        r0,r1,r2,r3=[u.reg_read(r) for r in (arm.UC_ARM_REG_R0,arm.UC_ARM_REG_R1,arm.UC_ARM_REG_R2,arm.UC_ARM_REG_R3)]
        if address==0x8710:
            self.events.append(('delay',r0))
            if r0==500:
                assert self.half(REGS+0x492)==0x1802
                assert u.reg_read(arm.UC_ARM_REG_CPSR)&0xc0==0xc0
            self.ret(); return
        if address==0x1bb31c:
            assert r0==PI and r1 in (0,1)
            self.depth+=1 if r1 else -1
            assert 0<=self.depth<=2
            self.events.append(('hold',r1)); self.put16(REGS+0x492,2)
            self.ret(); return
        if address==0x1bb210:
            assert r0==PI
            self.events.append(('cleanup',0)); self.ret(); return
        if address==0x215fa0:
            assert r0==PI and self.depth==0
            for off in (0,8,16): self.put32(STATE+off,0)
            self.events.append(('release',0)); self.ret(1); return
        if address==0x1bb3d6:
            sp=u.reg_read(arm.UC_ARM_REG_SP)
            assert (r0,r1,r2,r3,self.word(sp),self.word(sp+4))==(PI,0x6f00,1,0,0,1)
            self.events.append(('prepare',0))
            return # 真正执行固定旧固件的准备、延时和完成轮询指令。
        if address==0x1c620e:
            assert r0==PI
            if r1==0x403:
                value=int(self.remaining!=0)
                if self.remaining>0: self.remaining-=1
            else: value=self.phy.get(r1,0)
            self.ret(value); return
        if address in (0x1c6224,0x1c7daa,0x1c7dc4,0x1c7de0):
            assert r0==PI
            old=self.phy.get(r1,0)
            if address==0x1c6224: value=r2
            elif address==0x1c7daa: value=old&r2
            elif address==0x1c7dc4: value=old|r2
            else: value=(old&~r2)|(r3&r2)
            self.phy[r1]=value&0xffff
            if r1==0x402 and value&1: self.remaining=self.busy_reads
            self.ret(); return
        # 任意未建模 ROM 调用即失败，防止悄悄把未知函数当作成功。
        if address<0x180000: raise AssertionError('Unexpected ROM address '+hex(address))

    def call(self,name,selector=None):
        self.u.reg_write(arm.UC_ARM_REG_CPSR,0x13)
        self.u.reg_write(arm.UC_ARM_REG_SP,STACK+0xfff0)
        self.u.reg_write(arm.UC_ARM_REG_LR,STOP|1)
        self.u.reg_write(arm.UC_ARM_REG_R0,PI)
        self.u.reg_write(arm.UC_ARM_REG_R1,selector or 0)
        entry=0x214400|1 if selector is not None else manifest['symbols'][name]
        self.u.emu_start(entry,STOP,count=2000000)
        assert self.u.reg_read(arm.UC_ARM_REG_PC)==STOP
        assert self.u.reg_read(arm.UC_ARM_REG_SP)==STACK+0xfff0
        assert self.u.reg_read(arm.UC_ARM_REG_CPSR)&0xdf==0x13
        return self.u.reg_read(arm.UC_ARM_REG_R0)

def check():
    m=Machine()
    assert m.call('hbl_hw_fire')==9 and m.rf==0 and not m.events
    assert m.call('',0)==0x5850
    assert m.call('',41)==1 and m.rf==0 and m.depth==1
    assert ('delay',15) in m.events and ('delay',10) in m.events
    assert ('delay',500) not in m.events
    # 重复准备幂等；不重复持有、不发射。
    events=len(m.events)
    assert m.call('',41)==1 and len(m.events)==events and m.depth==1
    assert m.word(CONTEXT+16)==1
    for shot in range(1,101):
        at=len(m.events)
        assert m.call('',40)==1
        new=m.events[at:]
        assert new[0]==('start',shot),new[:4]
        assert new[1]==('delay',500)
        assert new.index(('prepare',0))>new.index(('cleanup',0))
        assert m.rf==shot and m.depth==1 and m.word(CONTEXT+16)==1
    assert m.call('',27)==1 and m.depth==0 and m.word(CONTEXT)==0
    assert m.phy[0x471]==0x1240 and m.half(REGS+0x55a)==0x1111 and m.half(REGS+0x55c)==0x2222
    assert m.call('',40)==9 and m.rf==100
    # 长时间未完成的硬件替身：保留原有有限轮询，失败撤销准备。
    m=Machine(-1)
    assert m.call('hbl_hw_prepare')==8 and m.rf==0 and m.depth==0 and m.word(CONTEXT)==0
    m=Machine(); assert m.call('hbl_hw_prepare')==1
    m.fail_after_start=True
    assert m.call('hbl_hw_fire')==10 and m.rf==1 and m.depth==0
    assert m.call('hbl_hw_fire')==9 and m.rf==1
    for field,value,expected in [(STATE+4,0,2),(REGS+0x120,1,5)]:
        m=Machine(); assert m.call('hbl_hw_prepare')==1
        m.put32(field,value)
        assert m.call('hbl_hw_fire')==expected and m.rf==0 and m.depth==0
    m=Machine(); assert m.call('hbl_hw_prepare')==1
    m.put16(REGS+0x55a,0x1234)
    assert m.call('hbl_hw_fire')==11 and m.rf==0 and m.depth==0
    report={'passed':True,'firmwareSha256':manifest['sha256'],'compiledThumbExecuted':True,
            'originalPreparationInstructionsExecuted':True,'prepareHasNoStartWrite':True,
            'repeatedPrepareIdempotent':True,'consecutiveShots':100,'firstFireSideEffectIsStart':True,
            'reprepareAfterEachFire':True,'failureNeverRetriesFire':True,'releaseRestoresSavedValues':True,
            'hardwareModel':'PHY register values, ROM delay, hold/cleanup and MAC release are explicit substitutes',
            'physicalStateRetentionVerified':False,'physicalRadioSilenceDuringPrepareVerified':False,
            'hardwareRequests':0}
    (OUT/'instruction-checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__': check()
