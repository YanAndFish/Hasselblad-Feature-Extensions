"""只替换七节点版的两个 Linux 可执行组件，不改变 FARM、FPGA 或无线固件。"""
from pathlib import Path
import gzip
import hashlib
import io
import json
import tarfile

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
BASE = HERE / 'build/mechanical-options-candidate'
OUT = HERE / 'build/mechanical-direct-candidate'
BASE_PACKAGE = '04863977b74d71103bbdc110ed993cd2009b84577f916958912b2380eca3d424'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def evidence():
    installed = json.loads((BASE / 'reinstall-20260911T201239Z/installation.json').read_text(encoding='utf-8'))
    assert installed['installed'] and installed['packageSha256'] == BASE_PACKAGE
    assert installed['sevenSourcesRetained'] and installed['threeSwitchesRetained']
    for name in ('client-build.json', 'dispatch-validation.json'):
        report = json.loads((OUT / name).read_text(encoding='utf-8'))
        assert report['passed']
        for source, expected in report['sourceHashes'].items():
            assert sha((HERE / source).read_bytes()) == expected, 'Changed source: ' + source
    built = json.loads((OUT / 'client-build.json').read_text(encoding='utf-8'))
    for name in ('wireless-worker', 'libhbl-mechanical-observer.so'):
        raw = (OUT / name).read_bytes()
        assert sha(raw) == built['outputs'][name]['sha256']
        assert len(raw) == built['outputs'][name]['bytes']
    return installed


def build(previous_installation=None, previous_archive=None, remote_leaf='d1'):
    assert Path.cwd().resolve() == ROOT
    installed = evidence()
    assert remote_leaf in ('d1', 'd2')
    new = {name: (OUT / name).read_bytes() for name in ('wireless-worker', 'libhbl-mechanical-observer.so')}
    if previous_installation is None:
        assert previous_archive is None and remote_leaf == 'd1'
        manifest = (BASE / 'package-files/manifest.sha256').read_bytes()
    else:
        previous_installation = Path(previous_installation).resolve()
        previous_archive = Path(previous_archive).resolve()
        assert previous_installation.is_relative_to(OUT) and previous_archive.is_relative_to(OUT)
        installed = json.loads(previous_installation.read_text(encoding='utf-8'))
        assert installed['installed'] and installed['kind'] == 'resident-mechanical-direct-dispatch'
        assert installed['sevenSourcesRetained'] and installed['threeSwitchesRetained']
        old_archive = previous_archive.read_bytes()
        assert sha(old_archive) == installed['packageSha256']
        with tarfile.open(fileobj=io.BytesIO(old_archive), mode='r:gz') as archive:
            manifest = archive.extractfile('manifest.sha256').read()
    assert sha(manifest) == installed['files']['manifest.sha256']['sha256']
    for name, raw in new.items():
        old = installed['files'][name]['sha256'].encode()
        assert manifest.count(old) == 1
        manifest = manifest.replace(old, sha(raw).encode())
    new['manifest.sha256'] = manifest
    guards = '\n'.join('[ "$(sha256sum "$d/%s" | cut -d\' \' -f1)" = %s ] || exit 62' %
                       (name, item['sha256']) for name, item in installed['files'].items())
    script = r'''#!/bin/sh
set -eu
d=/tmp/hbl-wireless-flash
u="$d/d1"
[ -d "$d" ] && [ ! -L "$d" ] && [ -d "$u" ] && [ ! -L "$u" ] || exit 60
[ "$(stat -c '%u:%a' "$d")" = '0:700' ] && [ "$(stat -c '%u:%a' "$u")" = '0:700' ] || exit 60
[ ! -e "$u/backup" ] && [ ! -e "$d/process-switch.lock" ] || exit 60
cd "$u"
sha256sum -c update.sha256 >/dev/null || exit 61
@GUARDS@
systemctl is-active --quiet victory-gui || exit 63
systemctl is-active --quiet msg2dbus-farm || exit 63
mode=0
if [ -f "$d/process-mode" ]; then mode=$(cat "$d/process-mode"); fi
case "$mode" in
    0) systemctl is-active --quiet hbl-wireless-worker || exit 63;;
    1) if systemctl is-active --quiet hbl-wireless-worker; then exit 63; fi;;
    *) exit 63;;
esac
chmod 700 "$u/wireless-worker"
"$u/wireless-worker" --check-direct || exit 68
"$u/wireless-worker" --check-slots || exit 68
"$u/wireless-worker" --check-options || exit 68
HBL_MECHANICAL_SYNC_SELFTEST=1 LD_PRELOAD="$u/libhbl-mechanical-observer.so" "$d/mechanical-sync-hook-check" || exit 68
mkdir -m 700 "$u/backup"
for name in wireless-worker libhbl-mechanical-observer.so manifest.sha256; do cp -p "$d/$name" "$u/backup/$name"; done
resume() {
    rm -f "$d/worker.status" "$d/runtime.status" "$d/mechanical-observer.status" "$d/worker.sock" "$d/mechanical-sync.sock"
    systemctl start msg2dbus-farm || return 1
    if [ "$mode" = 0 ]; then
        systemctl start hbl-wireless-worker || return 1
        for n in 1 2 3 4 5; do
            [ -S "$d/mechanical-sync.sock" ] && [ "$(cat "$d/worker.status" 2>/dev/null)" = worker-ready-default-off ] && break
            sleep 1
        done
        [ -S "$d/mechanical-sync.sock" ] && [ "$(cat "$d/worker.status" 2>/dev/null)" = worker-ready-default-off ] || return 1
        systemctl restart msg2dbus-farm || return 1
    fi
    systemctl start victory-gui || return 1
}
rollback() {
    result=$?
    trap - 0 1 2 15
    systemctl stop victory-gui hbl-wireless-worker msg2dbus-farm || true
    for name in wireless-worker libhbl-mechanical-observer.so manifest.sha256; do
        cp -p "$u/backup/$name" "$d/$name.rollback" && mv -f "$d/$name.rollback" "$d/$name"
    done
    resume || true
    printf 'direct-update-rolled-back\n' > "$u/result"
    exit "$result"
}
trap rollback 0
trap 'exit 72' 1 2 15
systemctl stop victory-gui hbl-wireless-worker
systemctl stop msg2dbus-farm
[ "$(/usr/bin/wl phyreg 0 b)" = 0x5851 ]
released=$(/usr/bin/wl phyreg 27 b)
case "$released" in 0x0001|0x1) ;; *) exit 64;; esac
for name in wireless-worker libhbl-mechanical-observer.so manifest.sha256; do
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
systemctl is-active --quiet victory-gui
systemctl is-active --quiet msg2dbus-farm
if [ "$mode" = 0 ]; then systemctl is-active --quiet hbl-wireless-worker; fi
grep -q '^stage=ready error=0 .* observe=1 output=1 ' "$d/mechanical-observer.status"
[ "$(cat "$d/worker.status" 2>/dev/null)" = worker-ready-default-off ]
printf 'direct-ready-default-off mode=%s\n' "$mode" > "$u/result"
trap - 0 1 2 15
cat "$u/result"
'''.replace('@GUARDS@', guards).replace('u="$d/d1"', 'u="$d/' + remote_leaf + '"')
    new['apply.sh'] = script.encode('ascii')
    new['update.sha256'] = ''.join(sha(raw) + '  ' + name + '\n' for name, raw in new.items()).encode('ascii')
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as archive:
        for name, raw in new.items():
            info = tarfile.TarInfo(name)
            info.size = len(raw); info.mode = 0o700 if name in ('wireless-worker', 'apply.sh') else 0o600
            archive.addfile(info, io.BytesIO(raw))
    package = gzip.compress(stream.getvalue(), mtime=0)
    with tarfile.open(fileobj=io.BytesIO(package), mode='r:gz') as archive:
        assert {item.name: archive.extractfile(item).read() for item in archive} == new
    for name, raw in new.items():
        (OUT / ('apply.sh' if name == 'apply.sh' else name + '.package')).write_bytes(raw)
    (OUT / 'update.tar.gz').write_bytes(package)
    report = {'passed': True, 'installed': False, 'hardwareRequests': 0,
              'packageSha256': sha(package), 'packageBytes': len(package), 'baselinePackageSha256': installed['packageSha256'],
              'previousInstallation': str(previous_installation.relative_to(HERE)) if previous_installation else None,
              'remoteDirectory': '/tmp/hbl-wireless-flash/' + remote_leaf,
              'updatedFiles': ['wireless-worker', 'libhbl-mechanical-observer.so', 'manifest.sha256'],
              'files': {name: {'sha256': sha(raw), 'bytes': len(raw)} for name, raw in new.items()},
              'sourceHashes': {str(Path(__file__).relative_to(HERE)): sha(Path(__file__).read_bytes())},
              'firmwareModified': False, 'farmModified': False, 'fpgaModified': False,
              'targetSelfCheckRequired': True, 'physicalTimingVerified': False}
    (OUT / 'package-validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in ('files', 'sourceHashes')}, ensure_ascii=False))
    return report


if __name__ == '__main__':
    build()
