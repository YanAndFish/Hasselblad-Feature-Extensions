"""仅根据已完成的机内检查、回读与会话证据更新安装记录；无设备请求。"""
from datetime import datetime,timezone
import json
from pathlib import Path

HERE=Path(__file__).resolve().parents[1]
OUT=HERE/'build/mechanical-sync-candidate'

def finish(loader,session,linux_ready,health,live,install_log):
    assert Path.cwd().resolve()==HERE.parents[1]
    if session.failed or loader.io.failed or not loader.io.closed or not loader.record.get('installed') or not loader.record.get('armed'):
        raise RuntimeError('Installation evidence incomplete')
    if not all(e['matched'] and e['closed'] and e.get('exit_code')==0 for e in session.entries):
        raise RuntimeError('Incomplete Linux command evidence')
    if linux_ready['output']!='linux-sync-chain-ready-farm-hook-pending-auto-off\n':
        raise RuntimeError('Linux chain not ready')
    if 'stage=ready error=0 ' not in health['output'] or ' observe=1 output=1 ' not in health['output']:
        raise RuntimeError('Observer not ready')
    if 'sync-hook-selftest: own=5 forwarded=272 status=1 hardware=0' not in install_log['output']:
        raise RuntimeError('No successful independent Qt message check')
    state={k:int(v) for k,v in (part.split('=',1) for part in live['output'].split())}
    if state.get('event')!=1 or state.get('on')!=0 or state.get('source')!=1 or state.get('sent')!=0:
        raise RuntimeError('Initial worker state does not match default-off B source')
    package=json.loads((OUT/'package-validation.json').read_text(encoding='utf-8'))
    report={'kind':'resident-mechanical-fpga-gms1-seven-signals','installed':True,
            'observedAt':datetime.now(timezone.utc).isoformat(),'files':package['files'],
            'packageSha256':package['packageSha256'],'farmPayloadSha256':package['farmPayloadSha256'],
            'farmRecoveryRecord':str(loader.path.relative_to(HERE)),'farmCaptureEnabled':True,
            'linuxReady':linux_ready,'observerHealth':health,'workerState':state,'targetQtCheck':install_log,
            'defaultSource':1,'defaultDelayMs':0,'defaultAutomaticEnabled':False,'userRetestPending':True,
            'afSpeedsPreserved':loader.record['af_speeds'],'cameraShotsTriggered':0,'agentFlashTrials':0,
            'physicalTimingMeasured':False,'physicalFlashVerified':False,
            'farmRequests':loader.io.requests,'farmWrites':loader.io.writes,'earlierPreflightReads':5,
            'linuxCommandRequests':sum(e['submitted'] for e in session.entries),'allHandlesClosed':True,
            'restoreOrder':package['restoreOrder'],'timingLimit':package['timingLimit']}
    previous=HERE/'build/installation.json'; backup=OUT/'previous-installation.json'
    if previous.exists() and not backup.exists(): backup.write_bytes(previous.read_bytes())
    text=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
    (OUT/'installation.json').write_text(text,encoding='utf-8'); previous.write_text(text,encoding='utf-8')
    doc=HERE/'MECHANICAL_SYNC_TRIAL.md'; old=doc.read_text(encoding='utf-8')
    first=old.index('当前状态：'); end=old.index('\n\n',first)
    current='当前状态：已临时安装到用户重启后的 X1D。版本、原指令、空白区、机内 Qt 消息分离、接收链及 FARM 回读均通过。七项候选可选，默认 B / 0 ms，引闪关闭；AF 三处速度仍为 3800。USB 句柄已关闭，等待用户实拍；尚未验证物理闪光时序。'
    doc.write_text(old[:first]+current+old[end:],encoding='utf-8')
    return {k:report[k] for k in ('installed','defaultSource','defaultDelayMs','defaultAutomaticEnabled','allHandlesClosed','farmRequests','farmWrites','linuxCommandRequests')}
