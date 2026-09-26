"""生成不可变内容寻址临时测试包。"""
from pathlib import Path
import hashlib,io,json,subprocess,tarfile
HERE=Path(__file__).resolve().parent
OUT=HERE/'build'
FILES=('libhbl-wifi-probe.so','button.rcc','health','baseline.sha256','launch.sh','monitor.sh','gui.conf','common.sh','run.sh')
def digest(b):return hashlib.sha256(b).hexdigest()
def build():
    for name in ('ui-validation.json','startup-validation.json','transaction-validation.json'):
        validation=json.loads((OUT/name).read_text())
        assert validation['passed']
        for path,expected in validation.get('sources',{}).items():assert digest((HERE/path).read_bytes())==expected
    payload={name:(OUT/name if name in FILES[:4] else HERE/name).read_bytes() for name in FILES}
    for name in FILES[3:]:assert b'\r' not in payload[name],name+' must use LF'
    report=json.loads((OUT/'build.json').read_text())
    assert json.loads((OUT/'ui-validation.json').read_text())['qmlSha256']==report['qmlSha256']
    assert digest(payload['button.rcc'])==report['rccSha256']
    for name in ('libhbl-wifi-probe.so','health'):assert digest(payload[name])==report['outputs'][name]['sha256']
    for name in ('launch.sh','monitor.sh','common.sh','run.sh'):
        r=subprocess.run(['C:/Program Files/Git/bin/sh.exe','-n',str(HERE/name)],capture_output=True,text=True);assert r.returncode==0,r.stderr
    manifest=''.join(digest(data)+'  '+name+'\n' for name,data in sorted(payload.items())).encode('ascii')
    payload['manifest.sha256']=manifest
    raw=io.BytesIO()
    with tarfile.open(fileobj=raw,mode='w:gz',format=tarfile.USTAR_FORMAT) as tf:
        for name,data in sorted(payload.items()):
            info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o700 if name=='health' or name.endswith('.sh') else 0o600;info.mtime=0
            tf.addfile(info,io.BytesIO(data))
    data=raw.getvalue();hash=digest(data);folder=OUT/'packages'/hash[:16];folder.mkdir(parents=True,exist_ok=False)
    archive=folder/'probe.tar.gz';archive.write_bytes(data)
    result={'packageSha256':hash,'archive':str(archive),'bytes':len(data),'files':{n:digest(b) for n,b in payload.items()},'targetValidated':False}
    (folder/'package.json').write_text(json.dumps(result,indent=2)+'\n')
    (OUT/'current.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'packageSha256':hash,'bytes':len(data),'members':len(payload)}))
if __name__=='__main__':build()
