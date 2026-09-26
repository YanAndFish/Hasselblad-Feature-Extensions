"""将离线核对的预准备固件和配套 worker 封装为独立完整临时包。"""
from pathlib import Path
import gzip,hashlib,io,json,subprocess,tarfile

HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]
OUT=HERE/'build/mechanical-hw-ready-candidate'
BASE=HERE/'build/mechanical-sync-candidate'
def sha(data): return hashlib.sha256(data).hexdigest()

def package():
    if Path.cwd().resolve()!=ROOT: raise RuntimeError('Workspace mismatch')
    m=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
    c=json.loads((OUT/'client-build.json').read_text(encoding='utf-8'))
    t=json.loads((OUT/'instruction-checks.json').read_text(encoding='utf-8'))
    parent=json.loads((BASE/'package-validation.json').read_text(encoding='utf-8'))
    if not c['passed'] or not t['passed'] or c['firmwareSha256']!=m['sha256'] or t['firmwareSha256']!=m['sha256']:
        raise RuntimeError('Evidence mismatch')
    if sha((BASE/'session-package.tar.gz').read_bytes())!=parent['packageSha256']: raise RuntimeError('Parent archive changed')
    with tarfile.open(BASE/'session-package.tar.gz','r:gz') as archive:
        files={p.name:archive.extractfile(p).read() for p in archive if p.isfile()}
    for name in ('wireless-worker','netlink-probe'): files[name]=(OUT/name).read_bytes()
    if sha(files['wireless-worker'])!=c['workerSha256'] or sha(files['netlink-probe'])!=c['netlinkProbeSha256']:
        raise RuntimeError('Client changed')
    firmware=(OUT/'hardware-ready-wltest.bin').read_bytes()
    if sha(firmware)!=m['sha256']: raise RuntimeError('Firmware changed')
    for index,(start,end) in enumerate(((307100,307104),(399416,399420),(606750,len(firmware)))):
        files['delta/'+str(index)+'.bin']=firmware[start:end]
    files['prepare-radio.sh']=(HERE/'prepare-radio.sh.in').read_text(encoding='ascii').replace('@FIRMWARE_SHA256@',m['sha256']).replace('0x584e','0x5850').encode('ascii')
    files['mechanical-sync-install.sh']=files['mechanical-sync-install.sh'].replace(b'0x584e',b'0x5850')
    files['release-radio.sh']=files['release-radio.sh'].replace(b'[ "$marker" = 0x584e ]',b'[ "$marker" = 0x584e ] || [ "$marker" = 0x5850 ]')
    files.pop('manifest.sha256')
    files['manifest.sha256']=''.join(sha(data)+'  '+name+'\n' for name,data in sorted(files.items())).encode('ascii')
    for name,data in files.items():
        p=OUT/'package-files'/name; p.parent.mkdir(exist_ok=True,parents=True); p.write_bytes(data)
        if name.endswith('.sh'):
            subprocess.run(['C:/Program Files/Git/bin/bash.exe','--noprofile','--norc','-n',str(p)],check=True,timeout=10)
    raw=io.BytesIO()
    with tarfile.open(fileobj=raw,mode='w',format=tarfile.USTAR_FORMAT) as archive:
        for name,data in sorted(files.items()):
            p=tarfile.TarInfo(name); p.size=len(data); p.mode=0o600; p.mtime=0
            archive.addfile(p,io.BytesIO(data))
    packed=gzip.compress(raw.getvalue(),mtime=0)
    with tarfile.open(fileobj=io.BytesIO(packed),mode='r:gz') as archive:
        assert {p.name for p in archive}==set(files)
        for p in archive: assert p.isfile() and archive.extractfile(p).read()==files[p.name]
    (OUT/'session-package.tar.gz').write_bytes(packed)
    report={'packageSha256':sha(packed),'packageBytes':len(packed),'farmPayloadSha256':parent['farmPayloadSha256'],
            'firmwareSha256':m['sha256'],'files':{name:{'sha256':sha(data),'bytes':len(data)} for name,data in files.items()},
            'instructionChecks':t,'clientChecks':c['wireChecks'],'sourcesRetained':7,
            'flashParameterTransmissionImplemented':False,'diagnosticsRemoved':True,
            'installed':False,'hardwareRequests':0,'targetQtChecksPassed':False,
            'physicalReadyRetentionVerified':False,'physicalEmissionDuringPrepareVerified':False}
    (OUT/'package-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {'packageBytes':len(packed),'files':len(files),'sha256':report['packageSha256'],'installed':False}

if __name__=='__main__': print(package())
