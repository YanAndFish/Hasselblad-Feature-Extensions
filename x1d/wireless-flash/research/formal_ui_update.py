"""已安装正式引闪的单次界面修正。默认只打包核对，显式参数才传输。"""
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

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import formal_transfer as transfer
from formal_install_session import check_host

HERE = transfer.HERE
OUT = HERE/'build/formal-ui-state-update'
INSTALL = transfer.OUT/'installation-20260912T090210Z.json'
PREVIOUS = transfer.OUT/'installed-20260912T090210Z'
REMOTE = '/tmp/hbl-wireless-flash/ui-state-update'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def build():
    current = check_host()
    previous = json.loads((PREVIOUS/'package-validation.json').read_text(encoding='utf-8'))
    installed = json.loads(INSTALL.read_text(encoding='utf-8'))
    if (not installed.get('installed') or installed.get('currentPackageSha256') or
            installed['packageSha256'] != previous['packageSha256'] or
            sha((PREVIOUS/'session-package.tar.gz').read_bytes()) != previous['packageSha256']):
        raise RuntimeError('Expected original successful installation record')
    changed = {n for n in current['files'] if current['files'][n] != previous['files'][n]}
    if changed != {'formal-ui.rcc', 'libhbl-formal.so', 'manifest.sha256'}:
        raise RuntimeError('Only QML resources, UI adapter and their manifest may change')
    old_manifest = previous['files']['manifest.sha256']['sha256']
    new_manifest = current['files']['manifest.sha256']['sha256']
    script = '''#!/bin/sh
set -eu
umask 077
d=/tmp/hbl-wireless-flash
u=$d/ui-state-update
[ "$(id -u)" = 0 ] || exit 61
for path in "$d" "$u"; do
    [ -d "$path" ] && [ ! -L "$path" ] && [ "$(stat -c '%u:%a' "$path")" = 0:700 ] || exit 61
done
[ "$(cat "$d/formal-state/owner")" = formal-linux-install-v1 ] || exit 61
[ -f "$d/formal-state/install-complete" ] && [ ! -e "$d/formal-stop.request" ] || exit 61
cd "$d"
[ "$(sha256sum manifest.sha256 | cut -d' ' -f1)" = @OLD@ ] || exit 62
sha256sum -c manifest.sha256 >/dev/null || exit 62
[ "$(sha256sum "$u/manifest.sha256" | cut -d' ' -f1)" = @NEW@ ] || exit 62
systemctl is-active --quiet victory-gui msg2dbus-farm || exit 62
[ ! -e "$u/previous.rcc" ] && [ ! -e "$u/previous.so" ] && [ ! -e "$u/previous.manifest" ] || exit 63
cp formal-ui.rcc "$u/previous.rcc"
cp libhbl-formal.so "$u/previous.so"
cp manifest.sha256 "$u/previous.manifest"
stopped=0
changed=0
rollback() {
    result=$?
    trap - 0 1 2 15
    if [ "$result" != 0 ] && [ "$stopped" = 1 ]; then
        systemctl stop victory-gui || exit 69
        if [ "$changed" = 1 ]; then
            cp "$u/previous.rcc" "$d/formal-ui.rcc" || exit 69
            cp "$u/previous.so" "$d/libhbl-formal.so" || exit 69
            cp "$u/previous.manifest" "$d/manifest.sha256" || exit 69
        fi
        systemctl start victory-gui || exit 69
        printf '%s\n' ui-update-failed-original-resources-restored > "$u/result"
    fi
    exit "$result"
}
trap rollback 0
trap 'exit 68' 1 2 15
stopped=1
systemctl stop victory-gui || exit 64
if systemctl is-active --quiet victory-gui; then exit 64; fi
# GUI 的正常退出与两秒心跳失联均撤销无线任务；保留 observer 消费 FARM 消息。
sleep 3
systemctl is-active --quiet msg2dbus-farm || exit 64
changed=1
cp "$u/formal-ui.rcc" "$d/formal-ui.rcc" || exit 65
cp "$u/libhbl-formal.so" "$d/libhbl-formal.so" || exit 65
cp "$u/manifest.sha256" "$d/manifest.sha256" || exit 65
sha256sum -c manifest.sha256 >/dev/null || exit 65
mv "$d/formal-runtime.status" "$u/previous-runtime.status" || exit 65
systemctl start victory-gui || exit 66
for n in 1 2 3 4 5 6 7 8 9 10; do
    [ "$(cat "$d/formal-runtime.status" 2>/dev/null || :)" = formal-ui-loaded-default-off ] && break
    sleep 1
done
[ "$(cat "$d/formal-runtime.status")" = formal-ui-loaded-default-off ] || exit 66
systemctl is-active --quiet victory-gui msg2dbus-farm || exit 66
[ -S "$d/formal-ui.sock" ] && [ -S "$d/formal-worker.sock" ] || exit 66
printf '%s\n' ui-state-update-loaded-default-off > "$u/result"
trap - 0 1 2 15
'''.replace('@OLD@', old_manifest).replace('@NEW@', new_manifest)
    files = {name: (transfer.OUT/'package-files'/name).read_bytes()
             for name in ('formal-ui.rcc', 'libhbl-formal.so', 'manifest.sha256')}
    files['apply.sh'] = script.encode('utf-8')
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(name);info.size=len(data);info.mode=0o600
            archive.addfile(info, io.BytesIO(data))
    data = gzip.compress(stream.getvalue(), mtime=0)
    OUT.mkdir(exist_ok=True)
    (OUT/'update.tar.gz').write_bytes(data)
    (OUT/'apply.sh').write_bytes(files['apply.sh'])
    proof = {'passed': True, 'hardwareRequests': 0, 'bytes': len(data), 'sha256': sha(data),
             'previousPackageSha256': previous['packageSha256'], 'currentPackageSha256': current['packageSha256'],
             'rccSha256': current['files']['formal-ui.rcc']['sha256'],
             'onlyChangedFiles': sorted(changed), 'restartsOnlyVictoryGui': True,
             'changesFarm': False, 'changesRadio': False,
             'sourceSha256': sha(Path(__file__).read_bytes())}
    (OUT/'candidate.json').write_text(json.dumps(proof, indent=2)+'\n')
    return proof, data


def install():
    proof, data = build()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    session = transfer.Session('ui-state-update-'+stamp+'.json')
    session.command('ui-update-stage', 'd='+REMOTE+';test ! -e "$d" && test ! -L "$d" && mkdir -m 700 "$d"')
    encoded = base64.b64encode(data).decode('ascii')
    for number, start in enumerate(range(0, len(encoded), 160)):
        command = 'printf %s '+shlex.quote(encoded[start:start+160])+(' >' if not number else ' >>')+REMOTE+'/p64'
        session.command('ui-update-chunk-'+str(number), command)
    session.command('ui-decode-once', 'd='+REMOTE+';(printf \'%b\' "$(awk -f /tmp/hbl-wireless-flash/d.awk "$d/p64")" >"$d/u.tgz";sha256sum "$d/u.tgz" >"$d/sha") </dev/null >/dev/null 2>&1 &')
    for _ in range(120):
        time.sleep(1)
        result = session.command('ui-decode-result', 'd='+REMOTE+';if test -f "$d/sha";then cat "$d/sha";else printf pending;fi')['output']
        if result != 'pending': break
    else: raise RuntimeError('Decode pending; no retry')
    if result.split()[0] != proof['sha256']: raise RuntimeError('Update archive mismatch')
    session.command('ui-extract', 'cd '+REMOTE+' && tar xzf u.tgz && sh -n apply.sh')
    session.command('ui-apply-once', 'd='+REMOTE+';test ! -e "$d/dispatched" && touch "$d/dispatched" && (sh "$d/apply.sh" >"$d/log" 2>&1;echo $? >"$d/exit") </dev/null >/dev/null 2>&1 &')
    for _ in range(30):
        time.sleep(1)
        result = session.command('ui-apply-result', 'd='+REMOTE+';if test -f "$d/exit";then cat "$d/exit" "$d/result";else printf pending;fi')['output']
        if result != 'pending': break
    else: raise RuntimeError('Apply pending; no retry')
    if result.splitlines() != ['0', 'ui-state-update-loaded-default-off']:
        raise RuntimeError('UI update did not report success')
    installed = json.loads(INSTALL.read_text(encoding='utf-8'))
    installed['currentPackageSha256'] = proof['currentPackageSha256']
    installed['uiUpdates'] = [{'at': stamp, 'rccSha256': proof['rccSha256'],
        'session': str(session.output.relative_to(HERE)).replace('\\','/'), 'allHandlesClosed': all(e['closed'] for e in session.entries),
        'previousPackageSha256': proof['previousPackageSha256'], 'newPackageSha256': proof['currentPackageSha256'],
        'farmWrites': 0, 'radioChanges': 0, 'agentFlashTrials': 0}]
    INSTALL.write_text(json.dumps(installed, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return {'installed': True, 'requests': len(session.entries), 'allHandlesClosed': all(e['closed'] for e in session.entries)}


if __name__ == '__main__':
    if not sys.argv[1:]: print(json.dumps(build()[0]))
    elif sys.argv[1:] == ['--install-current-session']: print(json.dumps(install()))
    else: raise SystemExit('Unsupported arguments')
