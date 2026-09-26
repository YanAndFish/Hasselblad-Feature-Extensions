"""对 r2 新根和诊断成功标记重跑完整 shell 事务集；设备状态均为替身。"""
from pathlib import Path
import hashlib,json,sys,types
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];CANDIDATE=HERE.parents[1];ROOT=CANDIDATE.parents[2]
SOURCE=CANDIDATE/'CodeTests/test_session.py'
sys.path.insert(0,str(HERE));import build
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    module=types.ModuleType('full_ui_r2_shell_fixture');module.__file__=str(SOURCE)
    code=SOURCE.read_text(encoding='utf-8').replace('/tmp/hbl-ui-resident',build.REMOTE).replace('ui-resident-ready-resources4-components4',build.READY)
    code=code.replace('timeout=60)','timeout=180)')
    code=code.replace("('fail-start','bad-component','missing-status','stale-pid','bad-installed-health')", "('fail-start','bad-component','missing-status','stale-pid','bad-installed-health','pool-error','pool-timeout','pool-pending')")
    code=code.replace("+' system=2 power=0')", "+(' system=4 power=1' if flag('standby') else ' system=2 power=0'))")
    code=code.replace("else '"+build.READY+"')", "else 'ui-resident-pool-failed' if flag('pool-error') else 'ui-resident-pool-timeout' if flag('pool-timeout') else 'ui-resident-pool-pending' if flag('pool-pending') else '"+build.READY+"')")
    code=code.replace("    source={p.relative_to(ROOT)", "    r,d,e=fixture(parent,'standby');write(r/'standby','1')\n    check('standby preflight rejected without service mutation',call(d,e,'preflight').returncode==62 and not mutations(r) and not (d/'state').exists())\n    source={p.relative_to(ROOT)")
    exec(compile(code,str(SOURCE),'exec'),module.__dict__)
    module.HERE=HERE;module.ROOT=ROOT;module.SRC=HERE/'session';original=module.fixture
    def fixture(parent,name):
        root,directory,environment=original(parent,name);module.write(root/'calls.jsonl','')
        module.write(root/'bin/id','#!/bin/sh\nprintf 0\n')
        module.write(root/'bin/stat',"#!/bin/sh\ncase \"$2\" in '%u:%a') printf 0:700;; *) printf 0:1;; esac\n")
        module.write(root/'bin/sleep','#!/bin/sh\nexit 0\n');return root,directory,environment
    module.fixture=fixture
    for name in module.NAMES:
        before=(CANDIDATE/'session'/name).read_bytes()
        assert (module.SRC/name).read_bytes()==build.shell(name,(HERE.parent/'full-pages-r1/session'/name).read_bytes())
    module.run();path=HERE/'build/session/install-validation.json';report=json.loads(path.read_text(encoding='utf-8'))
    # 事务测试只执行四份 shell；native 和清单由各自构建/归档证据绑定。
    report['sources']={name:value for name,value in report['sources'].items() if name.endswith('.sh')}
    report['sources'].update({p.relative_to(ROOT).as_posix():sha(p) for p in (Path(__file__),SOURCE,HERE/'build.py',HERE.parent/'full-pages-r1/CodeTests/session_paths.py')})
    report['fixtureTransformation']='r2 root/diagnostic marker; 180s host limit; fast UID/mode/sleep mocks; pool error/timeout/pending and standby cases'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
