"""离线执行实际解码脚本，并检验实际串行传输/阶段命令的失败边界。"""
from pathlib import Path
import base64,gzip,hashlib,importlib.util,json,os,subprocess,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
spec=importlib.util.spec_from_file_location('ui_delivery_under_test',HERE/'session/delivery.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run():
    assert Path.cwd().resolve()==ROOT
    checks=[]
    def check(name,v):
        if not v:raise AssertionError(name)
        checks.append(name)
    data=gzip.compress(bytes(range(256))*100,mtime=0)
    report={'bytes':len(data),'packageSha256':m.package.digest(data)}
    class Model:
        def __init__(self,fail=None):self.calls=[];self.dispatched=set();self.fail=fail;self.failed=False
        def command(self,label,command):
            assert not self.failed;m.bounded(command);self.calls.append((label,command))
            if self.fail=='unknown' and label=='chunk-2':self.failed=True;raise RuntimeError('unknown response')
            if label=='services':out='\n'.join(['active']*5)
            elif label=='d.awk-hash':out=m.package.digest(m.DECODER.encode())+' file'
            elif label=='decode.sh-hash':out=m.package.digest(m.decoder_script().encode())+' file'
            elif label=='encoded-hash':out=m.package.digest(base64.b64encode(data))+' file'
            elif label.startswith('decode-observe'):out='0\n'+('0'*64 if self.fail=='digest' else report['packageSha256'])+' file'
            elif label=='extract-once':out='replay-package-verified'
            elif label.endswith('-observe'):out='0\n'+m.MARKERS[label.removesuffix('-observe')]
            elif label=='status':out=m.MARKERS['status']
            else:out=''
            return {'output':out}
    model=Model();check('transfer completes',m.stage(model,report,data,lambda _:None)['staged'])
    for phase in m.MARKERS:m.phase(model,phase,lambda _:None)
    check('all actual commands fit 231 byte frame',all(len(c.encode())<=231 for _,c in model.calls))
    count=len(model.calls)
    try:m.phase(model,'ui',lambda _:None)
    except ValueError:pass
    else:raise AssertionError('duplicate accepted')
    check('duplicate phase sends nothing',len(model.calls)==count)
    for failure in ('unknown','digest'):
        model=Model(failure)
        try:m.stage(model,report,data,lambda _:None)
        except RuntimeError:pass
        else:raise AssertionError('failure ignored')
        check(failure+' blocks extraction without retry',not any(n=='extract-once' for n,c in model.calls) and (failure!='unknown' or model.calls[-1][0]=='chunk-2'))
    model=Model()
    try:m.stage(model,report,data+b'bad',lambda _:None)
    except ValueError:pass
    else:raise AssertionError('bad local digest')
    check('local digest checked before any request',not model.calls)
    folder=HERE/'build/session/decoder-test';folder.mkdir(parents=True,exist_ok=True)
    # 不压缩的二进制让单行足够长，并覆盖 NUL、引号和反斜线等所有字节。
    payload=bytes(range(256))*256
    (folder/'p64').write_bytes(base64.b64encode(payload));(folder/'d.awk').write_text(m.DECODER,encoding='ascii')
    script=m.decoder_script().replace(m.REMOTE,folder.as_posix())
    (folder/'decode.sh').write_text(script,encoding='ascii')
    target=folder/'session.tar.gz'
    if target.exists():target.unlink()
    result=subprocess.run(['C:/Program Files/Git/bin/sh.exe',str(folder/'decode.sh')],cwd=ROOT,capture_output=True,text=True,timeout=60)
    check('actual classic od awk printf preserves all bytes',result.returncode==0 and target.read_bytes()==payload)
    check('decoder status and SHA recorded', (folder/'decode.exit').read_text().strip()=='0' and (folder/'decode.sha').read_text().split()[0]==m.package.digest(payload))
    check('imports did not initialize USB',not any(n in sys.modules for n in ('read_usb_link_once','replay_reviewed_linux_transport')))
    source=HERE/'session/native/runtime.cpp';text=source.read_text(encoding='utf-8')
    release=m.package.build.fixed()
    binding=(m.package.OUT/'native/resource_binding.h').read_text(encoding='ascii')
    check('native verifies every fixed effective resource',all(e['outputSha256'] in binding for e in release['manifest']['resources'].values()) and m.package.build.RCC_SHA in binding and '#include "resource_binding.h"' in text)
    check('native does not instantiate test pages','component.create(' not in text and 'c.create(' not in text)
    check('transport source fixed',sha(m.TRANSPORT)==m.TRANSPORT_SHA)
    files=[Path(__file__),HERE/'session/delivery.py',source,m.TRANSPORT]
    proof={'passed':True,'checks':checks,'sources':{p.relative_to(ROOT).as_posix():sha(p) for p in files},'hardwareRequests':0,'targetValidated':False}
    m.package.build.save(HERE/'build/session/transfer-validation.json',proof)
    print(json.dumps({'passed':True,'checks':len(checks),'hardwareRequests':0}))
if __name__=='__main__':run()
