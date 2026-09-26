"""专用线程版的固定增量传输；没有自动设备连接入口。"""
import base64
import hashlib
import io
import json
from pathlib import Path
import shlex
import tarfile
import time
import package_mechanical_direct as candidate
from mechanical_hw_ready_transfer import DECODER

HERE = Path(__file__).resolve().parents[1]
OUT = HERE / 'build/mechanical-direct-candidate'


def package():
    installed = candidate.evidence()
    report = json.loads((OUT / 'package-validation.json').read_text(encoding='utf-8'))
    if report.get('previousInstallation'):
        previous_path = (HERE / report['previousInstallation']).resolve()
        assert previous_path.is_relative_to(OUT)
        installed = json.loads(previous_path.read_text(encoding='utf-8'))
        assert installed['installed'] and installed['packageSha256'] == report['baselinePackageSha256']
    assert report['remoteDirectory'] in ('/tmp/hbl-wireless-flash/d1', '/tmp/hbl-wireless-flash/d2')
    data = (OUT / 'update.tar.gz').read_bytes()
    assert report['passed'] and len(data) == report['packageBytes']
    assert hashlib.sha256(data).hexdigest() == report['packageSha256']
    for name, expected in report['sourceHashes'].items():
        assert hashlib.sha256((HERE / name).read_bytes()).hexdigest() == expected
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        members = archive.getmembers()
        assert len(members) == len(report['files']) == 5
        assert {m.name for m in members} == set(report['files'])
        for member in members:
            assert member.isfile() and '/' not in member.name and member.name != '..'
            raw = archive.extractfile(member).read()
            assert len(raw) == report['files'][member.name]['bytes']
            assert hashlib.sha256(raw).hexdigest() == report['files'][member.name]['sha256']
    return report, data, installed


def stage(session):
    assert not session.failed
    report, data, previous = package()
    remote = report['remoteDirectory']
    result = session.command('direct-baseline', "d=/tmp/hbl-wireless-flash;sha256sum \"$d/wireless-worker\" \"$d/libhbl-mechanical-observer.so\" | cut -d' ' -f1")
    assert result['output'].split() == [previous['files'][name]['sha256'] for name in ('wireless-worker', 'libhbl-mechanical-observer.so')]
    result = session.command('direct-camera-services', 'systemctl is-active victory-gui msg2dbus-farm')
    assert result['output'].split() == ['active', 'active']
    session.command('direct-create-stage', 'test ! -e ' + remote + ' && mkdir -m 700 ' + remote)
    for index, start in enumerate(range(0, len(DECODER), 90)):
        session.command('direct-decoder-' + str(index), 'printf %s ' + shlex.quote(DECODER[start:start+90]) + (' >' if index == 0 else ' >>') + remote + '/d.awk')
    encoded = base64.b64encode(data).decode('ascii')
    parts = [encoded[start:start+176] for start in range(0, len(encoded), 176)]
    for index, part in enumerate(parts):
        session.command('direct-package-' + str(index), 'printf %s ' + shlex.quote(part) + (' >' if index == 0 else ' >>') + remote + '/p64')
        if (index + 1) % 100 == 0:
            print('direct package chunks', index + 1, '/', len(parts), flush=True)
    session.command('direct-decode-once', 'd=' + remote + ';(printf \'%b\' "$(awk -f "$d/d.awk" "$d/p64")" >"$d/update.tar.gz";sha256sum "$d/update.tar.gz" >"$d/decode.sha") </dev/null >/dev/null 2>&1 &')
    for attempt in range(120):
        time.sleep(1)
        result = session.command('direct-archive-check-' + str(attempt), 'd=' + remote + ';if test -f "$d/decode.sha";then cat "$d/decode.sha";else printf pending;fi')
        if result['output'] != 'pending':
            break
    else:
        raise RuntimeError('Decode still pending; do not dispatch again')
    assert result['output'].split()[0] == report['packageSha256'], 'Archive mismatch; extraction refused'
    result = session.command('direct-extract-verified', 'cd ' + remote + ' && tar xzf update.tar.gz && sha256sum -c update.sha256 >/dev/null && sh -n apply.sh && printf direct-package-verified')
    assert result['output'] == 'direct-package-verified'
    return {'packageVerified': True, 'chunks': len(parts), 'bytes': len(data), 'packageSha256': report['packageSha256']}


def mock():
    from unittest.mock import patch
    report, _, previous = package()
    class Session:
        failed = False
        def __init__(self, wrong_hash=False):
            self.commands = []; self.wrong_hash = wrong_hash
        def command(self, label, command):
            assert 0 < len(command.encode('ascii')) <= 231 and '\n' not in command
            self.commands.append((label, command))
            if label == 'direct-baseline':
                output = '\n'.join(previous['files'][name]['sha256'] for name in ('wireless-worker', 'libhbl-mechanical-observer.so'))
            elif label == 'direct-camera-services': output = 'active\nactive\n'
            elif label.startswith('direct-archive-check-'): output = ('0' * 64 if self.wrong_hash else report['packageSha256']) + ' update.tar.gz\n'
            elif label == 'direct-extract-verified': output = 'direct-package-verified'
            else: output = ''
            return {'output': output}
    with patch.object(time, 'sleep', lambda seconds: None):
        session = Session(); result = stage(session)
        refused = Session(True)
        try: stage(refused)
        except AssertionError: pass
        else: raise AssertionError('Wrong archive accepted')
    assert sum(label == 'direct-decode-once' for label, _ in session.commands) == 1
    assert not any(label == 'direct-extract-verified' for label, _ in refused.commands)
    proof = {'passed': True, 'hardwareRequests': 0, 'commands': len(session.commands),
             'maxCommandBytes': max(len(command.encode('ascii')) for _, command in session.commands),
             'decodeDispatches': 1, 'wrongHashStopsBeforeExtraction': True,
             'packageSha256': result['packageSha256'],
             'sourceHashes': {str(Path(__file__).relative_to(HERE)): hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
    (OUT / 'transfer-validation.json').write_text(json.dumps(proof, indent=2) + '\n', encoding='utf-8')
    return proof


if __name__ == '__main__':
    print(json.dumps(mock()))
