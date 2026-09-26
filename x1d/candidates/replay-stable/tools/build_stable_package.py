"""仅在当前工作区生成完整离线候选包；任何输入或验证证据不匹配即拒绝。"""
from pathlib import Path
import gzip,hashlib,io,json,tarfile
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
BASE=ROOT/'x1d/candidates/replay-next/releases/session-compat-r2'
OUT=HERE/'releases/stable-r1'

def sha(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def bind(entries):
    for name,wanted in entries.items():
        path=(ROOT/name).resolve();path.relative_to(ROOT.resolve())
        assert sha(path.read_bytes())==wanted,('changed source/input',name)

def run():
    nativePath=HERE/'artifacts/adapter/manifest.json';sessionPath=HERE/'artifacts/session/manifest.json'
    native=read(nativePath);session=read(sessionPath)
    bind(native['sources']);bind(native['inputHashes']);bind(session['sourceHashes'])
    assert session['adapterManifestSha256']==sha(nativePath.read_bytes())
    abi=read(HERE/'artifacts/adapter/abi-audit.json')
    assert abi['buildManifestSha256']==sha(nativePath.read_bytes())
    assert abi['auditSourceSha256']==sha((HERE/'tools/audit_replay_adapter.py').read_bytes())
    products={}
    for folder,items in [('adapter',native['outputs']),('session',session['products'])]:
        for name,item in items.items():
            products[name]=(HERE/'artifacts'/folder/name).read_bytes()
            assert sha(products[name])==item['sha256'],name
    evidence={};counts={}
    for relative in ['stable-tests/provider.json','stable-tests/adapter.json','stable-tests/gate.json',
       'stable-tests/catalog.json','stable-tests/records.json','stable-tests/qml.json','stable-tests/static.json',
       'session-tests/abi.json','session-tests/qml.json']:
        path=HERE/'artifacts'/relative;report=read(path)
        assert report['passed'] and report['cameraAccess'] is False,relative
        bind(report['sourceHashes'])
        module='libx1d-jpeg-adapter.so' if relative=='stable-tests/adapter.json' else 'libx1d-replay-provider.so'
        if 'moduleHashes' in report:
            assert report['moduleHashes']['candidate']==sha(products[module]),relative
            for key,value in report['moduleHashes'].items():
                if key=='candidate':continue
                name='libturbojpeg.so.0.1.0' if key=='TurboJPEG' else 'libQt5'+key[2:]+'.so.5.5.1'
                assert value==sha((ROOT/'.research-cache/x1d-1.25.0/baseline/usr/lib'/name).read_bytes())
        if 'moduleSha256' in report:assert report['moduleSha256']==sha(products[module])
        if 'rccSha256' in report:assert report['rccSha256']==sha(products['replay-ui.rcc'])
        if 'sessionManifestSha256' in report:
            assert report['sessionManifestSha256']==sha(sessionPath.read_bytes())
            assert report['adapterManifestSha256']==sha(nativePath.read_bytes())
        evidence[path.relative_to(ROOT).as_posix()]=sha(path.read_bytes())
        counts[relative]=len(report.get('cases',report.get('checks',report.get('products',[]))))
    original=(BASE/'session.tar.gz').read_bytes()
    assert sha(original)=='cd11f9988b86d5018ea02f92819b34a1b7e0568b234f696f2e7cf29f63162108'
    with tarfile.open(fileobj=io.BytesIO(original),mode='r:gz') as archive:
        members=archive.getmembers();assert len(members)==14 and all(m.isfile() and m.mode==0o700 for m in members)
        files={m.name:archive.extractfile(m).read() for m in members}
    for name,folder in [('configstore','full-jpeg-v1'),('jpeg-daemon','jpeg-failure-v1')]:
        assert files['payload/'+name]==(ROOT/'x1d/artifacts'/folder/(name+'.elf')).read_bytes()
    assert files['common.sh']==(HERE/'session/common.sh').read_bytes()
    for name in ['preflight.sh','install.sh','restore.sh','status.sh']:
        assert files[name]==(HERE/'session'/name).read_bytes(),name
    previous=dict(files);files.update(products)
    files['manifest.sha256']=''.join(sha(value)+'  '+name+'\n' for name,value in sorted(files.items()) if name!='manifest.sha256').encode()
    raw=io.BytesIO()
    with tarfile.open(fileobj=raw,mode='w',format=tarfile.USTAR_FORMAT) as archive:
        for name,value in sorted(files.items()):
            m=tarfile.TarInfo(name);m.size=len(value);m.mode=0o700;m.uid=m.gid=m.mtime=0;archive.addfile(m,io.BytesIO(value))
    data=gzip.compress(raw.getvalue(),mtime=0)
    OUT.mkdir(parents=True,exist_ok=True);(OUT/'session.tar.gz').write_bytes(data)
    code=(BASE/'transfer.py').read_bytes();(OUT/'transfer.py').write_bytes(code)
    for name in ['common.sh','manifest.sha256']:(OUT/name).write_bytes(files[name])
    proof={'passed':True,'evidenceHashes':evidence,'checkGroups':counts,
      'nativeManifestSha256':sha(nativePath.read_bytes()),'sessionManifestSha256':sha(sessionPath.read_bytes()),
      'cameraAccess':False,'fullArchiveRoundtripEvidence':'validation.json (separate)' ,'buildToolSha256':sha(Path(__file__).read_bytes())}
    (OUT/'offline.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report={'schemaVersion':1,'release':'stable-r1','firmwareSource':'X1D-50c 1.25.0',
      'packageReadyForDelegatedLoad':False,'offlineBuildAndFunctionChecksPassed':True,
      'packageSha256':sha(data),'packageBytes':len(data),'files':{n:sha(b) for n,b in sorted(files.items())},
      'baseArchiveSha256':sha(original),'baseArchivePath':(BASE/'session.tar.gz').relative_to(ROOT).as_posix(),
      'changedTargetFiles':[n for n,b in files.items() if b!=previous[n]],'baselineChecks':74,'remoteRoot':'/tmp/hbl-x1d-rp',
      'transferChunks':(4*((len(data)+2)//3)+175)//176,'transferSha256':sha(code),
      'offlineEvidenceSha256':sha((OUT/'offline.json').read_bytes()),
      'targetFunctionalValidated':False,'targetLatencyValidated':False,'targetMemoryValidated':False,
      'fullArchiveTransferOnTargetValidated':False,'cameraAccessByThisTask':False,'installed':False,
      'knownLimits':['当前无实机功能、速度、内存证据；旧故障根因未确定',
        '目录缺失判定依赖刚读过的原模型缓存，不是原子存储快照；GUI 模型采集尚未目标执行',
        '旧同名 JPEG/3FR 的拍摄身份不能只凭 JPEG 证明；不读取 RAW 验证身份',
        '旧 JPEG 没有记录时按同卡同目录同名匹配；缓存不可用时无法确认缺失便保守拒绝 RAW 回退',
        '实际成功 CloseFile 后记录发布及 QSaveFile 尚未完整运行联调',
        'Full 同时只允许一个；上传瞬间仍可能同时存在约 200 MB CPU 与约 200 MB GPU 副本',
        '首次冷入、放大时延和拍后自动回放时延仍需分别验收'],
      'sourceHashes':{Path(__file__).relative_to(ROOT).as_posix():sha(Path(__file__).read_bytes())}}
    (OUT/'package.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'built':True,'sha256':sha(data),'bytes':len(data),'offlineEvidenceGroups':sum(counts.values()),'cameraAccess':False}))

if __name__=='__main__':run()
