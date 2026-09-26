"""核对本次持久安装；可单次重启获授权的 GUI，绝不重装或整机重启。"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'x1d/patch-distribution'
sys.dont_write_bytecode = True
sys.path[:0] = [str(PACKAGE), str(ROOT / 'x1d/tools')]
from usb_transport import Channel


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    assert Path.cwd().resolve() == ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build')
    parser.add_argument('--restart-gui', action='store_true')
    args = parser.parse_args()
    out = Path(args.build).resolve()
    assert out.parent == PACKAGE / 'build' and out.name.startswith('confirmed-ui-')
    evidence = json.loads((out / 'final-release-validation.json').read_text(encoding='utf-8'))
    assert evidence['passed']
    assert sha((out / 'x1d-authorized-candidate.tgz').read_bytes()) == evidence['archiveSha256']
    client = json.loads((out / 'native-client-package.json').read_text(encoding='utf-8'))
    native_result = json.loads((Path(client['directory']) / 'last-result.json').read_text(encoding='utf-8'))
    assert native_result['completed'] and native_result['action'] == 'install'
    record = out / 'installation-result.json'
    result = json.loads(record.read_text(encoding='utf-8')) if record.exists() else {
        'installed': True, 'nativeClientConfirmed': True, 'coldBootVerified': False,
        'performanceValidated': False, 'userValidatedDragSmooth': False,
        'cameraBusinessRequests': 0, 'wholeCameraRestartRequested': False,
    }

    def save():
        record.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')

    channel = Channel()

    def command(text):
        assert len(text.encode('ascii')) <= 231
        return channel.command(text)

    def digest(path):
        answer = command('sha256sum ' + path).split()
        assert len(answer) == 2 and re.fullmatch('[0-9a-f]{64}', answer[0]) and answer[1] == path
        return answer[0]

    def main_pid():
        value = command('systemctl show -p MainPID victory-gui')
        assert re.fullmatch('MainPID=[0-9]+', value)
        return int(value.split('=')[1])

    def services():
        return {name: command('systemctl is-active ' + name + ';true') for name in
                ('victory-gui', 'msg2dbus-farm', 'configstore', 'jpeg-daemon', 'bodystate-daemon')}

    try:
        with channel.session():
            expected_manifest = sha((out / 'stage/files/manifest.sha256').read_bytes())
            result['manifestReadbackMatched'] = digest('/opt/hbl-af-only-v1/manifest.sha256') == expected_manifest
            assert result['manifestReadbackMatched'], 'Installed package differs; GUI restart refused'
            result['payloadVerifiedOnCamera'] = command('cd /opt/hbl-af-only-v1 && sha256sum -c manifest.sha256 >/dev/null 2>&1;echo $?') == '0'
            assert result['payloadVerifiedOnCamera']
            result['nativeLauncherMatched'] = digest('/opt/hbl-patch-launch') == evidence['nativeComponents']['files/camera-launch']
            assert result['nativeLauncherMatched']
            result['rootMountOptions'] = command("awk '$2==\"/\"{v=$4}END{print v}' /proc/mounts")
            assert 'ro' in result['rootMountOptions'].split(',')
            boot_marker = command('sha256sum /proc/sys/kernel/random/boot_id').split()[0]
            assert re.fullmatch('[0-9a-f]{64}', boot_marker)
            result.setdefault('bootMarkerSha256', boot_marker)
            result['lastObservedBootMarkerSha256'] = boot_marker
            result['servicesBefore'] = services()
            assert all(value == 'active' for value in result['servicesBefore'].values())
            old_pid = main_pid()
            assert old_pid > 1
            if args.restart_gui:
                assert not result.get('guiRestartAttempted'), 'GUI restart already attempted; inspect status, never redispatch'
                assert command('test ! -L /run/hbl-four-module && stat -c %u:%a:%F /run/hbl-four-module') == '0:700:directory'
                pid_path = '/run/hbl-four-module/gui.pid'
                assert command('test ! -L ' + pid_path + ' && stat -c %u:%h:%F ' + pid_path) == '0:1:regular file'
                assert command('cat ' + pid_path) == str(old_pid)
                result['guiRestartAttempted'] = True
                result['oldGuiPid'] = old_pid
                save()
                assert command('systemctl daemon-reload;echo $?') == '0'
                # This is one explicit service stop. An uncertain transport
                # result leaves the attempt on disk and must not be replayed.
                assert command('systemctl stop victory-gui;echo $?') == '0'
                assert main_pid() == 0 and command('systemctl is-active victory-gui;true') == 'inactive'
                result['guiStopped'] = True
                save()
                assert command('p=' + pid_path + ';test ! -L "$p" && test "$(cat "$p")" = ' + str(old_pid) + ' && rm "$p";echo $?') == '0'
                result['guiStartAttempted'] = True
                save()
                assert command('systemctl start --no-block victory-gui;echo $?') == '0'
                for _ in range(40):
                    if main_pid() > 1 and command('systemctl is-active victory-gui;true') == 'active':
                        break
                    time.sleep(1)
                else:
                    raise RuntimeError('GUI startup not confirmed; no automatic restart')
                time.sleep(3)
            result['servicesAfter'] = services()
            result['guiActive'] = result['servicesAfter']['victory-gui'] == 'active'
            result['guiPid'] = main_pid()
            result['guiRestartConfirmed'] = bool(result.get('guiStartAttempted') and result['guiActive'] and
                                                result['guiPid'] != result['oldGuiPid'])
            if result['guiRestartConfirmed']:
                runtime = {}
                for local, remote in [('hotspot-libhotspot-entry.so', 'libhotspot-entry.so'),
                                      ('hotspot-radio-mode.sh', 'radio-mode.sh'), ('af-ui.rcc', 'flash-ui.rcc')]:
                    runtime[remote] = digest('/run/hbl-hotspot-ui/' + remote) == sha((out / 'stage/files' / local).read_bytes())
                result['runtimeFilesMatched'] = runtime
                assert all(runtime.values())
                result['resourceStatus'] = command('cat /run/hbl-hotspot-ui/resource.status')
                assert result['resourceStatus'] == 'sealed-resource-registered'
                pid = result['guiPid']
                result['newEntryMapped'] = command('grep -q /run/hbl-hotspot-ui/libhotspot-entry.so /proc/' + str(pid) + '/maps;echo $?') == '0'
                assert result['newEntryMapped']
            assert all(value == 'active' for value in result['servicesAfter'].values())
            if boot_marker != result['bootMarkerSha256'] and result.get('newEntryMapped'):
                ready = command('test -f /run/hbl-four-module/boot.ready && test ! -f /run/hbl-four-module/boot-failed && echo yes || echo no')
                result['launcherRolesAfterBoot'] = {role: command('cat /run/hbl-launch-trace/' + role + '.status')
                    for role in ('gui', 'farm', 'config', 'jpeg', 'body')}
                assert ready == 'yes' and all(value == 'authorized-dispatch' for value in result['launcherRolesAfterBoot'].values())
                result['coldBootVerified'] = True
                result['coldBootScope'] = 'Boot marker changed; all five native launcher roles authorized; services active; current resource/library hashes matched; no startup failure marker'
    finally:
        result['readbackRequests'] = channel.requests
        save()
    print(json.dumps({key: result.get(key) for key in ('installed', 'manifestReadbackMatched', 'payloadVerifiedOnCamera',
        'nativeLauncherMatched', 'rootMountOptions', 'guiRestartConfirmed', 'guiActive', 'runtimeFilesMatched',
        'resourceStatus', 'newEntryMapped', 'coldBootVerified', 'performanceValidated')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
