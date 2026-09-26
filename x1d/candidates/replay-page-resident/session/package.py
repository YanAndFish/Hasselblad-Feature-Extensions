"""冻结独立回放页会话包；默认只校验，本文件不含设备传输。"""
from pathlib import Path
import gzip,hashlib,importlib.util,io,json,sys,tarfile
sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('replay_page_session_build',Path(__file__).with_name('build.py'))
build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)
HERE=build.HERE;ROOT=build.ROOT;OUT=build.OUT
def digest(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def bound(root,values):
    for name,value in values.items():
        p=(root/name).resolve()
        if not p.is_relative_to(ROOT) or build.sha(p)!=value:raise ValueError('changed source '+name)
def install_proof(report):
    # 事务模型实际运行的四份 shell；native/传输/归档分别绑定各自证明。
    keys=[(HERE/n).relative_to(ROOT).as_posix() for n in ('common.sh','install.sh','restore.sh','run.sh')]
    bound(ROOT,{n:report['sources'][n] for n in keys})
    if build.sha(build.CANDIDATE/'CodeTests/test_session.py')!=report['testSha256']:raise ValueError('test changed')

def control_proof():
    report=read(OUT/'control-validation.json')
    if not report['passed'] or report['hardwareRequests']!=0:raise ValueError('control validation')
    for path,key in [(OUT/'native/replay-control','binarySha256'),(HERE/'native/control.cpp','sourceSha256'),(build.CANDIDATE/'CodeTests/test_control.py','testSha256')]:
        if build.sha(path)!=report[key]:raise ValueError('control proof changed')
def make():
    if Path.cwd().resolve()!=ROOT:raise ValueError('workspace mismatch')
    build.fixed();native=read(OUT/'native/build.json');validation=read(OUT/'install-validation.json')
    if not native['compiled'] or not validation['passed']:raise ValueError('offline checks not passed')
    bound(ROOT,native['sources']);install_proof(validation);control_proof()
    transfer=read(OUT/'transfer-validation.json')
    if not transfer['passed']:raise ValueError('transfer validation')
    bound(ROOT,transfer['sources'])
    files={n:(HERE/n).read_bytes() for n in ('common.sh','install.sh','restore.sh','run.sh')}
    for n in ('libhbl-replay-page.so','replay-health','replay-control'):
        p=OUT/'native'/n
        if build.sha(p)!=native['outputs'][n]['sha256']:raise ValueError('native changed')
        files[n]=p.read_bytes()
    files['replay-page.rcc']=(build.FIXED/'replay-page.rcc').read_bytes()
    baseline=set()
    for name in native['sources']:
        p=ROOT/name
        if p.is_relative_to(build.BASELINE):baseline.add(p)
    baseline.update(build.BASELINE/p for p in ('usr/bin/victory-gui','usr/lib/libappscommon.so.1.0.0'))
    msg=build.CACHE/'usb-diagnostic-inputs/usr/bin/msg2dbus'
    if build.sha(msg)!='988bf67864d09e6183b86b65a2e0ad5b60b18df84c2a06076da96ebff84d6eb1':raise ValueError('msg2dbus baseline changed')
    files['baseline.sha256']=(''.join(build.sha(p)+'  /'+p.relative_to(build.BASELINE).as_posix()+'\n' for p in sorted(baseline))+
        build.sha(msg)+'  /usr/bin/msg2dbus\n').encode()
    files['manifest.sha256']=''.join(digest(v)+'  '+n+'\n' for n,v in sorted(files.items())).encode()
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w',format=tarfile.USTAR_FORMAT) as archive:
        for n,v in sorted(files.items()):
            m=tarfile.TarInfo(n);m.size=len(v);m.mtime=0;m.mode=0o700 if n.endswith('.sh') or n in ('replay-health','replay-control') else 0o600
            archive.addfile(m,io.BytesIO(v))
    blob=gzip.compress(stream.getvalue(),compresslevel=9,mtime=0)
    folder=OUT/'packages'/digest(blob)[:16];folder.mkdir(parents=True,exist_ok=True)
    path=folder/'replay-page-session.tar.gz'
    if path.exists() and path.read_bytes()!=blob:raise ValueError('immutable package conflict')
    path.write_bytes(blob)
    with tarfile.open(path) as archive:
        if {m.name:archive.extractfile(m).read() for m in archive.getmembers()}!=files:raise ValueError('archive roundtrip')
    proofs=[Path(__file__),HERE/'delivery.py',OUT/'native/build.json',OUT/'install-validation.json',OUT/'transfer-validation.json',OUT/'control-validation.json',build.FIXED/'release.json',msg]
    report={'kind':'independent-replay-page-session','archive':path.relative_to(ROOT).as_posix(),'bytes':len(blob),'packageSha256':digest(blob),
        'files':{n:digest(v) for n,v in files.items()},'proofs':{p.relative_to(ROOT).as_posix():build.sha(p) for p in proofs},
        'rccSha256':build.RCC_SHA,'stages':['stage','preflight','ui','status','restore'],
        'hardwareRequests':0,'targetValidated':False,'installed':False,'farmWrites':0,'busRestarts':0,'otherModulesIncluded':False}
    build.save(folder/'package.json',report);build.save(OUT/'current.json',{'report':(folder/'package.json').relative_to(ROOT).as_posix()})
    return report
def verify():
    build.fixed();report=read(ROOT/read(OUT/'current.json')['report']);bound(ROOT,report['proofs'])
    native=read(OUT/'native/build.json');bound(ROOT,native['sources'])
    install_proof(read(OUT/'install-validation.json'));control_proof();bound(ROOT,read(OUT/'transfer-validation.json')['sources'])
    blob=(ROOT/report['archive']).read_bytes()
    if digest(blob)!=report['packageSha256'] or len(blob)!=report['bytes']:raise ValueError('archive changed')
    return report,blob
if __name__=='__main__':
    result=make() if sys.argv[1:]==['--build'] else verify()[0]
    print(json.dumps({k:result[k] for k in ('archive','packageSha256','bytes','targetValidated','hardwareRequests')}))
