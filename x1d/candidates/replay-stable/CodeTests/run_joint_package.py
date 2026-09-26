"""正式模块包的成员、摘要、实际 tar 解包与 shell 语法验证；不执行目标代码。"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
def sha(data):return hashlib.sha256(data).hexdigest()

def run(package_path):
    package_path=Path(package_path).resolve();package_path.relative_to((HERE/'artifacts/joint').resolve())
    report=json.loads(package_path.read_text(encoding='utf-8'));folder=package_path.parent
    archive=(folder/'replay-module.tar.gz').read_bytes()
    assert report['modulePackageReady'] and report['standaloneInstallable'] is False
    assert len(archive)==report['archiveBytes'] and sha(archive)==report['archiveSha256']
    seen=set()
    with tarfile.open(fileobj=io.BytesIO(archive),mode='r:gz') as bundle:
        for entry in bundle:
            assert entry.isfile() and entry.name in report['files'] and entry.name not in seen
            assert entry.mode==0o700 and entry.uid==0 and entry.gid==0
            assert sha(bundle.extractfile(entry).read())==report['files'][entry.name]
            seen.add(entry.name)
    assert seen==set(report['files'])
    out=HERE/'artifacts/joint-package-tests'/report['archiveSha256'][:16];out.mkdir(parents=True,exist_ok=True)
    staged=out/'staged'
    if staged.exists():staged.resolve().relative_to(out.resolve());shutil.rmtree(staged)
    staged.mkdir()
    script='PATH=/usr/bin:/bin; export PATH\nset -eu\ncd "$1"\ntar xzf "$2"\nsha256sum -c manifest.sha256\nsh -n backend.sh\n'
    archive_path=folder/'replay-module.tar.gz'
    shell_archive='/'+archive_path.drive[0].lower()+archive_path.as_posix()[2:]
    result=subprocess.run(['C:/Program Files/Git/bin/sh.exe','-c',script,'joint-package',str(staged),shell_archive],
                          cwd=ROOT,env=dict(os.environ,MSYS_NO_PATHCONV='1'),capture_output=True,text=True,encoding='utf-8',timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    for name,wanted in report['files'].items():assert sha((staged/name).read_bytes())==wanted
    assert 'hbl-wireless-worker' not in (staged/'backend.sh').read_text(encoding='utf-8')
    validation={'passed':True,'cameraAccess':False,'targetCodeExecuted':False,'hostFilesystemPermissionsAreNotTargetEvidence':True,
                'archiveSha256':report['archiveSha256'],'verifiedMembers':len(seen),'actualTarAndShellSyntaxChecked':True,
                'packageReportSha256':sha(package_path.read_bytes()),
                'sourceHashes':{Path(__file__).relative_to(ROOT).as_posix():sha(Path(__file__).read_bytes())}}
    (out/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'jointPackageVerified':True,'members':len(seen),'archiveSha256':report['archiveSha256'],'cameraAccess':False}))
    return validation

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--package',required=True,type=Path)
    run(parser.parse_args().package)
