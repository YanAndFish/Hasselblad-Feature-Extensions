"""真实 sh 中验证临时只读通路事务和恢复分支；服务、内存读回均为替身。"""
from pathlib import Path
import hashlib,json,os,subprocess,time
HERE=Path(__file__).resolve().parent;WORK=HERE.parent;ROOT=HERE.parents[4]
OUT=HERE/'probe-output'/str(time.time_ns());OUT.mkdir(parents=True)
SHELL=Path('C:/Program Files/Git/bin/sh.exe')
source=(WORK/'probe.sh').read_text(encoding='utf-8')
subprocess.run([str(SHELL),'-n',str(WORK/'probe.sh')],check=True)
def posix(p):return '/'+p.drive[0].lower()+p.as_posix()[2:]
def run(case):
    d=OUT/case;d.mkdir();stage=d/'stage';runtime=d/'runtime';flash=d/'flash';b=d/'bin';units=d/'units'
    for p in (stage,runtime,flash,b,units):p.mkdir()
    env=dict(os.environ,CASE=case,TEST_ROOT=posix(d))
    for n,body in {'formal-system-check':'printf "system=2 suc=0 farm=0 pwr=0 ui-power=0 hold=0"',
                   'formal-sync-hook-check':'[ "$CASE" != bad-selfcheck ] || exit 2;printf "sync-hook-selftest: own=10 forwarded=10 status=1 hardware=0\\n"'}.items():
        (flash/n).write_text('#!/bin/sh\n'+body+'\n')
    (d/'pid').write_text('100');(d/'next').write_text('101')
    (flash/'formal-enable.ready').write_text('ready');(flash/'formal-enable.confirmed').write_text('ready')
    (stage/'manifest.sha256').write_text('fixture')
    (b/'sha256sum').write_text('''#!/bin/sh
if [ "$1" = -c ];then exit 0;fi
case "$1" in
 */manifest.sha256) hash=f53e6a360c2eb68c1fce98ba52412b0479704166fa70c191e3662a7f154043b9;;
 *) hash=c960ea0e8685073adf3fc593e3fbe4c3e58a44dcbf29cb42ca8bb68733fc53e0;;
esac
[ "$CASE" != bad-baseline ] || hash=bad
printf '%s  %s\\n' "$hash" "$1"
''')
    (b/'sleep').write_text('''#!/bin/sh
set -eu
d=$TEST_ROOT/flash
if [ -f "$d/formal-stop.request" ] && [ "$CASE" != stop-unconfirmed ];then
 printf 'formal-worker-stopped-default-off\\nmaster=0 radio-held=0 radio-busy=0 same-process=1 pid=%s' "$(cat "$TEST_ROOT/pid")" >"$d/formal-worker.status"
fi
if [ -f "$d/formal-enable.ready" ];then printf ready >"$d/formal-enable.confirmed";fi
''')
    (b/'systemctl').write_text('''#!/bin/sh
set -eu
r=$TEST_ROOT
printf '%s\\n' "$*" >>"$r/events"
case "$1" in
 is-active|daemon-reload) exit 0;;
 show) if [ "$4" = victory-gui ];then echo MainPID=50;else printf 'MainPID=%s\\n' "$(cat "$r/pid")";fi;;
 stop) [ "$CASE" != restore-stop-failed ] || [ ! -f "$r/probed" ] || exit 2;echo 0 >"$r/pid";;
 start)
   if [ -f "$r/units/probe.conf" ];then
     touch "$r/probed"
     [ "$CASE" != probe-start-failed ] || exit 2
   fi
   n=$(cat "$r/next");echo "$n" >"$r/pid";echo $((n+1)) >"$r/next"
   printf 'formal-worker-ready-default-off\\nmaster=0 radio-held=0 radio-busy=0 same-process=1 pid=%s' "$n" >"$r/flash/formal-worker.status"
   if [ -f "$r/units/probe.conf" ];then
     if [ "$CASE" = probe-failed ];then state=readonly-probe-failed;else state=readonly-probe-ready;fi
     printf 'stage=%s requests=3 writes=0 pid=%s' "$state" "$n" >"$r/runtime/boot-transport.status"
   fi;;
 *) exit 3;;
esac
''')
    (flash/'formal-worker.status').write_text('waiting')
    script=source.replace('/tmp/hbl-boot-probe-r1',posix(stage)).replace('/tmp/hbl-wireless-flash',posix(flash)).replace('/run/hbl-four-module',posix(runtime)).replace('/run/systemd/system/msg2dbus-farm.service.d/90-hbl-boot-probe.conf',posix(units/'probe.conf'))
    script=script.replace('LD_PRELOAD=', 'MODEL_PRELOAD=')
    (stage/'probe.sh').write_text(script,encoding='utf-8',newline='\n')
    env['PATH']=str(b)+os.pathsep+str(SHELL.parents[1]/'usr/bin')+os.pathsep+env['PATH']
    # 生产脚本不提供测试绕过参数；只在本次私有副本中重定向固定目录。
    done=subprocess.run([str(SHELL),'-c','PATH="$1:$PATH";export PATH;exec sh "$2"','check',posix(b),posix(stage/'probe.sh')],env=env,capture_output=True,text=True,timeout=30)
    events=(d/'events').read_text() if (d/'events').exists() else ''
    state=(stage/'result').read_text() if (stage/'result').exists() else ''
    if case=='normal':assert done.returncode==0 and state=='readonly-probe-ready-original-restored',(done.returncode,done.stdout,done.stderr,state)
    elif case in ('bad-baseline','bad-selfcheck'):
        assert done.returncode!=0 and 'stop msg2dbus-farm' not in events
    elif case in ('probe-failed','probe-start-failed'):
        assert done.returncode!=0 and state=='readonly-probe-failed-restored' and not (units/'probe.conf').exists(),(case,done.stderr,state)
        assert (stage/'restored').exists()
    elif case=='stop-unconfirmed':assert done.returncode==81 and 'stop msg2dbus-farm' not in events
    elif case=='restore-stop-failed':assert done.returncode==81 and state=='restoration-needs-review' and events.count('stop msg2dbus-farm\n')==2
    return {'case':case,'exit':done.returncode,'result':state}
results=[run(c) for c in ('normal','bad-baseline','bad-selfcheck','probe-failed','probe-start-failed','stop-unconfirmed','restore-stop-failed')]
proof={'passed':True,'hardwareRequests':0,'scriptSha256':hashlib.sha256((WORK/'probe.sh').read_bytes()).hexdigest(),'cases':results}
(HERE/'probe-transaction-validation.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof))
