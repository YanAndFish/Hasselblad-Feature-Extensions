"""升级事务的隔离文件系统模拟与传输边界检查；不打开设备。"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]
assert Path.cwd().resolve()==ROOT
sys.path.insert(0,str(HERE/'research'))
import formal_expand as expand
spec=importlib.util.spec_from_file_location('formal_install_fixtures',HERE/'CodeTests/formal_install.test.py')
fixtures=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixtures)
OUT=HERE/'CodeTests/formal_expand_output'
fixtures.OUT=OUT
write,sha=fixtures.write,fixtures.sha

def make_case(name,flag=None):
    root,d,env=fixtures.make_case(name,'test','/factory-search','inactive','inactive')
    u=d/'u2';s=d/'formal-state';u.mkdir();s.mkdir()
    write(s/'owner','formal-linux-install-v1\n');write(s/'install-complete','');write(s/'stop-confirmed','')
    write(s/'firmware-class.path','/factory-search');write(s/'module-firmware.path','test')
    write(s/'gui.dropin','fixture-gui-dropin');write(s/'farm.dropin','fixture-farm-dropin')
    write(root/'run/systemd/system/victory-gui.service.d/80-hbl-formal-flash.conf','fixture-gui-dropin')
    write(root/'run/systemd/system/msg2dbus-farm.service.d/80-hbl-formal-flash.conf','fixture-farm-dropin')
    write(root/'services/victory-gui','inactive');write(root/'marker','old')
    write(d/'formal-worker.status','formal-worker-stopped-default-off\n')
    write(d/'formal-stop.request','stop\n');write(d/'formal-enable.ready','ready\n');write(d/'formal-enable.confirmed','ready\n')
    write(d/'test/brcm/brcmfmac4356-pcie.bin',b'OLD')
    old_manifest=(d/'manifest.sha256').read_bytes()
    write(s/'package-manifest.sha256',sha(old_manifest)+'\n')
    members=[line.split()[1] for line in old_manifest.decode().splitlines()]
    for member in members:write(u/member,(d/member).read_bytes())
    for member in ('formal-ui.rcc','libhbl-formal.so','libhbl-formal-observer.so'):write(u/member,b'new fixture')
    write(u/'manifest.sha256',''.join(sha((u/n).read_bytes())+'  '+n+'\n' for n in members))
    text=(HERE/'formal-expand.sh.in').read_text(encoding='utf-8')
    replacements={'@OLD_MANIFEST@':sha(old_manifest),'@NEW_MANIFEST@':sha((u/'manifest.sha256').read_bytes()),
        '@OLD_FIRMWARE@':sha(b'OLD'),'@NEW_FIRMWARE@':sha(b'BEST'),
        '@DELTA_COMMANDS@':'dd if="$u/delta/0.bin" bs=1 seek=1 1<>"$u/new-radio.bin" 2>/dev/null || exit 65',
        '/tmp/hbl-wireless-flash':d.as_posix(),'/run/systemd/system':(root/'run/systemd/system').as_posix(),
        '/sys/module':(root/'sys/module').as_posix(),'/proc/':(root/'proc').as_posix()+'/',
        '/usr/bin/wl':(root/'bin/wl').as_posix(),
        '/lib/firmware/test/brcm/brcmfmac4356-pcie.bin':(root/'lib/firmware/test/brcm/brcmfmac4356-pcie.bin').as_posix()}
    for old,new in replacements.items():text=text.replace(old,new)
    text=text.replace('[ -S "$d/formal-worker.sock" ]','[ -f "$d/formal-worker.sock" ]').replace('[ -S "$d/formal-ui.sock" ]','[ -f "$d/formal-ui.sock" ]')
    text=text.replace('HBL_FORMAL_SYNC_SELFTEST=1 LD_PRELOAD=','HBL_FORMAL_SYNC_SELFTEST=1 FORMAL_TEST_PRELOAD=')
    write(u/'apply.sh',text);write(u/'capture-disarmed','verified')
    fake=fixtures.FAKE
    fake=fake.replace("write(r/'marker','formal' if path==str(d).replace('\\\\','/') else 'factory')",
                      "write(r/'marker','formal' if (d/'test/brcm/brcmfmac4356-pcie.bin').read_bytes()==b'BEST' else 'old')")
    fake=fake.replace("'0x5854' if (r/'marker').read_text()=='formal' else '0x0000'",
                      "'0x5854' if (r/'marker').read_text()=='formal' else '0x5853'")
    fake=fake.replace("'formal-qml-component-failed\\n' if (r/'fail_gui').exists()", 
                      "'formal-qml-component-failed\\n' if (r/'fail_gui').exists() and (d/'formal-ui.rcc').read_bytes()==b'new fixture'")
    write(root/'fake.py',fake)
    if flag=='bad_new_manifest':write(u/'formal-ui.rcc','tampered')
    elif flag=='no_disarm':(u/'capture-disarmed').unlink()
    elif flag:write(root/flag,'1')
    return (root,d,env),old_manifest

def run():
    proof,data=expand.build();checks=[]
    def check(name,condition):assert condition,name;checks.append(name)
    result=subprocess.run([str(fixtures.SHELL),'-n',str(expand.OUT/'apply.sh')],capture_output=True,text=True)
    check('目标脚本POSIX语法',result.returncode==0)
    for flag in (None,'bad_new_manifest','no_disarm','fail_modprobe_once','fail_gui'):
        case,old_manifest=make_case(flag or 'normal',flag);root,d,env=case
        result=fixtures.execute(case,'u2/apply.sh');events=fixtures.commands(root)
        if flag in ('bad_new_manifest','no_disarm'):
            check(str(flag)+'在变更前拒绝',result.returncode!=0 and not any(e['command'] in ('rmmod','modprobe') or e['command']=='systemctl' and e['args'][0] in ('stop','start') for e in events))
            check(str(flag)+'旧文件不变',(d/'manifest.sha256').read_bytes()==old_manifest and (d/'test/brcm/brcmfmac4356-pcie.bin').read_bytes()==b'OLD')
        else:
            rollback=flag is not None
            check(str(flag)+'结果正确',(result.returncode!=0)==rollback and (d/'u2/result').read_text().strip()==('expansion-failed-previous-package-restored-locked' if rollback else 'expanded-package-loaded-default-off-locked'))
            check(str(flag)+'两服务恢复运行',fixtures.is_active(root,'victory-gui') and fixtures.is_active(root,'msg2dbus-farm'))
            check(str(flag)+'界面与无线来自同一版本',(d/'formal-ui.rcc').read_bytes()==(b'test fixture only' if rollback else b'new fixture') and (d/'test/brcm/brcmfmac4356-pcie.bin').read_bytes()==(b'OLD' if rollback else b'BEST'))
            check(str(flag)+'仍需显式解锁',not (d/'formal-enable.ready').exists() and not (d/'formal-stop.request').exists())
            check(str(flag)+'原驱动搜索路径保持',(root/'sys/module/firmware_class/parameters/path').read_bytes()==b'/factory-search')
            check(str(flag)+'历史包可用',(d/'u2/previous/manifest.sha256').read_bytes()==old_manifest and (d/'u2/previous/radio.bin').read_bytes()==b'OLD')
        check(str(flag)+'升级不发射不持有',all(e['args'] in [['phyreg','0','b'],['phyreg','17','b']] for e in events if e['command']=='wl' and e['args'][:1]==['phyreg']))
    class Model:
        def __init__(self,mode='normal'):self.commands=[];self.mode=mode
        def command(self,label,command):
            assert 0<len(command.encode('ascii'))<=231 and '\n' not in command
            self.commands.append((label,command))
            if self.mode=='ambiguous' and label=='expansion-part-3':raise RuntimeError('ambiguous test transport')
            return {'output':(('0'*64 if self.mode=='bad_hash' else proof['sha256'])+' u.tgz') if label=='expansion-decode-result' else ''}
    normal=Model();expand.stage(normal,proof,data,lambda _:None)
    check('包只解码一次',sum(label=='expansion-decode-once' for label,_ in normal.commands)==1)
    for mode in ('bad_hash','ambiguous'):
        model=Model(mode)
        try:expand.stage(model,proof,data,lambda _:None)
        except RuntimeError:pass
        else:raise AssertionError('failed transport accepted')
        check(mode+'停止且不解包',not any(label=='expansion-extract' for label,_ in model.commands))
    sources=[Path(__file__),HERE/'CodeTests/formal_install.test.py',HERE/'research/formal_expand.py',HERE/'formal-expand.sh.in']
    report={'passed':True,'checkCount':len(checks),'checks':checks,'candidateSha256':proof['sha256'],
            'hardwareRequests':0,'radioRequests':0,'sourceHashes':{p.relative_to(HERE).as_posix():sha(p.read_bytes()) for p in sources}}
    write(expand.OUT/'validation.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'passed':len(checks),'hardwareRequests':0},ensure_ascii=False))

if __name__=='__main__':run()
