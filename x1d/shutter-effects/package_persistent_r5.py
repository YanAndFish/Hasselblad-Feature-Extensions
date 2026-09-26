"""Reissue the X1D effect from the actually installed startup-repair baseline.

Builds an offline signed archive. It does not open the camera connection.
"""
from pathlib import Path
import hashlib
import io
import json
import sys
import tarfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / 'build/candidate'
BASE = ROOT / 'x1d/patch-distribution/build/startup-repair-20260923-002840/x1d-authorized-candidate.tgz'
BASE_REPORT = ROOT / 'x1d/patch-distribution/build/startup-repair-20260923-002840/build-report.json'
LOADER = ROOT / 'x1d/patch-distribution/build/boot-hold-repair/libhbl-af-loader.so'
ARCHIVE = OUT / 'x1d-ciallo-persistent-candidate-r5.tgz'
REPORT = OUT / 'result-r5.json'

sys.path.insert(0, str(ROOT / 'x1d/patch-distribution'))
import licensing as lic
sys.path.insert(0, str(ROOT / 'x1d/wifi-region/temporary-ui'))
import seal_resources


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_members(path):
    result = {}
    with tarfile.open(path, 'r:gz') as archive:
        for info in archive.getmembers():
            if not info.isfile() or info.name in result or info.name.startswith('/') or '..' in Path(info.name).parts:
                raise ValueError('Unsafe baseline archive member')
            result[info.name] = (info, archive.extractfile(info).read())
    return result


def checked_lists(members):
    listed = {}
    for line in members['package.sha256'][1].decode('ascii').splitlines():
        expected, name = line.split('  ', 1)
        if name in listed or name not in members or digest(members[name][1]) != expected:
            raise ValueError('Baseline package checksum mismatch')
        listed[name] = expected
    if set(listed) != set(members) - {'package.sha256'}:
        raise ValueError('Incomplete baseline package checksum list')
    manifest = {}
    for line in members['files/manifest.sha256'][1].decode('ascii').splitlines():
        expected, name = line.split('  ', 1)
        if name in manifest or 'files/' + name not in members or digest(members['files/' + name][1]) != expected:
            raise ValueError('Baseline payload checksum mismatch')
        manifest[name] = expected
    if set(manifest) != {name[6:] for name in members if name.startswith('files/')} - {'manifest.sha256', 'authorization.bin'}:
        raise ValueError('Incomplete baseline payload checksum list')
    return manifest


def main():
    if ARCHIVE.exists() or REPORT.exists():
        raise FileExistsError('Keep prior candidate immutable')
    base_report = json.loads(BASE_REPORT.read_text(encoding='utf-8'))
    if digest(BASE.read_bytes()) != base_report['archiveSha256']:
        raise ValueError('Startup-repair baseline changed')
    members = read_members(BASE)
    old_manifest = checked_lists(members)
    original = json.loads((OUT / 'result.json').read_text(encoding='utf-8'))
    if not original['nativeCompiled'] or not original['resourceSealed']:
        raise ValueError('Native X1D effect was not verified')
    if digest(LOADER.read_bytes()) != old_manifest['libhbl-af-loader.so']:
        raise ValueError('Current camera startup repair does not match baseline')
    unsealed = seal_resources.unseal(
        members['files/af-ui.rcc'][1],
        seal_resources.host_library(original['resourceSealId']))
    if digest(unsealed) != original['sourceRccSha256']:
        raise ValueError('GUI resource baseline changed')
    changed = {
        'files/af-ui.rcc': (OUT / 'af-ui.rcc').read_bytes(),
        'files/hotspot-libhotspot-entry.so': (OUT / 'hotspot-libhotspot-entry.so').read_bytes(),
        'files/ciallo.wav': (HERE / 'audio/ciallo-yaoyao.wav').read_bytes(),
    }
    if digest(changed['files/ciallo.wav']) != original['audioSha256']:
        raise ValueError('Long audio has changed')
    # Prove this is a narrow extension of the current package.
    if any(digest(members['files/' + name][1]) != expected for name, expected in old_manifest.items()):
        raise ValueError('Unexpected baseline payload change')
    for name, data in changed.items():
        if name in members:
            members[name] = (members[name][0], data)
        else:
            info = tarfile.TarInfo(name); info.mode = 0o600
            members[name] = (info, data)
    file_names = sorted(name for name in members if name.startswith('files/') and name not in ('files/manifest.sha256', 'files/authorization.bin'))
    manifest = ''.join(digest(members[name][1]) + '  ' + name[6:] + '\n' for name in file_names).encode('ascii')
    members['files/manifest.sha256'] = (members['files/manifest.sha256'][0], manifest)
    key = lic.PRIVATE / 'signing-key.pem'
    serials = lic.parse_whitelist(lic.PRIVATE / 'WHITELIST.md')
    public = lic.openssl('pkey', '-in', key, '-pubout', '-outform', 'DER')
    previous = members['files/authorization.bin'][1]
    previous_manifest = read_members(BASE)['files/manifest.sha256'][1]
    count = int.from_bytes(previous[40:44], 'little')
    authorized = [serial for serial in serials if lic.verify(previous, public, serial, previous_manifest)]
    if count < 1 or len(authorized) != count:
        raise ValueError('Could not prove existing authorized device set')
    signature, _ = lic.issue(key, authorized, manifest)
    if not all(lic.verify(signature, public, serial, manifest) for serial in authorized):
        raise ValueError('New authorization failed verification')
    members['files/authorization.bin'] = (members['files/authorization.bin'][0], signature)
    checks = ''.join(digest(members[name][1]) + '  ' + name + '\n' for name in sorted(members) if name != 'package.sha256').encode('ascii')
    members['package.sha256'] = (members['package.sha256'][0], checks)
    if members['camera-transaction'][0].mode & 0o111 == 0:
        raise ValueError('Native camera transaction lost its executable mode')
    with tarfile.open(ARCHIVE, 'w:gz') as archive:
        for name in sorted(members):
            template, data = members[name]
            info = tarfile.TarInfo(name)
            info.size = len(data); info.mode = template.mode
            info.uid = info.gid = 0
            archive.addfile(info, io.BytesIO(data))
    checked_lists(read_members(ARCHIVE))
    report = dict(original)
    report.update(packagePath=str(ARCHIVE), packageSha256=digest(ARCHIVE.read_bytes()),
                  baseline='startup-repair-20260923-002840', installed=False,
                  cameraValidated=False, offlineInstallReady=True,
                  preservesCurrentLoader=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Signed startup-repair-compatible X1D candidate ready')


if __name__ == '__main__':
    main()
