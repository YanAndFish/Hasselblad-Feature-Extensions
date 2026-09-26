"""冻结可交接的模块文件、源码与证据；同摘要目录不覆盖不同内容。"""
import argparse
import hashlib
import json
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
def sha(data):return hashlib.sha256(data).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8'))

def freeze(package_path):
    package_path=Path(package_path).resolve();package_path.relative_to((HERE/'artifacts/joint').resolve())
    package=read(package_path);joint_path=ROOT/package['jointManifest'];joint=read(joint_path)
    assert sha(joint_path.read_bytes())==package['jointManifestSha256']
    archive=(package_path.parent/'replay-module.tar.gz').read_bytes();assert sha(archive)==package['archiveSha256']
    verified_path=HERE/'artifacts/joint-package-tests'/package['archiveSha256'][:16]/'validation.json'
    verified=read(verified_path)
    assert verified['passed'] and verified['archiveSha256']==sha(archive)
    assert verified['packageReportSha256']==sha(package_path.read_bytes())
    main=ROOT/joint['mainQmlPath'];assert sha(main.read_bytes())==package['mainQmlSha256']
    identity_path=main.parent/'identity.json';identity=read(identity_path)
    assert identity['kind']=='combined-main-only-frozen' and identity['mainQmlSha256']==package['mainQmlSha256']
    assert identity['systemCheckSha256']==package['coordinatorCheckerSha256']
    assert sha((ROOT/package['coordinatorCheckerPath']).read_bytes())==package['coordinatorCheckerSha256']
    collected={'replay-module.tar.gz':archive,'package.json':package_path.read_bytes(),
               'inputs/main.qml':main.read_bytes(),'evidence/final-main-identity.json':identity_path.read_bytes(),
               'evidence/joint-build-manifest.json':joint_path.read_bytes(),
               'evidence/package-validation.json':verified_path.read_bytes()}
    for name,wanted in package['files'].items():
        data=(package_path.parent/'files'/name).read_bytes();assert sha(data)==wanted
        collected['files/'+name]=data
    sources={};reports=[package,joint,verified]
    evidence_names=set(package['evidenceHashes'])|{'artifacts/joint-tests/coexistence.json','artifacts/adapter/manifest.json',
        'artifacts/adapter/abi-audit.json','artifacts/session/manifest.json','artifacts/review-summary.json'}
    summary=read(HERE/'artifacts/review-summary.json')
    evidence_names.update(summary['artifacts'])
    for name in sorted(evidence_names):
        path=HERE/name;content=path.read_bytes();report=read(path)
        if name in package['evidenceHashes']:assert sha(content)==package['evidenceHashes'][name]
        if name in summary['artifacts']:assert sha(content)==summary['artifacts'][name]
        collected['evidence/'+name]=content;reports.append(report)
    for report in reports:
        for field in ('sourceHashes','sources'):
            for name,wanted in report.get(field,{}).items():
                if name in sources:assert sources[name]==wanted,name
                sources[name]=wanted
    own=Path(__file__);sources[own.relative_to(ROOT).as_posix()]=sha(own.read_bytes())
    coexistence=read(HERE/'artifacts/joint-tests/coexistence.json')
    sources['x1d/wireless-flash/native/formal_worker.cpp']=coexistence['workerStatusWriterSourceSha256']
    for name,wanted in sorted(sources.items()):
        p=(ROOT/name).resolve();p.relative_to(ROOT.resolve());data=p.read_bytes();assert sha(data)==wanted,name
        collected['sources/'+name]=data
    for name,wanted in coexistence['recoveryEvidenceHashes'].items():assert sha((ROOT/name).read_bytes())==wanted,name
    lock={'kind':'frozen-replay-module-for-root-composition','firmwareSource':'X1D-50c 1.25.0',
          'modulePackageReady':True,'standaloneInstallable':False,'cameraAccess':False,'targetValidated':False,
          'fullRccFrozenHere':False,'archiveSha256':sha(archive),'archiveBytes':len(archive),
          'mainQmlSha256':package['mainQmlSha256'],'coordinatorCheckerSha256':package['coordinatorCheckerSha256'],
          'backendSha256':package['files']['backend.sh'],
          'checks':{'resourceComposition':17,'hostQmlReceipt':6,'backendContract':28,'armWindowPolicy':16,'archiveMembers':len(package['files'])},
          'sources':sources,'files':{name:sha(data) for name,data in sorted(collected.items())}}
    collected['freeze.json']=(json.dumps(lock,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    out=HERE/'artifacts/joint/fixed'/('module-'+sha(archive)[:16])
    if out.exists():
        existing={p.relative_to(out).as_posix() for p in out.rglob('*') if p.is_file()}
        assert existing<=set(collected),'冻结目录含未知文件'
        for name,data in collected.items():
            if (out/name).exists():assert (out/name).read_bytes()==data,'冻结目录存在不同内容：'+name
    for name,data in collected.items():
        path=out/name;path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists():path.write_bytes(data)
    for name,data in collected.items():assert (out/name).read_bytes()==data
    print(json.dumps({'frozenDirectory':out.relative_to(ROOT).as_posix(),'archiveSha256':sha(archive),
                      'freezeSha256':sha(collected['freeze.json']),'frozenFiles':len(collected),'cameraAccess':False}))
    return out

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--package',required=True,type=Path)
    freeze(parser.parse_args().package)
