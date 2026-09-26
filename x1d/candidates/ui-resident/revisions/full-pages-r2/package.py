"""冻结独立 r2 诊断包；默认只离线核验。"""
from pathlib import Path
import gzip,hashlib,io,json,sys,tarfile
sys.dont_write_bytecode=True
import importlib.util
spec=importlib.util.spec_from_file_location('full_ui_r2_build',Path(__file__).with_name('build.py'))
build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)
ROOT=build.ROOT;HERE=build.SESSION;OUT=build.OUT;REV=build.HERE
PROOFS=('build/resources/manifest.json','build/session/native/build.json','build/reuse-validation.json','build/diagnostic-validation.json','build/meta-enum-validation.json','build/session/install-validation.json','build/session/transfer-validation.json')
def digest(data):return hashlib.sha256(data).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8'))
def bound(values):
    for name,value in values.items():
        path=(ROOT/name).resolve()
        if not path.is_relative_to(ROOT) or build.sha(path)!=value:raise ValueError('source changed: '+name)
def evidence():
    manifest=read(REV/'build/resources/manifest.json');native=read(OUT/'native/build.json')
    if not native['compiled'] or manifest['rccSha256']!=build.RCC_SHA:raise ValueError('build proof')
    for name in PROOFS:
        report=read(REV/name)
        if name.endswith('build.json'):
            if not report['compiled']:raise ValueError(name)
        elif not name.endswith('manifest.json') and not report['passed']:raise ValueError(name)
        if report.get('hardwareRequests',0)!=0:raise ValueError('unexpected hardware proof')
        bound(report.get('sources',{}))
    for name,entry in native['outputs'].items():
        if build.sha(OUT/'native'/name)!=entry['sha256']:raise ValueError('native changed')
    if build.sha(REV/'build/resources/ui-resident.rcc')!=build.RCC_SHA:raise ValueError('RCC changed')
    return manifest,native
def make():
    if Path.cwd().resolve()!=ROOT:raise ValueError('workspace mismatch')
    manifest,native=evidence()
    files={name:(HERE/name).read_bytes() for name in ('common.sh','install.sh','restore.sh','run.sh','baseline.sha256')}
    files.update({name:(OUT/'native'/name).read_bytes() for name in ('libhbl-ui-resident.so','ui-health')})
    files['ui-resident.rcc']=(REV/'build/resources/ui-resident.rcc').read_bytes()
    files['manifest.sha256']=''.join(digest(value)+'  '+name+'\n' for name,value in sorted(files.items())).encode()
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w',format=tarfile.USTAR_FORMAT) as archive:
        for name,data in sorted(files.items()):
            member=tarfile.TarInfo(name);member.size=len(data);member.mtime=0;member.mode=0o700 if name.endswith('.sh') or name=='ui-health' else 0o600
            archive.addfile(member,io.BytesIO(data))
    blob=gzip.compress(stream.getvalue(),compresslevel=9,mtime=0)
    folder=OUT/'packages'/digest(blob)[:16];folder.mkdir(parents=True,exist_ok=True);archive=folder/'ui-full-pages-diagnostic-r2.tar.gz'
    if archive.exists() and archive.read_bytes()!=blob:raise ValueError('immutable conflict')
    archive.write_bytes(blob)
    report={'kind':'independent-full-pages-diagnostic-r2','archive':archive.relative_to(ROOT).as_posix(),'packageSha256':digest(blob),'bytes':len(blob),
        'files':{name:digest(data) for name,data in files.items()},'resources':manifest['resources'],'rccSha256':build.RCC_SHA,'remoteRoot':build.REMOTE,
        'proofs':{p.relative_to(ROOT).as_posix():build.sha(p) for p in [Path(__file__),REV/'build.py',REV/'delivery.py',*(REV/name for name in PROOFS)]},
        'hardwareRequests':0,'targetValidated':False,'installed':False,'persistent':False,'otherModulesIncluded':False,
        'changeFromR1':'public Loader.item collector and ui.diag fixed-key numeric snapshot; QML/JS RCC identical',
        'readiness':{'menus':3,'ordinaryPages':23,'allRowsRequired':True,'deadlineMs':30000,'stableSamples':3,'intervalMs':200,'successMarker':build.READY}}
    build.save(folder/'package.json',report);build.save(OUT/'current.json',{'report':(folder/'package.json').relative_to(ROOT).as_posix()});verify();return report
def verify():
    report=read(ROOT/read(OUT/'current.json')['report']);bound(report['proofs']);evidence();blob=(ROOT/report['archive']).read_bytes()
    if digest(blob)!=report['packageSha256'] or len(blob)!=report['bytes']:raise ValueError('archive changed')
    with tarfile.open(fileobj=io.BytesIO(blob)) as archive:
        members=archive.getmembers()
        if len(members)!=9 or {v.name for v in members}!=set(report['files']):raise ValueError('members')
        for member in members:
            data=archive.extractfile(member).read()
            if not member.isfile() or member.uid or member.gid or member.mtime or digest(data)!=report['files'][member.name]:raise ValueError('member')
            if member.name.endswith('.sh') and b'\r' in data:raise ValueError('CRLF')
    return report,blob
if __name__=='__main__':
    report=make() if sys.argv[1:]==['--build'] else verify()[0]
    print(json.dumps({k:report[k] for k in ('packageSha256','bytes','archive','targetValidated','hardwareRequests')}))
