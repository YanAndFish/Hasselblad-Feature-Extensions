"""第一版触发路径优化完整重装的证据收尾；导入和调用均不发相机请求。"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
OUT = HERE / 'build/mechanical-sync-candidate'


def finish(loader, session, ready, health, state, checks, qml, runtime, prior_upload=None, recovered_hash=None):
    if loader.io.failed or not loader.io.closed or not loader.record.get('armed') or not loader.record.get('installed'):
        raise RuntimeError('FARM installation incomplete')
    if session.failed or not session.entries or not all(
            e['matched'] and e['closed'] and e.get('exit_code') == 0 for e in session.entries):
        raise RuntimeError('Linux evidence incomplete')
    if ready['output'] != 'linux-sync-chain-ready-farm-hook-pending-auto-off\n':
        raise RuntimeError('Linux ready marker mismatch')
    if 'stage=ready error=0 ' not in health['output'] or ' observe=1 output=1 ' not in health['output']:
        raise RuntimeError('Observer health mismatch')
    for expected in ('sync-hook-selftest: own=5 forwarded=272 status=1 hardware=0',
                     'qt-receiver-check=3 hardware-requests=0',
                     'timerfd-check=3 units=us hardware-requests=0'):
        if expected not in checks['output']:
            raise RuntimeError('Target self-check missing')
    values = {k: int(v) for k, v in (p.split('=', 1) for p in state['output'].split())}
    if any(values.get(k) != v for k, v in {'on': 0, 'source': 3, 'delay_us': 0, 'event': 1, 'sent': 0, 'fail': 0}.items()):
        raise RuntimeError('Default worker state mismatch')
    if qml['output'].strip() != '0':
        raise RuntimeError('QML error count mismatch')
    if runtime['output'] != 'ui-loaded-worker-default-off\nactive\nactive\nactive\n':
        raise RuntimeError('Runtime or services not ready')
    from mechanical_sync_loader import offline_ready
    if not offline_ready():
        raise RuntimeError('Offline source evidence changed')
    package = json.loads((OUT / 'package-validation.json').read_text(encoding='utf-8'))
    build = json.loads((OUT / 'manifest.json').read_text(encoding='utf-8'))
    if build['checks'].get('prepared_requests') != 1000 or not build['checks'].get('microsecond_deadlines'):
        raise RuntimeError('Fast path checks missing')
    digest = hashlib.sha256((OUT / 'session-package.tar.gz').read_bytes()).hexdigest()
    decodes = [e for e in session.entries if e['label'] == 'decode-package']
    extracted = [e for e in session.entries if e['label'] == 'extract-and-verify']
    if digest != package['packageSha256']:
        raise RuntimeError('Local archive changed')
    if prior_upload is None:
        if len(decodes) != 1 or decodes[0]['output'].split()[0] != digest:
            raise RuntimeError('Uploaded archive not verified')
    else:
        if not prior_upload.failed or not prior_upload.entries or decodes:
            raise RuntimeError('Unexpected prior upload state')
        last = prior_upload.entries[-1]
        if last['label'] != 'decode-package' or last['submitted'] != 1 or not last['closed'] or last.get('usb_error') != 'USB_READ':
            raise RuntimeError('Unexpected decode failure')
        if not all(e['matched'] and e['closed'] and e.get('exit_code') == 0 for e in prior_upload.entries[:-1]):
            raise RuntimeError('An earlier upload operation failed')
        hashes = [e for e in session.entries if e['label'] == 'verify-existing-archive']
        if len(hashes) != 1 or not recovered_hash or hashes[0]['output'] != recovered_hash['output'] or recovered_hash['output'].split()[0] != digest:
            raise RuntimeError('Independent archive verification missing')
    if len(extracted) != 1 or extracted[0]['output'] != 'package-verified':
        raise RuntimeError('Extracted archive not verified')
    now = datetime.now(timezone.utc)
    folder = OUT / ('fast-install-' + now.strftime('%Y%m%dT%H%M%SZ'))
    folder.mkdir()
    previous = OUT / 'installation.json'
    if previous.exists():
        (folder / 'previous-installation.json').write_bytes(previous.read_bytes())
    report = {
        'kind': 'resident-mechanical-prepared-trigger-fast-v1', 'installed': True,
        'observedAt': now.isoformat(), 'files': package['files'],
        'packageSha256': digest, 'farmPayloadSha256': package['farmPayloadSha256'],
        'farmRecoveryRecord': str(loader.path.relative_to(HERE)),
        'linuxEvidence': str(session.output.relative_to(HERE)),
        'farmCaptureEnabled': True, 'defaultSource': 3, 'defaultDelayUs': 0,
        'delayStepUs': 10, 'defaultAutomaticEnabled': False,
        'workerState': values, 'observerHealth': health, 'targetChecks': checks,
        'qmlErrorCount': 0, 'runtimeAndServices': runtime,
        'afSpeedsPreserved': loader.record['af_speeds'],
        'physicalTimingMeasured': False, 'autoOffCauseNotYetDiagnosed': True,
        'preparedRequestChecks': 1000, 'waveformChanged': False,
        'hardwareInterruptImplemented': False, 'schedulerPolicyChanged': False,
        'cameraShotsTriggered': 0, 'agentFlashTrials': 0,
        'farmRequests': loader.io.requests, 'farmWrites': loader.io.writes,
        'linuxCommandRequests': sum(e['submitted'] for e in session.entries),
        'allHandlesClosed': True, 'restoreOrder': package['restoreOrder'],
        'timingLimit': package['timingLimit']}
    if prior_upload is not None:
        report.update(priorUploadEvidence=str(prior_upload.output.relative_to(HERE)),
                      priorUploadRequests=sum(e['submitted'] for e in prior_upload.entries),
                      decodeReplyTimedOut=True, decodeCommandRetried=False,
                      recoveredArchiveHash=recovered_hash)
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    for path in (folder / 'installation.json', previous, HERE / 'build/installation.json'):
        path.write_text(encoded, encoding='utf-8')
    doc = HERE / 'MECHANICAL_SYNC_TRIAL.md'
    text = doc.read_text(encoding='utf-8')
    start = text.index('当前状态：'); end = text.index('\n\n', start)
    text = text[:start] + '当前状态：第一版触发路径优化已在本次重新开机后完整临时装入 X1D。已提前编码下一次发射请求，触发样本改为固定内存记录，延后诊断格式化与写入；FARM 载荷、无线波形和 AF 速度保持。默认“退出空闲”、0.00 ms、引闪关闭，调节最小步长 10 µs。目标机接收、自检、界面和 FARM 回读通过，USB 句柄已关闭；物理延迟与波动的改善仍待用户试拍验证。' + text[end:]
    doc.write_text(text, encoding='utf-8')
    return {k: report[k] for k in ('installed', 'afSpeedsPreserved', 'allHandlesClosed', 'farmRequests', 'farmWrites', 'linuxCommandRequests')}
