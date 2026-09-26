"""为已装预准备版生成只替换 worker 的记录候选包；无设备操作。"""
from pathlib import Path
import gzip
import hashlib
import io
import json
import subprocess
import tarfile

HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]
BASE=HERE/'build/mechanical-hw-ready-candidate'
OUT=HERE/'build/mechanical-timing-candidate'
def sha(data): return hashlib.sha256(data).hexdigest()

def archive_bytes(files):
    raw=io.BytesIO()
    with tarfile.open(fileobj=raw,mode='w',format=tarfile.USTAR_FORMAT) as archive:
        for name,data in sorted(files.items()):
            item=tarfile.TarInfo(name); item.size=len(data); item.mode=0o600; item.mtime=0
            archive.addfile(item,io.BytesIO(data))
    packed=gzip.compress(raw.getvalue(),mtime=0)
    with tarfile.open(fileobj=io.BytesIO(packed),mode='r:gz') as archive:
        assert {p.name for p in archive}==set(files)
        for p in archive: assert p.isfile() and archive.extractfile(p).read()==files[p.name]
    return packed

def package():
    if Path.cwd().resolve()!=ROOT: raise RuntimeError('Workspace mismatch')
    client=json.loads((OUT/'client-build.json').read_text(encoding='utf-8'))
    parent=json.loads((BASE/'package-validation.json').read_text(encoding='utf-8'))
    installed=json.loads((BASE/'installation.json').read_text(encoding='utf-8'))
    if not client['passed'] or not installed['installed']: raise RuntimeError('Missing validated baseline')
    for name,digest in client['sourceHashes'].items():
        if sha((HERE/name).read_bytes())!=digest: raise RuntimeError('Changed recording source: '+name)
    if sha((BASE/'session-package.tar.gz').read_bytes())!=parent['packageSha256']:
        raise RuntimeError('Baseline archive mismatch')
    with tarfile.open(BASE/'session-package.tar.gz','r:gz') as archive:
        files={p.name:archive.extractfile(p).read() for p in archive if p.isfile()}
    for name,data in files.items():
        if sha(data)!=installed['files'][name]['sha256']: raise RuntimeError('Installed baseline differs: '+name)
    files['wireless-worker']=(OUT/'wireless-worker').read_bytes()
    if sha(files['wireless-worker'])!=client['workerSha256']: raise RuntimeError('Worker changed')
    del files['manifest.sha256']
    files['manifest.sha256']=''.join(sha(data)+'  '+name+'\n' for name,data in sorted(files.items())).encode('ascii')
    for name,data in files.items():
        path=OUT/'package-files'/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data)
    full=archive_bytes(files); (OUT/'session-package.tar.gz').write_bytes(full)
    checks='\n'.join('[ "$(sha256sum "$d/'+name+'" | cut -d\' \' -f1)" = '+meta['sha256']+' ] || exit 62'
                     for name,meta in sorted(installed['files'].items()))
    apply='''#!/bin/sh
set -eu
d=/tmp/hbl-wireless-flash
u="$d/timing1"
[ -d "$d" ] && [ ! -L "$d" ] && [ -d "$u" ] && [ ! -L "$u" ] || exit 60
[ "$(stat -c '%u:%a' "$d")" = '0:700' ] || exit 60
[ "$(stat -c '%u:%a' "$u")" = '0:700' ] || exit 60
[ ! -e "$u/backup" ] || exit 60
cd "$u"
sha256sum -c update.sha256 >/dev/null || exit 61
@CHECKS@
for service in victory-gui msg2dbus-farm hbl-wireless-worker; do systemctl is-active --quiet "$service" || exit 63; done
chmod 700 "$u/wireless-worker"
"$u/wireless-worker" --check-slots || exit 64
"$u/wireless-worker" --check-timer || exit 64
mkdir -m 700 "$u/backup"
for name in wireless-worker manifest.sha256; do cp -p "$d/$name" "$u/backup/$name"; done
[ ! -f "$d/timing.bin" ] || cp "$d/timing.bin" "$u/backup/timing.bin"
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
    for name in wireless-worker manifest.sha256; do
        cp -p "$u/backup/$name" "$d/$name.rollback" && mv -f "$d/$name.rollback" "$d/$name"
    done
    resume || true
    printf 'timing-update-rolled-back\\n' > "$u/result"
    exit "$result"
}
trap rollback 0
trap 'exit 72' 1 2 15
systemctl stop hbl-wireless-worker victory-gui
for name in wireless-worker manifest.sha256; do
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
printf 'timing-record-ready-default-off\\n' > "$u/result"
trap - 0 1 2 15
cat "$u/result"
'''.replace('@CHECKS@',checks).encode('utf-8')
    updates={name:files[name] for name in ('wireless-worker','manifest.sha256')}
    updates['apply.sh']=apply
    updates['update.sha256']=''.join(sha(data)+'  '+name+'\n' for name,data in sorted(updates.items())).encode('ascii')
    update=OUT/'update'; update.mkdir(exist_ok=True)
    for name,data in updates.items(): (update/name).write_bytes(data)
    subprocess.run(['C:/Program Files/Git/bin/bash.exe','--noprofile','--norc','-n',str(update/'apply.sh')],check=True,timeout=10)
    packed=archive_bytes(updates); (update/'update.tar.gz').write_bytes(packed)
    report={'packageSha256':sha(full),'packageBytes':len(full),'files':{n:{'sha256':sha(d),'bytes':len(d)} for n,d in files.items()},
            'previousFiles':installed['files'],'updateSha256':sha(packed),'updateBytes':len(packed),
            'farmPayloadSha256':installed['farmPayloadSha256'],'firmwareSha256':client['firmwareSha256'],
            'changedInstalledFiles':['wireless-worker','manifest.sha256'],'compensationImplemented':False,
            'newHardwareInterruptImplemented':False,'ringCapacity':2048,'saveOnlyWhileDisabledAndIdle':True,
            'duringEnabledFileWrites':False,'targetQtRuntimeChecked':False,'hardwareRequests':0,'installed':False}
    (OUT/'package-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {k:report[k] for k in ('packageBytes','updateBytes','changedInstalledFiles','installed')}

if __name__=='__main__': print(package())
