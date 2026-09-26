"""执行实际 apply/restore/run；服务与健康为隔离替身，不访问设备。"""
import hashlib,json,subprocess,sys,tempfile
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1]
SHELL=Path('C:/Program Files/Git/bin/bash.exe')
def run():
    for name in ('common.sh','apply.sh','restore.sh','run.sh'):
        subprocess.run([str(SHELL),'-n',str(HERE/name)],check=True,capture_output=True)
    output=HERE/'test-build/shell';output.mkdir(parents=True,exist_ok=True);checks=[]
    with tempfile.TemporaryDirectory(dir=output) as temp:
        for case in ('normal','local-check-fails','new-bus-fails','foreign-dropin','gui-changed','wrong-base'):
            folder=Path(temp)/case;folder.mkdir();(folder/'phases').mkdir()
            base=folder/'90.conf';base.write_text('original AF bus\n',encoding='ascii')
            (folder/'96-hbl-af-bus-r5.conf').write_bytes((HERE/'96-hbl-af-bus-r5.conf').read_bytes())
            posix=folder.as_posix();posix='/'+posix[0].lower()+posix[2:]
            model='''set -eu
umask 077
d=FIXTURE
farm=$d/90.conf
delta=$d/96.conf
previous_delta=$d/95.conf
absent(){ [ ! -e "$1" ] && [ ! -L "$1" ]; }
regular(){ [ -f "$1" ] && [ ! -L "$1" ]; }
private(){ [ -d "$1" ]; }
delta_package(){ return 0; }
base_ready(){ [ CASE != wrong-base ] && [ ! -f "$delta" ]; }
gui_same(){ [ ! -f "$d/changed" ]; }
pid(){ if [ "$1" = victory-gui ];then if [ -f "$d/changed" ];then printf 789;else printf 234;fi;else printf 456;fi; }
stop_bus(){ printf '%s\n' stop-bus >> "$d/calls"; }
systemctl(){ printf '%s\n' "$*" >> "$d/calls"; }
wait_ready(){ "$1"; }
new_ready(){ [ CASE != new-bus-fails ]; }
old_ready(){ return 0; }
value(){ if [ -f "$d/foreign" ];then printf '%s %s %s %s' "$farm" "$previous_delta" "$delta" "$d/99.conf";elif [ -f "$delta" ];then printf '%s %s %s' "$farm" "$previous_delta" "$delta";else printf '%s %s' "$farm" "$previous_delta";fi; }
'''.replace('FIXTURE',posix).replace('CASE',case)
            (folder/'common.sh').write_text(model,encoding='utf-8',newline='\n')
            (folder/'bus-local-check').write_text('#!/bin/sh\nexit '+('1' if case=='local-check-fails' else '0')+'\n',encoding='ascii',newline='\n')
            for name in ('apply.sh','restore.sh','run.sh'):
                source=(HERE/name).read_text(encoding='utf-8').replace('/tmp/hbl-af-bus-r5',posix)
                (folder/name).write_text(source,encoding='utf-8',newline='\n')
            def call(action):return subprocess.run([str(SHELL),str(folder/'run.sh'),action],capture_output=True,text=True,encoding='utf-8',timeout=20)
            result=call('apply')
            if case in ('local-check-fails','wrong-base'):
                assert result.returncode==({'local-check-fails':62,'wrong-base':61}[case]),(case,result.returncode,result.stderr)
                assert not (folder/'calls').exists() and not (folder/'touched').exists()
                checks.append('preflight rejects before service changes: '+case)
            elif case=='new-bus-fails':
                assert result.returncode==66,(result.returncode,result.stdout,result.stderr)
                assert not (folder/'96.conf').exists() and (folder/'failure-restored').exists()
                checks.append('new bus failure restores only old bus')
            else:
                assert result.returncode==0,(case,result.returncode,result.stdout,result.stderr)
                assert (folder/'96.conf').read_bytes()==(HERE/'96-hbl-af-bus-r5.conf').read_bytes()
                assert call('apply').returncode==61
                if case in ('foreign-dropin','gui-changed'):
                    (folder/('foreign' if case=='foreign-dropin' else 'changed')).write_text('1')
                    count=len((folder/'calls').read_text().splitlines())
                    result=call('restore');assert result.returncode==67
                    assert (folder/'96.conf').exists() and len((folder/'calls').read_text().splitlines())==count
                    checks.append('foreign state preserved: '+case)
                else:
                    result=call('restore');assert result.returncode==0,(result.returncode,result.stdout,result.stderr)
                    assert not (folder/'96.conf').exists();checks.append('apply/explicit restore/duplicate guard')
            assert base.read_text()=='original AF bus\n'
            if (folder/'calls').exists():
                calls=(folder/'calls').read_text().splitlines()
                assert all(c in ('stop-bus','daemon-reload','start msg2dbus-farm') for c in calls)
    report={'passed':True,'checks':checks,'hardwareRequests':0,'healthAndPackageChecksMocked':True,'targetShellTested':False,
        'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [HERE/n for n in ('common.sh','apply.sh','restore.sh','run.sh')]}}
    (HERE/'shell-tests.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report))
if __name__=='__main__':run()
