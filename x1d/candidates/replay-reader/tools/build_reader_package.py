"""构建 GUI 专用整包；绑定源码、固定依赖、执行证据。无设备连接入口。"""
from pathlib import Path
import gzip,hashlib,io,json,tarfile
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
BASE=ROOT/'x1d/candidates/replay-stable/releases/stable-r1'
OUT=HERE/'releases/reader-r1'
def sha(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def bind(items):
    for name,wanted in items.items():
        p=(ROOT/name).resolve();p.relative_to(ROOT.resolve())
        assert sha(p.read_bytes())==wanted,('changed source or input',name)
def run():
    nativePath=HERE/'artifacts/adapter/manifest.json';sessionPath=HERE/'artifacts/session/manifest.json'
    native=read(nativePath);session=read(sessionPath)
    bind(native['sources']);bind(native['inputHashes']);bind(session['sourceHashes'])
    assert session['adapterManifestSha256']==sha(nativePath.read_bytes())
    assert set(native['outputs'])=={'libx1d-replay-provider.so'}
    files={}
    for folder,products in [('adapter',native['outputs']),('session',session['products'])]:
        for name,item in products.items():
            data=(HERE/'artifacts'/folder/name).read_bytes();assert sha(data)==item['sha256']
            files[name]=data
    evidence={};groups={}
    for relative in ('stable-tests/provider.json','stable-tests/catalog.json','stable-tests/gate.json',
                     'stable-tests/qml.json','session-tests/qml.json','session-tests/abi.json',
                     'reader-tests/contract.json','install-tests/validation.json','diagnosis/completion-execution.json'):
        path=HERE/'artifacts'/relative;report=read(path)
        assert report['passed'] and report['cameraAccess'] is False,relative
        bind(report['sourceHashes'])
        if 'factorySha256' in report:assert report['factorySha256']==sha((ROOT/'.research-cache/x1d-1.25.0/baseline/usr/bin/jpeg-daemon').read_bytes())
        if 'moduleHashes' in report:
            assert report['moduleHashes']['candidate']==sha(files['libx1d-replay-provider.so'])
            for key,wanted in report['moduleHashes'].items():
                if key=='candidate':continue
                name='libturbojpeg.so.0.1.0' if key=='TurboJPEG' else 'libQt5'+key[2:]+'.so.5.5.1'
                assert wanted==sha((ROOT/'.research-cache/x1d-1.25.0/baseline/usr/lib'/name).read_bytes())
        if 'moduleSha256' in report:assert report['moduleSha256']==sha(files['libx1d-replay-provider.so'])
        if 'rccSha256' in report:assert report['rccSha256']==sha(files['replay-ui.rcc'])
        if 'sessionManifestSha256' in report:
            assert report['sessionManifestSha256']==sha(sessionPath.read_bytes())
            assert report['adapterManifestSha256']==sha(nativePath.read_bytes())
        evidence[path.relative_to(ROOT).as_posix()]=sha(path.read_bytes())
        groups[relative]=len(report.get('cases',report.get('checks',report.get('products',[]))))
    old=(BASE/'session.tar.gz').read_bytes()
    assert sha(old)=='1df99fb712e23c10ada543b2b58ded609ad289d9c16993317cf7414b340469b0'
    with tarfile.open(fileobj=io.BytesIO(old),mode='r:gz') as t:
        files['baseline.sha256']=t.extractfile('baseline.sha256').read()
    for name in ('common.sh','preflight.sh','install.sh','restore.sh','status.sh'):
        files[name]=(HERE/'session'/name).read_bytes()
    assert len(files)==10 and not any('payload' in n or 'jpeg-adapter' in n for n in files)
    files['manifest.sha256']=''.join(sha(b)+'  '+n+'\n' for n,b in sorted(files.items())).encode()
    raw=io.BytesIO()
    with tarfile.open(fileobj=raw,mode='w',format=tarfile.USTAR_FORMAT) as t:
        for name,data in sorted(files.items()):
            m=tarfile.TarInfo(name);m.size=len(data);m.mode=0o700;m.uid=m.gid=m.mtime=0;t.addfile(m,io.BytesIO(data))
    data=gzip.compress(raw.getvalue(),mtime=0);OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'session.tar.gz').write_bytes(data)
    transfer=(BASE/'transfer.py').read_bytes();(OUT/'transfer.py').write_bytes(transfer)
    for name in ('common.sh','manifest.sha256'):(OUT/name).write_bytes(files[name])
    proof={'passed':True,'cameraAccess':False,'evidenceHashes':evidence,'checkGroups':groups,
      'nativeManifestSha256':sha(nativePath.read_bytes()),'sessionManifestSha256':sha(sessionPath.read_bytes()),
      'buildToolSha256':sha(Path(__file__).read_bytes())}
    (OUT/'offline.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report={'schemaVersion':1,'release':'reader-r1','firmwareSource':'X1D-50c 1.25.0',
      'packageReadyForDelegatedLoad':False,'offlineBuildAndFunctionChecksPassed':True,
      'packageSha256':sha(data),'packageBytes':len(data),'files':{n:sha(b) for n,b in sorted(files.items())},
      'baseArchivePath':(BASE/'session.tar.gz').relative_to(ROOT).as_posix(),'baseArchiveSha256':sha(old),
      'baselineChecks':74,'remoteRoot':'/tmp/hbl-x1d-rp','transferSha256':sha(transfer),
      'transferChunks':(4*((len(data)+2)//3)+175)//176,'offlineEvidenceSha256':sha((OUT/'offline.json').read_bytes()),
      'modifiedServiceRoles':['victory-gui'],'producerHooks':False,'completionRecords':False,
      'targetFunctionalValidated':False,'targetLatencyValidated':False,'targetMemoryValidated':False,
      'fullArchiveTransferOnTargetValidated':False,'cameraAccessByThisTask':False,'installed':False,
      'knownLimits':['红灯持续及后续RAW缺失的现场根因未确认，原现场已重启',
        '保留原厂图像格式与尺寸设置；不强制生成JPEG，不保证卡中已有JPEG为Full尺寸',
        '新增读取只读同目录同名JPEG；不读RAW确认拍摄身份，旧同名错配仍无法独立证明',
        'RAW-only回退依赖新鲜完整原模型缓存；缓存不足或JPEG异常时保守返回空，不全面回退原provider',
        '原厂Qt5 GUI模型采集、自动回放重试事件循环、实际存储与GPU尚未实机验证',
        '失败图可见时同源最多四次JPEG重试，每次至少一秒；Loading及Ready状态不重读',
        'Full上传瞬间CPU和GPU各约200MB；不是进程总内存上限',
        '首次回放、自动回放、放大速度及连续拍摄需要另行实机验收'],
      'sourceHashes':{Path(__file__).relative_to(ROOT).as_posix():sha(Path(__file__).read_bytes())}}
    (OUT/'package.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'built':True,'sha256':sha(data),'bytes':len(data),'members':len(files),'checks':sum(groups.values()),'cameraAccess':False}))
if __name__=='__main__':run()
