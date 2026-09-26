"""针对已安装 f325 AF 会话的四资源增量；只写 ui-resident 内的新版本。"""
from pathlib import Path
import hashlib,importlib.util,io,json,os,struct,subprocess,sys,tarfile,zlib
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;CANDIDATE=HERE.parent;ROOT=CANDIDATE.parents[2]
OUT=CANDIDATE/'build/af-session';CACHE=ROOT/'.research-cache/x1d-1.25.0'
AF=ROOT/'x1d/combined-runtime/af-only'
AF_ARCHIVE=AF/'build/package/f325db70de366f52/af-only.tar.gz'
AF_SHA='f325db70de366f52ae3b58b98f8e9fd3e496f353dbab64c6ca4712a49064cc6a'
AF_RCC_SHA='dc63f7162f4794faca80b60b206ac1c17f58b3a402730ac5ab6e43a209be0040'
AF_MANIFEST_SHA='79da1a75552717936fbad737d8d4532c489907a7e02197e4acd0605f43c63b05'
AF_PROOF='b17e63af75ea9ee026a20a362b0b0cc7d4dfc5872d9a50120c45073550db114b'
INSTALL=ROOT/'x1d/af-experiment/camera-settings-r1/delivery-r3/build/sessions/af-only-install-20260912T165707900998Z/installation.json'
INSTALL_SHA='3887d348751c596c5a1d1cf71ef1201750ab2cd330a0ef823149a259add97929'
FIXED=CANDIDATE/'build/fixed/ui-resident-0456d37bc5ddbc57'
REMOTE='/tmp/hbl-ui-af'
OLD='/tmp/hbl-x1d-combined'
OLD_PRELOAD=OLD+'/libhbl-af-only.so:/tmp/hbl-af-ui-r4/libhbl-af-ui.so'
NEW_PRELOAD=REMOTE+'/libhbl-ui-af.so:'+OLD_PRELOAD
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(b):return hashlib.sha256(b).hexdigest()
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode())
def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
def original_session():return load_module('ui_original_session_build',CANDIDATE/'session/build.py')
def r4_inputs(required=False):
    path=HERE/'r4-binding.json'
    if not path.exists():
        if required:raise ValueError('AF owner r4 fixed delivery required before packaging')
        return None,{}
    binding=json.loads(path.read_text(encoding='utf-8'));archive_path=(ROOT/binding['archive']).resolve()
    if not archive_path.is_relative_to(ROOT) or sha(archive_path)!=binding['archiveSha256']:raise ValueError('r4 archive changed')
    with tarfile.open(archive_path) as archive:
        members=archive.getmembers()
        if any(not (m.isfile() or m.isdir()) or m.name.startswith('/') or '..' in Path(m.name).parts for m in members):raise ValueError('r4 archive member')
        files={m.name:archive.extractfile(m).read() for m in members if m.isfile()}
    if {n:digest(v) for n,v in files.items()}!=binding['files']:raise ValueError('r4 member digest mismatch')
    if binding['remoteRoot']!='/tmp/hbl-af-ui-r4':raise ValueError('r4 namespace changed')
    if files['95-hbl-af-ui-r4.conf']!=binding['guiDropinText'].encode() or sha(ROOT/binding['validation'])!=binding['validationSha256']:raise ValueError('r4 fixed contract changed')
    return binding,files
def read_rcc(data):
    if data[:8]!=b'qres\0\0\0\1':raise ValueError('RCC v1 required')
    tree,payload,names=struct.unpack_from('>III',data,8);result={};visited=set()
    def walk(index,parent):
        if index in visited:raise ValueError('cyclic RCC tree')
        visited.add(index);at=tree+index*14
        name_at,flags=struct.unpack_from('>IH',data,at)
        length=struct.unpack_from('>H',data,names+name_at)[0]
        name=data[names+name_at+6:names+name_at+6+length*2].decode('utf-16-be')
        if index and (not name or name in ('.','..') or '/' in name):raise ValueError('RCC name')
        path=parent+'/'+name if index else ''
        if flags&2:
            count,first=struct.unpack_from('>II',data,at+6)
            for child in range(first,first+count):walk(child,path)
        else:
            offset=struct.unpack_from('>I',data,at+10)[0];size=struct.unpack_from('>I',data,payload+offset)[0]
            raw=data[payload+offset+4:payload+offset+4+size]
            if len(raw)!=size:raise ValueError('RCC length')
            if flags&1:
                expected=struct.unpack_from('>I',raw)[0];raw=zlib.decompress(raw[4:])
                if len(raw)!=expected:raise ValueError('RCC decompression length')
            if path in result:raise ValueError('duplicate RCC resource')
            result[path]=raw.decode('utf-8')
    walk(0,'');return result
def inputs():
    if Path.cwd().resolve()!=ROOT:raise ValueError('workspace mismatch')
    original_session().fixed()
    if sha(AF_ARCHIVE)!=AF_SHA or sha(INSTALL)!=INSTALL_SHA:raise ValueError('fixed AF installation changed')
    installed=json.loads(INSTALL.read_text(encoding='utf-8'))
    if not all(installed.get(k) for k in ('completed','afInstalled','holdReleased','allHandlesClosed','afHandlesClosed')) or installed['packageSha256']!=AF_SHA:raise ValueError('AF completion proof')
    if sha(ROOT/installed['afRecovery'])!=AF_PROOF:raise ValueError('AF receipt changed')
    with tarfile.open(AF_ARCHIVE) as archive:
        files={m.name:archive.extractfile(m).read() for m in archive.getmembers() if m.isfile()}
    if digest(files['manifest.sha256'])!=AF_MANIFEST_SHA or digest(files['af-only-ui.rcc'])!=AF_RCC_SHA:raise ValueError('AF payload changed')
    for line in files['manifest.sha256'].decode().splitlines():
        expected,name=line.split()
        if digest(files[name])!=expected:raise ValueError('AF manifest member')
    resources=read_rcc(files['af-only-ui.rcc'])
    manifest=json.loads((AF/'build/resources/manifest.json').read_text(encoding='utf-8'))
    if {k:digest(v.encode()) for k,v in resources.items()}!=manifest['qml'] or len(resources)!=7:raise ValueError('AF QML provenance')
    binding,r4=r4_inputs()
    if binding:
        updated=read_rcc(r4['af-only-ui.rcc'])
        if set(updated)!=set(resources) or any(updated[k]!=v for k,v in resources.items() if k!='/af-settings/SettingsPage.qml'):raise ValueError('r4 scope differs from agreed contract')
        resources=updated
    return files,resources
def resources():
    files,af=inputs();sys.path.insert(0,str(CANDIDATE/'tools'))
    ui=load_module('ui_resident_compose_for_af',CANDIDATE/'tools/build.py')
    if sha(CANDIDATE/'tools/build.py')!='915fdf996a40dc88a319c431a5b0402b9d37e2598de09470624e45d829002753':raise ValueError('compose source changed')
    combined=ui.compose(af);delta={k:combined[k] for k in (*ui.PATHS,'/mainmenu/ResidentLoader.qml')}
    if len(combined)!=10 or any(combined[k]!=v for k,v in af.items() if k!='/settings/SettingsGeneric.qml'):raise ValueError('AF resource changed')
    for name in ('/mainmenu/MainScreen.qml','/mainmenu/Menu.qml','/mainmenu/ResidentLoader.qml'):
        if delta[name].encode()!=(FIXED/'overlay'/name.lstrip('/')).read_bytes():raise ValueError('resident scope expanded')
    generic=delta['/settings/SettingsGeneric.qml']
    for anchor in ('case "cameraSettingsAdvancedAF":','item.afCloseRequested.connect(subDialog.closeSubDialog);'):
        if generic.count(anchor)!=1:raise ValueError('AF generic navigation lost')
    directory=OUT/'resources';directory.mkdir(parents=True,exist_ok=True)
    blob=ui.rcc(delta);(directory/'ui-af.rcc').write_bytes(blob)
    binding,r4=r4_inputs()
    effective_af=r4['af-only-ui.rcc'] if binding else files['af-only-ui.rcc']
    (directory/'af-only-ui.rcc').write_bytes(effective_af)
    for key,value in combined.items():
        path=directory/'effective'/key.lstrip('/');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(value.encode())
    src=[Path(__file__),CANDIDATE/'tools/build.py',CANDIDATE/'tools/resource_bundle.py',CANDIDATE/'qml/mainmenu/ResidentLoader.qml',AF_ARCHIVE,INSTALL,AF/'build/resources/manifest.json']
    if binding:src.extend([HERE/'r4-binding.json',ROOT/binding['archive'],ROOT/binding['validation']])
    report={'afArchiveSha256':AF_SHA,'afRccSha256':digest(effective_af),'r4Bound':bool(binding),'r4ArchiveSha256':binding['archiveSha256'] if binding else None,'rccSha256':digest(blob),'bytes':len(blob),
        'afResources':{k:digest(v.encode()) for k,v in af.items()},'effectiveResources':{k:digest(v.encode()) for k,v in combined.items()},
        'deltaResources':{k:digest(v.encode()) for k,v in delta.items()},'resourceCount':10,'overlap':['/settings/SettingsGeneric.qml'],
        'sources':{p.relative_to(ROOT).as_posix():sha(p) for p in src},'hardwareRequests':0,'targetValidated':False}
    save(directory/'manifest.json',report)
    header='// 自动生成：固定最终资源摘要。\nstatic const char rccSha[]="'+digest(blob)+'";\nstatic const char afRccSha[]="'+digest(effective_af)+'";\nstatic const Entry entries[]={\n'+''.join('    {":'+k+'","'+v+'"},\n' for k,v in sorted(report['effectiveResources'].items()))+'};\n'
    (directory/'resources.h').write_bytes(header.encode())
    return report
def native():
    report=resources();out=OUT/'native';out.mkdir(parents=True,exist_ok=True)
    base=original_session();old=json.loads((base.OUT/'native/build.json').read_text(encoding='utf-8'))
    source=HERE/'native/runtime.cpp';layout=out/'relocations.ld'
    layout.write_bytes(b'SECTIONS { .rel.dyn : { *(.rel.dyn) } .rel.plt : { *(.rel.plt) } } INSERT BEFORE .ARM.exidx;\n')
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
    for key,name in [('ZIG_GLOBAL_CACHE_DIR','global-cache'),('ZIG_LOCAL_CACHE_DIR','local-cache'),('TEMP','tmp'),('TMP','tmp')]:
        d=out/name;d.mkdir(exist_ok=True);env[key]=str(d)
    mapping={str(base.HERE/'native/runtime.cpp'):str(source),str(base.OUT/'native/libhbl-ui-resident.o'):str(out/'runtime.o'),
        str(base.OUT/'native/libhbl-ui-resident.so'):str(out/'libhbl-ui-af.so'),'-Wl,-soname,libhbl-ui-resident.so':'-Wl,-soname,libhbl-ui-af.so',
        '-Wl,-T,'+str(base.OUT/'native/relocations.ld'):'-Wl,-T,'+str(layout)}
    commands=[]
    for item in old['commands'][:2]:
        args=[mapping.get(v,v) for v in item['arguments']]
        if args[0]=='c++':args+=['-I',str(OUT/'resources')]
        result=subprocess.run([str(CACHE/'toolchain/zig-windows-x86_64-0.13.0/zig.exe')]+args,env=env,capture_output=True,text=True,timeout=60)
        commands.append({'arguments':args,'exit':result.returncode,'stderr':result.stderr})
        if result.returncode:raise RuntimeError(result.stderr)
    sys.path.insert(0,str(CACHE/'python'));from elftools.elf.elffile import ELFFile
    binary=out/'libhbl-ui-af.so';elf=ELFFile(io.BytesIO(binary.read_bytes()))
    rel=elf.get_section_by_name('.rel.dyn');plt=elf.get_section_by_name('.rel.plt')
    assert elf.elfclass==32 and elf['e_machine']=='EM_ARM' and rel['sh_addr']+rel['sh_size']==plt['sh_addr']
    dependency_sources={k:v for k,v in old['sources'].items() if (ROOT/k).is_relative_to(base.BASELINE)}
    if sha(base.OUT/'native/ui-health')!=old['outputs']['ui-health']['sha256']:raise ValueError('health binary changed')
    (out/'ui-health').write_bytes((base.OUT/'native/ui-health').read_bytes())
    proof={'compiled':True,'sha256':sha(binary),'bytes':binary.stat().st_size,'healthSha256':sha(out/'ui-health'),
        'resourcesSha256':sha(OUT/'resources/manifest.json'),'sources':{**dependency_sources,source.relative_to(ROOT).as_posix():sha(source),
        Path(__file__).relative_to(ROOT).as_posix():sha(Path(__file__)),(base.OUT/'native/build.json').relative_to(ROOT).as_posix():sha(base.OUT/'native/build.json')},
        'commands':commands,'relocationsContiguous':True,'hardwareRequests':0,'targetValidated':False}
    save(out/'build.json',proof);return {'compiled':True,'librarySha256':sha(binary),'deltaSha256':report['rccSha256'],'deltaBytes':report['bytes'],'hardwareRequests':0}
if __name__=='__main__':print(json.dumps(native()))
