"""新临时根的实际 shell 事务检查；沿用已审阅 a8 服务替身，0设备。"""
from pathlib import Path
import hashlib,importlib.util,json,os,subprocess,sys,types
sys.dont_write_bytecode=True
FIX=Path(__file__).resolve().parents[1];CANDIDATE=FIX.parents[1];ROOT=CANDIDATE.parents[2]
SOURCE=CANDIDATE/'CodeTests/test_session.py'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run():
    m=types.ModuleType('card_format_existing_shell_fixture');m.__file__=str(SOURCE)
    code=SOURCE.read_text(encoding='utf-8').replace('/tmp/hbl-ui-resident','/tmp/hbl-ui-format-r1')
    exec(compile(code,str(SOURCE),'exec'),m.__dict__)
    m.SRC=FIX/'session';m.ROOT=ROOT
    from datetime import datetime,timezone
    parent=FIX/'build/session/tests'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');parent.mkdir(parents=True)
    checks=[]
    def check(n,c):
        assert c,n
        checks.append(n);print(json.dumps({'check':n,'passed':True}),flush=True)
    def fixture(name):
        r,d,e=m.fixture(parent,name)
        m.write(r/'bin/id','#!/bin/sh\nprintf 0\n')
        m.write(r/'bin/stat',"#!/bin/sh\ncase \"$2\" in '%u:%a') printf 0:700;; *) printf 0:1;; esac\n")
        m.write(r/'bin/sleep','#!/bin/sh\nexit 0\n')
        return r,d,e
    def call(d,e,p):
        result=subprocess.run([str(m.SHELL),'-c','PATH="$UI_TEST_BIN:/usr/bin:/bin";export PATH;exec sh "$@"','ui-test',str(d/'run.sh'),p],cwd=ROOT,env=e,capture_output=True,text=True,encoding='utf-8',timeout=60)
        return result
    def actions(r):
        p=r/'calls.jsonl'
        return [v for v in (json.loads(v) for v in p.read_text().splitlines()) if v[0]=='systemctl' and v[1] in ('start','stop','restart')] if p.exists() else []
    for name in m.NAMES:
        subprocess.run([str(m.SHELL),'-n',str(m.SRC/name)],check=True)
        old=(CANDIDATE/'session'/name).read_bytes();new=(m.SRC/name).read_bytes()
        check('only remote root changed '+name,new==old.replace(b'/tmp/hbl-ui-resident',b'/tmp/hbl-ui-format-r1'))
    r,d,e=fixture('normal')
    for p in ('preflight','ui','status'):
        result=call(d,e,p);check(p+' succeeds at new root',result.returncode==0)
        if p=='preflight':check('preflight has no service mutation',not actions(r))
    check('UI only restarts GUI once',actions(r)==[['systemctl','restart','victory-gui']])
    check('duplicate ui refused',call(d,e,'ui').returncode==62)
    check('new restore returns factory',call(d,e,'restore').returncode==0 and (d/'state/restored.done').is_file())
    check('restore never restarts bus',actions(r)==[['systemctl','restart','victory-gui'],['systemctl','stop','victory-gui'],['systemctl','start','victory-gui']])
    for label,file in [('old-a8','90-hbl-ui-resident.conf'),('other-overlay','95-foreign.conf')]:
        r,d,e=fixture(label);conf=r/'run/systemd/system/victory-gui.service.d'/file;m.write(conf,'original foreign state')
        check(label+' refused before mutation',call(d,e,'ui').returncode==61 and not actions(r) and conf.read_text()=='original foreign state')
    r,d,e=fixture('component-failure');m.write(r/'bad-component','1');result=call(d,e,'ui')
    check('component failure automatically restores factory',result.returncode==64 and (d/'state/restored.done').is_file())
    r,d,e=fixture('changed-owner');check('setup owned phase',call(d,e,'ui').returncode==0)
    conf=r/'run/systemd/system/victory-gui.service.d/90-hbl-ui-resident.conf';m.write(conf,'changed externally');before=actions(r)
    check('restore never removes changed owner config',call(d,e,'restore').returncode==66 and conf.read_text()=='changed externally' and actions(r)==before)
    report={'passed':True,'checks':checks,'sources':{p.relative_to(ROOT).as_posix():sha(p) for p in [*(m.SRC/n for n in m.NAMES),SOURCE,Path(__file__)]},'hardwareRequests':0,'scope':'actual shell at new remote root; services/processes/UID/health are explicit mocks'}
    m.write(FIX/'build/session/install-validation.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'passed':True,'checks':len(checks),'hardwareRequests':0}))
if __name__=='__main__':run()
