"""实际独立 AF shell 的阶段、失败及恢复检查，设备与服务为隔离替身。"""
from pathlib import Path
from datetime import datetime,timezone
import importlib.util
import json
import subprocess
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[2]
spec=importlib.util.spec_from_file_location('shell_fixture',HERE.parent/'CodeTests/test_install.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
base.HERE=HERE
base.FAKE=base.FAKE.replace('90-hbl-combined.conf','90-hbl-af-only.conf').replace('formal-ui-loaded-default-off','af-only-ui-ready')
base.FAKE=base.FAKE.replace("write(r/'af/backend.sock','')","write(r/'af/backend.sock','');write(r/'af/backend-r2.status','stage=ready error=0 meta=1 uart=1\\n')")
base.FAKE=base.FAKE.replace("if role=='victory-gui' and flag('fail-provider') and 'libx1d-replay-provider.so' in text:","if role=='victory-gui' and flag('fail-gui') and text:")
def run():
    assert Path.cwd().resolve()==ROOT
    parent=HERE/'CodeTests/output'/('shell-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));parent.mkdir(parents=True)
    checks=[]
    def check(name,value,result=None):
        if not value:raise AssertionError((name,None if result is None else (result.returncode,result.stdout,result.stderr)))
        checks.append(name)
    def call(d,e,phase):
        return subprocess.run([str(base.SHELL),'-c','PATH="$COMBINED_TEST_BIN:/usr/bin:/bin"; export PATH; exec sh "$@"','af-only-test',str(d/'run.sh'),phase],cwd=ROOT,env=e,capture_output=True,text=True,encoding='utf-8',timeout=60)
    def good(d,e,phase):
        r=call(d,e,phase);check(phase+' success',r.returncode==0,r)
    def fixture(name):
        r,d,e=base.fixture(parent,name)
        # 组合 fixture 中旧模块只是模型文件；独立脚本不会启动任何旧模块。
        return r,d,e
    for name in base.SOURCE_NAMES:subprocess.run([str(base.SHELL),'-n',str(HERE/name)],check=True)
    r,d,e=fixture('normal')
    for phase in ('preflight','ui','bus'):good(d,e,phase)
    base.write(d/'install-state/af-installed.sha256','a'*64+'\n');good(d,e,'release')
    calls=[json.loads(line) for line in (r/'calls.jsonl').read_text().splitlines()]
    check('one fixed deadline',sum(v==['system-check','--begin-hold'] for v in calls)==1)
    check('only GUI and AF bus restarted',[v for v in calls if v[0]=='systemctl' and v[1] in ('restart','start','stop')]==[['systemctl','restart','victory-gui'],['systemctl','restart','msg2dbus-farm']])
    check('no radio or replay helpers',not any('formal' in v[0] or 'replay' in v[0] for v in calls))
    check('duplicate phase refused',call(d,e,'bus').returncode==62)
    r,d,e=fixture('missing-af-proof');good(d,e,'ui');good(d,e,'bus')
    check('release needs completed AF proof',call(d,e,'release').returncode==65 and not (d/'install-state/hold.release').exists())
    r,d,e=fixture('expired');good(d,e,'ui');base.write(r/'expired','1')
    check('expiry blocks bus',call(d,e,'bus').returncode==65)
    r,d,e=fixture('changed');base.write(d/'af/libhbl-af-ui.so','changed')
    check('changed package no install',call(d,e,'ui').returncode==60 and not (d/'install-state').exists())
    r,d,e=fixture('foreign');(r/'af').mkdir()
    check('foreign AF dir preserved',call(d,e,'ui').returncode==61 and not (d/'install-state').exists())
    r,d,e=fixture('ui-failure');base.write(r/'fail-gui','1')
    check('UI failure bounded',call(d,e,'ui').returncode==64)
    good(d,e,'restore-linux')
    r,d,e=fixture('restore-before-ram');good(d,e,'ui');good(d,e,'bus');good(d,e,'restore-linux')
    check('original services restored',all(v['active'] for v in json.loads((r/'services.json').read_text()).values()))
    r,d,e=fixture('ram-started');good(d,e,'ui');good(d,e,'bus');base.write(d/'install-state/ram.started','started')
    check('RAM blocks consumer removal',call(d,e,'restore-linux').returncode==64 and (r/'run/systemd/system/msg2dbus-farm.service.d/90-hbl-af-only.conf').exists())
    r,d,e=fixture('foreign-dropin');good(d,e,'ui')
    target=r/'run/systemd/system/victory-gui.service.d/90-hbl-af-only.conf';base.write(target,'foreign')
    check('foreign dropin kept',call(d,e,'restore-linux').returncode==60 and target.read_text()=='foreign')
    proof={'passed':True,'checks':checks,'sources':{(HERE/n).relative_to(ROOT).as_posix():base.sha(HERE/n) for n in base.SOURCE_NAMES},'testSha256':base.sha(Path(__file__)),'hardwareRequests':0,'targetValidated':False}
    base.write(HERE/'CodeTests/output/install.json',json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'passed':True,'checks':len(checks),'hardwareRequests':0}))
if __name__=='__main__':run()
