"""原厂关闭请求的 ARM 控制流；时钟、队列及物理关闭动作均为替身。"""
from pathlib import Path
import hashlib,json,struct,sys
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[1];OUT=HERE/'build/mechanical-irq-candidate'
sys.path.insert(0,str(ROOT/'.research-cache/x1d-1.25.0/python'))
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn import arm_const as arm
SHA='317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca'
def run(farm):
    assert hashlib.sha256(farm).hexdigest()==SHA
    cases=[]
    for mode in ('busy-suc','recently-used','idle'):
        u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0x100000,0x1c0000);u.mem_write(0x100000,farm)
        u.mem_map(0x6b0000,0x40000);u.mem_map(0x3000000,0x10000)
        def put(a,v):u.mem_write(a,struct.pack('<I',v))
        put(0x6db2c4,0x6ef000);put(0x6db2c0,0x6ef100);put(0x2b20cc,1)
        for i in range(26):
            a=0x6dae18+44*i;put(a+4,9900 if mode=='recently-used' and i==21 else 0)
            put(a+12,1 if mode=='busy-suc' and i==21 else 0)
        calls=[];replies=[]
        def hook(uc,a,n,_):
            regs=[uc.reg_read(r) for r in (arm.UC_ARM_REG_R0,arm.UC_ARM_REG_R1,arm.UC_ARM_REG_R2,arm.UC_ARM_REG_R3)]
            calls.append((a,regs))
            if a==0x2209f4:raise AssertionError('原厂断言')
            if a==0x1e80d0:replies.append(bytes(uc.mem_read(regs[0],5)));result=0
            elif a==0x22a924:result=10000
            elif a in (0x186b70,0x186500):
                assert regs[0]==0x6ef000
                result=1
            elif a==0x22c784:
                assert regs[0]==0;put(0x2b20cc,0);result=0
            else:result=0
            uc.reg_write(arm.UC_ARM_REG_R0,result);uc.reg_write(arm.UC_ARM_REG_PC,uc.reg_read(arm.UC_ARM_REG_LR))
        stubs=(0x2209f4,0x1e80d0,0x22a924,0x236a14,0x186b70,0x186500,0x18a020,
               0x239714,0x227870,0x22ab60,0x22ad5c,0x22ab30,0x22067c,0x22c784)
        for a in stubs:u.hook_add(UC_HOOK_CODE,hook,begin=a,end=a)
        u.mem_write(0x6c37f4,bytes.fromhex('1b02080100'))
        u.reg_write(arm.UC_ARM_REG_CPSR,0x60000013);u.reg_write(arm.UC_ARM_REG_SP,0x300f000)
        u.reg_write(arm.UC_ARM_REG_R0,0x6c37f4);u.reg_write(arm.UC_ARM_REG_LR,0x3200000)
        u.emu_start(0x1e1964,0x3200000,count=100000)
        assert u.reg_read(arm.UC_ARM_REG_PC)==0x3200000
        assert replies==[bytes.fromhex('1c020108')+bytes([0 if mode=='idle' else 3])]
        if mode!='idle':
            assert not any(a in (0x239714,0x227870,0x22ab60,0x22ad5c,0x22ab30,0x22067c,0x22c784) for a,_ in calls)
            assert bytes(u.mem_read(0x2b20cc,1))==b'\x01'
            assert sum(a==0x18a020 for a,_ in calls)==1
        else:
            assert [regs[:2] for a,regs in calls if a==0x22067c]==[[20,0],[21,0]]
            assert bytes(u.mem_read(0x2b20cc,1))==b'\x00'
        assert sum(a==0x186500 for a,_ in calls)==1
        cases.append({'mode':mode,'replyStatus':replies[0][4],'originalLockAndResourceChecksExecuted':True})
    report={'passed':True,'hardwareRequests':0,'cases':cases,'physicalShutdownAndClockAreStubs':True,
            'busyReplyMayScheduleOriginalDeferredShutdown':True,'physicalShutdownNotValidated':True,
            'sourceHashes':{str(Path(__file__).relative_to(HERE)):hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
    (OUT/'irq-power-down-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report
if __name__=='__main__':
    sys.path.insert(0,str(ROOT/'x1d/tools'));from farm_diagnostic_binary import FarmApplication
    print(json.dumps(run(FarmApplication().data),ensure_ascii=False))
