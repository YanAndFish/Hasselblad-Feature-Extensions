"""封装协调器调用的回放模块；必须显式绑定最终 main 与共同 system-check，不能独立装载。"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
def sha(data):return hashlib.sha256(data).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8'))
def check_sources(report):
    for name,wanted in report.get('sourceHashes',{}).items():assert sha((ROOT/name).read_bytes())==wanted,name
def build(manifest_path,system_check,system_check_sha256):
    manifest_path=Path(manifest_path).resolve();manifest_path.relative_to((HERE/'artifacts/joint').resolve())
    joint=read(manifest_path);check_sources(joint)
    assert joint['jointModuleBuilt'] and not joint['standaloneInstallable'] and not joint['registersResource']
    assert sha((ROOT/joint['mainQmlPath']).read_bytes())==joint['mainQmlSha256']
    system_check=Path(system_check).resolve();system_check.relative_to(ROOT.resolve())
    assert sha(system_check.read_bytes())==system_check_sha256
    evidence={}
    for name in ('artifacts/joint-tests/composition.json','artifacts/joint-tests/qml.json','artifacts/joint-backend-tests/validation.json','artifacts/joint-policy-tests/validation.json'):
        report=read(HERE/name);assert report['passed'];check_sources(report);evidence[name]=sha((HERE/name).read_bytes())
    core=read(HERE/'artifacts/adapter/manifest.json')
    for name,wanted in core['sources'].items():assert sha((ROOT/name).read_bytes())==wanted
    files={name:(HERE/'joint'/name).read_bytes() for name in ('backend.sh',)}
    files['baseline.sha256']=(HERE/'artifacts/session-package/baseline.sha256').read_bytes()
    original_package=read(HERE/'artifacts/session-package/package.json')
    assert sha(files['baseline.sha256'])==original_package['files']['baseline.sha256']
    files['coordinator.sha256']=(system_check_sha256+'  /tmp/hbl-x1d-combined/system-check\n').encode('ascii')
    for name,path,digest in [
        ('libx1d-replay-joint.so',ROOT/joint['module'],joint['moduleSha256']),
        ('replay-joint-check',ROOT/joint['gpuChecker'],joint['gpuCheckerSha256']),
        ('replay-owners',HERE/'artifacts/session/replay-check',read(HERE/'artifacts/session/manifest.json')['products']['replay-check']['sha256']),
    ]:
        files[name]=path.read_bytes();assert sha(files[name])==digest
    for name,item in core['outputs'].items():
        files[name]=(HERE/'artifacts/adapter'/name).read_bytes();assert sha(files[name])==item['sha256']
    for folder,role in [('full-jpeg-v1','configstore'),('jpeg-failure-v1','jpeg-daemon')]:
        source=ROOT/'x1d/artifacts'/folder;info=read(source/'manifest.json')
        files['payload/'+role]=(source/(role+'.elf')).read_bytes();assert sha(files['payload/'+role])==info['candidateSha256']
    files['manifest.sha256']=''.join(sha(data)+'  '+name+'\n' for name,data in sorted(files.items())).encode('ascii')
    out=manifest_path.parent/'module-package';out.mkdir(exist_ok=True)
    assert {p.relative_to(out/'files').as_posix() for p in (out/'files').rglob('*') if p.is_file()}<=set(files),'输出目录含未知旧文件'
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w',format=tarfile.USTAR_FORMAT) as archive:
        for name,data in sorted(files.items()):
            info=tarfile.TarInfo(name);info.mode=0o700;info.size=len(data);archive.addfile(info,io.BytesIO(data))
            p=out/'files'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    compressed=gzip.compress(stream.getvalue(),mtime=0)
    (out/'replay-module.tar.gz').write_bytes(compressed)
    report={'modulePackageReady':True,'standaloneInstallable':False,'cameraAccess':False,'targetValidated':False,
            'remoteDirectory':'/tmp/hbl-x1d-combined/replay','moduleState':'/tmp/hbl-x1d-combined/replay-state',
            'archiveSha256':sha(compressed),'archiveBytes':len(compressed),'files':{name:sha(data) for name,data in sorted(files.items())},
            'jointManifest':manifest_path.relative_to(ROOT).as_posix(),'jointManifestSha256':sha(manifest_path.read_bytes()),
            'mainQmlSha256':joint['mainQmlSha256'],'coordinatorCheckerPath':system_check.relative_to(ROOT).as_posix(),
            'coordinatorCheckerSha256':system_check_sha256,'evidenceHashes':evidence,
            'sourceHashes':{p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in [Path(__file__),HERE/'joint/backend.sh']},
            'doesNotManage':['GUI drop-in/RCC/preload','msg2dbus-farm','wireless worker','FARM/AF RAM and callbacks','common hold lifecycle'],
            'entryPoints':['backend.sh --prepare','backend.sh --config','backend.sh --jpeg','backend.sh --status','backend.sh --restore']}
    (out/'package.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'modulePackage':(out/'replay-module.tar.gz').relative_to(ROOT).as_posix(),'sha256':sha(compressed),'bytes':len(compressed),'standaloneInstallable':False}))
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--joint-manifest',required=True,type=Path)
    parser.add_argument('--system-check',required=True,type=Path)
    parser.add_argument('--system-check-sha256',required=True)
    a=parser.parse_args();build(a.joint_manifest,a.system_check,a.system_check_sha256)
