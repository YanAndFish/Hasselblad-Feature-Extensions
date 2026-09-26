"""从已确认的 u3 回滚状态继续同一 Linux 修复包。

只复用哈希一致的已上传组件，重新派发有独立记录的更新；不重放未知事务。
FARM 采集已关闭，只核验原代码并在更新完成后恢复使能。不操作无线驱动。
"""
import base64
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import shlex
import sys
import tarfile
import time

sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent))
import formal_linux_update as update

HERE=update.HERE
OUT=HERE/'build/formal-linux-resume'
FAILED=update.OUT/'installation-20260912T105953Z.json'
REMOTE='/tmp/hbl-wireless-flash/u4'
EXPECTED='64\nlinux-update-failed-previous-package-restored-locked\n'
sha=update.sha

def resumed_script(text):
    substitutions={
        'u=$d/u3':'u=$d/u4',
        'mkdir "$u/previous/gates"':'[ ! -e "$d/formal-enable.ready" ] && [ ! -L "$d/formal-enable.ready" ] || exit 62\n[ ! -e "$d/formal-enable.confirmed" ] && [ ! -L "$d/formal-enable.confirmed" ] || exit 62\nmkdir "$u/previous/gates"',
        'for name in formal-stop.request formal-enable.ready formal-enable.confirmed; do':'for name in formal-stop.request; do',
        '"$d/formal-client-check" --check-direct || exit 64':'direct_result=0\n"$d/formal-client-check" --check-direct || direct_result=$?\nprintf "direct-selfcheck-exit=%s\\n" "$direct_result"\n[ "$direct_result" = 0 ] || exit 64',
    }
    for old,new in substitutions.items():
        if text.count(old)!=1:raise RuntimeError('Resume script source mismatch')
        text=text.replace(old,new)
    return text

def build():
    old=json.loads(FAILED.read_text(encoding='utf-8'))
    current=update.check_host()
    installed=json.loads(update.INSTALL.read_text(encoding='utf-8'))
    transcript=json.loads((HERE/old['session']).read_text(encoding='utf-8'))
    if (old['installed'] or old['stage']!='stopped-with-recorded-state-no-retry' or
            old['lastCompletedStage']!='two-linux-components-update-dispatched-once' or
            old['farmWrites']!=1 or not old['allHandlesClosed'] or
            transcript['entries'][-1]['output']!=EXPECTED or
            installed['currentPackageSha256']!=old['proof']['previousPackageSha256'] or
            current['packageSha256']!=old['proof']['currentPackageSha256']):
        raise RuntimeError('Only the confirmed stopped and rolled-back update can resume')
    for name,digest in old['proof']['sourceHashes'].items():
        if sha((HERE/name).read_bytes())!=digest:raise RuntimeError('Failed update source changed')
    data=(update.OUT/'update.tar.gz').read_bytes()
    if sha(data)!=old['proof']['sha256']:raise RuntimeError('Original staged candidate changed')
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
        raw=resumed_script(archive.extractfile('apply.sh').read().decode('utf-8')).encode('utf-8')
    proof={'passed':True,'hardwareRequests':0,'sha256':sha(raw),'bytes':len(raw),
           'previousPackageSha256':old['proof']['previousPackageSha256'],
           'currentPackageSha256':current['packageSha256'],'currentFirmwareSha256':current['firmwareSha256'],
           'failedRecord':FAILED.relative_to(HERE).as_posix(),'sourceHashes':{
               p.relative_to(HERE).as_posix():sha(p.read_bytes()) for p in
               (Path(__file__),HERE/'research/formal_sync_loader.py')}}
    OUT.mkdir(exist_ok=True)
    (OUT/'apply.sh').write_bytes(raw)
    (OUT/'candidate.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof,raw,old

def stage(session,proof,raw,pause=time.sleep):
    result=session.command('resume-confirm-rollback','d=/tmp/hbl-wireless-flash/u3;cat "$d/exit" "$d/result"')['output']
    if result!=EXPECTED:raise RuntimeError('Live rollback state differs from recorded result')
    session.command('resume-create','d='+REMOTE+';test ! -e "$d" && test ! -L "$d" && mkdir -m 700 "$d"')
    session.command('resume-copy-verified-components','d=/tmp/hbl-wireless-flash;for n in formal-ui.rcc libhbl-formal-observer.so manifest.sha256 update-manifest.sha256;do cp "$d/u3/$n" "$d/u4/$n" || exit 61;done')
    encoded=base64.b64encode(raw).decode('ascii')
    for index,start in enumerate(range(0,len(encoded),176)):
        session.command('resume-part-'+str(index),'printf %s '+shlex.quote(encoded[start:start+176])+(' >' if not index else ' >>')+REMOTE+'/a64')
    session.command('resume-decode-once','d='+REMOTE+';(printf \'%b\' "$(awk -f /tmp/hbl-wireless-flash/d.awk "$d/a64")" >"$d/apply.sh";sha256sum "$d/apply.sh" >"$d/sha") </dev/null >/dev/null 2>&1 &')
    for _ in range(20):
        pause(0.3)
        result=session.command('resume-decode-result','d='+REMOTE+';if test -f "$d/sha";then cat "$d/sha";else printf pending;fi')['output']
        if result!='pending':break
    else:raise RuntimeError('Resume script decode pending; no retry')
    if result.split()[0]!=proof['sha256']:raise RuntimeError('Resume script hash mismatch')
    session.command('resume-verify-components','cd '+REMOTE+' && sha256sum -c update-manifest.sha256 >/dev/null && sh -n apply.sh')

def install():
    proof,raw,old=build()
    validation=json.loads((OUT/'validation.json').read_text(encoding='utf-8'))
    if not validation['passed'] or validation['candidateSha256']!=proof['sha256']:
        raise RuntimeError('Resume validation required')
    for name,digest in validation['sourceHashes'].items():
        if sha((HERE/name).read_bytes())!=digest:raise RuntimeError('Resume checks changed')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    loader=update.capture.Loader()
    loader.record=json.loads((HERE/old['recoveryRecord']).read_text(encoding='utf-8'))
    if loader.record.get('armed') or loader.record.get('payload_sha256')!=update.capture.PAYLOAD_SHA:
        raise RuntimeError('Recorded capture is not paused')
    loader.saved=True;loader.path=HERE/'build'/('formal-capture-recovery-'+stamp+'.json')
    session=update.transfer.Session('linux-resume-session-'+stamp+'.json')
    record_path=OUT/('installation-'+stamp+'.json')
    if loader.path.exists() or record_path.exists():raise RuntimeError('Resume record already exists')
    record={'installed':False,'stage':'host-verified','proof':proof,'cameraShotsTriggered':0,'agentFlashTrials':0,
            'recoveryRecord':loader.path.relative_to(HERE).as_posix(),'session':session.output.relative_to(HERE).as_posix()}
    def save(state):
        record.update(stage=state,linuxRequests=len(session.entries),farmRequests=loader.io.requests,
                      farmWrites=loader.io.writes,allHandlesClosed=loader.io.closed and all(e['closed'] for e in session.entries))
        record_path.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({k:record[k] for k in ('stage','linuxRequests','farmRequests','farmWrites')}),flush=True)
    save('host-verified')
    try:
        stage(session,proof,raw)
        result=session.command('resume-stop-old','sh /tmp/hbl-wireless-flash/formal-restore.sh stop',timeout_ms=30000)
        if result['output'].strip()!='formal-linux-stopped-observer-retained':raise RuntimeError('Old worker stop not confirmed')
        loader.verify(0);loader.save()
        save('paused-capture-code-and-hooks-verified')
        session.command('resume-capture-confirmed','umask 077;d='+REMOTE+';test ! -e "$d/capture-disarmed" && (set -C;printf verified >"$d/capture-disarmed")')
        session.command('resume-apply-once','d='+REMOTE+';test ! -e "$d/dispatched" && touch "$d/dispatched" && (sh "$d/apply.sh" >"$d/log" 2>&1;echo $? >"$d/exit") </dev/null >/dev/null 2>&1 &')
        save('resume-dispatched-once')
        for _ in range(60):
            time.sleep(1)
            result=session.command('resume-result','d='+REMOTE+';if test -f "$d/exit";then cat "$d/exit" "$d/result";else printf pending;fi')['output']
            if result!='pending':break
        else:raise RuntimeError('Resume still pending; no replay')
        if result.splitlines()!=['0','updated-package-loaded-default-off-locked']:
            raise RuntimeError('Resume failed; capture remains paused and user gate stays locked')
        save('updated-components-checked-default-off')
        loader.arm()
        if loader.io.read(update.capture.RECORD+4)!=1 or loader.io.read(update.capture.RECORD+8):raise RuntimeError('Capture rearm not confirmed')
        save('capture-rearmed')
        session.command('resume-unlock','d=/tmp/hbl-wireless-flash;umask 077;test ! -e "$d/formal-enable.ready" && (set -C;printf ready >"$d/formal-enable.ready")')
        for _ in range(20):
            time.sleep(0.2)
            result=session.command('resume-enable-result','d=/tmp/hbl-wireless-flash;if test -f "$d/formal-enable.confirmed";then cat "$d/formal-enable.confirmed";systemctl is-active victory-gui msg2dbus-farm;else printf pending;fi')['output']
            if result!='pending':break
        else:raise RuntimeError('Resume unlock pending; no replay')
        if result.splitlines()!=['ready','active','active']:raise RuntimeError('Resumed components are not ready')
        installed=json.loads(update.INSTALL.read_text(encoding='utf-8'))
        installed.update(currentPackageSha256=proof['currentPackageSha256'],currentFirmwareSha256=proof['currentFirmwareSha256'],
                         recoveryRecord=loader.path.relative_to(HERE).as_posix())
        installed.setdefault('linuxComponentUpdates',[]).append({'at':stamp,'record':record_path.relative_to(HERE).as_posix(),
            'previousPackageSha256':proof['previousPackageSha256'],'currentPackageSha256':proof['currentPackageSha256']})
        update.INSTALL.write_text(json.dumps(installed,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        record['installed']=True;save('fixed-components-installed-default-off-ready-for-user')
        return record
    except Exception as error:
        record.update(lastCompletedStage=record['stage'],error=str(error),automaticRetry=False)
        save('stopped-with-recorded-state-no-retry')
        raise

if __name__=='__main__':
    if not sys.argv[1:]:print(json.dumps(build()[0]))
    elif sys.argv[1:]==['--install-current-session']:print(json.dumps(install()))
    else:raise SystemExit('Unsupported arguments')
