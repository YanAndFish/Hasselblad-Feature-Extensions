"""生成两个开关的完整包和绑定当前纯记录版的增量安装包；无设备操作。"""
from pathlib import Path
import hashlib, importlib.util, json, subprocess, tarfile
from package_mechanical_timing_record import archive_bytes

HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]
BASE=HERE/'build/mechanical-timing-candidate'
OUT=HERE/'build/mechanical-options-candidate'
def sha(data): return hashlib.sha256(data).hexdigest()

def package():
    if Path.cwd().resolve()!=ROOT: raise RuntimeError('Workspace mismatch')
    client=json.loads((OUT/'client-build.json').read_text(encoding='utf-8'))
    firmware=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
    checks=json.loads((OUT/'instruction-checks.json').read_text(encoding='utf-8'))
    installed=json.loads((BASE/'installation.json').read_text(encoding='utf-8'))
    if not client['passed'] or not installed['installed'] or not checks['passed'] or checks['firmwareSha256']!=firmware['sha256']:
        raise RuntimeError('Missing matching validation')
    for name,digest in client['sourceHashes'].items():
        if sha((HERE/name).read_bytes())!=digest: raise RuntimeError('Changed source '+name)
    with tarfile.open(BASE/'session-package.tar.gz','r:gz') as archive:
        files={p.name:archive.extractfile(p).read() for p in archive if p.isfile()}
    for name,data in files.items():
        if sha(data)!=installed['files'][name]['sha256']: raise RuntimeError('Parent installed mismatch '+name)
    for name,meta in client['outputs'].items():
        files[name]=(OUT/name).read_bytes()
        if sha(files[name])!=meta['sha256']: raise RuntimeError('Changed binary')
    fw=(OUT/'hardware-ready-wltest.bin').read_bytes()
    if sha(fw)!=firmware['sha256']: raise RuntimeError('Firmware mismatch')
    for index,(start,end) in enumerate(((307100,307104),(399416,399420),(606750,len(fw)))):
        files['delta/'+str(index)+'.bin']=fw[start:end]
    files['prepare-radio.sh']=(HERE/'prepare-radio.sh.in').read_text(encoding='ascii').replace('@FIRMWARE_SHA256@',firmware['sha256']).replace('0x584e','0x5851').encode('ascii')
    files['release-radio.sh']=files['release-radio.sh'].replace(b'[ "$marker" = 0x5850 ]',b'[ "$marker" = 0x5850 ] || [ "$marker" = 0x5851 ]')
    installer=files['mechanical-sync-install.sh'].decode('utf-8').replace('0x5850','0x5851')
    installer=installer.replace('"$d/wireless-worker" --check-timer || exit 68','"$d/wireless-worker" --check-timer || exit 68\n"$d/wireless-worker" --check-options || exit 68')
    files['mechanical-sync-install.sh']=installer.encode('utf-8')
    files['switch-process.sh']=(HERE/'native/switch_mechanical_process.sh').read_bytes().replace(b'\r\n',b'\n')
    spec=importlib.util.spec_from_file_location('options_assets',HERE/'build.py'); assets=importlib.util.module_from_spec(spec); spec.loader.exec_module(assets)
    qml=OUT/'qml'
    qmlfiles={'/'+str(p.relative_to(qml)).replace('\\','/'):p.read_text(encoding='utf-8') for p in qml.rglob('*.qml')}
    files['ui.rcc']=assets.rcc(qmlfiles)
    del files['manifest.sha256']
    files['manifest.sha256']=''.join(sha(data)+'  '+name+'\n' for name,data in sorted(files.items())).encode('ascii')
    for name,data in files.items():
        p=OUT/'package-files'/name; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(data)
    full=archive_bytes(files); (OUT/'session-package.tar.gz').write_bytes(full)
    oldchecks='\n'.join('[ "$(sha256sum "$d/'+name+'" | cut -d\' \' -f1)" = '+meta['sha256']+' ] || exit 62' for name,meta in sorted(installed['files'].items()))
    oldnames=' '.join(sorted(installed['files']))
    newnames=' '.join(sorted(files))
    apply='''#!/bin/sh
set -eu
d=/tmp/hbl-wireless-flash
u="$d/options1"
[ -d "$d" ] && [ ! -L "$d" ] && [ -d "$u" ] && [ ! -L "$u" ] || exit 60
[ "$(stat -c '%u:%a' "$d")" = '0:700' ] && [ "$(stat -c '%u:%a' "$u")" = '0:700' ] || exit 60
[ ! -e "$u/backup" ] && [ ! -e "$d/process-mode" ] && [ ! -e "$d/switch-process.sh" ] || exit 60
cd "$u"
sha256sum -c update.sha256 >/dev/null || exit 61
@CHECKS@
for service in victory-gui msg2dbus-farm hbl-wireless-worker; do systemctl is-active --quiet "$service" || exit 63; done
chmod 700 "$u/wireless-worker" "$u/netlink-probe" "$u/mechanical-sync-hook-check"
HBL_MECHANICAL_SYNC_SELFTEST=1 LD_PRELOAD="$u/libhbl-mechanical-observer.so" "$u/mechanical-sync-hook-check" || exit 68
"$u/wireless-worker" --check-slots || exit 68
"$u/wireless-worker" --check-timer || exit 68
"$u/wireless-worker" --check-options || exit 68
mkdir -m 700 "$u/backup"
mkdir -m 700 "$u/backup/delta"
for name in @OLD@; do cp -p "$d/$name" "$u/backup/$name"; done
resume() {
    rm -f "$d/worker.status" "$d/runtime.status" "$d/mechanical-observer.status" "$d/worker.sock" "$d/mechanical-sync.sock"
    systemctl start msg2dbus-farm || return 1
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
    systemctl stop victory-gui hbl-wireless-worker msg2dbus-farm || true
    for name in @OLD@; do cp -p "$u/backup/$name" "$d/$name.rollback" && mv -f "$d/$name.rollback" "$d/$name"; done
    rm -f "$d/switch-process.sh" "$d/process-mode"
    sh "$d/prepare-radio.sh" || true
    resume || true
    printf 'options-update-rolled-back\\n' > "$u/result"
    exit "$result"
}
trap rollback 0
trap 'exit 72' 1 2 15
systemctl stop victory-gui hbl-wireless-worker
systemctl stop msg2dbus-farm
[ ! -f "$d/timing.bin" ] || cp "$d/timing.bin" "$u/backup/timing.bin"
for name in @NEW@; do cp "$u/$name" "$d/$name.next" && mv -f "$d/$name.next" "$d/$name"; done
chmod 700 "$d/wireless-worker" "$d/netlink-probe" "$d/mechanical-sync-hook-check"
printf '0\\n' > "$d/process-mode"
cd "$d"
sha256sum -c manifest.sha256 >/dev/null
sh "$d/prepare-radio.sh"
"$d/netlink-probe"
resume
for n in 1 2 3 4 5 6 7 8 9 10; do
    sleep 1
    [ "$(cat "$d/runtime.status" 2>/dev/null)" = ui-loaded-worker-default-off ] && break
done
[ "$(cat "$d/runtime.status" 2>/dev/null)" = ui-loaded-worker-default-off ]
for service in victory-gui msg2dbus-farm hbl-wireless-worker; do systemctl is-active --quiet "$service"; done
grep -q '^stage=ready error=0 .* observe=1 output=1 ' "$d/mechanical-observer.status"
[ "$(cat "$d/worker.status" 2>/dev/null)" = worker-ready-default-off ]
printf 'options-ready-default-off\\n' > "$u/result"
trap - 0 1 2 15
cat "$u/result"
'''.replace('@CHECKS@',oldchecks).replace('@OLD@',oldnames).replace('@NEW@',newnames).encode('utf-8')
    updates=dict(files); updates['apply.sh']=apply
    updates['update.sha256']=''.join(sha(data)+'  '+name+'\n' for name,data in sorted(updates.items())).encode('ascii')
    for name,data in updates.items():
        p=OUT/'update'/name; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(data)
        if name.endswith('.sh'):
            subprocess.run(['C:/Program Files/Git/bin/bash.exe','--noprofile','--norc','-n',str(p)],check=True,timeout=10)
    update=archive_bytes(updates); (OUT/'update/update.tar.gz').write_bytes(update)
    report={'packageSha256':sha(full),'packageBytes':len(full),'updateSha256':sha(update),'updateBytes':len(update),
            'files':{n:{'sha256':sha(d),'bytes':len(d)} for n,d in files.items()},'previousFiles':installed['files'],
            'firmwareSha256':firmware['sha256'],'farmPayloadSha256':installed['farmPayloadSha256'],
            'preparationModes':['held','per-shot'],'processingModes':['separate-process','same-process'],
            'sameProcessCrossThreadDelivery':'bounded Qt event queue when caller thread differs',
            'sourcesRetained':7,'compensationImplemented':False,'newHardwareInterruptImplemented':False,
            'installed':False,'hardwareRequests':0,'targetChecksPassed':False}
    (OUT/'package-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {'packageBytes':len(full),'updateBytes':len(update),'installed':False}

if __name__=='__main__': print(package())
