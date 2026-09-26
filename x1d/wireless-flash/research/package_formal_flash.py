"""正式引闪完整临时包：固定原厂输入、当前检查报告、独立可撤销安装脚本。

只在电脑上打包。包内没有自动拍摄、试闪或 FARM 写入入口。
"""
from pathlib import Path, PurePosixPath
import gzip
import hashlib
import io
import json
import tarfile
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
OUT = HERE / 'build/formal-flash-package'
PROGRAM = HERE / 'build/formal-flash-program'
RF = HERE / 'build/formal-flash-candidate'
UI = HERE / 'build/formal-runtime-ui'
BASE_SHA = 'e5eb76a8b333e402b213843e2e93ff771615adcbc05ca7113d04ef0951555159'
FIRMWARE_SHA = '86d10d4131bcaa90dd0781545cec918ab10e56fd3d808c2dc85a019ee9edba98'
DELTAS = ((307100, 4), (399416, 4), (606750, 15842))
PROGRAMS = ('libhbl-formal-observer.so', 'libhbl-formal.so', 'formal-sync-hook-check',
            'formal-client-check', 'formal-netlink-probe', 'formal-system-check')
REPORTS = ('build/formal-flash-program/client-build.json',
           'build/formal-flash-candidate/firmware-build.json',
           'build/formal-flash-candidate/firmware-validation.json',
           'build/formal-sync-capture/validation.json',
           'build/formal-sync-capture/loader-validation.json',
           'build/formal-runtime-ui/compiled.json',
           'build/formal-runtime-ui/validation.json',
           'CodeTests/formal_radio_output/build-report.json',
           'CodeTests/formal_policy_output/validation.json',
           'CodeTests/formal_install_output/validation.json',
           'CodeTests/formal_direct_output/validation.json',
           'CodeTests/formal_session_output/validation.json',
           'CodeTests/formal_hold_output/validation.json',
           'build/formal-flash-candidate/configuration-validation.json')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def read_report(name):
    item = json.loads((HERE / name).read_text(encoding='utf-8'))
    hashes = item.get('sourceHashes', item.get('source_hashes', item.get('sources')))
    require(bool(hashes), 'Report lacks source binding: ' + name)
    for source, digest in hashes.items():
        path = (HERE / source).resolve()
        require(path.is_relative_to(HERE), 'Report source outside module')
        require(sha(path.read_bytes()) == digest, 'Source changed after check: ' + source)
    return item


def evidence():
    require(Path.cwd().resolve() == ROOT, 'workspace mismatch')
    reports = {name: read_report(name) for name in REPORTS}
    for name, report in reports.items():
        if name.endswith(('client-build.json', 'firmware-build.json', 'compiled.json')):
            continue
        passed = report.get('passed')
        require(passed is True or (isinstance(passed, list) and len(passed) == report.get('checks') and not report.get('warnings')),
                'Required validation has not passed: ' + name)
    built = reports[REPORTS[0]]
    require(built.get('compiled') is True and set(built['outputs']) == set(PROGRAMS), 'Client build incomplete')
    for name in PROGRAMS:
        raw = (PROGRAM / name).read_bytes()
        require(sha(raw) == built['outputs'][name]['sha256'] and len(raw) == built['outputs'][name]['bytes'], 'Client changed: ' + name)
        require(built['abi'][name]['relocationsContiguous'], 'Target loader ABI mismatch')
    require(reports[REPORTS[2]]['firmwareSha256'] == FIRMWARE_SHA, 'Firmware validation mismatch')
    require(reports[REPORTS[2]]['checkCount'] == 95, 'Firmware checks incomplete')
    require(reports[REPORTS[-1]]['firmwareSha256'] == FIRMWARE_SHA, 'Expanded configuration validation mismatch')
    require(reports[REPORTS[5]]['rccSha256'] == reports[REPORTS[6]]['rccSha256'] == sha((UI / 'formal-ui.rcc').read_bytes()),
            'QML resource validation mismatch')
    import formal_sync_loader
    require(formal_sync_loader.offline_ready(), 'FARM loader validation changed')
    return reports


def firmware_deltas():
    original = (HERE / 'build/vendor-wltest.bin').read_bytes()
    final = (RF / 'formal-wltest.bin').read_bytes()
    require(len(original) == 606750 and sha(original) == BASE_SHA, 'Original wireless input mismatch')
    require(len(final) == 622592 and sha(final) == FIRMWARE_SHA, 'Formal wireless candidate mismatch')
    reconstructed = bytearray(original)
    delta = {}
    for index, (start, size) in enumerate(DELTAS):
        data = final[start:start+size]
        require(len(data) == size, 'Delta length mismatch')
        reconstructed[start:start+size] = data
        delta['delta/' + str(index) + '.bin'] = data
    require(bytes(reconstructed) == final, 'Delta does not reconstruct full candidate')
    return delta


def build():
    reports = evidence()
    files = {name: (PROGRAM / name).read_bytes() for name in PROGRAMS}
    files['formal-ui.rcc'] = (UI / 'formal-ui.rcc').read_bytes()
    files['formal-hold.check'] = b'HBL hold file ABI check\n'
    files.update(firmware_deltas())
    template = (HERE / 'formal-prepare-radio.sh.in').read_text(encoding='utf-8')
    # 目标 BusyBox 1.23.2 的 dd 没有 conv=notrunc；读写重定向保留原文件。
    patches = '\n'.join('dd if="$d/delta/%s.bin" bs=1 seek=%s 1<>"$d/test/brcm/brcmfmac4356-pcie.bin" 2>/dev/null' % (i, start)
                        for i, (start, _) in enumerate(DELTAS))
    for key, value in (('@FORMAL_FIRMWARE_SHA256@', FIRMWARE_SHA), ('@FORMAL_DELTA_COMMANDS@', patches)):
        require(template.count(key) == 1, 'Installer template placeholder mismatch: ' + key)
        template = template.replace(key, value)
    require('@FORMAL_' not in template, 'Unresolved installer template')
    files['formal-prepare-radio.sh'] = template.encode('utf-8')
    for name in ('formal-install.sh', 'formal-restore.sh'):
        files[name] = (HERE / name).read_text(encoding='utf-8').encode('utf-8')
    files['manifest.sha256'] = ''.join(sha(raw) + '  ' + name + '\n' for name, raw in sorted(files.items())).encode('ascii')
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        for name, raw in sorted(files.items()):
            item = tarfile.TarInfo(name)
            item.size = len(raw)
            item.mode = 0o700 if name.endswith('.sh') or name in PROGRAMS[2:] else 0o600
            archive.addfile(item, io.BytesIO(raw))
    package = gzip.compress(stream.getvalue(), compresslevel=9, mtime=0)
    OUT.mkdir(exist_ok=True)
    folder = OUT / 'package-files'
    folder.mkdir(exist_ok=True)
    for name, raw in files.items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    (OUT / 'session-package.tar.gz').write_bytes(package)
    source_names = list(REPORTS) + ['research/package_formal_flash.py', 'formal-install.sh', 'formal-restore.sh', 'formal-prepare-radio.sh.in']
    report = {'passed': True, 'kind': 'formal-dual-shutter-flash-full-temporary-package',
              'sourceVersion': 'X1D 1.25.0', 'packageSha256': sha(package), 'packageBytes': len(package),
              'remoteDirectory': '/tmp/hbl-wireless-flash', 'freshDirectoryRequired': True,
              'baseFirmwareSha256': BASE_SHA, 'firmwareSha256': FIRMWARE_SHA,
              'firmwareDeltas': [{'offset': s, 'bytes': n} for s, n in DELTAS],
              'files': {name: {'sha256': sha(raw), 'bytes': len(raw)} for name, raw in files.items()},
              'sourceHashes': {name: sha((HERE / name).read_bytes()) for name in source_names},
              'installed': False, 'hardwareRequests': 0, 'targetSelfChecksRun': False,
              'physicalTimingVerified': False, 'agentFlashTrials': 0, 'cameraShotsTriggered': 0,
              'userWorkflow': {'masterDefault': False, 'powerOnStandardFullPress': True,
                               'powerOnGroupEdit': True, 'mechanicalAndElectronicSync': True,
                               'groups': list('ABCDEF0123456789'), 'defaultChannel': 5, 'defaultId': 5,
                               'channelRange': [1,32], 'idRange': [0,99], 'idOff': 0,
                               'customExposureEntryIntegrated': False, 'modelingLampIntegrated': True}}
    (OUT / 'package-validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    verify_package()
    return {key: report[key] for key in ('passed', 'packageSha256', 'packageBytes', 'installed', 'hardwareRequests')}


def verify_package():
    evidence()
    report = read_report('build/formal-flash-package/package-validation.json')
    data = (OUT / 'session-package.tar.gz').read_bytes()
    require(report.get('passed') is True and sha(data) == report['packageSha256'] and len(data) == report['packageBytes'], 'Package mismatch')
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        members = archive.getmembers()
        require(len(members) == len(report['files']) and {m.name for m in members} == set(report['files']), 'Archive member mismatch')
        for member in members:
            path = PurePosixPath(member.name)
            require(member.isfile() and not path.is_absolute() and '..' not in path.parts and '\\' not in member.name, 'Unsafe member')
            raw = archive.extractfile(member).read()
            expected = report['files'][member.name]
            require(len(raw) == expected['bytes'] and sha(raw) == expected['sha256'], 'Archive content mismatch')
    return report, data


if __name__ == '__main__':
    print(json.dumps(build(), ensure_ascii=False))
