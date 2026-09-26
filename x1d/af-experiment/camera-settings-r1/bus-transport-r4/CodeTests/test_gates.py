"""执行当前 common.sh 的 r5 绑定、GUI 身份和新旧 bus 就绪谓词。"""
import hashlib,json,os,subprocess,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[3]
SHELL=Path('C:/Program Files/Git/bin/bash.exe')
def write(p,s):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s,encoding='utf-8',newline='\n')
def run():
    output=HERE/'test-build/gates';output.mkdir(parents=True,exist_ok=True);checks=[]
    with tempfile.TemporaryDirectory(dir=output) as temp:
        t=Path(temp);root=t.as_posix();root='/'+root[0].lower()+root[2:]
        d=t/'delta';r=t/'base';a=t/'af';s=r/'install-state'
        gui=t/'gui.conf';farm=t/'farm.conf'
        base='''set -eu
r=ROOT/base
s=$r/install-state
a=ROOT/af
gui=ROOT/gui.conf
farm=ROOT/farm.conf
private(){ [ -d "$1" ] && [ ! -L "$1" ]; }
regular(){ [ -f "$1" ] && [ ! -L "$1" ]; }
absent(){ [ ! -e "$1" ] && [ ! -L "$1" ]; }
verify_package(){ return 0; }
owned(){ return 0; }
owned_dropins(){ return 0; }
value(){ cat "ROOT/$1.$2"; }
pid(){ value "$1" MainPID; }
systemctl(){ [ "$1" = is-active ]; }
stat(){ printf 0:600; }
[(){ if test "$#" = 3 && test "$1" = -S;then test -f "$2";else builtin [ "$@";fi; }
'''.replace('ROOT',root)
        write(r/'common.sh',base)
        for name in ('af-installed.sha256','hold.release','release.done'):write(s/name,'1')
        write(s/'package.sha256','bd347c5f9919eaba4710fac9e62d7212bf6fb15f4bd65783a7c3f426e566ca6e\n')
        write(r/'system-check','#!/bin/sh\nexit 0\n')
        for name in ('common.sh','apply.sh','restore.sh','run.sh','95-hbl-af-bus-r4.conf'):
            text=(HERE/name).read_text(encoding='utf-8').replace('/tmp/hbl-x1d-combined',root+'/base').replace('/tmp/hbl-af-bus-r4',root+'/delta')
            text=text.replace('/run/systemd/system/msg2dbus-farm.service.d/95-hbl-af-bus-r4.conf',root+'/delta.conf').replace('/proc/',root+'/proc/')
            write(d/name,text)
        for name in ('libhbl-af-bus.so','bus-local-check'):write(d/name,'fixture')
        write(d/'manifest.sha256',''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in sorted(d.iterdir())))
        write(t/'victory-gui.MainPID','100\n');write(t/'msg2dbus-farm.MainPID','200\n')
        write(t/'victory-gui.DropInPaths',root+'/gui.conf\n');write(t/'msg2dbus-farm.DropInPaths',root+'/farm.conf\n')
        write(t/'proc/100/maps',root+'/base/libhbl-af-only.so\n'+root+'/base/af/libhbl-af-ui.so\n')
        write(t/'proc/200/maps',root+'/base/af/libhbl-af-bus.so\n')
        write(a/'ui-r4.status','stage=visible pid=100 bound=1 shown=1\n')
        write(a/'backend-r3.status','stage=ready error=0 meta=1 uart=1\n');write(a/'backend-r3-flow.status','stage=expired\n')
        write(a/'ui.sock','socket fixture');write(a/'backend.sock','socket fixture')
        def expect(predicate,ok):
            result=subprocess.run([str(SHELL),'-c','. "$1";'+predicate,'gate',str(d/'common.sh')],capture_output=True,text=True,timeout=10)
            assert (result.returncode==0)==ok,(predicate,result.returncode,result.stdout,result.stderr)
        expect('base_ready',True);checks.append('actual r5 baseline predicates')
        write(s/'package.sha256','0'*64+'\n');expect('delta_package',False)
        write(s/'package.sha256','bd347c5f9919eaba4710fac9e62d7212bf6fb15f4bd65783a7c3f426e566ca6e\n');checks.append('wrong r5 manifest rejected')
        write(t/'victory-gui.DropInPaths',root+'/gui.conf '+root+'/foreign.conf\n');expect('ui_ready',False)
        write(t/'victory-gui.DropInPaths',root+'/gui.conf\n');checks.append('foreign GUI drop-in rejected')
        write(d/'gui.pid','100\n');write(d/'old-bus.pid','200\n')
        write(t/'msg2dbus-farm.MainPID','300\n');write(t/'msg2dbus-farm.DropInPaths',root+'/farm.conf '+root+'/delta.conf\n')
        write(t/'proc/300/maps',root+'/delta/libhbl-af-bus.so\n')
        write(a/'backend-r4.status','stage=ready error=0 meta=1 uart=1\n')
        write(a/'backend-r4-flow.status','stage=ready error=0 pending=0 events=0 \n')
        write(a/'backend-r4-transport.status','stage=observe calls=0 private=0 \n')
        expect('new_ready',True);checks.append('new bus requires transport status and exact GUI identity')
        write(a/'backend-r4-transport.status','incomplete\n');expect('new_ready',False)
        write(a/'backend-r4-transport.status','stage=observe calls=0 private=0 \n');checks.append('incomplete transport status rejected')
        write(d/'gui.pid','101\n');expect('new_ready',False);checks.append('changed GUI owner rejected')
    report={'passed':True,'checks':checks,'hardwareRequests':0,'inheritedPackageOwnershipAndOSMocked':True,
        'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (HERE/'common.sh',Path(__file__))}}
    (HERE/'gates-tests.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report))
if __name__=='__main__':run()
