"""独立全页 UI 包：冻结前绑定离线证据；默认只校验，不接触设备。"""
from pathlib import Path
import gzip,hashlib,io,json,sys,tarfile
sys.dont_write_bytecode=True
import importlib.util
spec=importlib.util.spec_from_file_location('full_ui_build',Path(__file__).with_name('build.py'))
build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)
ROOT=build.ROOT;HERE=build.SESSION;OUT=build.OUT;REV=build.HERE
PROOFS=('build/resources/manifest.json','build/session/native/build.json','build/qml-validation.json','build/race-validation.json','build/readiness-validation.json','build/qt55-identifiers.json','build/session/install-validation.json','build/session/transfer-validation.json','build/memory-summary.json')
def digest(data):return hashlib.sha256(data).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8'))
def bound(values):
    for name,value in values.items():
        path=(ROOT/name).resolve()
        if not path.is_relative_to(ROOT) or build.sha(path)!=value:raise ValueError('source changed: '+name)
def evidence():
    resources={k:build.patch.digest(v) for k,v in build.patch.resources()[0].items()}
    for name in PROOFS:
        report=read(REV/name)
        if name.endswith('build.json'):
            if not report['compiled']:raise ValueError('not compiled')
        elif not name.endswith('manifest.json'):
            if not report['passed']:raise ValueError('not passed: '+name)
        if report.get('hardwareRequests',0)!=0:raise ValueError('unexpected device proof')
        bound(report.get('sources',{}))
        if 'resources' in report and report['resources']!=resources:raise ValueError('resource proof changed: '+name)
    native=read(OUT/'native/build.json')
    for name,entry in native['outputs'].items():
        if build.sha(OUT/'native'/name)!=entry['sha256']:raise ValueError('native output changed')
    manifest=read(REV/'build/resources/manifest.json')
    if build.sha(REV/'build/resources/ui-resident.rcc')!=manifest['rccSha256']:raise ValueError('RCC changed')
    return native,manifest
def make():
    if Path.cwd().resolve()!=ROOT:raise ValueError('workspace mismatch')
    native,manifest=evidence()
    files={n:(HERE/n).read_bytes() for n in ('common.sh','install.sh','restore.sh','run.sh','baseline.sha256')}
    files.update({n:(OUT/'native'/n).read_bytes() for n in ('libhbl-ui-resident.so','ui-health')})
    files['ui-resident.rcc']=(REV/'build/resources/ui-resident.rcc').read_bytes()
    files['manifest.sha256']=''.join(digest(v)+'  '+n+'\n' for n,v in sorted(files.items())).encode()
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w',format=tarfile.USTAR_FORMAT) as archive:
        for name,data in sorted(files.items()):
            member=tarfile.TarInfo(name);member.size=len(data);member.mtime=0;member.mode=0o700 if name.endswith('.sh') or name=='ui-health' else 0o600
            archive.addfile(member,io.BytesIO(data))
    blob=gzip.compress(stream.getvalue(),compresslevel=9,mtime=0)
    folder=OUT/'packages'/digest(blob)[:16];folder.mkdir(parents=True,exist_ok=True)
    archive=folder/'ui-full-pages-session.tar.gz'
    if archive.exists() and archive.read_bytes()!=blob:raise ValueError('immutable archive conflict')
    archive.write_bytes(blob)
    report={'kind':'independent-full-pages-ui-r1','archive':archive.relative_to(ROOT).as_posix(),'packageSha256':digest(blob),'bytes':len(blob),
        'files':{n:digest(v) for n,v in files.items()},'resources':manifest['resources'],'rccSha256':manifest['rccSha256'],'remoteRoot':build.REMOTE,
        'proofs':{p.relative_to(ROOT).as_posix():build.sha(p) for p in [Path(__file__),REV/'build.py',REV/'delivery.py',*(REV/n for n in PROOFS)]},
        'hardwareRequests':0,'targetValidated':False,'installed':False,'otherModulesIncluded':False,'persistent':False,
        'readiness':{'menus':3,'ordinaryPages':23,'allRowsRequired':True,'deadlineMs':30000,'stableSamples':3,'intervalMs':200,'installSystem':2,'installPower':0}}
    build.save(folder/'package.json',report);build.save(OUT/'current.json',{'report':(folder/'package.json').relative_to(ROOT).as_posix()})
    verify();return report
def verify():
    report=read(ROOT/read(OUT/'current.json')['report']);bound(report['proofs']);evidence()
    blob=(ROOT/report['archive']).read_bytes()
    if digest(blob)!=report['packageSha256'] or len(blob)!=report['bytes']:raise ValueError('archive changed')
    with tarfile.open(fileobj=io.BytesIO(blob)) as archive:
        members=archive.getmembers()
        if len(members)!=9 or {m.name for m in members}!=set(report['files']):raise ValueError('archive members')
        for member in members:
            if not member.isfile() or member.uid or member.gid or member.mtime:raise ValueError('archive metadata')
            data=archive.extractfile(member).read()
            if digest(data)!=report['files'][member.name]:raise ValueError('archive member hash')
            if member.name.endswith('.sh') and b'\r' in data:raise ValueError('CRLF shell')
    return report,blob
if __name__=='__main__':
    report=make() if sys.argv[1:]==['--build'] else verify()[0]
    print(json.dumps({k:report[k] for k in ('packageSha256','bytes','archive','targetValidated','hardwareRequests')}))
