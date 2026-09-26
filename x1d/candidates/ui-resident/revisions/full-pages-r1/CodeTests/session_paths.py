"""完整既有 shell 事务集及全页就绪/待机拒绝；服务与进程为离线替身。"""
from pathlib import Path
import hashlib,json,sys,types
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];CANDIDATE=HERE.parents[1];ROOT=CANDIDATE.parents[2]
SOURCE=CANDIDATE/'CodeTests/test_session.py'
sys.path.insert(0,str(HERE));import build
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    module=types.ModuleType('full_ui_original_shell_fixture');module.__file__=str(SOURCE)
    code=SOURCE.read_text(encoding='utf-8').replace('/tmp/hbl-ui-resident','/tmp/hbl-ui-full-r1').replace('ui-resident-ready-resources4-components4',build.READY)
    code=code.replace('timeout=60)','timeout=180)')
    code=code.replace("('fail-start','bad-component','missing-status','stale-pid','bad-installed-health')", "('fail-start','bad-component','missing-status','stale-pid','bad-installed-health','pool-error','pool-timeout','pool-pending')")
    code=code.replace("+' system=2 power=0')", "+(' system=4 power=1' if flag('standby') else ' system=2 power=0'))")
    code=code.replace("else '"+build.READY+"')", "else 'ui-resident-pool-failed' if flag('pool-error') else 'ui-resident-pool-timeout' if flag('pool-timeout') else 'ui-resident-pool-pending' if flag('pool-pending') else '"+build.READY+"')")
    code=code.replace("    source={p.relative_to(ROOT)", "    r,d,e=fixture(parent,'standby');write(r/'standby','1')\n    check('standby preflight rejected without service mutation',call(d,e,'preflight').returncode==62 and not mutations(r) and not (d/'state').exists())\n    source={p.relative_to(ROOT)")
    exec(compile(code,str(SOURCE),'exec'),module.__dict__)
    module.HERE=HERE;module.ROOT=ROOT;module.SRC=HERE/'session';original=module.fixture
    def fixture(parent,name):
        r,d,e=original(parent,name)
        module.write(r/'calls.jsonl','')
        module.write(r/'bin/id','#!/bin/sh\nprintf 0\n')
        module.write(r/'bin/stat',"#!/bin/sh\ncase \"$2\" in '%u:%a') printf 0:700;; *) printf 0:1;; esac\n")
        module.write(r/'bin/sleep','#!/bin/sh\nexit 0\n')
        return r,d,e
    module.fixture=fixture
    for name in module.NAMES:
        before=(CANDIDATE/'session'/name).read_bytes()
        assert (module.SRC/name).read_bytes()==build.shell(name,before)
    module.run()
    path=HERE/'build/session/install-validation.json';report=json.loads(path.read_text(encoding='utf-8'))
    report['sources'].update({p.relative_to(ROOT).as_posix():sha(p) for p in (Path(__file__),SOURCE)})
    report['fixtureTransformation']='new root/full-pool marker; 180s host subprocess limit; fast UID/mode/sleep mocks; native pool error/timeout/pending and standby cases'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
