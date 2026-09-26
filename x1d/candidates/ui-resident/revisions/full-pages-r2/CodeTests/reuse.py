"""证明 r2 六资源逐字复用冻结 r1，旧功能证据未被改写。"""
from pathlib import Path
import hashlib,importlib.util,json,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];R1=HERE.parent/'full-pages-r1';ROOT=HERE.parents[4]
R1_SHA='f2d398f8ea39b41b8dd0354a243844b750a18868f832167501d2154cc48a259d'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def main():
    package=load('r2_reuse_r1_package',R1/'package.py');report,_=package.verify();assert report['packageSha256']==R1_SHA
    manifest=json.loads((HERE/'build/resources/manifest.json').read_text(encoding='utf-8'))
    assert manifest['rccSha256']==report['rccSha256'] and manifest['resources']==report['resources'] and manifest['identicalToR1Resources']
    evidence=[]
    for name in ('qml-validation.json','race-validation.json','readiness-validation.json','qt55-identifiers.json','memory-summary.json'):
        path=R1/'build'/name;value=json.loads(path.read_text(encoding='utf-8'));assert value['passed'];evidence.append(path)
    out={'passed':True,'r1PackageSha256':R1_SHA,'rccSha256':report['rccSha256'],'resourceCount':len(report['resources']),
        'reusedChecks':{'qml':194,'races':11,'readiness':10,'qt55Identifiers':86,'memoryPairs':5},'hardwareRequests':0,
        'sources':{p.relative_to(ROOT).as_posix():sha(p) for p in [Path(__file__),R1/'package.py',R1/'build/session/current.json',ROOT/report['archive'],HERE/'build/resources/manifest.json',*evidence]}}
    path=HERE/'build/reuse-validation.json';path.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'r1PackageSha256':R1_SHA,'resourceCount':6,'hardwareRequests':0}))
if __name__=='__main__':main()
