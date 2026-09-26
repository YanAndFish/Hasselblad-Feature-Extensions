"""单处 text2 修正的独立原厂 GUI 会话构建，不改变 a8 输入或设备状态。"""
from pathlib import Path
import difflib,hashlib,importlib.util,io,json,sys,tarfile
sys.dont_write_bytecode=True
FIX=Path(__file__).resolve().parent;CANDIDATE=FIX.parents[1];ROOT=CANDIDATE.parents[2]
HERE=FIX/'session';OUT=FIX/'build/session';REMOTE='/tmp/hbl-ui-format-r1';OLD_REMOTE='/tmp/hbl-ui-resident'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(b):return hashlib.sha256(b).hexdigest()
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
patch=load('card_format_role_patch',FIX/'patch.py')
original=load('card_format_original_session_build',CANDIDATE/'session/build.py')
def build():
    if Path.cwd().resolve()!=ROOT:raise ValueError('workspace mismatch')
    original.fixed()
    old=load('card_format_original_session_package',CANDIDATE/'session/package.py');old_report,old_blob=old.verify()
    with tarfile.open(fileobj=io.BytesIO(old_blob)) as archive:old_files={m.name:archive.extractfile(m).read() for m in archive.getmembers()}
    data=patch.resources();out=OUT/'resources';out.mkdir(parents=True,exist_ok=True)
    rcc=load('card_format_resource_bundle',CANDIDATE/'tools/resource_bundle.py').rcc(data)
    (out/'ui-resident.rcc').write_bytes(rcc)
    for path,value in data.items():
        target=out/path.lstrip('/');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(value.encode())
    before=(patch.FROZEN/'settings/SettingsGeneric.qml').read_text(encoding='utf-8')
    (out/'changes.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),data['/settings/SettingsGeneric.qml'].splitlines(True),fromfile='a/settings/SettingsGeneric.qml',tofile='b/settings/SettingsGeneric.qml')),encoding='utf-8')
    resource_report={'rccSha256':digest(rcc),'resources':{p:digest(v.encode()) for p,v in data.items()},'a8PackageSha256':old_report['packageSha256'],
        'sources':{p.relative_to(ROOT).as_posix():sha(p) for p in (FIX/'patch.py',Path(__file__),CANDIDATE/'tools/resource_bundle.py')}}
    save(out/'manifest.json',resource_report)
    for name in ('common.sh','install.sh','restore.sh','run.sh'):
        current=(CANDIDATE/'session'/name).read_bytes()
        if current!=old_files[name]:raise ValueError('a8 source no longer fixed '+name)
        HERE.mkdir(parents=True,exist_ok=True);(HERE/name).write_bytes(current.replace(OLD_REMOTE.encode(),REMOTE.encode()))
    native=HERE/'native';native.mkdir(parents=True,exist_ok=True)
    source=(CANDIDATE/'session/native/runtime.cpp').read_text(encoding='utf-8')
    for previous,new in [(OLD_REMOTE,REMOTE),(original.RCC_SHA,digest(rcc)),(patch.OLD_SETTINGS_SHA,resource_report['resources']['/settings/SettingsGeneric.qml'])]:
        if previous not in source:raise ValueError('native binding anchor')
        source=source.replace(previous,new)
    (native/'runtime.cpp').write_bytes(source.encode());(native/'health.cpp').write_bytes((CANDIDATE/'session/native/health.cpp').read_bytes())
    original.HERE=HERE;original.OUT=OUT;original.RCC_SHA=digest(rcc)
    result=original.build()
    report=json.loads((OUT/'native/build.json').read_text(encoding='utf-8'))
    report['sources'].update(resource_report['sources']);report['resourcesManifestSha256']=sha(out/'manifest.json')
    save(OUT/'native/build.json',report)
    save(OUT/'source-binding.json',{'oldPackageSha256':old_report['packageSha256'],'scriptChange':'remote root substitution only',
        'remoteRoot':REMOTE,'oldSources':{p.relative_to(ROOT).as_posix():sha(p) for p in (CANDIDATE/'session/build.py',CANDIDATE/'session/native/runtime.cpp',CANDIDATE/'session/native/health.cpp')},
        'shellSources':{p.relative_to(ROOT).as_posix():sha(p) for p in HERE.glob('*.sh')},'hardwareRequests':0})
    return {'compiled':True,'rccSha256':digest(rcc),'outputs':result['outputs'],'hardwareRequests':0}
if __name__=='__main__':print(json.dumps(build()))
