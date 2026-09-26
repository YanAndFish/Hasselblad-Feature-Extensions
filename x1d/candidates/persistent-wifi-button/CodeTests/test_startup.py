"""执行实际 POSIX 启动器/有限监护脚本；GUI 与 systemctl 为本地替身。"""
from pathlib import Path
import hashlib,json,os,subprocess,time
HERE=Path(__file__).resolve().parents[1]
SHELL='C:/Program Files/Git/bin/sh.exe'
def write(p,text):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8',newline='\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    out=HERE/'build/startup-tests'/str(time.time_ns());out.mkdir(parents=True)
    checks=[]
    def run(script,args,env):
        r=subprocess.run([SHELL,script.as_posix()]+args,env=env,capture_output=True,text=True,timeout=10)
        return r
    for mode in ('first-and-restart','bad-manifest','bad-baseline'):
        case=out/mode;case.mkdir();runtime=case/'runtime';payload=case/'payload';payload.mkdir();bin=case/'bin';bin.mkdir()
        gui=case/'gui.sh';write(gui,'#!/bin/sh\nprintf "GUI:%s\\n" "${HBL_WIFI_PROBE:-factory}" >> "$CASE/events"\n')
        write(bin/'systemctl','#!/bin/sh\nprintf "MainPID=99999999\\n"\n')
        write(bin/'sleep','#!/bin/sh\nexit 0\n')
        launch=(HERE/'launch.sh').read_text(encoding='utf-8').replace('/run/hbl-wifi-probe',runtime.as_posix()).replace('/usr/bin/victory-gui',gui.as_posix()).replace('LD_PRELOAD=','MOCK_PRELOAD=')
        write(payload/'launch.sh',launch)
        write(payload/'monitor.sh',(HERE/'monitor.sh').read_text().replace('/run/hbl-wifi-probe',runtime.as_posix()))
        write(payload/'health','#!/bin/sh\nexit 1\n')
        write(payload/'button.rcc','fixture-rcc')
        write(payload/'libhbl-wifi-probe.so','fixture-native-library-not-executed')
        write(payload/'baseline.sha256',sha(gui)+'  '+gui.as_posix()+'\n')
        members=list(payload.iterdir());write(payload/'manifest.sha256',''.join(sha(p)+'  '+p.name+'\n' for p in members))
        if mode=='bad-manifest':write(payload/'button.rcc','changed')
        if mode=='bad-baseline':write(gui,gui.read_text()+'# changed baseline\n')
        env=dict(os.environ,CASE=case.as_posix(),PATH=bin.as_posix()+os.pathsep+os.environ['PATH'])
        r=run(payload/'launch.sh',[],env);assert r.returncode==0,(mode,r.stderr)
        events=(case/'events').read_text().splitlines()
        assert events==(['GUI:1'] if mode=='first-and-restart' else ['GUI:factory']),events
        checks.append(mode)
        if mode=='first-and-restart':
            r=run(payload/'launch.sh',[],env);assert r.returncode==0
            assert (case/'events').read_text().splitlines()==['GUI:1','GUI:factory']
            checks.append('same-boot second invocation bypasses preload')
    for mode in ('healthy','component-failed','timeout','unhealthy','changed-pid','transient-health','standby','mixed-state'):
        case=out/mode;case.mkdir();runtime=case/'runtime';runtime.mkdir();bin=case/'bin';bin.mkdir()
        text=(HERE/'monitor.sh').read_text().replace('/run/hbl-wifi-probe',runtime.as_posix()).replace('"$n" -lt 25','"$n" -lt 2')
        write(case/'monitor.sh',text)
        current='124' if mode=='changed-pid' else '123'
        write(bin/'systemctl','#!/bin/sh\ncase "$1" in show) printf "MainPID='+current+'\\n";; *) printf "%s\\n" "$*" >> "$CASE/restarts";; esac\n')
        write(bin/'sleep','#!/bin/sh\nexit 0\n')
        write(runtime/'health','#!/bin/sh\n'+('exit 1\n' if mode=='unhealthy' else 'printf "ui-health-ready pid=123 system=2 power=0\\n"\n'))
        if mode=='transient-health':write(runtime/'health','#!/bin/sh\nif [ ! -e "$CASE/health-first" ];then echo 1 > "$CASE/health-first";echo "health-failed sample=0 system=-1" >&2;exit 65;fi\nprintf "ui-health-ready pid=123 system=2 power=0\\n"\n')
        if mode=='standby':write(runtime/'health','#!/bin/sh\nprintf "ui-health-ready pid=123 system=4 power=1\\n"\n')
        if mode=='mixed-state':write(runtime/'health','#!/bin/sh\nprintf "ui-health-ready pid=123 system=4 power=0\\n"\n')
        if mode!='timeout':write(runtime/'ui.status','probe-component-failed pid=123\n' if mode=='component-failed' else 'probe-ready pid=123\n')
        env=dict(os.environ,CASE=case.as_posix(),PATH=bin.as_posix()+os.pathsep+os.environ['PATH'])
        r=run(case/'monitor.sh',['123'],env);assert r.returncode==0,(mode,r.stderr)
        assert (runtime/'verified').exists()==(mode in ('healthy','transient-health','standby')),mode
        restart=case/'restarts'
        if mode in ('component-failed','timeout','unhealthy','mixed-state'):
            assert restart.read_text().splitlines()==['--no-block restart victory-gui'],mode
        else:assert not restart.exists(),mode
        checks.append(mode)
    report={'passed':True,'checks':checks,'sources':{n:sha(HERE/n) for n in ('launch.sh','monitor.sh')},'hardwareRequests':0,'nativeArmExecuted':False,'testScope':'actual launch.sh/monitor.sh with local GUI, health and systemctl fixtures; Windows harness renames LD_PRELOAD to MOCK_PRELOAD; no native loading claim'}
    write(HERE/'build/startup-validation.json',json.dumps(report,indent=2)+'\n')
    print(json.dumps({'passed':True,'checks':len(checks)}))
if __name__=='__main__':main()
