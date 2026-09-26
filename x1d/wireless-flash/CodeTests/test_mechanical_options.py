"""执行双准备模式实际 Thumb 分发与原准备函数；外设/ROM 使用显式模型。"""
from pathlib import Path
import json

HERE=Path(__file__).resolve().parents[1]
OUT=HERE/'build/mechanical-options-candidate'
original=(HERE/'CodeTests/test_mechanical_hw_ready.py').read_text(encoding='utf-8')
original=original.replace("build/mechanical-hw-ready-candidate","build/mechanical-options-candidate").replace('0x5850','0x5851')
scope={'__file__':str(Path(__file__)), '__name__':'original_hold_tests'}
exec(compile(original,str(Path(__file__)), 'exec'),scope)
scope['check']()
Machine=scope['Machine']
CONTEXT,REGS,STATE=scope['CONTEXT'],scope['REGS'],scope['STATE']

def check():
    m=Machine()
    assert m.call('',42)==1 and m.rf==0 and not m.events
    for shot in range(1,101):
        start=len(m.events)
        assert m.call('',43)==1
        events=m.events[start:]
        assert events.index(('prepare',0))<events.index(('start',shot))
        assert events.count(('prepare',0))==1
        assert events.index(('cleanup',0))>events.index(('start',shot))
        assert m.rf==shot and m.depth==0 and m.word(CONTEXT)==0
        assert m.half(REGS+0x55a)==0x1111 and m.half(REGS+0x55c)==0x2222
    # 保持态拒绝逐次 fire，不进行隐式清理或重复射频输出。
    assert m.call('',41)==1
    before=list(m.events)
    assert m.call('',43)==9 and m.events==before and m.rf==100
    # 42 明确撤销保持态，保留波形/MAC 资格。旧保持 fire 必须拒绝。
    assert m.call('',42)==1 and m.depth==0
    assert m.call('',40)==9 and m.rf==100
    assert m.call('',43)==1 and m.rf==101 and m.depth==0
    assert m.call('',41)==1 and m.depth==1
    assert m.call('',40)==1 and m.rf==102 and m.depth==1
    assert m.call('',27)==1 and m.depth==0 and m.word(CONTEXT)==0
    assert m.call('',43)==2 and m.rf==102
    # 两种模式均遵守旧错误白名单；准备轮询失败不引闪。
    m=Machine(-1)
    assert m.call('',42)==1
    assert m.call('',43)==8 and m.rf==0 and m.depth==0
    for field,value,expected in [(STATE+4,0,2),(REGS+0x120,1,5)]:
        m=Machine(); m.put32(field,value)
        assert m.call('',42)==expected and m.call('',43)==expected and m.rf==0
    p=OUT/'instruction-checks.json'
    report=json.loads(p.read_text(encoding='utf-8'))
    report.update(perShotConsecutiveShots=100,perShotOriginalThumbExecuted=True,
                  perShotPreparesBeforeEachStart=True,perShotHasNoReprepareAfterFire=True,
                  modeSwitchReleaseVerified=True,crossModeFireRejected=True)
    p.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('two-mode instruction checks passed; hardware=0')

if __name__=='__main__': check()
