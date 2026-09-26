"""修复当前扩展版的频道回执并更新单行曝光摘要；默认仅离线生成。

更新期间仅切换本模块自有 FARM 采集使能；原厂与 AF 指令不变。
任何未知传输结果均停止，不重放写入或安装命令。
"""
import base64
from datetime import datetime, timezone
import gzip
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
import formal_transfer as transfer
import formal_sync_loader as capture
from formal_install_session import check_host

HERE=transfer.HERE
OUT=HERE/'build/formal-linux-update'
INSTALL=transfer.OUT/'installation-20260912T090210Z.json'
PREVIOUS=transfer.OUT/'installed-expansion-20260912T103726Z'
REMOTE='/tmp/hbl-wireless-flash/u3'
CHANGED=('formal-ui.rcc','libhbl-formal-observer.so')

def sha(data):return hashlib.sha256(data).hexdigest()

def build():
    current=check_host()
    previous=json.loads((PREVIOUS/'package-validation.json').read_text(encoding='utf-8'))
    installed=json.loads(INSTALL.read_text(encoding='utf-8'))
    if (not installed.get('installed') or installed.get('currentPackageSha256')!=previous['packageSha256'] or
            sha((PREVIOUS/'session-package.tar.gz').read_bytes())!=previous['packageSha256'] or
            set(current['files'])!=set(previous['files']) or
            current['firmwareSha256']!=previous['firmwareSha256'] or
            {n for n in current['files'] if current['files'][n]!=previous['files'][n]}!=set(CHANGED)|{'manifest.sha256'}):
        raise RuntimeError('Expected current linux-update installation and only two Linux component changes')
    replacements={
        '@OLD_MANIFEST@':previous['files']['manifest.sha256']['sha256'],
        '@NEW_MANIFEST@':current['files']['manifest.sha256']['sha256'],
        '@FIRMWARE@':current['firmwareSha256']}
    script=(HERE/'formal-linux-update.sh.in').read_text(encoding='utf-8')
    for key,value in replacements.items():
        if script.count(key)!=1:raise RuntimeError('Linux update placeholder mismatch: '+key)
        script=script.replace(key,value)
    files={name:(transfer.OUT/'package-files'/name).read_bytes() for name in (*CHANGED,'manifest.sha256')}
    files['update-manifest.sha256']=''.join(sha(files[n])+'  '+n+'\n' for n in sorted(files)).encode('ascii')
    files['apply.sh']=script.encode('utf-8')
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w',format=tarfile.USTAR_FORMAT) as archive:
        for name,raw in sorted(files.items()):
            item=tarfile.TarInfo(name);item.size=len(raw)
            item.mode=0o700 if name.endswith('.sh') or name in transfer.candidate.PROGRAMS[2:] else 0o600
            archive.addfile(item,io.BytesIO(raw))
    data=gzip.compress(stream.getvalue(),mtime=0)
    OUT.mkdir(exist_ok=True)
    (OUT/'update.tar.gz').write_bytes(data)
    (OUT/'apply.sh').write_bytes(files['apply.sh'])
    proof={'passed':True,'hardwareRequests':0,'bytes':len(data),'sha256':sha(data),
           'previousPackageSha256':previous['packageSha256'],'currentPackageSha256':current['packageSha256'],
           'currentFirmwareSha256':current['firmwareSha256'],'payloadSha256':capture.PAYLOAD_SHA,
           'changesFarmInstructions':False,'changesAf':False,'farmEnableWrites':2,'changesRadio':False,
           'sourceHashes':{p.relative_to(HERE).as_posix():sha(p.read_bytes()) for p in
                           [Path(__file__),HERE/'formal-linux-update.sh.in',HERE/'research/formal_sync_loader.py']}}
    (OUT/'candidate.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof,data

def stage(session,proof,data,pause=time.sleep):
    session.command('linux-update-create','d='+REMOTE+';test ! -e "$d" && test ! -L "$d" && mkdir -m 700 "$d"')
    encoded=base64.b64encode(data).decode('ascii')
    for index,start in enumerate(range(0,len(encoded),176)):
        session.command('linux-update-part-'+str(index),'printf %s '+shlex.quote(encoded[start:start+176])+(' >' if not index else ' >>')+REMOTE+'/p64')
        if (index+1)%200==0:print('linux-update-package-chunks',index+1,'/',(len(encoded)+175)//176,flush=True)
    session.command('linux-update-decode-once','d='+REMOTE+';(printf \'%b\' "$(awk -f /tmp/hbl-wireless-flash/d.awk "$d/p64")" >"$d/u.tgz";sha256sum "$d/u.tgz" >"$d/sha") </dev/null >/dev/null 2>&1 &')
    for _ in range(120):
        pause(1)
        result=session.command('linux-update-decode-result','d='+REMOTE+';if test -f "$d/sha";then cat "$d/sha";else printf pending;fi')['output']
        if result!='pending':break
    else:raise RuntimeError('Decode remains pending; no retry')
    if result.split()[0]!=proof['sha256']:raise RuntimeError('Linux update archive mismatch')
    session.command('linux-update-extract','cd '+REMOTE+' && tar xzf u.tgz && sha256sum -c update-manifest.sha256 >/dev/null && sh -n apply.sh')

def install():
    proof,data=build()
    validation=json.loads((OUT/'validation.json').read_text(encoding='utf-8'))
    if not validation.get('passed') or validation.get('candidateSha256')!=proof['sha256']:
        raise RuntimeError('Current linux-update script and transfer validation required')
    for path,digest in validation['sourceHashes'].items():
        if sha((HERE/path).read_bytes())!=digest:raise RuntimeError('Linux update checks changed')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    installed=json.loads(INSTALL.read_text(encoding='utf-8'))
    saved=json.loads((HERE/installed['recoveryRecord']).read_text(encoding='utf-8'))
    if saved.get('payload_sha256')!=capture.PAYLOAD_SHA or not saved.get('installed'):
        raise RuntimeError('Original capture installation is not verified')
    session=transfer.Session('linux-update-session-'+stamp+'.json')
    loader=capture.Loader();loader.record=saved;loader.saved=True
    loader.path=HERE/'build'/('formal-capture-recovery-'+stamp+'.json')
    record_path=OUT/('installation-'+stamp+'.json')
    if loader.path.exists() or record_path.exists():raise RuntimeError('Linux update record already exists')
    record={'installed':False,'stage':'host-verified','proof':proof,'cameraShotsTriggered':0,'agentFlashTrials':0,
            'recoveryRecord':loader.path.relative_to(HERE).as_posix(),'session':session.output.relative_to(HERE).as_posix()}
    def save(value):
        record.update(stage=value,linuxRequests=len(session.entries),farmRequests=loader.io.requests,
                      farmWrites=loader.io.writes,allHandlesClosed=loader.io.closed and all(e['closed'] for e in session.entries))
        record_path.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({k:record[k] for k in ('stage','linuxRequests','farmRequests','farmWrites')},ensure_ascii=False),flush=True)
    save('host-verified')
    try:
        stage(session,proof,data)
        save('new-package-staged-old-program-running')
        result=session.command('linux-update-stop-old','sh /tmp/hbl-wireless-flash/formal-restore.sh stop',timeout_ms=30000)
        if result['output'].strip()!='formal-linux-stopped-observer-retained':raise RuntimeError('Old worker stop not verified')
        save('old-worker-stopped-observer-retained')
        loader.verify(1)
        loader.save()
        save('existing-capture-code-and-hooks-verified')
        loader.write(capture.RECORD+4,0)
        loader.record.update(armed=False,stage='paused_for_wireless_linux-update');loader.save()
        if loader.io.read(capture.RECORD+8) or loader.io.read(capture.pre.AF_IDLE)&255:
            raise RuntimeError('Capture or AF active after disabling')
        save('capture-disabled-no-instruction-changes')
        session.command('linux-update-capture-confirmed','umask 077;d='+REMOTE+';test ! -e "$d/capture-disarmed" && (set -C;printf verified >"$d/capture-disarmed")')
        session.command('linux-update-apply-once','d='+REMOTE+';test ! -e "$d/dispatched" && touch "$d/dispatched" && (sh "$d/apply.sh" >"$d/log" 2>&1;echo $? >"$d/exit") </dev/null >/dev/null 2>&1 &')
        save('two-linux-components-update-dispatched-once')
        for _ in range(60):
            time.sleep(1)
            result=session.command('linux-update-apply-result','d='+REMOTE+';if test -f "$d/exit";then cat "$d/exit" "$d/result";else printf pending;fi')['output']
            if result!='pending':break
        else:raise RuntimeError('Linux update apply remains pending; no retry')
        if result.splitlines()!=['0','updated-package-loaded-default-off-locked']:
            raise RuntimeError('Linux update did not finish; capture remains disabled and user gate stays locked')
        save('updated-linux-loaded-and-selfchecked-default-off')
        loader.arm()
        if loader.io.read(capture.RECORD+4)!=1 or loader.io.read(capture.RECORD+8):raise RuntimeError('Capture rearm not verified')
        save('capture-rearmed-original-hooks-preserved')
        session.command('linux-update-unlock','d=/tmp/hbl-wireless-flash;umask 077;test ! -e "$d/formal-enable.ready" && (set -C;printf ready >"$d/formal-enable.ready")')
        for _ in range(20):
            time.sleep(0.2)
            result=session.command('linux-update-enable-result','d=/tmp/hbl-wireless-flash;if test -f "$d/formal-enable.confirmed";then cat "$d/formal-enable.confirmed";systemctl is-active victory-gui msg2dbus-farm;else printf pending;fi')['output']
            if result!='pending':break
        else:raise RuntimeError('Worker unlock has not confirmed; no retry')
        if result.splitlines()!=['ready','active','active']:raise RuntimeError('Expanded worker or UI not ready')
        installed.update(currentPackageSha256=proof['currentPackageSha256'],currentFirmwareSha256=proof['currentFirmwareSha256'],
                         recoveryRecord=loader.path.relative_to(HERE).as_posix())
        installed.setdefault('linuxComponentUpdates',[]).append({'at':stamp,'record':record_path.relative_to(HERE).as_posix(),
            'previousPackageSha256':proof['previousPackageSha256'],'currentPackageSha256':proof['currentPackageSha256']})
        INSTALL.write_text(json.dumps(installed,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        record['installed']=True;save('updated-package-installed-default-off-ready-for-user')
        return record
    except Exception as error:
        record.update(lastCompletedStage=record['stage'],error=str(error),automaticRetry=False)
        save('stopped-with-recorded-state-no-retry')
        raise

if __name__=='__main__':
    if not sys.argv[1:]:print(json.dumps(build()[0]))
    elif sys.argv[1:]==['--install-current-session']:print(json.dumps(install(),ensure_ascii=False))
    else:raise SystemExit('Unsupported arguments')
