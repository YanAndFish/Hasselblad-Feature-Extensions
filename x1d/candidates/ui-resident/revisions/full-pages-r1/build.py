"""独立全普通页六资源、ARM32 注册库和临时会话脚本的离线构建。"""
from pathlib import Path
import difflib,hashlib,importlib.util,io,json,sys,tarfile,types
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;CANDIDATE=HERE.parents[1];ROOT=CANDIDATE.parents[2]
SESSION=HERE/'session';OUT=HERE/'build/session';REMOTE='/tmp/hbl-ui-full-r1'
OLD_REMOTE='/tmp/hbl-ui-resident'
READY='ui-resident-ready-resources6-components5-pools3-pages23-rows'
def shell(name,before):
    after=before.replace(OLD_REMOTE.encode(),REMOTE.encode()).replace(b'ui-resident-ready-resources4-components4',READY.encode())
    if name=='common.sh':
        old=b'wait_ready() { for n in 1 2 3 4 5 6 7 8 9 10;do "$1" 2>/dev/null && return 0;sleep 1;done;return 1; }'
        new=b'''wait_ready() {
    limit=10;[ "$1" != gui_ready ] || limit=40
    n=0
    while [ "$n" -lt "$limit" ];do
        n=$((n+1))
        if [ "$1" = gui_ready ];then
            if ! regular "$r/ui.status";then sleep 1;continue;fi
            case "$(cat "$r/ui.status")" in
                ui-resident-*-failed*|ui-resident-pool-timeout*) return 1;;
                ui-resident-pool-pending*) sleep 1;continue;;
            esac
        fi
        "$1" 2>/dev/null && return 0
        sleep 1
    done
    return 1
}'''
        assert after.count(old)==1
        after=after.replace(old,new)
    if name=='install.sh':
        after=after.replace(b'if [ "$1" = preflight ];then',b'case "$health_result" in "ui-health-ready pid="*" system=2 power=0") ;; *) exit 62;;esac\nif [ "$1" = preflight ];then')
    return after
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(data):return hashlib.sha256(data).hexdigest()
def save(p,data):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
patch=load('full_ui_patch',HERE/'patch.py')
def build():
    if Path.cwd().resolve()!=ROOT:raise ValueError('workspace mismatch')
    values,factory=patch.resources();resource_dir=HERE/'build/resources';resource_dir.mkdir(parents=True,exist_ok=True)
    bundle=load('full_ui_rcc',CANDIDATE/'tools/resource_bundle.py').rcc(values)
    (resource_dir/'ui-resident.rcc').write_bytes(bundle)
    diffs=[]
    for path,value in values.items():
        target=resource_dir/path.lstrip('/');target.parent.mkdir(parents=True,exist_ok=True);target.write_text(value,encoding='utf-8')
        diffs.append(''.join(difflib.unified_diff(factory.get(path,'').splitlines(True),value.splitlines(True),fromfile='factory'+path,tofile='full-pages-r1'+path)))
    (resource_dir/'changes.patch').write_text(''.join(diffs),encoding='utf-8')
    manifest={'firmware':'X1D 1.25.0','guiSha256':patch.GUI_SHA,'rccSha256':digest(bundle),
        'resources':{p:patch.digest(v) for p,v in values.items()},'sourceResources':{p:patch.digest(factory.get(p,'')) for p in values},
        'sources':{p.relative_to(ROOT).as_posix():sha(p) for p in [Path(__file__),HERE/'patch.py',HERE/'qml/mainmenu/ResidentLoader.qml',CANDIDATE/'tools/resource_bundle.py']},'hardwareRequests':0}
    layout=('/main.qml','/common/TouchWindow.qml','/liveview/EVFWindow.qml')
    assert factory['/main.qml'].count('source: "qrc:///common/TouchWindow.qml"')==1
    assert factory['/main.qml'].count('source: "qrc:///liveview/EVFWindow.qml"')==1
    assert sum(v.count('source: guiconfig.mainMenuName') for v in factory.values())==1
    assert factory['/common/TouchWindow.qml'].count('source: guiconfig.mainMenuName')==1
    assert all(v not in factory['/liveview/EVFWindow.qml'] for v in ('MainScreen','mainMenuName','TouchWindow'))
    manifest['layoutProof']={'sourceSha256':{p:patch.digest(factory[p]) for p in layout},'mainScreenInstances':1,'menuPools':1,'EVFHasSeparateMenu':False,'method':'fixed factory QML source paths; actual target object counts still gated at boot'}
    save(resource_dir/'manifest.json',manifest)
    original=load('full_ui_native_parent',CANDIDATE/'session/build.py');original.fixed()
    package=load('full_ui_parent_package',CANDIDATE/'session/package.py');old_report,old_blob=package.verify()
    with tarfile.open(fileobj=io.BytesIO(old_blob)) as archive:old_files={m.name:archive.extractfile(m).read() for m in archive.getmembers()}
    for name in ('common.sh','install.sh','restore.sh','run.sh'):
        before=(CANDIDATE/'session'/name).read_bytes()
        if before!=old_files[name]:raise ValueError('original session changed '+name)
        after=shell(name,before)
        SESSION.mkdir(parents=True,exist_ok=True);(SESSION/name).write_bytes(after)
    extra_baseline=''.join(sha(original.BASELINE/('usr/lib/libQt5'+n+'.so.5.5.1'))+'  /usr/lib/libQt5'+n+'.so.5.5.1\n' for n in ('Quick','Gui'))
    (SESSION/'baseline.sha256').write_bytes(old_files['baseline.sha256']+extra_baseline.encode())
    native=SESSION/'native';native.mkdir(parents=True,exist_ok=True)
    source=(CANDIDATE/'session/native/runtime.cpp').read_text(encoding='utf-8')
    start=source.index('const Entry entries[]={');end=source.index('\n};',start)+3
    entries='const Entry entries[]={\n'+',\n'.join('    {"'+':'+p+'","'+manifest['resources'][p]+'"}' for p in values)+'\n};'
    source=source[:start]+entries+source[end:]
    source=source.replace(OLD_REMOTE,REMOTE).replace(original.RCC_SHA,digest(bundle)).replace('只注册固定四资源','只注册固定六资源')
    source=source.replace('    for(const Entry &e:entries) {\n        QQmlComponent','    for(const Entry &e:entries) {\n        if(!QString::fromLatin1(e.path).endsWith(QStringLiteral(".qml"))) continue;\n        QQmlComponent')
    source=source.replace('extern "C" bool ui_register(int,const', '#include "readiness.h"\nextern "C" bool ui_register(int,const',1)
    source=source.replace('    original(engine,url);\n    if(engine->rootObjects()', '    BootGate *gate = new BootGate(engine);\n    original(engine,url);\n    if(engine->rootObjects()')
    source=source.replace('    status("ui-resident-ready-resources4-components4");','    gate->start();')
    for name in ('gate_policy.h','readiness.h'):(native/name).write_bytes((HERE/'native'/name).read_bytes())
    catalog_path=CANDIDATE/'evaluation/full-pages/build/catalog.json'
    catalog=json.loads(catalog_path.read_text(encoding='utf-8'))
    page_keys=[v['settingsList'] for group in catalog['menus'] for v in group if not v.get('demo') and v['itemFile']=='qrc:///settings/SettingsGeneric.qml']
    assert len(page_keys)==len(set(page_keys))==23
    catalog_cpp='// 固定 GUI 的 MenuItemSpecificationsWedge.js 目录。\n'
    for name,keys in [('Menus',['camera','general','video']),('Pages',page_keys)]:
        catalog_cpp+='QSet<QString> expected'+name+'() { return QSet<QString>{'+','.join('QStringLiteral('+json.dumps(k)+')' for k in keys)+'}; }\n'
    (native/'catalog.h').write_text(catalog_cpp,encoding='utf-8')
    (native/'runtime.cpp').write_text(source,encoding='utf-8')
    (native/'health.cpp').write_bytes((CANDIDATE/'session/native/health.cpp').read_bytes())
    original_code=(CANDIDATE/'session/build.py').read_text(encoding='utf-8')
    assert original_code.count("('Qml','Core')")==1
    native_builder=types.ModuleType('full_ui_native_builder');native_builder.__file__=str(CANDIDATE/'session/build.py')
    original_code=original_code.replace("('Qml','Core')","('Quick','Qml','Gui','Core')").replace("'-Wno-deprecated-declarations'", "'-isystem',str(base/'include/QtANGLE'),'-Wno-deprecated-declarations'")
    exec(compile(original_code,native_builder.__file__,'exec'),native_builder.__dict__)
    original=native_builder;original.HERE=SESSION;original.OUT=OUT;original.RCC_SHA=digest(bundle)
    result=original.build();proof=json.loads((OUT/'native/build.json').read_text(encoding='utf-8'))
    proof['sources'].update(manifest['sources']);proof['sources'].update({p.relative_to(ROOT).as_posix():sha(p) for p in [catalog_path,*(HERE/'native'/n for n in ('gate_policy.h','readiness.h')),*(native/n for n in ('gate_policy.h','readiness.h','catalog.h'))]});proof['resourceManifestSha256']=sha(resource_dir/'manifest.json')
    angle=original.CACHE/'qt-public/qtbase-opensource-src-5.5.1/src/3rdparty/angle/include'
    proof['sources'].update({p.relative_to(ROOT).as_posix():sha(p) for p in (angle/'GLES2/gl2.h',angle/'GLES2/gl2platform.h',angle/'KHR/khrplatform.h')})
    save(OUT/'native/build.json',proof)
    save(OUT/'source-binding.json',{'parentPackageSha256':old_report['packageSha256'],'remoteRoot':REMOTE,'shellDelta':'remote root; real pool readiness marker; bounded 40s wait; installation requires active System2/Power0; baseline adds QtQuick/QtGui',
        'sources':{p.relative_to(ROOT).as_posix():sha(p) for p in [CANDIDATE/'session/native/runtime.cpp',CANDIDATE/'session/native/health.cpp',CANDIDATE/'session/build.py',*(SESSION/n for n in ('common.sh','install.sh','restore.sh','run.sh','baseline.sha256'))]},'hardwareRequests':0})
    return {'compiled':True,'resources':len(values),'rccSha256':digest(bundle),'outputs':result['outputs'],'hardwareRequests':0,'targetValidated':False}
if __name__=='__main__':print(json.dumps(build()))
