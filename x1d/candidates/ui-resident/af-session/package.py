"""固定 AF r4 共存包；未拿到 AF owner 的确定修复产物时禁止发布为可装。"""
from pathlib import Path
import gzip,hashlib,importlib.util,io,json,shlex,sys,tarfile
sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('ui_af_session_build',Path(__file__).with_name('build.py'))
build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)
HERE=build.HERE;ROOT=build.ROOT;OUT=build.OUT
def digest(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def bound(values):
    for n,h in values.items():
        p=(ROOT/n).resolve()
        if not p.is_relative_to(ROOT) or build.sha(p)!=h:raise ValueError('dependency changed '+n)
def af_dropin(source,marker):
    lines=[v.strip() for v in source.decode().splitlines() if '> "$s/'+marker+'"' in v and v.strip().startswith('printf ')]
    if len(lines)!=1:raise ValueError('AF drop-in generating statement')
    words=shlex.split(lines[0]);words=words[:words.index('>')]
    if words[:2]!=['printf','%s\\n']:raise ValueError('AF printf contract')
    return ('\n'.join(v.replace('$r',build.OLD) for v in words[2:])+'\n').encode()
def validate_inputs():
    binding,r4=build.r4_inputs(required=True);af,_=build.inputs()
    resources=read(OUT/'resources/manifest.json');native=read(OUT/'native/build.json')
    tests=[read(OUT/n) for n in ('qml-validation.json','install-validation.json','transfer-validation.json')]
    if not resources['r4Bound'] or resources['r4ArchiveSha256']!=binding['archiveSha256'] or not native['compiled'] or not all(t['passed'] for t in tests):raise ValueError('r4 tests incomplete')
    bound(resources['sources']);bound(native['sources']);bound(tests[1]['sources']);bound(tests[2]['sources'])
    if native['resourcesSha256']!=build.sha(OUT/'resources/manifest.json') or tests[0]['resourcesManifestSha256']!=build.sha(OUT/'resources/manifest.json'):raise ValueError('resource report changed')
    for test,name in zip(tests[:2],('test_af_coexist_qml.py','test_af_coexist_install.py')):
        if test['testSha256']!=build.sha(build.CANDIDATE/'CodeTests'/name):raise ValueError('test changed')
    if tests[0]['rccSha256']!=resources['rccSha256'] or build.sha(OUT/'native/libhbl-ui-af.so')!=native['sha256'] or build.sha(OUT/'native/ui-health')!=native['healthSha256']:raise ValueError('generated payload changed')
    return binding,r4,af,resources,native
def make():
    if Path.cwd().resolve()!=ROOT:raise ValueError('workspace mismatch')
    binding,r4,af,resources,native=validate_inputs()
    files={n:(HERE/n).read_bytes() for n in ('common.sh','install.sh','restore.sh','run.sh')}
    files.update({'ui-af.rcc':(OUT/'resources/ui-af.rcc').read_bytes(),'libhbl-ui-af.so':(OUT/'native/libhbl-ui-af.so').read_bytes(),'ui-health':(OUT/'native/ui-health').read_bytes()})
    old=build.load_module('original_ui_session_package',build.CANDIDATE/'session/package.py');old_report,old_blob=old.verify()
    with tarfile.open(fileobj=io.BytesIO(old_blob)) as archive:files['baseline.sha256']=archive.extractfile('baseline.sha256').read()
    files['af-gui.expected']=af_dropin(af['install.sh'],'gui.dropin')
    files['af-bus.expected']=af_dropin(af['install.sh'],'farm.dropin')
    files['r4-gui.expected']=binding['guiDropinText'].encode()
    if not files['r4-gui.expected'].endswith(b'\n') or b'\r' in files['r4-gui.expected'] or build.OLD_PRELOAD.encode() not in files['r4-gui.expected']:raise ValueError('r4 drop-in contract')
    files['af-receipt.expected']=(build.AF_PROOF+'\n').encode()
    inherited={build.OLD+'/'+n:digest(v) for n,v in af.items()}
    inherited.update({binding['remoteRoot']+'/'+n:digest(v) for n,v in r4.items()})
    files['inherited.sha256']=''.join(h+'  '+n+'\n' for n,h in sorted(inherited.items())).encode()
    files['manifest.sha256']=''.join(digest(v)+'  '+n+'\n' for n,v in sorted(files.items())).encode()
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w',format=tarfile.USTAR_FORMAT) as archive:
        for n,v in sorted(files.items()):
            m=tarfile.TarInfo(n);m.size=len(v);m.mtime=0;m.mode=0o700 if n.endswith('.sh') or n=='ui-health' else 0o600
            archive.addfile(m,io.BytesIO(v))
    blob=gzip.compress(stream.getvalue(),compresslevel=9,mtime=0)
    directory=OUT/'packages'/digest(blob)[:16];directory.mkdir(parents=True,exist_ok=True)
    path=directory/'ui-af-session.tar.gz'
    if path.exists() and path.read_bytes()!=blob:raise ValueError('frozen path conflict')
    path.write_bytes(blob)
    with tarfile.open(path) as archive:
        if {m.name:archive.extractfile(m).read() for m in archive.getmembers()}!=files:raise ValueError('archive roundtrip')
    proofs=[Path(__file__),HERE/'delivery.py',HERE/'r4-binding.json',OUT/'native/build.json',OUT/'resources/manifest.json',
        OUT/'qml-validation.json',OUT/'install-validation.json',OUT/'transfer-validation.json',ROOT/old_report['archive']]
    report={'kind':'ui-resident-on-af-r4','archive':path.relative_to(ROOT).as_posix(),'bytes':len(blob),'packageSha256':digest(blob),
        'files':{n:digest(v) for n,v in files.items()},'proofs':{p.relative_to(ROOT).as_posix():build.sha(p) for p in proofs},
        'afArchiveSha256':build.AF_SHA,'r4ArchiveSha256':binding['archiveSha256'],'rccSha256':resources['rccSha256'],
        'preload':build.NEW_PRELOAD,'recoveryPreload':build.OLD_PRELOAD,'remoteRoot':build.REMOTE,
        'hardwareRequests':0,'farmMemoryWrites':0,'busRestarts':0,'afLogicChanged':False,'targetValidated':False,'installed':False}
    build.save(directory/'package.json',report);build.save(OUT/'current.json',{'report':(directory/'package.json').relative_to(ROOT).as_posix()})
    return report
def verify():
    validate_inputs();report=read(ROOT/read(OUT/'current.json')['report']);bound(report['proofs'])
    blob=(ROOT/report['archive']).read_bytes()
    if digest(blob)!=report['packageSha256'] or len(blob)!=report['bytes']:raise ValueError('archive changed')
    return report,blob
if __name__=='__main__':
    r=make() if sys.argv[1:]==['--build'] else verify()[0]
    print(json.dumps({k:r[k] for k in ('archive','packageSha256','bytes','targetValidated','hardwareRequests')}))
