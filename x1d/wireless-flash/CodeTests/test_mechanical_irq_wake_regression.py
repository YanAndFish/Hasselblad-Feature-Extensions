"""固定故障候选的正常唤醒等待回归；仅 ARM 和模拟 MMIO，不连接设备。"""
from pathlib import Path
import hashlib
import json
import sys

HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[1]
OUT=HERE/'build/mechanical-irq-candidate'
sys.path.insert(0,str(Path(__file__).parent))
import test_mechanical_irq_pcap_guard as guard
from unicorn import UC_HOOK_MEM_READ,UC_HOOK_CODE
from unicorn import arm_const as arm

class WakeModel(guard.ResourceModel):
    def __init__(self,farm,build,patched,ready_after=8192):
        super().__init__(farm,'ready-stuck',build,upper_guard=patched)
        self.ready_reads=0;self.ready_reached=False
        def read(uc,access,a,n,v,_):
            self.ready_reads+=1
            self.put(a,0x100 if self.ready_reads>=ready_after else 0)
        def code(uc,a,n,_):
            if a==0x188624:
                # 就绪等待读取 1024 次才过一个 tick，打破旧模型每调用 +100。
                uc.reg_write(arm.UC_ARM_REG_R0,self.ready_reads//1024)
            if a==0x22cdb4:self.ready_reached=True;uc.emu_stop()
        self.u.hook_add(UC_HOOK_MEM_READ,read,begin=guard.old.REG+0x80,end=guard.old.REG+0x80)
        self.u.hook_add(UC_HOOK_CODE,code)

class ScheduledWakeModel(guard.ResourceModel):
    def __init__(self,farm,build,ready_tick):
        super().__init__(farm,'ready-stuck',build)
        self.elapsed=0;self.ready_reached=False
        def code(uc,a,n,_):
            if a==0x187bd8:
                self.elapsed+=1 # 一次 SLEEP(1) 的原厂调度行为为显式替身。
            if a==0x188624:uc.reg_write(arm.UC_ARM_REG_R0,self.elapsed)
            if a==0x22cdb4:self.ready_reached=True;uc.emu_stop()
        def read(uc,access,a,n,v,_):self.put(a,0x100 if self.elapsed>=ready_tick else 0)
        self.u.hook_add(UC_HOOK_CODE,code)
        self.u.hook_add(UC_HOOK_MEM_READ,read,begin=guard.old.REG+0x80,end=guard.old.REG+0x80)

def run(farm):
    assert Path.cwd().resolve()==ROOT
    saved=OUT/'fault-stage-20260912'
    build=json.loads((saved/'irq-pcap-guard-build.json').read_text(encoding='utf-8'))
    # 保留失败候选，后续构建不得覆写此证据。
    original_out=guard.OUT;guard.OUT=saved
    try:
        baseline=WakeModel(farm,build,False).run(0x22e6e4,limit=2000000)
        candidate=WakeModel(farm,build,True).run(0x22e6e4,limit=2000000)
    finally:guard.OUT=original_out
    assert baseline.ready_reached and baseline.ready_reads==8192 and not baseline.returned
    assert not candidate.ready_reached and candidate.returned and candidate.result==1
    assert candidate.ready_reads==4096 and not candidate.dma_started
    current=json.loads((OUT/'irq-pcap-guard-build.json').read_text(encoding='utf-8'))
    fixed=WakeModel(farm,current,True)
    fixed.put(current['entries']['mechanical_irq_guard_active'],0)
    fixed.run(0x22e6e4,limit=2000000)
    assert fixed.ready_reached and fixed.ready_reads==8192
    assert 0x188624 not in fixed.calls and 0x187bd8 not in fixed.calls
    stage=json.loads((OUT/'irq-stage-build.json').read_text(encoding='utf-8'))
    stage['payloadFile']='irq-stage.bin'
    integrated=WakeModel(farm,stage,True)
    integrated.put(stage['entries']['mechanical_irq_guard_active'],0)
    integrated.run(0x22e6e4,limit=2000000)
    assert integrated.ready_reached and integrated.ready_reads==8192
    assert 0x188624 not in integrated.calls and 0x187bd8 not in integrated.calls
    scheduled=[]
    for ready_tick in (8,399,400,401):
        m=ScheduledWakeModel(farm,current,ready_tick).run(0x22e6e4)
        assert m.ready_reached==(ready_tick<=400)
        assert m.elapsed==min(ready_tick,400)
        if ready_tick>400:assert m.returned and m.result==1 and not m.dma_started
        scheduled.append({'readyTick':ready_tick,'waitedTicks':m.elapsed,'readyReached':m.ready_reached})
    report={'passed':True,'hardwareRequests':0,'firmwareSha256':guard.old.FARM_SHA,
      'testedGuardSha256':build['sha256'],'stockReachesReady':True,'candidatePrematurelyFails':True,
      'stockReadyReads':baseline.ready_reads,'candidateReadyReads':candidate.ready_reads,
      'modeledElapsedTicksAtCandidateFailure':candidate.ready_reads//1024,
      'candidateTickLimit':400,'hardwareFaultRootCauseConfirmed':False,
      'normalWakeWaitRegressionConfirmedInArmModel':True,
      'fixedGuardSha256':current['sha256'],'inactiveGuardPreservesOriginalDelayedReady':True,
      'fixedStageSha256':stage['sha256'],'integratedStagePreservesOriginalDelayedReady':True,
      'fixedInactivePathDoesNotCallNewTickOrSleep':True,'explicitReloadWaitCases':scheduled,
      'schedulerAndReadinessAreModels':True,
      'sourceHashes':{str(p.relative_to(HERE)):hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in (Path(__file__),Path(guard.__file__),Path(guard.old.__file__))}}
    (OUT/'wake-regression-reproduction.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report

if __name__=='__main__':
    sys.path.insert(0,str(ROOT/'x1d/tools'))
    from farm_diagnostic_binary import FarmApplication
    print(json.dumps(run(FarmApplication().data),ensure_ascii=False))
