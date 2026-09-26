"""实际完整包 shell 的首次装载与恢复；服务/健康/socket 为隔离替身。"""
import hashlib,importlib.util,json,subprocess,sys,tempfile
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[3]
spec=importlib.util.spec_from_file_location('r5_shell_fixture',ROOT/'x1d/combined-runtime/CodeTests/test_install.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
base.HERE=HERE/'inputs';base.ROOT=ROOT
base.FAKE=base.FAKE.replace('90-hbl-combined.conf','90-hbl-af-only.conf').replace('formal-ui-loaded-default-off','af-only-ui-ready')
base.FAKE=base.FAKE.replace("write(r/'af/ui.sock','')", "write(r/'af/ui.sock','');write(r/'af/ui-r4.status','stage=ready pid='+str(st['pid'])+' bound=1 \\n')")
base.FAKE=base.FAKE.replace("write(r/'af/backend.sock','')", "write(r/'af/backend.sock','');write(r/'af/backend-r5.status','stage=ready error=0 meta=1 uart=1\\n');write(r/'af/backend-r5-flow.status','stage=ready error=0 pending=0 events=0 \\n');write(r/'af/backend-r5-transport.status','stage=observe calls=0 private=0 \\n')")
base.FAKE=base.FAKE.replace("elif cmd=='replay-joint-check':", "elif cmd=='bus-local-check':\n if flag('local-fail'):sys.exit(1)\nelif cmd=='replay-joint-check':")
base.FAKE=base.FAKE.replace("if role=='victory-gui' and flag('fail-provider') and 'libx1d-replay-provider.so' in text:","if role=='victory-gui' and flag('fail-gui') and text:")
base.FAKE=base.FAKE.replace("st['pid']+=1000;st['active']=True", "if role=='msg2dbus-farm' and flag('fail-bus') and text:save();sys.exit(1)\n   st['pid']+=1000;st['active']=True")

def run():
    parent=HERE/'CodeTests/output';parent.mkdir(exist_ok=True);checks=[]
    for name in base.SOURCE_NAMES:subprocess.run([str(base.SHELL),'-n',str(HERE/'inputs'/name)],check=True,capture_output=True)
    with tempfile.TemporaryDirectory(dir=parent) as temp:
        def fixture(name):
            r,d,e=base.fixture(Path(temp),name)
            base.write(d/'bus-local-check','#!/bin/sh\nexec "$COMBINED_TEST_PYTHON" "$COMBINED_TEST_FAKE" bus-local-check "$@"\n')
            for n in base.SOURCE_NAMES:
                s=(d/n).read_text(encoding='utf-8').replace('/tmp/hbl-af-ui-r4',(r/'af-ui-r4').as_posix()).replace('/tmp/hbl-af-bus-r3',(r/'af-bus-r3').as_posix())
                base.write(d/n,s)
            base.write(d/'manifest.sha256',''.join(base.sha(p)+'  '+p.relative_to(d).as_posix()+'\n' for p in sorted(d.rglob('*')) if p.is_file() and p.name!='manifest.sha256'))
            return r,d,e
        def call(d,e,phase):
            return subprocess.run([str(base.SHELL),'-c','PATH="$COMBINED_TEST_BIN:/usr/bin:/bin"; export PATH; exec sh "$@"','r5-test',str(d/'run.sh'),phase],cwd=ROOT,env=e,capture_output=True,text=True,encoding='utf-8',timeout=60)
        def expect(d,e,phase,code=0):
            v=call(d,e,phase);assert v.returncode==code,(phase,code,v.returncode,v.stdout,v.stderr);return v
        def calls(r):return [json.loads(x) for x in (r/'calls.jsonl').read_text().splitlines()]
        r,d,e=fixture('normal')
        for phase in ('preflight','ui','bus'):expect(d,e,phase)
        base.write(d/'install-state/af-installed.sha256','a'*64+'\n');expect(d,e,'release')
        c=calls(r)
        transitions=[x for x in c if x[0]=='systemctl' and x[1] in ('restart','start','stop')]
        assert transitions==[['systemctl','restart','victory-gui'],['systemctl','restart','msg2dbus-farm']]
        assert sum(x==['bus-local-check'] for x in c)==1
        assert sum(x==['system-check','--begin-hold'] for x in c)==1
        assert (d/'install-state/gui.dropin').read_text().count('HBL_AF_UI_R4_ENABLE=0')==1
        assert len(list((r/'run/systemd/system').rglob('*.conf')))==2
        expect(d,e,'bus',62);checks.append('one GUI restart and one new bus restart, one hold, no 95 increments, duplicate refused')
        r,d,e=fixture('local-fail');base.write(r/'local-fail','1');expect(d,e,'preflight',62)
        assert not any(x[0]=='systemctl' and x[1] in ('restart','start','stop') for x in calls(r))
        checks.append('local socket check fails before service changes')
        for case,phase,code in [('gui-fail','ui',64),('bus-fail','bus',68)]:
            r,d,e=fixture(case);expect(d,e,'preflight')
            if phase=='bus':expect(d,e,'ui')
            base.write(r/('fail-gui' if phase=='ui' else 'fail-bus'),'1');expect(d,e,phase,code)
            expect(d,e,'restore-linux')
            assert all(v['active'] for v in json.loads((r/'services.json').read_text()).values())
            assert not list((r/'run/systemd/system').rglob('*.conf'))
            checks.append(case+' restores original services without RAM action')
        r,d,e=fixture('early-restore');expect(d,e,'restore-linux');checks.append('already-original baseline confirmed without restart')
        r,d,e=fixture('ram-pending');expect(d,e,'ui');expect(d,e,'bus');base.write(d/'install-state/ram.started','1')
        expect(d,e,'restore-linux',64);assert list((r/'run/systemd/system').rglob('*.conf'))
        checks.append('RAM intent prevents premature Linux removal')
        r,d,e=fixture('foreign');expect(d,e,'ui');target=r/'run/systemd/system/victory-gui.service.d/90-hbl-af-only.conf';base.write(target,'foreign')
        expect(d,e,'restore-linux',60);assert target.read_text()=='foreign';checks.append('foreign configuration preserved')
        r,d,e=fixture('unknown');base.write(d/'phases/ui.sent','unknown');expect(d,e,'bus',62);checks.append('unknown earlier phase blocks later actions')
        r,d,e=fixture('expired');expect(d,e,'ui');base.write(r/'expired','1');expect(d,e,'bus',65);checks.append('expired hold blocks bus')
        r,d,e=fixture('old-increment');(r/'af-ui-r4').mkdir();expect(d,e,'preflight',61);checks.append('old increment directory rejects fresh install')
    proof={'passed':True,'hardwareRequests':0,'checks':checks,'targetShellVerified':False,
        'sources':{(HERE/'inputs'/n).relative_to(ROOT).as_posix():base.sha(HERE/'inputs'/n) for n in base.SOURCE_NAMES}}
    (HERE/'CodeTests/output/linux.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'checks':len(checks),'hardwareRequests':0}))
if __name__=='__main__':run()
