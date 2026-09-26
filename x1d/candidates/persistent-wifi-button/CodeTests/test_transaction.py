"""实际临时安装/撤回脚本的隔离事务测试；服务、UID/stat、健康为替身。"""
from pathlib import Path
import hashlib,json,os,subprocess,time
HERE=Path(__file__).resolve().parents[1]
SHELL='C:/Program Files/Git/bin/sh.exe'
def write(p,t):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(t,encoding='utf-8',newline='\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def mp(p):return '/'+p.drive[0].lower()+p.as_posix()[2:]
def main():
    out=HERE/'build/transaction-tests'/str(time.time_ns());out.mkdir(parents=True)
    checks=[]
    for mode in ('success','activation-failure','foreign-dropin','corrupt-payload','foreign-restore','standby'):
        case=out/mode;case.mkdir();payload=case/'payload';payload.mkdir();bin=case/'bin';bin.mkdir()
        fs=case/'fs';run=fs/'run';etc=fs/'etc';lib=fs/'lib';proc=fs/'proc';runtime=run/'hbl-wifi-probe'
        def adapt(text):
            for name,path in (('/run/',run),('/etc/',etc),('/lib/systemd/',lib/'systemd'),('/proc/',proc)):
                text=text.replace(name,mp(path)+'/')
            text=text.replace('proc=/proc','proc='+mp(proc))
            return text
        for name in ('run.sh','common.sh','launch.sh','monitor.sh','gui.conf'):write(payload/name,adapt((HERE/name).read_text(encoding='utf-8')))
        write(payload/'health','#!/bin/sh\np=$(cat "$CASE/gui.pid")\nprintf "ui-health-ready pid=%s system=2 power=0\\n" "$p"\n')
        if mode=='standby':write(payload/'health','#!/bin/sh\np=$(cat "$CASE/gui.pid")\nprintf "ui-health-ready pid=%s system=4 power=1\\n" "$p"\n')
        write(payload/'button.rcc','fixture-rcc');write(payload/'libhbl-wifi-probe.so','fixture-native')
        write(payload/'baseline.sha256',sha(payload/'button.rcc')+'  '+(payload/'button.rcc').as_posix()+'\n')
        files=list(payload.iterdir());assert len(files)==9
        write(payload/'manifest.sha256',''.join(sha(p)+'  '+p.name+'\n' for p in files))
        write(case/'gui.pid','101\n');write(case/'gui.active','1\n')
        for p in (101,102,201):write(proc/str(p)/'environ','');write(proc/str(p)/'maps',mp(runtime/'libhbl-wifi-probe.so')+'\n' if p==102 else '')
        (run/'systemd/system').mkdir(parents=True)
        write(bin/'id','#!/bin/sh\nprintf "0\\n"\n')
        write(bin/'stat','#!/bin/sh\ncase "$2" in %u:%h) printf "0:1\\n";; %u:%a) printf "0:700\\n";; *) exit 1;;esac\n')
        write(bin/'sleep','#!/bin/sh\nexit 0\n')
        write(bin/'mkdir','#!/bin/sh\nif [ "${1:-}" = -m ];then shift 2;fi\nexec /usr/bin/mkdir "$@"\n')
        stub='''#!/bin/sh
set -eu
gui="$CASE/fs/run/systemd/system/victory-gui.service.d/91-hbl-wifi-probe.conf"
runtime="$CASE/fs/run/hbl-wifi-probe"
case "$1" in
show)
  field=$3;role=$4
  case "$field" in
    MainPID) if [ "$role" = victory-gui ];then cat "$CASE/gui.pid" | sed 's/^/MainPID=/';else printf 'MainPID=201\n';fi;;
    FragmentPath) printf 'FragmentPath=%s/fs/lib/systemd/system/%s.service\n' "$CASE" "$role";;
    DropInPaths) if [ "$role" = victory-gui ] && [ -f "$gui" ];then printf 'DropInPaths=%s\n' "$gui";else printf 'DropInPaths=\n';fi;;
    Environment) printf 'Environment=\n';;
  esac;;
is-active)
  if [ "${3:-}" = victory-gui ] && [ "$(cat "$CASE/gui.active")" = 0 ];then exit 3;fi;;
stop) printf '0\n' > "$CASE/gui.active";printf 'stop\n' >> "$CASE/events";;
start|restart)
  printf '1\n' > "$CASE/gui.active";printf '%s\n' "$1" >> "$CASE/events"
  if [ -f "$gui" ];then
    printf '102\n' > "$CASE/gui.pid";mkdir -p "$runtime";cp "$CASE/payload/health" "$runtime/health"
    if [ "$MODE" = activation-failure ];then printf 'failed\n' > "$runtime/fallback.reason"
    else printf 'probe-ready pid=102\n' > "$runtime/ui.status";printf 'probe-verified pid=102\n' > "$runtime/verified";fi
  else printf '101\n' > "$CASE/gui.pid";fi;;
daemon-reload) :;;
*) exit 1;;
esac
'''
        write(bin/'systemctl',stub)
        env=dict(os.environ,CASE=mp(case),MODE=mode,TEST_BIN=mp(bin))
        def invoke(action):return subprocess.run([SHELL,'-c','export PATH="$TEST_BIN:$PATH";exec sh "$@"','harness',(payload/'run.sh').as_posix(),action],env=env,capture_output=True,text=True,timeout=15)
        gui=run/'systemd/system/victory-gui.service.d/91-hbl-wifi-probe.conf'
        if mode=='foreign-dropin':write(etc/'systemd/system/victory-gui.service.d/other.conf','foreign')
        if mode=='corrupt-payload':write(payload/'button.rcc','corrupt')
        result=invoke('temporary')
        if mode in ('foreign-dropin','corrupt-payload'):
            assert result.returncode!=0 and not (case/'events').exists() and not runtime.exists(),(mode,result.stdout,result.stderr)
        elif mode=='activation-failure':
            assert result.returncode!=0 and not gui.exists() and (case/'gui.pid').read_text().strip()=='101',(mode,result.stdout,result.stderr)
            assert 'factory-restored' in (payload/'recovery.log').read_text(),mode
        else:
            assert result.returncode==0 and result.stdout.strip()=='probe-temporary-ready',(mode,result.stdout,result.stderr)
            if mode=='foreign-restore':
                write(gui,'foreign');before=(case/'events').read_text();result=invoke('restore')
                assert result.returncode!=0 and gui.read_text()=='foreign' and (case/'events').read_text()==before
            else:
                result=invoke('restore');assert result.returncode==0 and not gui.exists() and (case/'gui.pid').read_text().strip()=='101',(result.stdout,result.stderr)
                result=invoke('archive-runtime');assert result.returncode==0 and not runtime.exists(),(result.stdout,result.stderr)
        checks.append(mode)
    write(HERE/'build/transaction-validation.json',json.dumps({'passed':True,'checks':checks,'sources':{n:sha(HERE/n) for n in ('run.sh','common.sh')},'hardwareRequests':0,'mocked':['systemctl and service side effects','UID/stat metadata and mkdir mode','health result'],'actual':['run.sh','common.sh','file copies and exact-match restoration','hash validation']},indent=2)+'\n')
    print(json.dumps({'passed':True,'checks':len(checks)}))
if __name__=='__main__':main()
