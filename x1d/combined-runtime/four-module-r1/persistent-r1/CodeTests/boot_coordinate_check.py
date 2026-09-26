"""真实 sh 的启动编排检查；所有设备状态/装载结果为替身。"""
from pathlib import Path
import hashlib,json,os,subprocess,time
HERE=Path(__file__).resolve().parent;WORK=HERE.parent
SHELL=Path('C:/Program Files/Git/bin/sh.exe');OUT=HERE/'bc'/str(time.time_ns())
def posix(p):return '/'+p.drive[0].lower()+p.as_posix()[2:]
def put(p,s):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s,encoding='utf-8',newline='\n')
def run(case):
    root=OUT/case
    for n in ('bin','u','d/formal-state','data','package'): (root/n).mkdir(parents=True,exist_ok=True)
    common=(WORK/'boot-common.sh').read_text(encoding='utf-8').replace('/opt/hbl-four-module-v1',posix(root/'package')).replace('/tmp/hbl-wireless-flash',posix(root/'d')).replace('/run/hbl-four-module',posix(root/'u'))
    put(root/'package/boot-common.sh',common)
    script=(WORK/'boot-coordinate.sh').read_text(encoding='utf-8').replace('/opt/hbl-four-module-v1',posix(root/'package')).replace('/media/data/hbl-four-module',posix(root/'data'))
    put(root/'coordinate.sh',script)
    put(root/'u/gui.pid','123')
    put(root/'u/ui.status','ui-resident-ready-resources6-components5-pools3-pages23-rows-diag1 pid=123' if case!='gui-failed' else 'not-ready')
    put(root/'u/replay.status','replay-page-ready-resources7-components7-pages2 pid=123')
    put(root/'d/formal-runtime.status','formal-ui-loaded-default-off')
    put(root/'d/formal-worker.status','formal-worker-ready-default-off\nmaster=0 radio-held=0 radio-busy=0 same-process=1 pid=456')
    put(root/'bin/stat','#!/bin/sh\nprintf 0:700\n')
    put(root/'bin/systemctl','#!/bin/sh\ncase "$4" in victory-gui)echo MainPID=123;;msg2dbus-farm)echo MainPID=456;;*)exit 2;;esac\n')
    put(root/'d/formal-system-check','#!/bin/sh\nexit 0\n')
    put(root/'d/formal-netlink-probe','#!/bin/sh\nexit 0\n')
    put(root/'d/formal-prepare-radio.sh','#!/bin/sh\necho prepare-radio >>"$TEST_ROOT/events"\n[ "$CASE" != radio-failed ]\n')
    if case=='prior-incomplete':put(root/'data/boot-incomplete','pending')
    put(root/'bin/sleep','''#!/bin/sh
r=$TEST_ROOT
if [ -f "$r/u/load.request" ] && [ ! -f "$r/u/boot-loader.status" ];then
 if [ "$CASE" = native-failed ];then echo 'state=failed phase=cache-probe inFlight=1' >"$r/u/boot-loader.status";
 else echo 'state=ready phase=modules-ready requests=18219 writes=2415 inFlight=0' >"$r/u/boot-loader.status";fi
fi
if [ -f "$r/d/formal-enable.ready" ];then printf ready >"$r/d/formal-enable.confirmed";fi
if [ -f "$r/d/formal-state/hold.release" ];then
 if [ "$CASE" = restore-failed ];then state=failed;else state=ready;fi
 printf 'HPR1 123 %s\n' "$state" >"$r/u/settings-restore.status"
fi
''')
    env=dict(os.environ,TEST_ROOT=posix(root),CASE=case)
    put(root/'d/boot-wait','''#!/bin/sh
sleep 0
case "$1" in
--loader)
 [ -f "$TEST_ROOT/u/load.request" ] || exit 80
 [ "$CASE" != native-failed ] || exit 83
 [ "$CASE" != native-timeout ] || exit 84;;
--controls)
 [ -f "$TEST_ROOT/d/formal-enable.ready" ] || exit 80
 [ "$CASE" != controls-timeout ] || exit 84;;
--settings)
 [ "$2" = 123 ] && [ -f "$TEST_ROOT/d/formal-state/hold.release" ] || exit 80
 [ "$CASE" != restore-failed ] || exit 83
 [ "$CASE" != restore-timeout ] || exit 84;;
*)exit 80;;esac
exit 0
''')
    cmd=[str(SHELL),'-c','PATH="$1:$PATH";export PATH;exec sh "$2"','check',posix(root/'bin'),posix(root/'coordinate.sh')]
    done=subprocess.run(cmd,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30)
    if case in ('normal','prior-incomplete'):
        assert done.returncode==0,(done.stdout,done.stderr)
        assert (root/'u/boot.ready').read_text()=='ready\n' and not (root/'u/boot-failed').exists()
        second=subprocess.run(cmd,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30)
        assert second.returncode!=0 and not (root/'u/boot-failed').exists()
        assert (root/'events').read_text().splitlines()==['prepare-radio']
    else:
        assert done.returncode!=0,(case,done.stdout,done.stderr)
        assert (root/'u/boot-failed').exists() and not (root/'u/boot.ready').exists()
        if case in ('gui-failed','radio-failed'):assert not (root/'u/load.request').exists()
        if case=='native-failed':assert not (root/'d/formal-enable.ready').exists() and not (root/'d/formal-state/hold.release').exists()
    return {'case':case,'exit':done.returncode}
results=[run(c) for c in ('normal','gui-failed','prior-incomplete','radio-failed','native-failed','restore-failed')]
proof={'passed':True,'hardwareRequests':0,'scripts':{n:hashlib.sha256((WORK/n).read_bytes()).hexdigest() for n in ('boot-common.sh','boot-coordinate.sh')},'cases':results}
(HERE/'boot-coordinate-validation.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
print(json.dumps(proof))
