"""共存包实际传输入口的离线帧、解码与停止边界。"""
from pathlib import Path
import base64,hashlib,importlib.util,json,subprocess,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
spec=importlib.util.spec_from_file_location('ui_af_delivery_test',HERE/'af-session/delivery.py')
d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d);m=d.transport
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run():
    assert Path.cwd().resolve()==ROOT
    data=bytes(range(256))*4;report={'bytes':len(data),'packageSha256':hashlib.sha256(data).hexdigest()};checks=[]
    def check(n,v):
        if not v:raise AssertionError(n)
        checks.append(n)
    class Model:
        def __init__(self,fail=None):self.calls=[];self.dispatched=set();self.failed=False;self.fail=fail
        def command(self,label,command):
            assert not self.failed;m.bounded(command);self.calls.append((label,command))
            if self.fail=='unknown' and label=='chunk-2':self.failed=True;raise RuntimeError('unknown outcome')
            if label=='services':out='\n'.join(['active']*5)
            elif label=='d.awk-hash':out=hashlib.sha256(m.DECODER.encode()).hexdigest()+' file'
            elif label=='decode.sh-hash':out=hashlib.sha256(m.decoder_script().encode()).hexdigest()+' file'
            elif label=='encoded-hash':out=hashlib.sha256(base64.b64encode(data)).hexdigest()+' file'
            elif label.startswith('decode-observe'):out='0\n'+('0'*64 if self.fail=='digest' else report['packageSha256'])+' file'
            elif label=='extract-once':out='ui-package-verified'
            elif label.endswith('-observe'):out='0\n'+m.MARKERS[label.removesuffix('-observe')]
            elif label=='status':out=m.MARKERS['status']
            else:out=''
            return {'output':out}
    model=Model();check('stage actual code completes',m.stage(model,report,data,lambda _:None)['staged'])
    for phase in m.MARKERS:m.phase(model,phase,lambda _:None)
    check('all coexist commands fit reviewed frame',all(len(c.encode())<=231 for n,c in model.calls))
    check('only own remote staging namespace used',all('/tmp/hbl-ui-resident' not in c and '/tmp/hbl-x1d-combined' not in c for n,c in model.calls))
    count=len(model.calls)
    try:m.phase(model,'ui',lambda _:None)
    except ValueError:pass
    else:raise AssertionError('duplicate phase accepted')
    check('duplicate sends nothing',len(model.calls)==count)
    for failure in ('unknown','digest'):
        model=Model(failure)
        try:m.stage(model,report,data,lambda _:None)
        except RuntimeError:pass
        else:raise AssertionError('failure ignored')
        check(failure+' stops before extraction',not any(n=='extract-once' for n,c in model.calls) and (failure!='unknown' or model.calls[-1][0]=='chunk-2'))
    folder=HERE/'build/af-session/decode-test';folder.mkdir(parents=True,exist_ok=True)
    payload=bytes(range(256))*256
    (folder/'p64').write_bytes(base64.b64encode(payload));(folder/'d.awk').write_bytes(m.DECODER.encode())
    script=m.decoder_script().replace(m.REMOTE,folder.as_posix());(folder/'decode.sh').write_bytes(script.encode())
    target=folder/'session.tar.gz'
    if target.exists():target.unlink()
    result=subprocess.run(['C:/Program Files/Git/bin/sh.exe',str(folder/'decode.sh')],cwd=ROOT,capture_output=True,text=True,timeout=60)
    check('actual classic decoder preserves every byte',result.returncode==0 and target.read_bytes()==payload)
    check('default imports no device module','read_usb_link_once' not in sys.modules and 'ui_reviewed_linux_transport' not in sys.modules)
    af,_=d.package.build.inputs()
    for marker in ('gui.dropin','farm.dropin'):
        text=d.package.af_dropin(af['install.sh'],marker)
        check('AF original dropin reconstructed from frozen printf '+marker,text.startswith(b'[Service]\n') and b'$r' not in text and b'\r' not in text)
    files=[Path(__file__),HERE/'af-session/delivery.py',d.BASE,m.TRANSPORT]
    report={'passed':True,'checks':checks,'sources':{p.relative_to(ROOT).as_posix():sha(p) for p in files},'hardwareRequests':0,'targetValidated':False}
    d.package.build.save(HERE/'build/af-session/transfer-validation.json',report)
    print(json.dumps({'passed':True,'checks':len(checks),'hardwareRequests':0}))
if __name__=='__main__':run()
