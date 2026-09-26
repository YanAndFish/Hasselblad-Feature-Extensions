"""231 字节命令边界、一次派发/不重试、未知结果与哈希错误拒绝；无设备连接。"""
import base64
import hashlib
import json
from pathlib import Path
import os
import subprocess
import sys
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path.insert(0,str(HERE/'tools'))
from transfer_session import Transfer,DECODER

class Model:
    failed=False
    all_commands=[]
    def __init__(self,digest,fail=None):self.digest=digest;self.fail=fail;self.commands=[]
    def command(self,label,command):
        self.commands.append((label,command))
        self.all_commands.append((label,command))
        assert len(command.encode('ascii'))<=231
        if label==self.fail:raise RuntimeError('ambiguous simulated response')
        text=''
        if label=='replay-decode-result':text=self.digest+' session.tar.gz'
        if label=='replay-extract':text='replay-package-verified'
        if label.endswith('-result') and 'decode' not in label:text='0\nphase-finished'
        return {'exit_code':0,'closed':True,'output':text}

def run():
    out=HERE/'artifacts/transfer-tests';out.mkdir(parents=True,exist_ok=True)
    data=bytes(range(256))*17;digest=hashlib.sha256(data).hexdigest()
    package=({'packageSha256':digest},data);checks=[];Model.all_commands=[]
    def check(label,ok):assert ok,label;checks.append(label)
    m=Model(digest);t=Transfer(m,package);t.upload();assert t.finish_upload()
    for phase in ('ui','enable','restore'):
        t.dispatch(phase)
        if phase=='ui':
            try:t.dispatch('restore')
            except RuntimeError:pass
            else:raise AssertionError('Overlapping phase accepted')
            check('pending-phase-cannot-overlap',True)
        assert t.result(phase)['exit_code']==0
    check('all-generated-commands-fit',all(len(c.encode('ascii'))<=231 for _,c in m.commands))
    for phase in ('ui','enable','restore'):
        try:t.dispatch(phase)
        except RuntimeError:pass
        else:raise AssertionError('Repeated phase accepted')
    check('one-dispatch-per-phase',all(sum(n=='replay-'+p+'-dispatch' for n,_ in m.commands)==1 for p in ('ui','enable','restore')))
    for fail in ('replay-create','replay-chunk-3','replay-decode','replay-extract','replay-ui-dispatch'):
        m=Model(digest,fail);t=Transfer(m,package)
        try:t.upload();t.finish_upload();t.dispatch('ui')
        except RuntimeError:pass
        else:raise AssertionError(fail)
        before=len(m.commands)
        try:t.send('forbidden','printf retry')
        except RuntimeError:pass
        else:raise AssertionError('Retry accepted')
        check(fail+'-stops-without-retry',t.stopped and len(m.commands)==before)
    m=Model('0'*64);t=Transfer(m,package);t.upload()
    try:t.finish_upload()
    except RuntimeError:pass
    else:raise AssertionError('Wrong digest accepted')
    check('bad-hash-not-extracted',not any(n=='replay-extract' for n,_ in m.commands))
    # 实际 shell/awk 解码所有字节（包括 NUL、反斜线、引号）；不依赖 mock 的输出。
    (out/'decoder.awk').write_text(DECODER,encoding='ascii',newline='\n')
    (out/'encoded').write_bytes(base64.b64encode(data))
    script='cd "$1"; printf \'%b\' "$(awk -f decoder.awk encoded)" > decoded'
    subprocess.run(['C:/Program Files/Git/bin/sh.exe','-c',script,'decoder-test',str(out)],check=True,cwd=ROOT,
                   env=dict(os.environ,MSYS_NO_PATHCONV='1'))
    check('actual-shell-all-byte-roundtrip',(out/'decoded').read_bytes()==data)
    report={'passed':True,'checks':checks,'cameraAccess':False,'deviceTransportUsed':False,
            'longestCommandBytes':max(len(c.encode('ascii')) for _,c in Model.all_commands),
            'sourceHashes':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),HERE/'tools/transfer_session.py']}}
    (out/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'transferChecks':len(checks),'cameraAccess':False}))

if __name__=='__main__':run()
