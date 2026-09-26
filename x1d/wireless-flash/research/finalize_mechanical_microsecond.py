"""将本轮装载证据独立留档；不发设备请求。"""
from datetime import datetime, timezone
import json
from pathlib import Path

HERE=Path(__file__).resolve().parents[1]
OUT=HERE/'build/mechanical-sync-candidate'

def finish(loader,session,ready,health,state,checks,qml,upload,recovered_hash,partial,before_pause):
    if loader.io.failed or not loader.io.closed or not loader.record.get('armed') or not loader.record.get('installed'):
        raise RuntimeError('FARM installation incomplete')
    if session.failed or not all(e['matched'] and e['closed'] and e.get('exit_code')==0 for e in session.entries):
        raise RuntimeError('Linux command evidence incomplete')
    if ready['output']!='linux-sync-chain-ready-farm-hook-pending-auto-off\n': raise RuntimeError('Linux chain not ready')
    if 'stage=ready error=0 ' not in health['output'] or ' observe=1 output=1 ' not in health['output']:
        raise RuntimeError('Observer health mismatch')
    for value in ('sync-hook-selftest: own=5 forwarded=272 status=1 hardware=0','qt-receiver-check=3 hardware-requests=0','timerfd-check=3 units=us hardware-requests=0'):
        if value not in checks['output']: raise RuntimeError('Missing target check')
    values={k:int(v) for k,v in (part.split('=',1) for part in state['output'].split())}
    if any(values.get(k)!=v for k,v in {'on':0,'source':3,'delay_us':0,'event':1,'sent':0,'fail':0}.items()):
        raise RuntimeError('Initial worker state mismatch')
    if qml['output'].strip()!='0': raise RuntimeError('QML errors')
    package=json.loads((OUT/'package-validation.json').read_text(encoding='utf-8'))
    if recovered_hash['output'].split()[0]!=package['packageSha256'] or not recovered_hash['closed']:
        raise RuntimeError('Recovered archive hash mismatch')
    if not upload.failed or upload.entries[-1]['label']!='decode-package' or not upload.entries[-1]['closed']:
        raise RuntimeError('Unexpected prior transfer state')
    if not all(e['matched'] and e['closed'] and e.get('exit_code')==0 for e in upload.entries[:-1]):
        raise RuntimeError('An earlier upload operation was ambiguous')
    if not partial.failed or partial.entries[-1].get('usb_error')!='USB_NOT_PRESENT' or partial.entries[-1]['submitted']!=0 or not partial.entries[-1]['closed']:
        raise RuntimeError('Unexpected unplugged session state')
    if not all(e['matched'] and e['closed'] and e.get('exit_code')==0 for e in partial.entries[:-1]):
        raise RuntimeError('An earlier Linux install operation was ambiguous')
    now=datetime.now(timezone.utc)
    folder=OUT/('microsecond-install-'+now.strftime('%Y%m%dT%H%M%SZ'))
    folder.mkdir()
    previous=OUT/'installation.json'
    if previous.exists(): (folder/'previous-installation.json').write_bytes(previous.read_bytes())
    report={'kind':'resident-mechanical-microsecond-continuous','installed':True,'observedAt':now.isoformat(),
        'files':package['files'],'packageSha256':package['packageSha256'],'farmPayloadSha256':package['farmPayloadSha256'],
        'farmRecoveryRecord':str(loader.path.relative_to(HERE)),'linuxEvidence':str(session.output.relative_to(HERE)),
        'farmCaptureEnabled':True,'defaultSource':3,'defaultDelayUs':0,'delayStepUs':10,
        'defaultAutomaticEnabled':False,'workerState':values,'observerHealth':health,'targetChecks':checks,
        'qmlErrorCount':0,'afSpeedsPreserved':loader.record['af_speeds'],'physicalTimingMeasured':False,
        'autoOffCauseNotYetDiagnosed':True,'stickyOffReasonAdded':True,
        'cameraShotsTriggered':0,'agentFlashTrials':0,'farmRequests':loader.io.requests,'farmWrites':loader.io.writes,
        'linuxCommandRequests':sum(e['submitted'] for e in session.entries),'allHandlesClosed':True,
        'priorUploadEvidence':str(upload.output.relative_to(HERE)),
        'priorUploadRequests':sum(e['submitted'] for e in upload.entries),
        'decodeReplyTimedOut':True,'decodeCommandRetried':False,'recoveredArchiveHash':recovered_hash,
        'priorLinuxInstallEvidence':str(partial.output.relative_to(HERE)),
        'priorLinuxInstallRequests':sum(e['submitted'] for e in partial.entries),
        'userStateBeforeCompletion':before_pause,
        'restoreOrder':package['restoreOrder'],'timingLimit':package['timingLimit']}
    text=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
    for path in (folder/'installation.json',previous,HERE/'build/installation.json'):
        path.write_text(text,encoding='utf-8')
    doc=HERE/'MECHANICAL_SYNC_TRIAL.md'; text=doc.read_text(encoding='utf-8')
    start=text.index('当前状态：'); end=text.index('\n\n',start)
    text=text[:start]+'当前状态：十微秒调节增强已重新临时装入用户重启后的 X1D。默认“退出空闲”、0.00 ms、引闪关闭；主参数页原闪光补偿位置为无线引闪入口。10/100/1000 µs 步长可选，各信号独立保留延迟。目标机 Qt 页面、消息接收、高分辨率定时器及 FARM 回读已通过，USB 句柄全部关闭。实际闪光误差未测；自动关闭的原因尚待复现，新版会保留最近关闭原因。'+text[end:]
    text=text.replace('该增强尚未实现或装入；需要同时检查时间单位、报文校验、调度器与界面，不能把可输入 10 µs 等同于实测达到 10 µs 精度。',
        '该增强已实现并装入：界面与通信使用整数微秒，严格十微秒倍数，机械通信版本拒绝旧毫秒包；Linux 消息到达时间转换为微秒后，用 CLOCK_MONOTONIC 绝对 timerfd 截止点等待。主机边界断言、界面替身及目标机三次非发射定时器检查均通过，不能把可输入 10 µs 等同于实测达到 10 µs 精度。')
    doc.write_text(text,encoding='utf-8')
    return {k:report[k] for k in ('installed','defaultSource','delayStepUs','afSpeedsPreserved','allHandlesClosed','farmRequests','farmWrites','linuxCommandRequests')}
