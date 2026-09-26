"""绑定 r2 包运行既有离线传输、解码和失败边界测试。"""
from pathlib import Path
import hashlib,importlib.util,json,sys,types
sys.dont_write_bytecode=True
REV=Path(__file__).resolve().parents[1];CANDIDATE=REV.parents[1];ROOT=CANDIDATE.parents[2];SOURCE=CANDIDATE/'CodeTests/test_delivery.py'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    spec=importlib.util.spec_from_file_location('r2_delivery_test',REV/'delivery.py');delivery=importlib.util.module_from_spec(spec);spec.loader.exec_module(delivery)
    module=types.ModuleType('r2_transfer_fixture');module.__file__=str(SOURCE);code=SOURCE.read_text(encoding='utf-8')
    code=code.replace("release=m.package.build.fixed()", "release={'manifest':{'resources':{k:{'outputSha256':v} for k,v in m.package.read(HERE/'build/resources/manifest.json')['resources'].items()}}}")
    code=code.replace('m.package.build.RCC_SHA',"m.package.read(HERE/'build/resources/manifest.json')['rccSha256']").replace("files=[Path(__file__),HERE/'session/delivery.py'", "files=[Path(__file__),HERE/'delivery.py'")
    exec(compile(code,str(SOURCE),'exec'),module.__dict__);module.HERE=REV;module.ROOT=ROOT;module.m=delivery.transport;module.run()
    path=REV/'build/session/transfer-validation.json';report=json.loads(path.read_text(encoding='utf-8'))
    report['sources'].update({p.relative_to(ROOT).as_posix():sha(p) for p in [Path(__file__),SOURCE,delivery.BASE,REV/'package.py',REV/'build.py']})
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
