"""已确认回滚后的组件恢复事务，完整运行目标脚本与传输失败模型。"""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1]
assert Path.cwd().resolve()==HERE.parents[1]
sys.path.insert(0,str(HERE/'research'))
import formal_linux_resume as resume
spec=importlib.util.spec_from_file_location('linux_update_cases',HERE/'CodeTests/formal_linux_update.test.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
base.fixtures.OUT=HERE/'CodeTests/formal_linux_resume_output'

def run():
    proof,raw,old=resume.build();checks=[]
    def check(name,condition):assert condition,name;checks.append(name)
    result=subprocess.run([str(base.fixtures.SHELL),'-n',str(resume.OUT/'apply.sh')],capture_output=True,text=True)
    check('继续安装脚本POSIX语法',result.returncode==0)
    for flag in (None,'bad_new_manifest','no_disarm','fail_gui'):
        case,old_manifest=base.make_case(flag or 'normal',flag)
        root,d,env=case;target=d/'u4'
        assert target.resolve().is_relative_to(base.fixtures.OUT.resolve())
        shutil.copytree(d/'u3',target)
        original=(target/'apply.sh').read_text(encoding='utf-8')
        base.write(target/'apply.sh',resume.resumed_script(original))
        for name in ('formal-enable.ready','formal-enable.confirmed'):(d/name).unlink()
        result=base.fixtures.execute(case,'u4/apply.sh');events=base.fixtures.commands(root)
        if flag in ('bad_new_manifest','no_disarm'):
            check(str(flag)+'变更前停止',result.returncode!=0 and (d/'manifest.sha256').read_bytes()==old_manifest)
        else:
            rollback=flag is not None
            expected='linux-update-failed-previous-package-restored-locked' if rollback else 'updated-package-loaded-default-off-locked'
            check(str(flag)+'返回状态与恢复一致',(result.returncode!=0)==rollback and (target/'result').read_text().strip()==expected)
            check(str(flag)+'两个组件版本一致',all((d/n).read_bytes()==(b'test fixture only' if rollback else b'new fixture') for n in resume.update.CHANGED))
            check(str(flag)+'原服务恢复',base.fixtures.is_active(root,'victory-gui') and base.fixtures.is_active(root,'msg2dbus-farm'))
            check(str(flag)+'继续保持引闪锁定',not (d/'formal-enable.ready').exists() and not (d/'formal-enable.confirmed').exists())
            check(str(flag)+'自检记录明确结果','direct-selfcheck-exit=0' in result.stdout)
        check(str(flag)+'无线驱动和文件保持',not any(e['command'] in ('rmmod','modprobe') for e in events) and (d/'test/brcm/brcmfmac4356-pcie.bin').read_bytes()==b'OLD')
        check(str(flag)+'不发射不持有',all(e['args'] in [['phyreg','0','b'],['phyreg','17','b']] for e in events if e['command']=='wl'))
    class Model:
        def __init__(self,mode='normal'):self.commands=[];self.mode=mode
        def command(self,label,command):
            assert 0<len(command.encode('ascii'))<=231 and '\n' not in command
            self.commands.append((label,command))
            if self.mode=='ambiguous' and label=='resume-part-3':raise RuntimeError('ambiguous test transport')
            result=''
            if label=='resume-confirm-rollback':result=resume.EXPECTED if self.mode!='wrong_state' else 'pending'
            if label=='resume-decode-result':result=('0'*64 if self.mode=='bad_hash' else proof['sha256'])+' apply.sh'
            return {'output':result}
    model=Model();resume.stage(model,proof,raw,lambda _:None)
    check('解码只派发一次',sum(label=='resume-decode-once' for label,_ in model.commands)==1)
    for mode in ('wrong_state','bad_hash','ambiguous'):
        model=Model(mode)
        try:resume.stage(model,proof,raw,lambda _:None)
        except RuntimeError:pass
        else:raise AssertionError('Invalid continuation accepted')
        check(mode+'终止且不进入安装',not any(label=='resume-verify-components' for label,_ in model.commands))
    paths=[Path(__file__),HERE/'CodeTests/formal_linux_update.test.py',HERE/'CodeTests/formal_install.test.py',HERE/'research/formal_linux_resume.py']
    report={'passed':True,'checkCount':len(checks),'checks':checks,'candidateSha256':proof['sha256'],
            'hardwareRequests':0,'sourceHashes':{p.relative_to(HERE).as_posix():resume.sha(p.read_bytes()) for p in paths}}
    (resume.OUT/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':len(checks),'hardwareRequests':0}))

if __name__=='__main__':run()
