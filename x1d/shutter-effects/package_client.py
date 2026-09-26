"""Wrap the signed X1D Ciallo payload in the existing native Windows installer.

This builds and validates a desktop release directory; it never opens USB.
"""
from pathlib import Path
import hashlib
import json
import shutil
import sys
import argparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / 'x1d/patch-distribution/build/startup-repair-20260923-002840/build-report.json'
CANDIDATE = HERE / 'build/candidate'
OUTPUT = HERE / 'build/native-client-r2'

sys.path.insert(0, str(ROOT / 'x1d/patch-distribution'))
import package_native_windows


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--revision',choices=['r5','r6'],default='r5')
    args=parser.parse_args()
    candidate=CANDIDATE if args.revision=='r5' else HERE/'build/candidate-r6'
    output=OUTPUT if args.revision=='r5' else HERE/'build/native-client-r3'
    archive = candidate / ('x1d-ciallo-persistent-candidate-'+args.revision+'.tgz')
    result = json.loads((candidate / ('result-'+args.revision+'.json')).read_text(encoding='utf-8'))
    content = archive.read_bytes()
    if (not result.get('offlineInstallReady') or
            hashlib.sha256(content).hexdigest() != result['packageSha256']):
        raise ValueError('Ciallo package is not the audited offline candidate')
    if output.exists():
        raise FileExistsError('Release directory is immutable: ' + str(output))
    output.mkdir(parents=True)
    shutil.copyfile(archive, output / 'x1d-authorized-candidate.tgz')
    report = json.loads(SOURCE.read_text(encoding='utf-8'))
    report['archiveSha256'] = result['packageSha256']
    report['installed'] = False
    report['cameraValidated'] = False
    report['coldBootValidated'] = False
    report['features']['x1dCialloShutterEffect'] = True
    if args.revision=='r6':
        report['installerRepair']=False
        report['retainsMappedBackupUntilNextBoot']=True
        report['cameraTransactionSha256']=result['transactionSha256']
    report['knownIssues'] = list(report['knownIssues']) + result['pending']
    (output / 'build-report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    release = package_native_windows.package(output)
    print('Native client release ready: ' + str(release))


if __name__ == '__main__':
    main()
