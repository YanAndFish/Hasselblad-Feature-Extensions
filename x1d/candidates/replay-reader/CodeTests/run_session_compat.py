"""兼容版的实际 shell 全包传输及错误拒绝验证；无设备、服务或照片访问。"""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile

HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[2]
RELEASE=HERE/'releases/session-compat-r2'
OUT=HERE/'artifacts/session-compat-tests'
SHELL='C:/Program Files/Git/bin/sh.exe'
AWK='C:/Program Files/Git/usr/bin/awk.exe'


def sha(data):return hashlib.sha256(data).hexdigest()


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    spec=importlib.util.spec_from_file_location('compat_transfer',RELEASE/'transfer.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    report,data=mod.verify_package();checks=[]
    def check(name,yes):assert yes,name;checks.append(name)
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as t:
        files={m.name:t.extractfile(m).read() for m in t}
    common=files['common.sh'].decode()
    baseline=re.search(r"awk '([^']+)'",common.split('baseline_check() {',1)[1]).group(1)
    maps=re.search(r"awk '([^']+)'",common.split('running() {',1)[1]).group(1)
    def accepts(program,text):return subprocess.run([AWK,program],input=text,capture_output=True).returncode==0
    check('all-74-factory-baseline-paths',len(files['baseline.sha256'].splitlines())==74 and accepts(baseline,files['baseline.sha256']))
    bad=[b'0'*64+b'  /tmp/foreign\n',b'0'*64+b'  /usr/lib/../foreign\n',b'0'*64+b'  /usr/lib/bad file\n',b'0'*63+b'  /usr/lib/x\n',files['baseline.sha256']+files['baseline.sha256'].splitlines()[0]+b'\n']
    for i,value in enumerate(bad):check('baseline-negative-'+str(i),not accepts(baseline,value))
    line=b'00000000-00001000 rw-s 00000000 00:05 1 /dev/zero (deleted)\n'
    for i,value in enumerate([line,line.replace(b'/dev/zero',b'/tmp/weston-shared-AbC123'),b'00000000-00001000 r-xp 00000000 08:01 2 /usr/lib/libQt5Core.so.5\n']):
        check('maps-allowed-'+str(i),accepts(maps,value))
    invalid=[line.replace(b'rw-s',b'r-xs'),line.replace(b'rw-s',b'rw-p'),line.replace(b'/dev/zero',b'/tmp/foreign.so'),line.replace(b'(deleted)',b'(deleted) extra'),line.replace(b'/dev/zero',b'/dev/zero-extra'),line.replace(b'/dev/zero',b'/tmp/weston-shared-'),line.replace(b'/dev/zero',b'/tmp/weston-shared-x.so'),line.replace(b'/dev/zero',b'/tmp/weston-shared-x/evil'),line.replace(b'/dev/zero',b'/foo/tmp/weston-shared-x')]
    for i,value in enumerate(invalid):check('maps-negative-'+str(i),not accepts(maps,value))
    # 每次运行独立工作副本，不删除上次证据。
    import tempfile
    work=Path(tempfile.mkdtemp(prefix='run-',dir=OUT))
    all_commands=[]
    class Model:
        failed=False
        def __init__(self,fail=None,bad=None):self.fail=fail;self.bad=bad;self.commands=[]
        def command(self,label,command):
            self.commands.append(command);all_commands.append(command)
            if label==self.fail:raise RuntimeError('Simulated uncertain response')
            text=''
            if label=='helper-hash':text=sha(mod.HELPER.encode())+' helper'
            if label=='replay-decode-result':text='0\n'+report['packageSha256']+' archive'
            if label=='replay-extract':text='replay-package-verified'
            if label.endswith('-result') and label!='replay-decode-result':text='0\nphase complete'
            if self.bad and label==self.bad[0]:text=self.bad[1]
            return {'exit_code':0,'closed':True,'output':text}
    m=Model();transfer=mod.Transfer(m);transfer.upload()
    dest=work/'staged'
    # 宿主映射不证明目标 root:0700 权限；生产 mkdir 保持原样。
    lines=['set -eu','PATH=/usr/bin:/bin; export PATH']+[c.replace(mod.REMOTE,dest.as_posix()).replace('mkdir -m 700','mkdir') for c in m.commands]
    lines+=['wait','cd "'+dest.as_posix()+'"','test "$(cat decode.exit)" = 0','sha256sum -c decode.sha','tar xzf session.tar.gz','sha256sum -c manifest.sha256']
    script=work/'transfer.sh';script.write_text('\n'.join(lines)+'\n',encoding='ascii',newline='\n')
    result=subprocess.run([SHELL,str(script)],cwd=ROOT,env=dict(os.environ,MSYS_NO_PATHCONV='1'),capture_output=True,text=True,timeout=120)
    assert result.returncode==0,result.stdout+result.stderr
    check('full-stream-decoded-archive-identical',(dest/'session.tar.gz').read_bytes()==data)
    check('all-14-members-identical',all(sha((dest/name).read_bytes())==digest for name,digest in report['files'].items()))
    for name in ['common.sh','preflight.sh','install.sh','restore.sh','status.sh']:
        subprocess.run([SHELL,'-n',str(dest/name)],check=True,cwd=ROOT)
    check('scripts-shell-syntax',True)
    assert transfer.finish_upload()
    for phase in ('ui','enable','restore'):
        transfer.dispatch(phase)
        try:transfer.dispatch('restore' if phase=='ui' else phase)
        except RuntimeError:pass
        else:raise AssertionError('Overlapping/repeated phase accepted')
        assert transfer.result(phase)['exit_code']==0
    check('sequential-once-only-dispatch',True)
    small=(report,b'contract bytes')
    for name in ['replay-create','helper-hash','replay-chunk-0','replay-decode','replay-extract','replay-ui-dispatch']:
        mm=Model(fail=name);t=mod.Transfer(mm,small)
        try:t.upload();t.finish_upload();t.dispatch('ui')
        except RuntimeError:pass
        else:raise AssertionError(name)
        before=len(mm.commands)
        try:t.send('retry','printf retry')
        except RuntimeError:pass
        else:raise AssertionError('Retry sent')
        check(name+'-uncertain-stops',t.stopped and len(mm.commands)==before)
    for label,value in [('helper-hash',''),('replay-decode-result','1\n'+report['packageSha256']),('replay-decode-result','0\n'+'0'*64),('replay-extract','unconfirmed')]:
        mm=Model(bad=(label,value));t=mod.Transfer(mm,small)
        try:t.upload();t.finish_upload()
        except RuntimeError:pass
        else:raise AssertionError(label)
        check(label+'-invalid-stops-'+str(len(checks)),t.stopped)
    check('every-command-within-231-bytes',max(len(c.encode('ascii')) for c in all_commands)<=231)
    check('original-frozen-package-unchanged',sha((HERE/'artifacts/session-package/session.tar.gz').read_bytes())==report['baseArchiveSha256'])
    validation={'passed':True,'checks':checks,'fullArchiveBytes':len(data),'verifiedMembers':14,
        'maxCommandBytes':max(len(c.encode('ascii')) for c in all_commands),'cameraAccess':False,
        'targetProgramExecuted':False,'hostFilesystemPermissionsAreNotTargetEvidence':True,
        'packageSha256':report['packageSha256'],'transferSha256':sha((RELEASE/'transfer.py').read_bytes()),
        'sourceSha256':sha(Path(__file__).read_bytes()),'workDirectory':work.relative_to(ROOT).as_posix()}
    encoded=(json.dumps(validation,ensure_ascii=False,indent=2)+'\n').encode()
    (RELEASE/'validation.json').write_bytes(encoded)
    report['packageReadyForDelegatedLoad']=True
    report['validationSha256']=sha(encoded)
    (RELEASE/'package.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'compatChecks':len(checks),'fullArchiveRoundtrip':True,'maxCommandBytes':validation['maxCommandBytes'],'cameraAccess':False}))


if __name__=='__main__':run()
