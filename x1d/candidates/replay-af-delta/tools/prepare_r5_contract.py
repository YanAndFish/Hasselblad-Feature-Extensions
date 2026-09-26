"""仅为离线合同测试固定原 r5 输入；不是补丁后的现场装载交付。"""
from pathlib import Path
import hashlib,json,tarfile,io
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
AF=ROOT/'x1d/af-experiment/camera-settings-r1/delivery-r5'
READER=ROOT/'x1d/candidates/replay-reader'
OUT=HERE/'artifacts/package-staging'
def sha(b):return hashlib.sha256(b).hexdigest()
def run():
    assert Path.cwd().resolve()==ROOT
    archive=(AF/'inputs/af-only.tar.gz').read_bytes()
    assert sha(archive)=='6bbd107079f76619c959574527f692a398732a4fce6f44850a14deff10b739c1'
    old=(READER/'releases/reader-r1/session.tar.gz').read_bytes()
    assert sha(old)=='c394a539b02453af4bafb7b0ccf6cd506dea465c8d93860d83bcbec86d140a36'
    with tarfile.open(fileobj=io.BytesIO(archive)) as t:af={m.name:t.extractfile(m).read() for m in t}
    with tarfile.open(fileobj=io.BytesIO(old)) as t:reader={m.name:t.extractfile(m).read() for m in t}
    assert sha(af['manifest.sha256'])=='bd347c5f9919eaba4710fac9e62d7212bf6fb15f4bd65783a7c3f426e566ca6e'
    for name,data in af.items():assert data==(AF/'inputs'/name).read_bytes(),name
    proof=AF/'recovery/af-only-first-install-20260912T190952805799Z.json'
    assert sha(proof.read_bytes())=='99e03536e84a431c2ed1bc8fb1017420e3f665c4f84dd210bb60da7296b198c4'
    files={name:(HERE/'session'/name).read_bytes() for name in ('common.sh','preflight.sh','install.sh','restore.sh','status.sh')}
    files['libx1d-replay-provider.so']=reader['libx1d-replay-provider.so']
    for name in ('libx1d-replay-session.so','replay-check','replay-ui.rcc'):files[name]=(HERE/'artifacts/session'/name).read_bytes()
    baseline={}
    for data in (reader['baseline.sha256'],af['baseline.sha256']):
        for line in data.decode().splitlines():
            digest,path=line.split();assert path not in baseline or baseline[path]==digest;baseline[path]=digest
    files['baseline.sha256']=''.join(h+'  '+p+'\n' for p,h in sorted(baseline.items())).encode()
    files['af-files.sha256']=''.join(sha(b)+'  /tmp/hbl-x1d-combined/'+n+'\n' for n,b in sorted(af.items())).encode()
    files['af-proof.txt']=(sha(proof.read_bytes())+'\n').encode()
    files['gui.af.conf']=b'[Service]\nRestart=no\nUMask=0077\nEnvironment=HBL_AF_ONLY_ENABLE=1\nEnvironment=HBL_AF_ONLY_HOLD=1\nEnvironment=HBL_AF_SETTINGS_ENABLE=1\nEnvironment=HBL_AF_UI_R4_ENABLE=0\nEnvironment=LD_PRELOAD=/tmp/hbl-x1d-combined/libhbl-af-only.so:/tmp/hbl-x1d-combined/af/libhbl-af-ui.so\n'
    files['bus.af.conf']=b'[Service]\nRestart=no\nUMask=0077\nEnvironment=HBL_AF_SETTINGS_ENABLE=1\nEnvironment=LD_PRELOAD=/tmp/hbl-x1d-combined/af/libhbl-af-bus.so\n'
    files['delta.conf']=b'[Service]\nEnvironment=X1D_REPLAY_SESSION=1\nEnvironment=LD_PRELOAD=/tmp/hbl-x1d-rpa/libx1d-replay-session.so:/tmp/hbl-x1d-rpa/libx1d-replay-provider.so:/tmp/hbl-x1d-combined/libhbl-af-only.so:/tmp/hbl-x1d-combined/af/libhbl-af-ui.so\n'
    files['manifest.sha256']=''.join(sha(b)+'  '+n+'\n' for n,b in sorted(files.items())).encode()
    OUT.mkdir(parents=True,exist_ok=True)
    for n,b in files.items():(OUT/n).write_bytes(b)
    report={'cameraAccess':False,'packageReadyForDelegatedLoad':False,'reason':'等待 AF 补丁后的真实交付重新绑定；本目录仅供原 r5 离线合同测试',
      'files':{n:sha(b) for n,b in files.items()},'providerByteIdentical':True,
      'afArchiveSha256':sha(archive),'readerArchiveSha256':sha(old),'baselineCount':len(baseline)}
    (OUT/'draft.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'draftMembers':len(files),'providerByteIdentical':True,'loadReady':False,'cameraAccess':False}))
if __name__=='__main__':run()
