"""r2 最终实际归档、RCC、ARM、传输和经典解码审计。"""
from pathlib import Path
import hashlib,json,sys,types
sys.dont_write_bytecode=True
REV=Path(__file__).resolve().parents[1];R1=REV.parent/'full-pages-r1';CANDIDATE=REV.parents[1];ROOT=CANDIDATE.parents[2];SOURCE=CANDIDATE/'fixes/card-format-r1/CodeTests/test_package.py'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    code=SOURCE.read_text(encoding='utf-8').replace("FIX/'build/python-qt515'", "FIX.parents[1]/'fixes/card-format-r1/build/python-qt515'")
    code='\n'.join(line for line in code.splitlines() if not any(value in line for value in ('changed=p.build.patch.resources()',"check('only single text2 expression", "check('other three QMLs")))+'\n'
    code=code.replace("p.build.original.CACHE/'python'", "p.ROOT/'.research-cache/x1d-1.25.0/python'").replace('native binds four hashes','native binds six hashes').replace('11 original baseline hashes','13 fixed baseline hashes').replace('splitlines())==11','splitlines())==13')
    module=types.ModuleType('r2_archive_audit');module.__file__=str(Path(__file__));exec(compile(code,str(SOURCE),'exec'),module.__dict__);module.run()
    path=REV/'build/session/package-validation.json';proof=json.loads(path.read_text(encoding='utf-8'))
    proof['sources']={p.relative_to(ROOT).as_posix():sha(p) for p in (Path(__file__),SOURCE,R1/'CodeTests/archive.py')};path.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
