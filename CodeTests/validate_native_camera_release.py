"""检查最终发行归档与已通过目标验证的组件是否一致；不连接相机。"""
from pathlib import Path
import argparse
import hashlib
import io
import json
import struct
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'x1d/patch-distribution'
sys.dont_write_bytecode = True
sys.path.insert(0, str(PACKAGE))
import build as distribution


def digest(data):
    return hashlib.sha256(data).hexdigest()


def static_arm(data):
    assert data[:7] == b'\x7fELF\x01\x01\x01' and len(data) >= 52
    assert struct.unpack_from('<HH', data, 16) == (2, 40)
    offset = struct.unpack_from('<I', data, 28)[0]
    width, count = struct.unpack_from('<HH', data, 42)
    assert width >= 32 and offset + width * count <= len(data)
    assert all(struct.unpack_from('<I', data, offset + width * i)[0] != 3 for i in range(count))


def manifest_matches(text, files, prefix=''):
    seen = set()
    for line in text.decode('ascii').splitlines():
        expected, name = line.split('  ', 1)
        assert name not in seen and name and not name.startswith('/') and '..' not in name
        seen.add(name)
        assert digest(files[prefix + name]) == expected, 'Manifest mismatch: ' + name
    assert seen
    return seen


def main():
    assert Path.cwd().resolve() == ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build')
    args = parser.parse_args()
    out = Path(args.build).resolve()
    assert out.parent == PACKAGE / 'build' and out.name.startswith('confirmed-ui-')
    report = json.loads((out / 'build-report.json').read_text(encoding='utf-8'))
    archive = (out / 'x1d-authorized-candidate.tgz').read_bytes()
    assert digest(archive) == report['archiveSha256']
    files, modes = {}, {}
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as bundle:
        for member in bundle.getmembers():
            assert member.isfile() and member.name not in files
            assert member.uid == member.gid == 0 and member.size <= 64 * 1024 * 1024
            assert not member.name.startswith('/') and '..' not in member.name
            files[member.name] = bundle.extractfile(member).read()
            modes[member.name] = member.mode
    assert files['transaction-profile'] == b'native-v1\n'
    assert 'install.sh' not in files and 'remove.sh' not in files
    assert set(files) - {'package.sha256'} == manifest_matches(files['package.sha256'], files)
    payload = manifest_matches(files['files/manifest.sha256'], files, 'files/')
    assert {'files/' + name for name in payload} == {
        name for name in files if name.startswith('files/')
    } - {'files/manifest.sha256', 'files/authorization.bin'}
    distribution.NATIVE_BOOTSTRAP = True
    bindings = {}
    for name, checker in [
        ('files/camera-launch', distribution.checked_native_launcher),
        ('files/camera-bootstrap', distribution.checked_native_bootstrap),
        ('camera-transaction', distribution.checked_native_transaction),
    ]:
        expected = checker().read_bytes()
        assert files[name] == expected and modes[name] == 0o700
        static_arm(expected)
        bindings[name] = digest(expected)
    scripts = sorted(name for name in files if name.endswith('.sh'))
    assert scripts == ['files/hotspot-radio-mode.sh', 'files/launch.sh',
                       'files/prepare-radio.sh', 'files/radio-mode.sh']
    assert files['files/launch.sh'] == b'#!/bin/sh\nexec /opt/hbl-patch-launch "$@"\n'
    for name in ['gui.sh', 'farm.sh', 'body.sh', 'coordinate.sh', 'common.sh', 'bus-ready.sh',
                 'hotspot-Main.qml', 'hotspot-Entry.qml', 'hotspot-network.sh', 'hotspot-dhcp.sh']:
        assert 'files/' + name not in files
    for name, role in [('gui.conf', 'gui'), ('farm.conf', 'farm'), ('body.conf', 'body'),
                       ('full-jpeg-config.conf', 'config'), ('full-jpeg-encoder.conf', 'jpeg')]:
        assert files['files/' + name] == ('[Service]\nExecStart=\nExecStart=/opt/hbl-patch-launch ' + role + '\n').encode()
    features = report['features']
    assert features['experimentalNetwork'] is False
    for name in ['nativeFocusCore', 'nativeTouchCore', 'nativeFlashCore',
                 'nativePagePoolCore', 'nativeSettingsRules', 'sealedQml']:
        assert features[name] is True
    assert not features['newReplayEnabled'] and not features['ownViewfinderEnabled'] and not features['formatLockEnabled']
    assert report['jpegQuality']['normal'] == 92 and report['jpegQuality']['high'] == 98
    assert report['sourceProtection']['remainingCameraScripts'] == scripts
    result = dict(passed=True, hardwareRequests=0, archiveSha256=digest(archive),
                  memberCount=len(files), nativeComponents=bindings, remainingCameraScripts=scripts,
                  experimentalNetworkIncluded=False, allBusinessScriptsRemoved=False,
                  coldBootValidated=False, reverseEngineeringHoursEstablished=None)
    (out / 'final-release-validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
