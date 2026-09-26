"""基于冻结 r1 的独立诊断修订；六个 QML/JS 资源逐字不变。"""
from pathlib import Path
import hashlib,importlib.util,json,os,shutil,sys,types
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;R1=HERE.parent/'full-pages-r1';CANDIDATE=HERE.parents[1];ROOT=CANDIDATE.parents[2]
SESSION=HERE/'session';OUT=HERE/'build/session';REMOTE='/tmp/hbl-ui-full-r2'
OLD_REMOTE='/tmp/hbl-ui-full-r1';OLD_READY='ui-resident-ready-resources6-components5-pools3-pages23-rows'
READY='ui-resident-ready-resources6-components5-pools3-pages23-rows-diag1'
RCC_SHA='1c794a21fe7f61a4bdab50f40b5eb02bc428fcd584e9ed2d9d8119c97223b551'
R1_PACKAGE_SHA='f2d398f8ea39b41b8dd0354a243844b750a18868f832167501d2154cc48a259d'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def shell(name,before):
    after=before.replace(OLD_REMOTE.encode(),REMOTE.encode()).replace(OLD_READY.encode(),READY.encode())
    if after==before:raise ValueError('r1 shell anchor missing: '+name)
    return after
def build():
    if Path.cwd().resolve()!=ROOT:raise ValueError('workspace mismatch')
    r1package=load('full_ui_r1_fixed_package',R1/'package.py');r1report,_=r1package.verify()
    if r1report['packageSha256']!=R1_PACKAGE_SHA or r1report['rccSha256']!=RCC_SHA:raise ValueError('r1 identity')
    resource_dir=HERE/'build/resources';resource_dir.mkdir(parents=True,exist_ok=True)
    source_rcc=R1/'build/resources/ui-resident.rcc'
    if sha(source_rcc)!=RCC_SHA:raise ValueError('r1 RCC changed')
    (resource_dir/'ui-resident.rcc').write_bytes(source_rcc.read_bytes())
    resource_manifest=json.loads((R1/'build/resources/manifest.json').read_text(encoding='utf-8'))
    save(resource_dir/'manifest.json',{'firmware':'X1D 1.25.0','rccSha256':RCC_SHA,'resources':resource_manifest['resources'],
        'layoutProof':resource_manifest['layoutProof'],'identicalToR1Resources':True,'r1PackageSha256':R1_PACKAGE_SHA,
        'sources':{p.relative_to(ROOT).as_posix():sha(p) for p in [source_rcc,R1/'build/resources/manifest.json',Path(__file__)]},'hardwareRequests':0})
    SESSION.mkdir(parents=True,exist_ok=True)
    for name in ('common.sh','install.sh','restore.sh','run.sh'):(SESSION/name).write_bytes(shell(name,(R1/'session'/name).read_bytes()))
    (SESSION/'baseline.sha256').write_bytes((R1/'session/baseline.sha256').read_bytes())
    native=SESSION/'native';native.mkdir(parents=True,exist_ok=True)
    runtime=(R1/'session/native/runtime.cpp').read_text(encoding='utf-8')
    if runtime.count(OLD_REMOTE)!=3:raise ValueError('runtime root anchors')
    (native/'runtime.cpp').write_text(runtime.replace(OLD_REMOTE,REMOTE),encoding='utf-8')
    for name in ('readiness.h','gate_policy.h'):(native/name).write_bytes((HERE/'native'/name).read_bytes())
    for name in ('catalog.h',):(native/name).write_bytes((R1/'session/native'/name).read_bytes())
    (native/'health.cpp').write_bytes((R1/'session/native/health.cpp').read_bytes())
    original_path=CANDIDATE/'session/build.py';code=original_path.read_text(encoding='utf-8')
    code=code.replace("('Qml','Core')","('Quick','Qml','Gui','Core')").replace("'-Wno-deprecated-declarations'", "'-isystem',str(base/'include/QtANGLE'),'-Wno-deprecated-declarations'")
    builder=types.ModuleType('full_ui_r2_native_builder');builder.__file__=str(original_path);exec(compile(code,str(original_path),'exec'),builder.__dict__)
    builder.HERE=SESSION;builder.OUT=OUT;builder.RCC_SHA=RCC_SHA;result=builder.build()
    report=json.loads((OUT/'native/build.json').read_text(encoding='utf-8'))
    inputs=[Path(__file__),HERE/'native/readiness.h',HERE/'native/gate_policy.h',R1/'session/native/runtime.cpp',R1/'session/native/catalog.h',R1/'session/native/health.cpp',
        R1/'package.py',R1/'build/session/current.json',ROOT/r1report['archive'],R1/'build/resources/manifest.json',source_rcc,original_path,
        *(SESSION/n for n in ('common.sh','install.sh','restore.sh','run.sh','baseline.sha256')),
        *(native/n for n in ('runtime.cpp','readiness.h','gate_policy.h','catalog.h','health.cpp'))]
    report['sources'].update({p.relative_to(ROOT).as_posix():sha(p) for p in inputs});report['r1PackageSha256']=R1_PACKAGE_SHA
    report['readinessChange']='public Loader.item; fixed-key numeric diagnostic; gate counts unchanged'
    save(OUT/'native/build.json',report)
    return {'compiled':True,'rccSha256':RCC_SHA,'outputs':result['outputs'],'hardwareRequests':0,'targetValidated':False}
if __name__=='__main__':print(json.dumps(build()))
