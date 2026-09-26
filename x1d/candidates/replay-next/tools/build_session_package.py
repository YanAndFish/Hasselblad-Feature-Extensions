"""把已核对的离线候选封装成会话包；不包含相机连接或执行代码。"""
from __future__ import annotations
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[2]
OUT=HERE/'artifacts/session-package'

def sha(data):return hashlib.sha256(data).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8'))
def checked(path,expected):
    data=path.read_bytes()
    assert sha(data)==expected,path
    return data
def check_paths(values):
    for name,digest in values.items():
        path=(ROOT/name).resolve();path.relative_to(ROOT.resolve());checked(path,digest)

def run():
    reports={}
    names=['adapter/manifest.json','adapter/abi-audit.json','review-summary.json',
           'load-preparation/review.json','load-preparation/inputs.json','load-preparation/services.json',
           'session/manifest.json','session-tests/abi.json','session-tests/qml.json',
           'session-tests/arm-gate.json','install-tests/validation.json','transfer-tests/validation.json']
    for name in names:
        report=read(HERE/'artifacts'/name);reports[name]=report
        for field in ('sourceHashes','sources','inputHashes'):check_paths(report.get(field,{}))
    core=reports['adapter/manifest.json'];session=reports['session/manifest.json']
    for name in ('session-tests/abi.json','session-tests/qml.json','session-tests/arm-gate.json',
                 'install-tests/validation.json','transfer-tests/validation.json'):
        assert reports[name]['passed'] is True,name
    assert reports['review-summary.json']['status']=='offline-candidate-evidence-matches-current-sources-and-modules'
    for path,digest in reports['review-summary.json']['artifacts'].items():
        checked(HERE/path,digest)
        report=read(HERE/path)
        for field in ('sourceHashes','sources'):check_paths(report.get(field,{}))
    core_digest=sha((HERE/'artifacts/adapter/manifest.json').read_bytes())
    assert session['adapterManifestSha256']==core_digest
    assert reports['adapter/abi-audit.json']['buildManifestSha256']==core_digest
    assert reports['adapter/abi-audit.json']['auditSourceSha256']==sha((HERE/'tools/audit_replay_adapter.py').read_bytes())
    assert reports['load-preparation/review.json']['candidateManifestSha256']==core_digest
    assert reports['session-tests/abi.json']['sessionManifestSha256']==sha((HERE/'artifacts/session/manifest.json').read_bytes())
    assert reports['session-tests/qml.json']['rccSha256']==session['products']['replay-ui.rcc']['sha256']
    assert reports['session-tests/arm-gate.json']['moduleSha256']==core['outputs']['libx1d-replay-provider.so']['sha256']
    for name,digest in reports['load-preparation/review.json']['evidenceHashes'].items():checked(HERE/'artifacts/load-preparation'/name,digest)
    inputs=reports['load-preparation/inputs.json']
    assert inputs['sourceSha256']==sha((HERE/'tools/prepare_load_inputs.py').read_bytes())
    baseline={}
    for name,item in inputs['files'].items():
        checked(HERE/'artifacts/load-preparation/inputs'/name,item['sha256'])
        baseline['/'+name]=item['sha256']
    # 同时校验 SONAME/解释器链接的实际内容，防止正确版本文件旁的别名被换指向。
    for alias,target in inputs['aliases'].items():baseline['/'+alias]=inputs['files'][target]['sha256']
    for role,item in reports['load-preparation/services.json']['services'].items():
        name='lib/systemd/system/'+role+'.service'
        checked(ROOT/'.research-cache/x1d-1.25.0/baseline'/name,item['sha256'])
        baseline['/'+name]=item['sha256']
    files={}
    for name in ('common.sh','preflight.sh','install.sh','restore.sh','status.sh'):
        files[name]=(HERE/'session'/name).read_bytes();assert b'\r' not in files[name]
    files['baseline.sha256']=''.join(digest+'  '+name+'\n' for name,digest in sorted(baseline.items())).encode('ascii')
    for name,item in session['products'].items():files[name]=checked(HERE/'artifacts/session'/name,item['sha256'])
    for name,item in core['outputs'].items():files[name]=checked(HERE/'artifacts/adapter'/name,item['sha256'])
    for folder,role in [('full-jpeg-v1','configstore'),('jpeg-failure-v1','jpeg-daemon')]:
        source=ROOT/'x1d/artifacts'/folder
        report=read(source/'manifest.json')
        assert report['sourceSha256']==baseline['/usr/bin/'+role]
        files['payload/'+role]=checked(source/(role+'.elf'),report['candidateSha256'])
    assert len(files)==13
    files['manifest.sha256']=''.join(sha(data)+'  '+name+'\n' for name,data in sorted(files.items())).encode('ascii')
    buffer=io.BytesIO()
    with tarfile.open(fileobj=buffer,mode='w',format=tarfile.USTAR_FORMAT) as archive:
        for name,data in sorted(files.items()):
            member=tarfile.TarInfo(name);member.size=len(data);member.mode=0o700;member.mtime=0;member.uid=member.gid=0
            archive.addfile(member,io.BytesIO(data))
    compressed=gzip.compress(buffer.getvalue(),compresslevel=9,mtime=0)
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'session.tar.gz').write_bytes(compressed)
    report={'schemaVersion':1,'firmwareSource':'X1D-50c 1.25.0','packageReadyForDelegatedLoad':True,
            'targetValidated':False,'cameraAccess':False,'installed':False,'persistentFirmwareChanged':False,
            'remoteRoot':'/tmp/hbl-x1d-rp','packageBytes':len(compressed),'packageSha256':sha(compressed),
            'files':{name:sha(data) for name,data in sorted(files.items())},'baselineChecks':len(baseline),
            'uncompressedFileBytes':sum(map(len,files.values())),
            'transferChunks':(4*((len(compressed)+2)//3)+175)//176,
            'phaseOrder':['upload-and-verify','ui-hold-and-gpu','enable','functional-validation-by-owner'],
            'remainingTargetValidation':['当前设备与运行状态','原动态链接器/Qt5.5及QML接入','实际DBus/写卡与记录发布',
                                         '真实GPU上传/内存峰值与耗时','真实装载/撤销'],
            'evidenceHashes':{'artifacts/'+name:sha((HERE/'artifacts'/name).read_bytes()) for name in names},
            'sourceHashes':{Path(__file__).relative_to(ROOT).as_posix():sha(Path(__file__).read_bytes())}}
    (OUT/'package.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (OUT/'baseline.sha256').write_bytes(files['baseline.sha256'])
    (OUT/'manifest.sha256').write_bytes(files['manifest.sha256'])
    from transfer_session import verify_package
    verify_package()
    print(json.dumps({k:report[k] for k in ('packageReadyForDelegatedLoad','packageBytes','packageSha256','transferChunks','baselineChecks','targetValidated','cameraAccess')}))

if __name__=='__main__':run()
