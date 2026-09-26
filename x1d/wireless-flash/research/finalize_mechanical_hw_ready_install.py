"""根据实际装载证据登记芯片预准备版本；不执行硬件请求。"""
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json

HERE=Path(__file__).resolve().parents[1]
OUT=HERE/'build/mechanical-hw-ready-candidate'
INDEX=HERE/'build/mechanical-sync-candidate/installation.json'

def finish(loader,session,ready,health,checks,qml,runtime,marker,worker_status,prior_probe,upload_session=None,repair_failures=()):
    if loader.io.failed or not loader.io.closed or not loader.record.get('installed') or not loader.record.get('armed'):
        raise RuntimeError('FARM not verified')
    if session.failed or not session.entries or not all(e['matched'] and e['closed'] and e.get('exit_code')==0 for e in session.entries):
        raise RuntimeError('Linux session incomplete')
    if not all(e['matched'] and e['closed'] for e in prior_probe.entries):
        raise RuntimeError('Initial probe closure unknown')
    package=json.loads((OUT/'package-validation.json').read_text(encoding='utf-8'))
    digest=hashlib.sha256((OUT/'session-package.tar.gz').read_bytes()).hexdigest()
    if digest!=package['packageSha256']: raise RuntimeError('Package changed')
    source_session=upload_session or session
    archive_digest=digest
    if upload_session is not None:
        old=json.loads((OUT/'before-probe-layout-fix/package-validation.json').read_text(encoding='utf-8'))
        archive_digest=old['packageSha256']
        if hashlib.sha256((OUT/'before-probe-layout-fix/session-package.tar.gz').read_bytes()).hexdigest()!=archive_digest:
            raise RuntimeError('Original uploaded archive changed')
        if not upload_session.failed or upload_session.entries[-1]['label']!='install-linux':
            raise RuntimeError('Unexpected original installation failure')
        if not all(e['matched'] and e['closed'] and e.get('exit_code')==0 for e in upload_session.entries[:-1]):
            raise RuntimeError('Upload failed before install check')
        if not upload_session.entries[-1]['matched'] or not upload_session.entries[-1]['closed']:
            raise RuntimeError('Original install outcome unknown')
        changed=[n for n in old['files'] if old['files'][n]!=package['files'][n]]
        if set(changed)!={'netlink-probe','manifest.sha256'}: raise RuntimeError('Repair exceeded probe scope')
        repair=json.loads((OUT/'probe-layout-repair.json').read_text(encoding='utf-8'))
        if repair['newSha256']!=package['files']['netlink-probe']['sha256']: raise RuntimeError('Repair hash changed')
        if not any(e['label']=='corrected-files-verified' and e['output']=='corrected-files-verified' for e in session.entries):
            raise RuntimeError('Corrected file set not verified')
        for failed in repair_failures:
            if not all(e['matched'] and e['closed'] for e in failed.entries): raise RuntimeError('Repair session outcome unknown')
    dispatched=[e for e in source_session.entries if e['label']=='decode-dispatched']
    verified=[e for e in source_session.entries if e['label'].startswith('verify-existing-archive-') and e['output'].split() and e['output'].split()[0]==archive_digest]
    extracted=[e for e in source_session.entries if e['label']=='extract-and-verify' and e['output']=='package-verified']
    if len(dispatched)!=1 or len(verified)!=1 or len(extracted)!=1: raise RuntimeError('Archive evidence incomplete')
    if ready['output']!='linux-sync-chain-ready-farm-hook-pending-auto-off\n': raise RuntimeError('Linux ready mismatch')
    if 'stage=ready error=0 ' not in health['output'] or ' observe=1 output=1 ' not in health['output']: raise RuntimeError('Observer mismatch')
    for text in ('sync-hook-selftest: own=5 forwarded=272 status=1 hardware=0',
                 'qt-receiver-check=3 hardware-requests=0','timerfd-check=3 units=us hardware-requests=0'):
        if text not in checks['output']: raise RuntimeError('Missing target check')
    if qml['output'].strip()!='0': raise RuntimeError('QML failed')
    if runtime['output']!='ui-loaded-worker-default-off\nactive\nactive\nactive\n': raise RuntimeError('Runtime mismatch')
    if worker_status['output']!='worker-ready-default-off\n': raise RuntimeError('Worker startup mismatch')
    if marker['output']!='normal-driver-marker=0x5850\n': raise RuntimeError('Firmware not reached through normal driver')
    now=datetime.now(timezone.utc)
    folder=OUT/('install-'+now.strftime('%Y%m%dT%H%M%SZ'));folder.mkdir()
    if INDEX.exists(): (folder/'previous-installation.json').write_bytes(INDEX.read_bytes())
    report={'kind':'resident-mechanical-chip-prepared-no-diagnostics','installed':True,
            'observedAt':now.isoformat(),'packageSha256':digest,'firmwareSha256':package['firmwareSha256'],
            'farmPayloadSha256':package['farmPayloadSha256'],'files':package['files'],
            'farmRecoveryRecord':str(loader.path.relative_to(HERE)),
            'linuxEvidence':str(session.output.relative_to(HERE)),
            'initialMissingTemporaryChainProbe':str(prior_probe.output.relative_to(HERE)),
            'priorProbeEntries':prior_probe.entries,'archiveDecodeDispatches':1,
            'defaultAutomaticEnabled':False,'defaultSource':3,'defaultDelayUs':0,'delayStepUs':10,
            'sourcesRetained':7,'flashParameterTransmissionImplemented':False,
            'continuousDiagnostics':False,'liveCounterTelemetryAvailable':False,
            'workerStartupStatus':worker_status,'observerHealth':health,'targetChecks':checks,
            'runtimeAndServices':runtime,'normalDriverMarker':marker,'qmlErrorCount':0,
            'afSpeedsPreserved':loader.record['af_speeds'],'farmCaptureEnabled':True,
            'farmRequests':loader.io.requests,'farmWrites':loader.io.writes,
            'linuxCommandRequests':sum(e['submitted'] for e in session.entries),
            'allHandlesClosed':True,'agentFlashTrials':0,'cameraShotsTriggered':0,
            'physicalReadyRetentionVerified':False,'physicalEmissionDuringPrepareVerified':False,
            'physicalTimingMeasured':False,'waveformBytesUnchanged':True,
            'prepareTiming':'Radio becomes ready only after chip prepare completion; prepare again after each fire',
            'instructionChecks':package['instructionChecks'],'clientChecks':package['clientChecks']}
    if upload_session is not None:
        report.update(originalUploadEvidence=str(upload_session.output.relative_to(HERE)),
                      originalUploadedArchiveSha256=archive_digest,
                      originalUploadAndAttemptRequests=sum(e['submitted'] for e in upload_session.entries),
                      correctedProbeLayout=repair,
                      repairAttemptEvidence=[str(s.output.relative_to(HERE)) for s in repair_failures],
                      repairAttemptRequests=sum(e['submitted'] for s in repair_failures for e in s.entries),
                      initialProbeCrashCorrectedAndTargetRetested=True)
    encoded=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
    for path in (folder/'installation.json',OUT/'installation.json',INDEX,HERE/'build/installation.json'):
        path.write_text(encoded,encoding='utf-8')
    doc=HERE/'MECHANICAL_SYNC_TRIAL.md';s=doc.read_text(encoding='utf-8')
    a=s.index('当前状态：');b=s.index('\n\n',a)
    s=s[:a]+'当前状态：无持续诊断、芯片预准备版本已完整临时装入 X1D。无线准备成功后才显示就绪；准备与等待移出拍摄触发入口，每次发射结束后准备下一次。七个触发节点、10 µs 调节和原无线波形保留，尚未增加闪光灯设置数据发送。目标机正常驱动、接收自检、页面及 FARM 回读已通过，默认自动引闪关闭，AF 三处速度保持 3800，USB 句柄已关闭。待发状态长期保持和实际时序改善仍待用户实拍验证。'+s[b:]
    doc.write_text(s,encoding='utf-8')
    research=HERE/'research/MECHANICAL_MINIMAL_PATH.md'
    r=research.read_text(encoding='utf-8')
    r=r.replace('当前机内为第一版；无诊断第二版已离线构建、封包，未安装。',
                '本报告记录第一版、无诊断版及芯片预准备版的演进；芯片预准备版现已完整临时装入，最新安装证据见 `build/mechanical-hw-ready-candidate/installation.json`。')
    r+='\n本轮机内装载已完成。配套检查程序首次因 ARM 动态重定位区不连续而崩溃；改用已验证的连续链接布局后，机内正常驱动检查及完整安装通过。失败记录、原始上传包、精确字节修复、重新校验和成功记录均保留。准备状态长期保持及实际引闪波动仍待用户试拍；未把软件安装成功写成物理验证成功。\n'
    research.write_text(r,encoding='utf-8')
    return {k:report[k] for k in ('installed','afSpeedsPreserved','allHandlesClosed','farmRequests','farmWrites','linuxCommandRequests')}
