"""实际完整包的传输命令在映射工作副本中解码、解包、验摘要；不执行 ARM 文件。"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path.insert(0,str(HERE/'tools'))
from transfer_session import Transfer,REMOTE,verify_package

class Transcript:
    def __init__(self):self.commands=[]
    def command(self,label,command):
        self.commands.append(command)
        return {'exit_code':0,'output':'','closed':True}

def run():
    report,data=verify_package()
    out=HERE/'artifacts/package-tests';out.mkdir(parents=True,exist_ok=True)
    staged=out/'staged'
    if staged.exists():
        staged.resolve().relative_to(out.resolve());shutil.rmtree(staged)
    model=Transcript();transfer=Transfer(model);transfer.upload()
    # Windows ACL 不能表达目标 root:0700；该项由安装契约替身及目标 preflight 检查。
    lines=['set -eu','PATH=/usr/bin:/bin; export PATH']+[c.replace(REMOTE,staged.as_posix()).replace('mkdir -m 700','mkdir') for c in model.commands]
    lines+=['wait','cd "'+staged.as_posix()+'"','sha256sum -c decode.sha','tar xzf session.tar.gz','sha256sum -c manifest.sha256']
    script=out/'transfer.sh';script.write_text('\n'.join(lines)+'\n',encoding='ascii',newline='\n')
    result=subprocess.run(['C:/Program Files/Git/bin/sh.exe',str(script)],cwd=ROOT,
                          env=dict(os.environ,MSYS_NO_PATHCONV='1'),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
    assert result.returncode==0,result.stdout+result.stderr
    assert (staged/'session.tar.gz').read_bytes()==data
    for name,wanted in report['files'].items():assert hashlib.sha256((staged/name).read_bytes()).hexdigest()==wanted,name
    value={'passed':True,'cameraAccess':False,'targetCodeExecuted':False,'realTransportExecuted':False,
           'fullGeneratedUploadCommands':len(model.commands),'longestCommandBytes':max(map(len,model.commands)),
           'actualShellDecodeAndTarExtract':True,'verifiedMembers':len(report['files']),
           'hostFilesystemPermissionsAreNotTargetEvidence':True,
           'packageSha256':report['packageSha256'],
           'packageReportSha256':hashlib.sha256((HERE/'artifacts/session-package/package.json').read_bytes()).hexdigest(),
           'sourceHashes':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),HERE/'tools/transfer_session.py']}}
    (out/'validation.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'fullPackageTransferAndExtract':'passed','members':len(report['files']),'cameraAccess':False}))

if __name__=='__main__':run()
