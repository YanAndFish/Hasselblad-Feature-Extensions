"""Continuation guards only; original GUI payload and AF tests are not rebuilt."""
import hashlib,json,subprocess,sys,tempfile
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[4]
sys.path.insert(0,str(HERE))
import continuation_package as package
SHELL=Path('C:/Program Files/Git/bin/bash.exe')
def sha(data):return hashlib.sha256(data).hexdigest()
def run():
    parent=HERE.parent
    original=(parent/'common.sh').read_text(encoding='utf-8')
    assert (HERE/'common.sh').read_text(encoding='utf-8')==original.replace('--require-active','--require-ui-stage')
    checker=ROOT/'x1d/wireless-flash/native/formal_system_check.cpp'
    build=package.read(ROOT/'x1d/combined-runtime/build/fixed/install-window-e373262db5b23f56/build.json')
    assert package.sha(checker)==build['sources']['x1d/wireless-flash/native/formal_system_check.cpp']
    assert package.sha(ROOT/'x1d/combined-runtime/build/fixed/install-window-e373262db5b23f56/system-check')=='e373262db5b23f567b22060f1a61687c723cbbbae3c1e237e60728015d3ccca0'
    for name in ('common.sh','apply.sh','restore.sh','run.sh'):subprocess.run([str(SHELL),'-n',str(HERE/name)],check=True,capture_output=True)
    report=package.make();out=HERE/'CodeTests/output';out.mkdir(exist_ok=True)
    checks=['only GUI gate flag changed twice','fixed existing checker source and binary identities match']
    with tempfile.TemporaryDirectory(dir=out) as temp:
        for case in ('good','log-changed','exit-changed','touched','bus-pid','foreign-delta','unknown','duplicate'):
            d=Path(temp)/case;fix=d/'preflight-r1';fix.mkdir(parents=True);(d/'phases').mkdir()
            for name,body in {'apply.sent':'sent','apply.exit':'61\n','apply.log':'system-active-hold-not-ready\n'}.items():(d/'phases'/name).write_text(body,encoding='ascii',newline='\n')
            original_bytes={p.name:p.read_bytes() for p in (d/'phases').iterdir()}
            posix=d.as_posix();posix='/'+posix[0].lower()+posix[2:]
            common='d='+posix+'\ndelta=$d/95.conf\nregular(){ [ -f "$1" ] && [ ! -L "$1" ]; }\nprivate(){ [ -d "$1" ]; }\nabsent(){ [ ! -e "$1" ] && [ ! -L "$1" ]; }\ndelta_package(){ return 0; }\n'
            (fix/'common.sh').write_text(common,encoding='ascii',newline='\n')
            (fix/'prior.sha256').write_bytes((HERE/'prior.sha256').read_bytes())
            (fix/'apply.sh').write_text('printf called > '+posix+'/called\nprintf "af-ui-r4-ready\\n"\n',encoding='ascii',newline='\n')
            (fix/'restore.sh').write_text('printf "restored\\n"\n',encoding='ascii',newline='\n')
            script=(HERE/'run.sh').read_text(encoding='utf-8').replace('/tmp/hbl-af-ui-r4',posix)
            (fix/'run.sh').write_text(script,encoding='ascii',newline='\n')
            (fix/'manifest.sha256').write_text(''.join(sha(p.read_bytes())+'  '+p.name+'\n' for p in fix.iterdir()),encoding='ascii',newline='\n')
            if case=='log-changed':(d/'phases/apply.log').write_text('other\n')
            if case=='exit-changed':(d/'phases/apply.exit').write_text('62\n')
            if case=='touched':(d/'touched').write_text('')
            if case=='bus-pid':(d/'bus.pid').write_text('234')
            if case=='foreign-delta':(d/'95.conf').write_text('foreign')
            if case=='unknown':(d/'phases/other.sent').write_text('sent')
            if case=='duplicate':
                (d/'phases/apply-preflight-r1.sent').write_text('sent');(d/'phases/apply-preflight-r1.exit').write_text('0\n')
            result=subprocess.run([str(SHELL),str(fix/'run.sh'),'apply-preflight-r1'],capture_output=True,text=True,timeout=10)
            assert result.returncode==(0 if case=='good' else 61),(case,result.returncode,result.stdout,result.stderr)
            assert (d/'called').exists()==(case=='good')
            if case=='good':assert all((d/'phases'/n).read_bytes()==v for n,v in original_bytes.items())
            checks.append(case)
    result={'passed':True,'checks':checks,'hardwareRequests':0,'guiPayloadRebuilt':False,'afTestsRerun':False}
    (out/'tests.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':run()
