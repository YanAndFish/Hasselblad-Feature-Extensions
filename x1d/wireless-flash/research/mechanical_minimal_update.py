"""独立低延迟增量包：只更新无诊断机械 worker、消息观察库、界面和清单。"""
from pathlib import Path
import gzip,hashlib,io,json,subprocess,tarfile
from mechanical_continuous_update import stage as stage_common

HERE=Path(__file__).resolve().parents[1]
OUT=HERE/'build/mechanical-sync-candidate'
UPDATE=OUT/'minimal-update'
REMOTE='/tmp/hbl-wireless-flash/minimal1'
NAMES=('wireless-worker','libhbl-mechanical-observer.so','ui.rcc','manifest.sha256')
def sha(data): return hashlib.sha256(data).hexdigest()

def make():
    assert Path.cwd().resolve()==HERE.parents[1]
    old=json.loads((OUT/'installation.json').read_text(encoding='utf-8'))
    new=json.loads((OUT/'package-validation.json').read_text(encoding='utf-8'))
    app=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
    if not old.get('installed') or app['checks'].get('prepared_requests')!=1000:
        raise RuntimeError('Missing installed baseline or prebuilt request checks')
    if old['farmPayloadSha256']!=new['farmPayloadSha256']: raise RuntimeError('FARM changed')
    for name,meta in old['files'].items():
        if name not in NAMES and meta!=new['files'][name]: raise RuntimeError('Unexpected change: '+name)
    from mechanical_sync_loader import offline_ready
    from waveform_payload_audit import audit
    if not offline_ready(): raise RuntimeError('Source evidence changed')
    source=(HERE/'native/mechanical_wireless_worker.cpp').read_text(encoding='utf-8')
    if any(x in source for x in ('MechanicalDiagnostics','mechanicalHistory','mechanical-samples','diagnostics')):
        raise RuntimeError('Worker still contains persistent diagnostics')
    wave=audit()
    files={}
    with tarfile.open(OUT/'session-package.tar.gz','r:gz') as archive:
        for name in NAMES: files[name]=archive.extractfile(name).read()
    checks='\n'.join('[ "$(sha256sum "$d/'+name+'" | cut -d\' \' -f1)" = '+old['files'][name]['sha256']+' ] || exit 62' for name in NAMES)
    files['apply.sh']=('''#!/bin/sh
set -eu
d=/tmp/hbl-wireless-flash
u="$d/minimal1"
[ -d "$d" ] && [ ! -L "$d" ] && [ -d "$u" ] && [ ! -L "$u" ] || exit 60
[ "$(stat -c '%u:%a' "$d")" = '0:700' ] || exit 60
[ "$(stat -c '%u:%a' "$u")" = '0:700' ] || exit 60
[ ! -e "$u/backup" ] || exit 60
cd "$u"
sha256sum -c update.sha256 >/dev/null || exit 61
@CHECKS@
for service in victory-gui msg2dbus-farm hbl-wireless-worker; do systemctl is-active --quiet "$service" || exit 63; done
grep -Eq '^stage=(ready|forwarded) error=0 .* observe=1 output=1 ' "$d/mechanical-observer.status" || exit 63
chmod 700 "$u/wireless-worker"
"$u/wireless-worker" --check-slots || exit 64
"$u/wireless-worker" --check-timer || exit 64
HBL_MECHANICAL_SYNC_SELFTEST=1 LD_PRELOAD="$u/libhbl-mechanical-observer.so" "$d/mechanical-sync-hook-check" || exit 64
mkdir -m 700 "$u/backup"
for name in wireless-worker libhbl-mechanical-observer.so ui.rcc manifest.sha256; do cp -p "$d/$name" "$u/backup/$name"; done
for name in diagnostics mechanical-samples last-off-reason; do [ ! -f "$d/$name" ] || cp "$d/$name" "$u/backup/$name"; done
resume() {
    rm -f "$d/worker.status" "$d/runtime.status" "$d/mechanical-observer.status"
    systemctl start hbl-wireless-worker || return 1
    for n in 1 2 3 4 5; do
        [ -S "$d/mechanical-sync.sock" ] && [ "$(cat "$d/worker.status" 2>/dev/null)" = worker-ready-default-off ] && break
        sleep 1
    done
    [ -S "$d/mechanical-sync.sock" ] && [ "$(cat "$d/worker.status" 2>/dev/null)" = worker-ready-default-off ] || return 1
    systemctl restart msg2dbus-farm || return 1
    systemctl start victory-gui || return 1
}
rollback() {
    result=$?
    trap - 0 1 2 15
    systemctl stop hbl-wireless-worker victory-gui || true
    for name in wireless-worker libhbl-mechanical-observer.so ui.rcc manifest.sha256; do
        cp -p "$u/backup/$name" "$d/$name.rollback" && mv -f "$d/$name.rollback" "$d/$name"
    done
    resume || true
    printf 'minimal-update-rolled-back\\n' > "$u/result"
    exit "$result"
}
trap rollback 0
trap 'exit 72' 1 2 15
systemctl stop hbl-wireless-worker victory-gui
rm -f "$d/diagnostics" "$d/mechanical-samples" "$d/last-off-reason" "$d/mechanical-timing"
for name in wireless-worker libhbl-mechanical-observer.so ui.rcc manifest.sha256; do
    cp "$u/$name" "$d/$name.next" && mv -f "$d/$name.next" "$d/$name"
done
chmod 700 "$d/wireless-worker"
cd "$d"
sha256sum -c manifest.sha256 >/dev/null
resume
for n in 1 2 3 4 5 6 7 8 9 10; do
    sleep 1
    [ "$(cat "$d/runtime.status" 2>/dev/null)" = ui-loaded-worker-default-off ] && break
done
[ "$(cat "$d/runtime.status" 2>/dev/null)" = ui-loaded-worker-default-off ]
for service in victory-gui msg2dbus-farm hbl-wireless-worker; do systemctl is-active --quiet "$service"; done
grep -q '^stage=ready error=0 .* observe=1 output=1 ' "$d/mechanical-observer.status"
[ "$(cat "$d/worker.status" 2>/dev/null)" = worker-ready-default-off ]
printf 'minimal-path-ready-default-off\\n' > "$u/result"
trap - 0 1 2 15
cat "$u/result"
'''.replace('@CHECKS@',checks)).encode('utf-8')
    files['update.sha256']=''.join(sha(data)+'  '+name+'\n' for name,data in sorted(files.items())).encode('ascii')
    UPDATE.mkdir(exist_ok=True)
    for name,data in files.items(): (UPDATE/name).write_bytes(data)
    subprocess.run(['C:/Program Files/Git/bin/bash.exe','--noprofile','--norc','-n',str(UPDATE/'apply.sh')],check=True,timeout=10)
    buffer=io.BytesIO()
    with tarfile.open(fileobj=buffer,mode='w',format=tarfile.USTAR_FORMAT) as archive:
        for name,data in sorted(files.items()):
            member=tarfile.TarInfo(name); member.mode=0o600; member.size=len(data); member.mtime=0
            archive.addfile(member,io.BytesIO(data))
    packed=gzip.compress(buffer.getvalue(),mtime=0)
    with tarfile.open(fileobj=io.BytesIO(packed),mode='r:gz') as archive:
        assert {m.name for m in archive}==set(files)
        for m in archive: assert m.isfile() and archive.extractfile(m).read()==files[m.name]
    (UPDATE/'update.tar.gz').write_bytes(packed)
    report={'sha256':sha(packed),'bytes':len(packed),'files':{n:sha(d) for n,d in files.items()},
        'previousFiles':old['files'],'newFiles':new['files'],'farmPayloadUnchanged':True,
        'waveformAudit':wave,'preparedRequestChecks':1000,'physicalLatencyMeasured':False,
        'continuousDiagnostics':False,'diagnosticThread':False,'sampleStatistics':False,
        'startupAndFaultStatusOnly':True,'liveCounterTelemetryAvailable':False,
        'installed':False,'agentFlashTrials':0,'cameraShotsTriggered':0}
    (UPDATE/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {k:report[k] for k in ('sha256','bytes','farmPayloadUnchanged','installed')}

def stage(session): return stage_common(session,UPDATE,REMOTE)

if __name__=='__main__': print(make())
