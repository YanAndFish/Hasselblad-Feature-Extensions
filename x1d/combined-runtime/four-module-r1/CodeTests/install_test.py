"""合并安装的真实 sh 故障场景；服务、驱动、socket 全部替身。"""
from pathlib import Path
from datetime import datetime, timezone
import importlib.util, json, sys, subprocess
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
spec=importlib.util.spec_from_file_location('formal_test',ROOT/'x1d/wireless-flash/CodeTests/formal_install.test.py')
t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)
t.OUT=HERE/'CodeTests/output'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
t.SOURCES[0]=HERE/'build/package/flash/formal-install.sh'
extra="""  write(r/'combined/ui.status',('failed' if (r/'fail_ui').exists() else 'ui-resident-ready-resources6-components5-pools3-pages23-rows-diag1')+' pid='+('99' if (r/'stale_pid').exists() else '101')+'\\n')
  write(r/'combined/replay.status',('failed' if (r/'fail_replay').exists() else 'replay-page-ready-resources7-components7-pages2')+' pid=101\\n')
"""
t.FAKE=t.FAKE.replace("  write(d/'formal-ui.sock','socket-double')", "  write(d/'formal-ui.sock','socket-double')\n"+extra.rstrip())
def case(name,flag=None):
    c=t.make_case(name,flag=flag);r,d,e=c
    p=d/'formal-install.sh';p.write_text(p.read_text(encoding='utf-8').replace('/run/hbl-four-module',(r/'combined').as_posix()),encoding='utf-8',newline='\n')
    paths=sorted(p for p in d.rglob('*') if p.is_file() and p.name!='manifest.sha256')
    t.write(d/'manifest.sha256',''.join(t.sha(p.read_bytes())+'  '+p.relative_to(d).as_posix()+'\n' for p in paths))
    return c
checks=[]
for name,flag in [('normal',None),('ui-failure','fail_ui'),('replay-failure','fail_replay'),('stale-pid','stale_pid'),('radio-failure','fail_modprobe_once'),('preload-refusal','unknown_preload')]:
    c=case(name,flag);r,d,_=c;result=t.execute(c,'formal-install.sh')
    events=t.commands(r)
    if flag is None:
        assert result.returncode==0,(name,result.stdout,result.stderr)
        assert (d/'formal-state/install-complete').exists()
    else:
        assert result.returncode!=0,name
        if flag in ('fail_ui','fail_replay','stale_pid'):
            assert not any(e['command'] in ('rmmod','modprobe') for e in events)
        if flag!='unknown_preload':assert (d/'formal-install.status').read_text().strip()=='formal-install-failed-original-linux-restored'
        assert t.is_active(r,'victory-gui') and t.is_active(r,'msg2dbus-farm')
    checks.append(name);print(json.dumps({'passed':name}),flush=True)
for path in [HERE/'build/package/run.sh',*t.SOURCES]:
    assert subprocess.run([str(t.SHELL),'-n',str(path)],capture_output=True).returncode==0
proof={'passed':True,'scenarios':checks,'hardwareRequests':0,'installSha256':t.sha(t.SOURCES[0].read_bytes())}
(HERE/'CodeTests/install-validation.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof))
