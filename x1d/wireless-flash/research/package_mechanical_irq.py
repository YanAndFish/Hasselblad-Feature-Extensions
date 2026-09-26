"""双中断 Linux 完整临时包；复用已验证原无线实现，替换协议与两来源界面。"""
from pathlib import Path
import hashlib,json,subprocess,tarfile
from package_mechanical_timing_record import archive_bytes
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[1]
BASE=HERE/'build/mechanical-options-candidate';OUT=HERE/'build/mechanical-irq-candidate'
def sha(data):return hashlib.sha256(data).hexdigest()
def build():
    assert Path.cwd().resolve()==ROOT
    prior=json.loads((BASE/'package-validation.json').read_text(encoding='utf-8'))
    assert sha((BASE/'session-package.tar.gz').read_bytes())==prior['packageSha256']
    with tarfile.open(BASE/'session-package.tar.gz','r:gz') as archive:
        files={p.name:archive.extractfile(p).read() for p in archive if p.isfile()}
    assert all(sha(data)==prior['files'][name]['sha256'] for name,data in files.items())
    clients=json.loads((OUT/'client-build.json').read_text(encoding='utf-8'))
    ui=json.loads((OUT/'ui-build.json').read_text(encoding='utf-8'))
    wire=json.loads((OUT/'irq-wire-validation.json').read_text(encoding='utf-8'))
    assert clients['passed'] and ui['built'] and wire['passed']
    for name,digest in clients['sourceHashes'].items():assert sha((HERE/name).read_bytes())==digest,name
    assert sha((HERE/'research/build_mechanical_irq_ui.py').read_bytes())==ui['sourceSha256']
    for name,meta in clients['outputs'].items():
        data=(OUT/name).read_bytes();assert sha(data)==meta['sha256'] and len(data)==meta['bytes']
        files['mechanical-sync-hook-check' if name=='sync-hook-check' else name]=data
    files['ui.rcc']=(OUT/'ui.rcc').read_bytes();assert sha(files['ui.rcc'])==ui['rccSha256']
    files.pop('switch-process.sh',None);files.pop('manifest.sha256')
    files['manifest.sha256']=''.join(sha(data)+'  '+name+'\n' for name,data in sorted(files.items())).encode('ascii')
    for name,data in files.items():
        p=OUT/'package-files'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        if name.endswith('.sh'):
            subprocess.run(['C:/Program Files/Git/bin/bash.exe','--noprofile','--norc','-n',str(p)],check=True,timeout=10)
    archive=archive_bytes(files);(OUT/'session-package.tar.gz').write_bytes(archive)
    report={'passed':True,'installed':False,'hardwareRequests':0,'packageSha256':sha(archive),'packageBytes':len(archive),
        'files':{n:{'sha256':sha(d),'bytes':len(d)} for n,d in files.items()},'sources':[2,3],
        'messageVersion':2,'bridgeVersion':4,'sameProcessSwitchRemoved':True,'interruptSwitchAdded':False,
        'radioFirmwareSha256':prior['firmwareSha256'],'radioImplementationReused':True,
        'sourceHashes':{str(Path(__file__).relative_to(HERE)):sha(Path(__file__).read_bytes())}}
    (OUT/'package-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {'passed':True,'bytes':len(archive),'files':len(files),'installed':False}
if __name__=='__main__':print(build())
