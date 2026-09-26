import json,sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import continuation_package as package
def main():
    package.previous()
    tests=[package.read(HERE/'CodeTests/output'/n) for n in ('tests.json','entry.json')]
    assert all(t['passed'] and t['hardwareRequests']==0 for t in tests)
    files=[p for p in HERE.iterdir() if p.is_file() and p.suffix in ('.sh','.py','.json','.sha256') and p.name!='validation.json']
    files += [p for p in (HERE/'CodeTests').rglob('*') if p.is_file()]
    files += [p for p in (HERE/'build').iterdir() if p.is_file()]
    files += [HERE.parent/'validation.json',package.ROOT/'x1d/wireless-flash/native/formal_system_check.cpp',
        package.ROOT/'x1d/combined-runtime/build/fixed/install-window-e373262db5b23f56/build.json',
        package.ROOT/'x1d/combined-runtime/build/fixed/install-window-e373262db5b23f56/system-check']
    result={'passed':True,'revision':'af-ui-r4-preflight-r1','hardwareRequests':0,'originalGuiPayloadUnchanged':True,
        'oldPhaseUntouched':True,'guiHealthGate':'existing --require-ui-stage','farmHealthGateUnchanged':True,
        'sources':{p.relative_to(package.ROOT).as_posix():package.sha(p) for p in files}}
    (HERE/'validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    r,_=package.verify();print(json.dumps({'passed':True,'package':r,'validationSha256':package.sha(HERE/'validation.json')}))
if __name__=='__main__':main()
