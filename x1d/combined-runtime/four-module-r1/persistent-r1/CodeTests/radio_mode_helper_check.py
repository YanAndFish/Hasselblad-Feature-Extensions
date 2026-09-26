"""执行真实交接脚本；设备工具全由状态化替身代替，不接触相机。"""
from pathlib import Path
import os, subprocess, sys, json, time, hashlib
sys.dont_write_bytecode=True
P=Path(__file__).resolve().parents[1]
O=P/'build/radio-three-state/helper-tests'/str(time.time_ns());O.mkdir(parents=True)
SH='C:/Program Files/Git/bin/sh.exe'
def posix(p):return '/'+p.drive[0].lower()+p.as_posix()[2:]
def put(p,s):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s,encoding='utf-8',newline='\n')

def setup(name,power='false'):
    r=O/name
    for n in ['opt/hbl-af-only-v1','run/hbl-four-module','bin','sys/module/firmware_class/parameters','sys/module/brcmfmac/parameters']:(r/n).mkdir(parents=True,exist_ok=True)
    put(r/'sys/module/firmware_class/parameters/path','')
    put(r/'sys/module/brcmfmac/parameters/firmware_path','')
    put(r/'power',power);put(r/'network','active' if power=='true' else 'inactive');put(r/'ap','active' if power=='true' else 'inactive')
    put(r/'band-preference','5G');put(r/'driver','factory')
    put(r/'radio-up','1' if power=='true' else '0')
    put(r/'opt/hbl-af-only-v1/radio.bin','candidate')
    script=(P/'radio-mode.sh').read_text(encoding='utf-8')
    for path in ['/opt/','/run/','/sys/']:script=script.replace(path,posix(r)+path)
    script=script.replace('/usr/bin/wl',posix(r/'bin/wl'))
    script=script.replace('86d10d4131bcaa90dd0781545cec918ab10e56fd3d808c2dc85a019ee9edba98',hashlib.sha256(b'candidate').hexdigest())
    put(r/'switch.sh',script)
    put(r/'bin/id','#!/bin/sh\necho 0\n');put(r/'bin/stat','#!/bin/sh\necho 0:700\n')
    put(r/'bin/wl','''#!/bin/sh
echo "wl $*" >>"$R/events"
case "$1" in ver)exit 0;;up)[ "$FAIL" != up ] || exit 1;echo 1 >"$R/radio-up";;down)echo 0 >"$R/radio-up";;phyreg)case "$2" in 0)echo 0x5854;;17)echo 0x0000;;esac;;esac
''')
    put(r/'bin/sleep','#!/bin/sh\nexit 0\n')
    put(r/'bin/rmmod','#!/bin/sh\necho rmmod >>"$R/events"\n[ "$FAIL" != rmmod ]\n')
    put(r/'bin/modprobe','''#!/bin/sh
echo "modprobe $*" >>"$R/events"
[ "$FAIL" != modprobe ] || exit 1
echo 0 >"$R/radio-up"
if [ "$2" = firmware_path=test ];then echo test >"$R/sys/module/brcmfmac/parameters/firmware_path";else : >"$R/sys/module/brcmfmac/parameters/firmware_path";fi
''')
    put(r/'bin/iw','#!/bin/sh\nif [ "$(cat "$R/ap")" = active ];then echo "type AP";else echo "type managed";fi\n')
    put(r/'bin/systemctl','''#!/bin/sh
echo "systemctl $*" >>"$R/events"
case "$1" in
stop)echo inactive >"$R/network";echo inactive >"$R/ap";;
start)echo active >"$R/network";;
is-active)[ "$(cat "$R/network")" = active ] && [ "$(cat "$R/ap")" = active ];;
*)exit 1;;esac
''')
    put(r/'bin/dbus-send','''#!/bin/sh
case "$*" in
*Properties.Get*)echo "variant boolean $(cat "$R/power")";;
*variant:boolean:false*)echo false >"$R/power";echo inactive >"$R/ap";echo power-false >>"$R/events";;
*variant:boolean:true*)echo true >"$R/power";echo power-true >>"$R/events";if [ "$FAIL" != ap ] && [ "$(cat "$R/radio-up")" = 1 ];then echo active >"$R/ap";fi;;
*)exit 1;;esac
''')
    return r

def run(r,mode,fail=''):
    x=subprocess.run([SH,'-c','PATH="$1:$PATH";export PATH;exec sh "$2" "$3"','check',posix(r/'bin'),posix(r/'switch.sh'),str(mode)],env=dict(os.environ,R=posix(r),FAIL=fail),capture_output=True,text=True,timeout=10)
    assert (r/'band-preference').read_text()=='5G'
    assert not (r/'run/hbl-four-module/radio-mode/lock').exists()
    return x

cases=[]
for initial in ['false','true']:
    r=setup(initial,initial);x=run(r,'boot');assert x.returncode==0,(x.stdout,x.stderr)
    assert x.stdout.strip()=='radio-mode-ready:'+('1' if initial=='true' else '0')
    e=(r/'events').read_text();assert 'power-' not in e and 'rmmod' not in e
    for mode in [2,1,0,1,2,0,2,1]:
        x=run(r,mode);assert x.returncode==0 and x.stdout.strip()==f'radio-mode-ready:{mode}',(mode,x.stdout,x.stderr)
    cases.append(initial+'-all-transitions')
for failure in ['rmmod','modprobe','ap','up']:
    r=setup(failure);assert run(r,'boot').returncode==0
    x=run(r,1 if failure in ['ap','up'] else 2,failure)
    assert x.returncode!=0 and 'radio-mode-ready:' not in x.stdout,(failure,x.stdout)
    cases.append(failure+'-no-false-success')
proof=dict(passed=True,cases=cases,hardwareRequests=0,scriptSha256=hashlib.sha256((P/'radio-mode.sh').read_bytes()).hexdigest())
(P/'build/radio-three-state/helper-validation.json').write_text(json.dumps(proof,indent=2))
print(json.dumps(proof))
