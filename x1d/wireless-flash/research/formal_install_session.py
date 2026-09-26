"""正式引闪安装编排。导入不连接硬件；实机入口要求本批次待机协调参数。

只装载临时 Linux / 无线运行文件与已验证 FARM RAM 采集代码。
失败保留准确阶段和逐写入记录，不自动重发有歧义操作。
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import formal_transfer as transfer
import formal_sync_loader as capture

HERE, ROOT, OUT = transfer.HERE, transfer.candidate.ROOT, transfer.OUT


def check_host():
    report, _ = transfer.candidate.verify_package()
    proof = transfer.candidate.read_report('build/formal-flash-package/transfer-validation.json')
    if not proof.get('passed') or proof.get('packageSha256') != report['packageSha256'] or not capture.offline_ready():
        raise RuntimeError('Current package/transfer/capture validation required')
    return report


def stage_package():
    """只上传并校验本轮 Linux 包；不建立保持、不重启服务、不访问 FARM。"""
    package=check_host()
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    path=OUT/('staged-'+stamp+'.json')
    if path.exists():raise RuntimeError('Staging record already exists')
    session=transfer.Session('stage-session-'+stamp+'.json')
    state={'packageSha256':package['packageSha256'],'staged':False,'allHandlesClosed':False,
           'stageSession':session.output.name,'farmRequests':0,'servicesRestarted':False}
    try:
        transfer.stage(session)
        state['staged']=True
    finally:
        state['allHandlesClosed']=bool(session.entries) and all(e['closed'] for e in session.entries)
        state['linuxRequests']=sum(e['submitted'] for e in session.entries)
        path.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {'stagedRecord':str(path),**state}


def install(awake_confirmed=False, retain_hold=False, staged_record=None):
    if awake_confirmed is not True:
        raise RuntimeError('Current batch requires user standby/USB coordination; no device requests')
    package = check_host()
    if staged_record is not None:
        staged_path=Path(staged_record).resolve()
        if staged_path.parent!=OUT.resolve() or not staged_path.name.startswith('staged-') or staged_path.suffix!='.json':
            raise RuntimeError('Staged record outside formal output')
        staged=json.loads(staged_path.read_text(encoding='utf-8'))
        if staged.get('packageSha256')!=package['packageSha256'] or staged.get('staged') is not True or staged.get('allHandlesClosed') is not True:
            raise RuntimeError('Staged package not fully verified')
    sys.path.insert(0, str(ROOT/'x1d/tools'))
    from farm_diagnostic_binary import FarmApplication
    farm = FarmApplication().data
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    record_path = OUT/('installation-'+stamp+'.json')
    if record_path.exists():
        raise RuntimeError('Installation record already exists')
    session = transfer.Session('session-'+stamp+'.json')
    loader = capture.Loader()
    recovery_path = HERE/'build'/('formal-capture-recovery-'+stamp+'.json')
    state = {'kind': 'formal-dual-shutter-flash-temporary-installation', 'createdAt': stamp,
             'packageSha256': package['packageSha256'], 'firmwareSha256': package['firmwareSha256'],
             'payloadSha256': capture.PAYLOAD_SHA, 'stage': 'host-verified', 'installed': False,
             'linuxInstalled': False, 'targetSelfChecksRun': False, 'farmArmed': False,
             'installationGateReleased': False,
             'masterDefault': False, 'physicalTimingVerified': False,
             'cameraShotsTriggered': 0, 'agentFlashTrials': 0,
             'recoveryRecord': str(recovery_path.relative_to(HERE)).replace('\\','/'),
             'sessionRecord': str(session.output.relative_to(HERE)).replace('\\','/'),
             'files': package['files']}
    def save(stage):
        state['stage'] = stage
        state['linuxRequests'] = sum(e['submitted'] for e in session.entries)
        state['farmRequests'], state['farmWrites'] = loader.io.requests, loader.io.writes
        state['allHandlesClosed'] = loader.io.closed and all(e['closed'] for e in session.entries)
        record_path.write_text(json.dumps(state, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print(json.dumps({'stage': stage, 'linuxRequests': state['linuxRequests'], 'farmRequests': state['farmRequests']}, ensure_ascii=False), flush=True)
    save('host-verified')
    try:
        # 上传只涉及 Linux 临时文件；FARM 首次读取必须等 UI 活动保持已验证。
        if staged_record is None:
            session.command('formal-fresh-preflight', 'test ! -e /tmp/hbl-wireless-flash && test ! -L /tmp/hbl-wireless-flash && systemctl is-active --quiet victory-gui msg2dbus-farm')
            transfer.stage(session)
        else:
            state['stagedRecord']=staged_path.name
            result=session.command('formal-staged-preflight', 'cd /tmp/hbl-wireless-flash && test ! -e formal-state && test ! -L formal-state && sha256sum -c manifest.sha256 >/dev/null && ./formal-system-check --require-ui-stage')
            if result['output'].strip() not in ('system=2 suc=0 farm=0 pwr=0 ui-power=0 hold=0','system=4 suc=0 farm=0 pwr=0 ui-power=1 hold=0'):
                raise RuntimeError('Current system/links not ready for normal GUI startup; no installation started')
        save('package-transferred-and-verified')
        def health(label):
            result=session.command(label, '/tmp/hbl-wireless-flash/formal-system-check --require-held')
            if result['output'].strip()!='system=2 suc=0 farm=0 pwr=0 ui-power=0 hold=1':
                raise RuntimeError('System Active/links/UI hold not confirmed')
            state['lastHealth']=result['output'].strip()
        def linux_phase(phase, marker):
            transfer.start_linux(session,phase)
            save('linux-'+phase+'-dispatched-once')
            for _ in range(90):
                time.sleep(1)
                outcome=transfer.linux_result(session,phase)
                if outcome!='pending':break
            else:raise RuntimeError('Linux phase pending; do not dispatch again')
            if outcome.splitlines()!=['0',marker]:
                raise RuntimeError('Linux phase failed; inspect its exact restore record')
        linux_phase('ui','formal-ui-hold-ready-default-off')
        health('formal-ui-held')
        state['targetSelfChecksRun']=True
        save('ui-hold-and-system-active-verified')
        loader.prepare(farm, recovery_path)
        save('camera-baseline-and-own-arena-verified')
        health('formal-before-observer')
        linux_phase('observer','formal-linux-ready-default-off')
        health('formal-before-capture')
        state['linuxInstalled']=True
        save('linux-target-selfchecks-and-default-off-verified')
        loader.probe()
        save('cache-probe-completed-and-restored')
        health('formal-before-hooks')
        loader.install_disarmed()
        save('farm-eight-hooks-installed-disarmed')
        health('formal-before-arm')
        state['farmArmed'] = None
        save('farm-arm-attempt-state-unknown-until-reply')
        loader.arm()
        state['farmArmed'] = True
        save('farm-arm-written-awaiting-verification')
        loader.verify(1)
        save('farm-armed-for-user-exposures')
        health('formal-final-health')
        result = session.command('formal-final-status', 'd=/tmp/hbl-wireless-flash;cat "$d/formal-runtime.status" "$d/formal-worker.status" "$d/formal-observer.status";systemctl is-active victory-gui msg2dbus-farm')
        output = result['output']
        if ('formal-ui-loaded-default-off' not in output or 'formal-worker-ready-default-off' not in output or
                'master=0 radio-held=0 radio-busy=0 same-process=1' not in output or
                'stage=ready meta=1 observe=1' not in output or output.splitlines()[-2:] != ['active','active']):
            raise RuntimeError('Final Linux status differs; installed capture retained for explicit recovery')
        state['defaultOffVerifiedWhileInstallationGateLocked'] = True
        if retain_hold:
            state.update(installed=True, installationHoldRetained=True)
            save('installed-default-off-locked-for-joint-af')
            return state
        save('default-off-verified-before-enabling-user-controls')
        state['installationGateReleased'] = None
        save('user-control-enable-attempt-state-unknown-until-reply')
        result = session.command('formal-release-install-gate', 'd=/tmp/hbl-wireless-flash;umask 077;test ! -e "$d/formal-enable.ready" && test ! -L "$d/formal-enable.ready" && (set -C;printf ready >"$d/formal-enable.ready") && printf gate-requested')
        if result['output'] != 'gate-requested':
            raise RuntimeError('Installation gate request not confirmed; do not retry')
        save('user-control-enable-requested-awaiting-worker')
        for _ in range(20):
            time.sleep(0.2)
            result = session.command('formal-enable-confirmation', 'd=/tmp/hbl-wireless-flash;if test -f "$d/formal-enable.confirmed";then cat "$d/formal-enable.confirmed";systemctl is-active victory-gui msg2dbus-farm;else printf pending;fi')
            if result['output'] != 'pending':
                break
        else:
            raise RuntimeError('Worker has not confirmed enable; do not issue a second request')
        if result['output'].splitlines() != ['ready','active','active']:
            raise RuntimeError('Enable confirmation or services not ready')
        state['installationGateReleased'] = True
        health('formal-before-hold-release')
        session.command('formal-release-hold', 'umask 077;set -C;printf release >/tmp/hbl-wireless-flash/formal-state/hold.release')
        state['installationHoldRetained']=False
        state['installed'] = True
        save('installed-default-off-ready-for-user')
        return state
    except Exception as error:
        state['lastCompletedStage'] = state['stage']
        state['errorClass'] = type(error).__name__
        state['failure'] = str(error)
        state['automaticRetryPerformed'] = False
        save('stopped-review-current-record-before-recovery')
        raise


def restore(installation_path, awake_confirmed=False):
    """只恢复本次已完整装入的固定版本；中断于部分写入的记录必须单独审查。"""
    if awake_confirmed is not True:
        raise RuntimeError('Current batch requires user standby/USB coordination; no device requests')
    package = check_host()
    path = Path(installation_path).resolve()
    if path.parent != OUT.resolve() or not path.name.startswith('installation-') or path.suffix != '.json':
        raise RuntimeError('Installation record outside formal output')
    installed = json.loads(path.read_text(encoding='utf-8'))
    recovery_path = (HERE/installed['recoveryRecord']).resolve()
    if recovery_path.parent != (HERE/'build').resolve() or not recovery_path.name.startswith('formal-capture-recovery-'):
        raise RuntimeError('Recovery record outside fixed module directory')
    saved = json.loads(recovery_path.read_text(encoding='utf-8'))
    if (installed.get('currentPackageSha256', installed.get('packageSha256')) != package['packageSha256'] or saved.get('payload_sha256') != capture.PAYLOAD_SHA or
            saved.get('installed') is not True or saved.get('payload_base') != capture.PAYLOAD_START or
            saved.get('payload_bytes') != capture.PAYLOAD_BYTES or saved.get('record_address') != capture.RECORD or
            {int(k):v for k,v in saved.get('original_hooks',{}).items()} != capture.ORIGINAL_HOOKS or
            {int(k):v for k,v in saved.get('new_hooks',{}).items()} != capture.NEW_HOOKS):
        raise RuntimeError('Recorded installation incomplete or changed; no automatic recovery')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    session = transfer.Session('restore-session-'+stamp+'.json')
    loader = capture.Loader()
    loader.path, loader.record, loader.saved = recovery_path, saved, True
    result = session.command('formal-stop-before-unhook', 'sh /tmp/hbl-wireless-flash/formal-restore.sh stop', timeout_ms=30000)
    if result['output'].strip() != 'formal-linux-stopped-observer-retained':
        raise RuntimeError('Worker stop not confirmed; FARM unhook refused')
    # 只有完成过全套安装的载荷才走此常规恢复；当前code、hook与空闲状态再次核验。
    armed = loader.io.read(capture.RECORD+4)
    if armed not in (0,1):
        raise RuntimeError('Capture enable state changed')
    loader.verify(armed)
    loader.unhook()
    result = session.command('formal-restore-original-linux', 'sh /tmp/hbl-wireless-flash/formal-restore.sh --after-farm-unhook', timeout_ms=45000)
    if result['output'].strip() != 'original-linux-services-and-radio-restored':
        raise RuntimeError('FARM restored but Linux restoration not confirmed')
    installed.update(installed=False, farmArmed=False, stage='restored-original-hooks-linux-and-radio',
                     payloadRetainedUntilUserRestart=True,
                     restorationSession=str(session.output.relative_to(HERE)).replace('\\','/'))
    path.write_text(json.dumps(installed,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return installed


if __name__ == '__main__':
    if sys.argv[1:] == ['--stage-package']:
        print(json.dumps(stage_package(), ensure_ascii=False))
    elif len(sys.argv)==4 and sys.argv[1]=='--install-staged' and sys.argv[3]=='--retain-hold-for-af':
        print(json.dumps(install(True,retain_hold=True,staged_record=sys.argv[2]),ensure_ascii=False))
    elif sys.argv[1:] == ['--install', '--current-standby-confirmed', '--retain-hold-for-af']:
        print(json.dumps(install(True,retain_hold=True), ensure_ascii=False))
    elif sys.argv[1:] == ['--install', '--current-standby-confirmed']:
        print(json.dumps(install(True), ensure_ascii=False))
    elif not sys.argv[1:]:
        report = check_host()
        print(json.dumps({'hostReady': True, 'hardwareRequests': 0, 'packageSha256': report['packageSha256']}, ensure_ascii=False))
    else:
        raise SystemExit('Unsupported arguments; no device requests')
