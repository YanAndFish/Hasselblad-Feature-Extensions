"""最终实际归档、Qt资源、ARM符号、新路径传输与恢复边界审计。"""
from pathlib import Path
from datetime import datetime,timezone
import base64,hashlib,importlib.util,io,json,os,subprocess,sys,tarfile
sys.dont_write_bytecode=True
FIX=Path(__file__).resolve().parents[1];sys.path.insert(0,str(FIX))
import delivery
p=delivery.package;m=delivery.transport
sys.path.insert(0,str(FIX/'build/python-qt515'))
from PyQt5.QtCore import QResource,QFile,QIODevice
def run():
    report,blob=p.verify();checks=[]
    def check(n,c):
        assert c,n
        checks.append(n)
    with tarfile.open(fileobj=io.BytesIO(blob)) as archive:
        members=archive.getmembers();files={v.name:archive.extractfile(v).read() for v in members}
        check('nine private regular files',len(members)==9 and all(v.isfile() and '/' not in v.name and v.uid==v.gid==0 and v.mode in (0o600,0o700) for v in members))
    check('all actual payload digests bound',{k:p.digest(v) for k,v in files.items()}==report['files'])
    manifest={n:h for h,n in (v.split() for v in files['manifest.sha256'].decode().splitlines())}
    check('manifest covers eight exact payloads',len(manifest)==8 and set(manifest)==set(files)-{'manifest.sha256'} and all(p.digest(files[n])==h for n,h in manifest.items()))
    check('shell and manifest LF',all(b'\r' not in b for n,b in files.items() if n.endswith(('.sh','.sha256'))))
    check('no AF or replay payload',set(files)=={'common.sh','install.sh','restore.sh','run.sh','baseline.sha256','manifest.sha256','libhbl-ui-resident.so','ui-health','ui-resident.rcc'})
    directory=FIX/'build/session/package-test'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');directory.mkdir(parents=True)
    path=directory/'payload.rcc';path.write_bytes(files['ui-resident.rcc'])
    check('actual Qt registers RCC v1',QResource.registerResource(str(path)))
    for key,h in report['resources'].items():
        f=QFile(':'+key);check('Qt reads exact effective '+key,f.open(QIODevice.ReadOnly) and p.digest(bytes(f.readAll()))==h);f.close();del f
    check('resource unregistered',QResource.unregisterResource(str(path)))
    changed=p.build.patch.resources();old=p.build.patch.FROZEN
    check('only single text2 expression changes',changed['/settings/SettingsGeneric.qml'].replace(p.build.patch.NEW,p.build.patch.OLD)==(old/'settings/SettingsGeneric.qml').read_text(encoding='utf-8'))
    check('other three QMLs byte identical',all(v.encode()==(old/k.lstrip('/')).read_bytes() for k,v in changed.items() if k!='/settings/SettingsGeneric.qml'))
    source=(FIX/'session/native/runtime.cpp').read_text(encoding='utf-8')
    check('native binds four hashes and new RCC',all(h in source for h in report['resources'].values()) and report['rccSha256'] in source)
    check('native normal-root load only no extra page create','component.create(' not in source and 'c.create(' not in source)
    sys.path.insert(0,str(p.build.original.CACHE/'python'));from elftools.elf.elffile import ELFFile
    elf=ELFFile(io.BytesIO(files['libhbl-ui-resident.so']))
    exports={v.name for v in elf.get_section_by_name('.dynsym').iter_symbols() if v['st_shndx']!='SHN_UNDEF'}
    check('ARM32 original Qt hooks',elf.elfclass==32 and elf['e_machine']=='EM_ARM' and {'_Z21qRegisterResourceDataiPKhS0_S0_','_ZN21QQmlApplicationEngine4loadERK4QUrl'}<=exports)
    check('health checker unchanged',report['files']['ui-health']=='6c503c33cf6316baf681c788ab45e553260d23907176ba4a47fb4004eed97f86')
    check('11 original baseline hashes',len(files['baseline.sha256'].decode().splitlines())==11 and b'libstdc++' in files['baseline.sha256'])
    class Model:
        def __init__(self,fail=None):self.calls=[];self.dispatched=set();self.fail=fail;self.failed=False
        def command(self,label,command):
            assert not self.failed;m.bounded(command);self.calls.append((label,command))
            if self.fail=='unknown' and label=='chunk-2':self.failed=True;raise RuntimeError('unknown response')
            if label=='services':out='\n'.join(['active']*5)
            elif label=='d.awk-hash':out=p.digest(m.DECODER.encode())+' file'
            elif label=='decode.sh-hash':out=p.digest(m.decoder_script().encode())+' file'
            elif label=='encoded-hash':out=p.digest(base64.b64encode(blob))+' file'
            elif label.startswith('decode-observe'):out='0\n'+('0'*64 if self.fail=='digest' else report['packageSha256'])+' file'
            elif label=='extract-once':out='ui-package-verified'
            elif label.endswith('-observe'):out='0\n'+m.MARKERS[label.removesuffix('-observe')]
            elif label=='status':out=m.MARKERS['status']
            else:out=''
            return {'output':out}
    model=Model();check('full archive transfer model',m.stage(model,report,blob,lambda _:None)['staged'])
    for phase in m.MARKERS:m.phase(model,phase,lambda _:None)
    check('new-root commands all within 231-byte limit',all(0<len(c.encode())<=231 for _,c in model.calls))
    count=len(model.calls)
    try:m.phase(model,'ui',lambda _:None)
    except ValueError:pass
    else:raise AssertionError('duplicate phase accepted')
    check('duplicate phase never dispatched',len(model.calls)==count)
    for failure in ('unknown','digest'):
        model=Model(failure)
        try:m.stage(model,report,blob,lambda _:None)
        except RuntimeError:pass
        else:raise AssertionError('failed transfer accepted')
        check(failure+' stops before extraction',not any(n=='extract-once' for n,c in model.calls) and (failure!='unknown' or model.calls[-1][0]=='chunk-2'))
    check('default import never loads USB driver','ui_reviewed_linux_transport' not in sys.modules and 'read_usb_link_once' not in sys.modules)
    (directory/'p64').write_bytes(base64.b64encode(blob));(directory/'d.awk').write_text(m.DECODER,encoding='ascii')
    script=m.decoder_script().replace(m.REMOTE,directory.as_posix());(directory/'decode.sh').write_text(script,encoding='ascii')
    result=subprocess.run(['C:/Program Files/Git/bin/sh.exe',str(directory/'decode.sh')],cwd=p.ROOT,capture_output=True,text=True,timeout=60)
    check('actual archive classic decoder roundtrip',result.returncode==0 and (directory/'session.tar.gz').read_bytes()==blob)
    check('actual decoder records digest and exit',(directory/'decode.exit').read_text().strip()=='0' and (directory/'decode.sha').read_text().split()[0]==report['packageSha256'])
    proof={'passed':True,'checks':checks,'packageSha256':report['packageSha256'],'testSha256':p.build.sha(Path(__file__)),
        'hardwareRequests':0,'targetQt55Validated':False,'mockFormatCalls':0,'maxCommandBytes':max(len(c.encode()) for _,c in model.calls)}
    p.build.save(p.OUT/'package-validation.json',proof)
    print(json.dumps({'passed':True,'checks':len(checks),'packageSha256':report['packageSha256'],'hardwareRequests':0}))
if __name__=='__main__':run()
