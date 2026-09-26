"""纯记录完整包的临时装载与证据登记；导入不操作设备。"""
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
import time

from mechanical_hw_ready_transfer import DECODER

HERE = Path(__file__).resolve().parents[1]
OUT = HERE / 'build/mechanical-timing-candidate'

def package():
    result = json.loads((OUT / 'package-validation.json').read_text(encoding='utf-8'))
    data = (OUT / 'session-package.tar.gz').read_bytes()
    if hashlib.sha256(data).hexdigest() != result['packageSha256'] or len(data) != result['packageBytes']:
        raise RuntimeError('Recording package changed')
    client = json.loads((OUT / 'client-build.json').read_text(encoding='utf-8'))
    if not client['passed']:
        raise RuntimeError('Missing offline checks')
    for name, digest in client['sourceHashes'].items():
        if hashlib.sha256((HERE / name).read_bytes()).hexdigest() != digest:
            raise RuntimeError('Recording source changed')
    return result, data

def stage(session):
    manifest, data = package()
    session.command('create-own-stage', 'test ! -e /tmp/hbl-wireless-flash && mkdir -m 700 /tmp/hbl-wireless-flash')
    for index, start in enumerate(range(0, len(DECODER), 90)):
        session.command('decoder-' + str(index), 'printf %s ' + shlex.quote(DECODER[start:start+90]) +
                        (' >' if index == 0 else ' >>') + '/tmp/hbl-wireless-flash/d.awk')
    encoded = base64.b64encode(data).decode('ascii')
    parts = [encoded[i:i+176] for i in range(0, len(encoded), 176)]
    for index, part in enumerate(parts):
        session.command('package-' + str(index), 'printf %s ' + shlex.quote(part) +
                        (' >' if index == 0 else ' >>') + '/tmp/hbl-wireless-flash/p64')
        if (index+1) % 100 == 0:
            print('recording package chunks', index+1, '/', len(parts), flush=True)
    session.command('decode-dispatched', 'd=/tmp/hbl-wireless-flash;(printf \'%b\' "$(awk -f "$d/d.awk" "$d/p64")" >"$d/session.tar.gz";sha256sum "$d/session.tar.gz" >"$d/decode.sha") </dev/null >/dev/null 2>&1 &')
    for attempt in range(90):
        time.sleep(1)
        result = session.command('verify-existing-archive-' + str(attempt), 'd=/tmp/hbl-wireless-flash;if test -f "$d/decode.sha"; then cat "$d/decode.sha"; else printf pending; fi')
        if result['output'] != 'pending':
            break
    else:
        raise RuntimeError('Decode pending; do not dispatch again')
    if result['output'].split()[0] != manifest['packageSha256']:
        raise RuntimeError('Uploaded recording archive hash mismatch')
    result = session.command('extract-and-verify', 'cd /tmp/hbl-wireless-flash && tar xzf session.tar.gz && sha256sum -c manifest.sha256 >/dev/null && printf package-verified')
    if result['output'] != 'package-verified':
        raise RuntimeError('Extracted package mismatch')
    print('recording package verified', len(parts), len(data), flush=True)

def finish(loader, session, ready, health, checks, qml, runtime, marker, worker):
    manifest, _ = package()
    if loader.io.failed or not loader.io.closed or not loader.record.get('installed') or not loader.record.get('armed'):
        raise RuntimeError('FARM verification incomplete')
    if session.failed or not session.entries or not all(e['matched'] and e['closed'] and e.get('exit_code') == 0 for e in session.entries):
        raise RuntimeError('Linux session incomplete')
    if sum(e['label'] == 'decode-dispatched' for e in session.entries) != 1:
        raise RuntimeError('Unexpected decode dispatches')
    if not any(e['label'].startswith('verify-existing-archive-') and e['output'].split()[0] == manifest['packageSha256'] for e in session.entries if e.get('output')):
        raise RuntimeError('Missing archive hash evidence')
    if not any(e['label'] == 'extract-and-verify' and e['output'] == 'package-verified' for e in session.entries):
        raise RuntimeError('Missing extracted file checks')
    expected = ((ready, 'linux-sync-chain-ready-farm-hook-pending-auto-off\n'),
                (runtime, 'ui-loaded-worker-default-off\nactive\nactive\nactive\n'),
                (marker, 'normal-driver-marker=0x5850\n'), (worker, 'worker-ready-default-off\n'))
    if any(item['output'] != value for item, value in expected) or qml['output'].strip() != '0':
        raise RuntimeError('Target runtime mismatch')
    if 'stage=ready error=0 ' not in health['output'] or ' observe=1 output=1 ' not in health['output']:
        raise RuntimeError('Observer not ready')
    for value in ('sync-hook-selftest: own=5 forwarded=272 status=1 hardware=0',
                  'qt-receiver-check=3 hardware-requests=0', 'timerfd-check=3 units=us hardware-requests=0'):
        if value not in checks['output']:
            raise RuntimeError('Missing target check')
    now = datetime.now(timezone.utc)
    folder = OUT / ('install-' + now.strftime('%Y%m%dT%H%M%SZ'))
    folder.mkdir()
    verified_evidence = folder/'verified-linux-session.json'
    verified_evidence.write_text(json.dumps({'failed': False, 'entries': session.entries,
        'agentFlashTrials': 0, 'cameraShotsTriggered': 0}, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    index = HERE / 'build/mechanical-sync-candidate/installation.json'
    if index.exists():
        (folder / 'previous-installation.json').write_bytes(index.read_bytes())
    report = {'kind': 'resident-mechanical-pure-timing-record', 'installed': True,
              'observedAt': now.isoformat(), 'packageSha256': manifest['packageSha256'],
              'files': manifest['files'], 'firmwareSha256': manifest['firmwareSha256'],
              'farmPayloadSha256': manifest['farmPayloadSha256'],
              'farmRecoveryRecord': str(loader.path.relative_to(HERE)),
              'linuxEvidence': str(verified_evidence.relative_to(HERE)),
              'completeSessionEvidence': str(session.output.relative_to(HERE)),
              'installationMode': 'full-temporary-chain-after-confirmed-absent-stage',
              'defaultAutomaticEnabled': False, 'sourcesRetained': 7,
              'compensationImplemented': False, 'newHardwareInterruptImplemented': False,
              'flashParameterTransmissionImplemented': False, 'timingRecordingImplemented': True,
              'timingRecordingOnTargetVerified': False, 'physicalTimingMeasured': False,
              'ringCapacity': 2048, 'saveOnlyWhileDisabledAndIdle': True,
              'targetChecks': checks, 'runtimeAndServices': runtime, 'normalDriverMarker': marker,
              'workerStartupStatus': worker, 'observerHealth': health, 'qmlErrorCount': 0,
              'afSpeedsPreserved': loader.record['af_speeds'],
              'farmRequests': loader.io.requests, 'farmWrites': loader.io.writes,
              'linuxCommandRequests': sum(e['submitted'] for e in session.entries),
              'allHandlesClosed': True, 'agentFlashTrials': 0, 'cameraShotsTriggered': 0}
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    for path in (folder/'installation.json', OUT/'installation.json', index, HERE/'build/installation.json'):
        path.write_text(encoded, encoding='utf-8')
    doc = HERE / 'MECHANICAL_SYNC_TRIAL.md'
    content = doc.read_text(encoding='utf-8')
    start = content.index('当前状态：'); end = content.index('\n\n', start)
    content = content[:start] + '当前状态：纯时序记录版已完整临时装入 X1D，目标机运行、自检和 FARM 回读通过。自动引闪默认关闭；开启后记录内存，关闭且无线空闲时保存。七个触发来源和原延迟行为保留，没有新增补偿或曝光硬件中断。尚未采集用户实拍记录，未测得物理发光时间。' + content[end:]
    doc.write_text(content, encoding='utf-8')
    doc = HERE / 'research/MECHANICAL_TIMING_RECORD.md'
    content = doc.read_text(encoding='utf-8')
    content = content.replace('**尚未装入相机**', '**现已完整临时装入相机**')
    content += '\n本轮安装：现场读回发现上次临时目录已不存在，故装入完整包并重新核验、装入相同 FARM 捕获代码及无线准备程序。目标机检查、页面及回读通过，自动引闪默认关闭。实际记录保存和分段耗时仍待用户试拍后读取；安装证据见 `../build/mechanical-timing-candidate/installation.json`。此前“硬件请求为零”为离线准备阶段记录。\n'
    doc.write_text(content, encoding='utf-8')
    return {k: report[k] for k in ('installed', 'afSpeedsPreserved', 'allHandlesClosed', 'farmRequests', 'farmWrites', 'linuxCommandRequests')}

def seal_existing_evidence(session, reader_session):
    """将安装通过时的前缀与后续只读工具检查分开存档，保留全部失败证据。"""
    report = json.loads((OUT/'installation.json').read_text(encoding='utf-8'))
    count = report['linuxCommandRequests']
    prefix = session.entries[:count]
    if len(prefix) != count or not all(e['submitted']==1 and e['matched'] and e['closed'] and e['exit_code']==0 for e in prefix):
        raise RuntimeError('Installation evidence prefix mismatch')
    when = datetime.fromisoformat(report['observedAt'])
    folder = OUT/('install-'+when.strftime('%Y%m%dT%H%M%SZ'))
    evidence = folder/'verified-linux-session.json'
    evidence.write_text(json.dumps({'failed': False, 'entries': prefix,
        'agentFlashTrials': 0, 'cameraShotsTriggered': 0}, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    if not all(e['matched'] and e['closed'] for e in session.entries+reader_session.entries):
        raise RuntimeError('Read check closure unknown')
    report.update(linuxEvidence=str(evidence.relative_to(HERE)),
                  completeSessionEvidence=str(session.output.relative_to(HERE)),
                  postInstallationReaderEvidence=str(reader_session.output.relative_to(HERE)),
                  postInstallationReaderNote='od 读取返回非零，原会话停止；新会话的 hexdump 固定长度偏移读取与主机字节匹配。没有相机试拍记录。',
                  postInstallationReaderVerified=True,
                  postInstallationReaderRequests=len(session.entries)-count+len(reader_session.entries))
    encoded=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
    for path in (folder/'installation.json',OUT/'installation.json',
                 HERE/'build/mechanical-sync-candidate/installation.json',HERE/'build/installation.json'):
        path.write_text(encoded,encoding='utf-8')
    return {'installed':report['installed'],'readerVerified':True,'savedTrialRecording':False}
