"""原厂完整 PCAP 下载与真实 ARM 有界复位候选的组合回放。"""
from pathlib import Path
import hashlib
import json
import struct
import sys

HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[1]
OUT=HERE/'build/mechanical-irq-candidate'
sys.path.insert(0,str(Path(__file__).parent))
import test_mechanical_irq_pcap as old
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn import arm_const as arm

class Model(old.Model):
    def __init__(self,farm,mode,build,guard=True):
        super().__init__(farm,mode)
        self.build=build;self.cpsr=0x60000013
        self.allowed_state_writes={build['entries']['mechanical_irq_download_state']}
        if guard:
            payload=(OUT/build.get('payloadFile','irq-pcap-guard.bin')).read_bytes()
            assert hashlib.sha256(payload).hexdigest()==build['sha256']
            self.u.mem_write(build['base'],payload)
            assert farm[0x22b910-0x100000:0x22b914-0x100000]==bytes.fromhex('f9feffeb')
            target=build['entries']['mechanical_irq_reset_call_guard']
            self.put(0x22b910,0xeb000000|(((target-0x22b910-8)//4)&0xffffff))
        if 'mechanical_irq_guard_active' in build['entries']:
            self.put(build['entries']['mechanical_irq_guard_active'],1)
        if mode=='queue-stuck':self.status|=0x80000000
        if mode=='masked-irq':self.cpsr|=0x80
        if mode=='irq-context':self.cpsr=0x60000012
        if mode=='bad-instance':self.put(old.INSTANCE+8,0)
        if mode=='encrypted-rate':self.ctrl|=0x1000;self.mode='success'

        def write(uc,access,a,n,v,_):
            if a==old.REG and mode=='init-rise-stuck':self.status&=~0x10
            if a==old.REG and mode=='frozen-clock':self.status|=0x10

        def code(uc,a,n,_):
            if a==0x188624 and mode=='frozen-clock':uc.reg_write(arm.UC_ARM_REG_R0,0)
            if a==0x188624 and mode=='wrap-clock':
                uc.reg_write(arm.UC_ARM_REG_R0,(self.tick-300)&0xffffffff)
        self.u.hook_add(UC_HOOK_MEM_WRITE,write)
        self.u.hook_add(UC_HOOK_CODE,code)

    def run(self,entry=0x22b800,limit=500000):
        u=self.u;u.reg_write(arm.UC_ARM_REG_CPSR,self.cpsr)
        u.reg_write(arm.UC_ARM_REG_SP,old.STACK+0x3000);u.reg_write(arm.UC_ARM_REG_LR,old.STOP)
        u.emu_start(entry,old.STOP,count=limit)
        self.returned=u.reg_read(arm.UC_ARM_REG_PC)==old.STOP
        self.result=u.reg_read(arm.UC_ARM_REG_R0)
        return self

class ResourceModel(Model):
    """真实上层控制流；资源锁、GPIO 和 SLCR 为明确替身，不模拟恢复成功。"""
    def __init__(self,farm,mode,build,upper_guard=True):
        super().__init__(farm,mode,build)
        self.resource_calls=[];self.resume_reached=False
        self.put(0x2b20cc,1 if mode=='already-on' else 0)
        if mode=='ready-stuck':self.put(old.REG+0x80,0)
        if upper_guard:
            for address,name,link in ((0x22ceb8,'mechanical_irq_download_call_guard',True),
                                      (0x22cd90,'mechanical_irq_ready_branch_guard',False)):
                target=build['entries'][name]
                self.put(address,(0xeb000000 if link else 0xea000000)|(((target-address-8)//4)&0xffffff))
            self.put(build['entries']['mechanical_irq_download_state'],0)
        def code(uc,a,n,_):
            if a in (0x22a9a4,0x22aa98,0x22067c,0x22acfc):
                args=[uc.reg_read(r) for r in (arm.UC_ARM_REG_R0,arm.UC_ARM_REG_R1,arm.UC_ARM_REG_R2)]
                self.resource_calls.append((a,args))
                uc.reg_write(arm.UC_ARM_REG_R0,1 if a==0x22a9a4 else 0)
                uc.reg_write(arm.UC_ARM_REG_PC,uc.reg_read(arm.UC_ARM_REG_LR))
            elif a in (0x22ab60,0x22ad2c,0x22ad5c,0x22cb08,0x2279e4,0x22c784):
                self.resume_reached=True
                uc.emu_stop() # 未模拟的资源恢复绝不当作执行成功。
        self.u.hook_add(UC_HOOK_CODE,code)

def run(farm):
    assert Path.cwd().resolve()==ROOT
    build=json.loads((OUT/'irq-pcap-guard-build.json').read_text(encoding='utf-8'))
    for name,digest in build['sourceHashes'].items():assert hashlib.sha256((HERE/name).read_bytes()).hexdigest()==digest
    results=[]
    for mode in ('success','encrypted-rate','dma-error','dma-timeout','init-stuck','init-rise-stuck','queue-stuck','frozen-clock','wrap-clock','masked-irq','irq-context'):
        m=Model(farm,mode,build).run()
        assert m.returned,mode
        success=mode in ('success','encrypted-rate')
        assert (m.result==0)==success,(mode,m.result)
        if mode in ('init-stuck','init-rise-stuck','queue-stuck','frozen-clock','masked-irq','irq-context'):
            assert not m.dma_started,mode
        if success:
            baseline=Model(farm,mode,build,False).run()
            assert baseline.returned and baseline.result==0 and m.mmio==baseline.mmio
        results.append({'mode':mode,'returned':True,'result':m.result,'dmaStarted':m.dma_started,
            'instructionsExecuted':sum(m.visits.values()),'successfulMmioMatchesOriginal':True if success else None})
    # 独立入口检查状态码；前置条件失败不能写复位寄存器。
    for mode,expected in (('success',0),('init-stuck',11),('init-rise-stuck',12),('queue-stuck',13),('frozen-clock',11),('masked-irq',10),('irq-context',10),('bad-instance',10)):
        m=Model(farm,mode,build).run(build['entries']['mechanical_irq_bounded_reset'])
        assert m.returned and m.result==expected,(mode,m.returned,m.result)
        if expected==10:assert not m.mmio
    resource_cases=[]
    for mode in ('ready-stuck','init-stuck','init-rise-stuck','dma-error','dma-timeout'):
        m=ResourceModel(farm,mode,build).run(0x22e6e4)
        assert m.returned and m.result==1 and not m.resume_reached,mode
        assert [a for a,args in m.resource_calls].count(0x22aa98)==1
        assert [args[:2] for a,args in m.resource_calls if a==0x22067c]==[[20,1],[21,1]]
        if mode=='ready-stuck':assert not m.mmio and not m.dma_started
        assert m.u.mem_read(build['entries']['mechanical_irq_download_state'],4)==struct.pack('<I',0 if mode=='ready-stuck' else 3)
        resource_cases.append({'mode':mode,'failureReturnedThroughOriginalWrapper':True,
            'resourceLockReleasedInModel':True,'successResumeNotReached':True,
            'gpioAndSlcrAreStubs':True,'runningHardwareRestored':False})
    negative=ResourceModel(farm,'dma-error',build,False).run(0x22e6e4)
    assert negative.resume_reached and not negative.returned
    already_on=ResourceModel(farm,'already-on',build).run(0x22e6e4)
    assert already_on.returned and already_on.result==0 and not already_on.dma_started and not already_on.resume_reached
    assert already_on.u.mem_read(build['entries']['mechanical_irq_download_state'],4)==bytes(4)
    # 普通资源申请必须透传原厂语义，不能启用专用装载的保护。
    caller=ResourceModel(farm,'dma-error',build)
    target=build['entries']['mechanical_irq_resource_call_guard']
    caller.put(0x22dbb0,0xeb000000|(((target-0x22dbb0-8)//4)&0xffffff))
    caller.put(build['entries']['mechanical_irq_guard_active'],0)
    outer_fp=old.STACK+0x3800
    caller.put(outer_fp-4,0);caller.put(outer_fp,old.STOP)
    caller.u.reg_write(arm.UC_ARM_REG_R11,outer_fp)
    caller.run(0x22dbb0)
    assert caller.resume_reached and not caller.returned
    assert not caller.u.mem_read(build['entries']['mechanical_irq_download_state'],4).strip(b'\0')
    report={'passed':True,'installed':False,'hardwareRequests':0,'cases':results,'directReturnCases':8,
        'firmwareSha256':old.FARM_SHA,'guardSha256':build['sha256'],
        'realOriginalDownloadInstructionsExecuted':True,'peripheralsModeled':True,
        'resetFailurePreventsDma':True,'originalHighLevelErrorPropagationStillUnimplemented':False,
        'resourceFailureCases':resource_cases,'unmodifiedHighLevelContinuesAfterDownloadFailure':True,
        'alreadyOnReturnsSuccessWithoutDownloadConfirmed':True,
        'normalResourceCallerPreservesOriginalBehavior':True,'otherCallerOuterFrameModeled':True,
        'guardsRequireExplicitStageActivation':True,
        'fullResourceRecoveryImplemented':False,'sourceHashes':{str(p.relative_to(HERE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),Path(old.__file__))}}
    (OUT/'irq-pcap-guard-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report

if __name__=='__main__':
    sys.path.insert(0,str(ROOT/'x1d/tools'))
    from farm_diagnostic_binary import FarmApplication
    print(json.dumps(run(FarmApplication().data),ensure_ascii=False))
