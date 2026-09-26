"""将已通过检查的 AF 独立 Linux 资源冻结成小包；不包含其他模块。"""
from pathlib import Path
import gzip,hashlib,io,json,sys,tarfile
sys.dont_write_bytecode=True
import build
HERE=build.HERE;ROOT=build.ROOT;AF=build.AF
def digest(data):return hashlib.sha256(data).hexdigest()
def sha(path):return digest(path.read_bytes())
def read(path):return json.loads(path.read_text(encoding='utf-8'))
def bind(root,values):
    for name,value in values.items():
        path=(root/name).resolve()
        if not path.is_relative_to(ROOT) or sha(path)!=value:raise ValueError('changed '+name)
def make():
    if Path.cwd().resolve()!=ROOT:raise RuntimeError('workspace mismatch')
    sys.path.insert(0,str(AF));from af_only_bus_r2_loader import runtime as af_only_loader
    af=af_only_loader.readiness()
    if not af:raise ValueError('AF standalone readiness')
    qml=read(HERE/'build/resources/manifest.json');native=read(HERE/'build/native/build.json')
    tests=[read(HERE/'CodeTests/output'/name) for name in ('resources.json','install.json')]
    if not all(t['passed'] for t in tests) or tests[0]['rccSha256']!=qml['rccSha256']:raise ValueError('validation mismatch')
    for report,key in [(qml,'sourceHashes'),(native,'sources'),(tests[0],'sourceHashes'),(tests[1],'sources')]:bind(ROOT,report[key])
    for test,name in zip(tests,('test_resources.py','test_install.py')):
        if test['testSha256']!=sha(HERE/'CodeTests'/name):raise ValueError('test source changed')
    if qml['resourceCount']!=7 or not qml['factoryMainPreserved'] or not qml['factorySettingsPreserved'] or not qml['factoryControlsPreserved'] or not native['compiled']:raise ValueError('independent build')
    files={name:(HERE/name).read_bytes() for name in ('common.sh','install.sh','restore.sh','run.sh')}
    if af.get('revision')!='af-only-bus-startup-r2':raise ValueError('AF bus startup revision')
    for key,name in [('runtimeUi','libhbl-af-ui.so'),('runtimeBus','libhbl-af-bus.so')]:
        path=(AF/af[key]['path']).resolve()
        if not path.is_relative_to(AF) or sha(path)!=af[key]['sha256']:raise ValueError('AF runtime identity')
        files['af/'+name]=path.read_bytes()
    files['libhbl-af-only.so']=(HERE/'build/native/libhbl-af-only.so').read_bytes()
    files['af-only-ui.rcc']=(HERE/'build/resources/af-only-ui.rcc').read_bytes()
    fixed=HERE.parent/'build/fixed/install-window-e373262db5b23f56'
    for name in ('system-check','hold-file.check'):files[name]=(fixed/name).read_bytes()
    if digest(files['system-check'])!='e373262db5b23f567b22060f1a61687c723cbbbae3c1e237e60728015d3ccca0':raise ValueError('checker')
    if digest(files['libhbl-af-only.so'])!=native['sha256'] or digest(files['af-only-ui.rcc'])!=qml['rccSha256']:raise ValueError('binaries changed')
    files['baseline.sha256']=('d29c62402091c3ad40f6f247c03ce55f248ca79e92531889b1670edeb014ed9b  /usr/bin/victory-gui\n'
        '2d834be366ba5a78cf370e679f28a5bb171b8dc5944fe2f69e81c2a170ddc263  /usr/lib/libappscommon.so.1.0.0\n'
        '988bf67864d09e6183b86b65a2e0ad5b60b18df84c2a06076da96ebff84d6eb1  /usr/bin/msg2dbus\n').encode()
    files['manifest.sha256']=''.join(digest(data)+'  '+name+'\n' for name,data in sorted(files.items())).encode()
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w',format=tarfile.USTAR_FORMAT) as archive:
        directory=tarfile.TarInfo('af');directory.type=tarfile.DIRTYPE;directory.mode=0o700;directory.mtime=0;archive.addfile(directory)
        for name,data in sorted(files.items()):
            member=tarfile.TarInfo(name);member.size=len(data);member.mtime=0
            member.mode=0o700 if name.endswith('.sh') or name=='system-check' else 0o600
            archive.addfile(member,io.BytesIO(data))
    blob=gzip.compress(stream.getvalue(),compresslevel=9,mtime=0)
    directory=HERE/'build/package'/digest(blob)[:16];directory.mkdir(parents=True,exist_ok=True)
    path=directory/'af-only.tar.gz';path.write_bytes(blob)
    with tarfile.open(path) as archive:
        if {m.name:archive.extractfile(m).read() for m in archive.getmembers() if m.isfile()}!=files:raise ValueError('archive roundtrip')
    proofs=[Path(__file__),AF/'build/af-only-bus-r2-validation.json',HERE/'build/resources/manifest.json',HERE/'build/native/build.json',HERE/'CodeTests/output/resources.json',HERE/'CodeTests/output/install.json']
    report={'kind':'af-only-fixed-package','archive':path.relative_to(ROOT).as_posix(),'packageSha256':digest(blob),'bytes':len(blob),
        'files':{k:digest(v) for k,v in files.items()},'proofs':{p.relative_to(ROOT).as_posix():sha(p) for p in proofs},
        'flashIncluded':False,'replayIncluded':False,'residentUiIncluded':False,'afTimingActionsConnected':False,'hardwareRequests':0,'installed':False}
    build.save(directory/'package.json',report);build.save(HERE/'build/package/current.json',{'report':(directory/'package.json').relative_to(ROOT).as_posix()})
    return report
def verify():
    report=read(ROOT/read(HERE/'build/package/current.json')['report']);bind(ROOT,report['proofs'])
    # 当前 AF 完整来源再次核验。
    sys.path.insert(0,str(AF));from af_only_bus_r2_loader import runtime as af_only_loader
    if not af_only_loader.readiness():raise ValueError('AF source changed')
    data=(ROOT/report['archive']).read_bytes()
    if digest(data)!=report['packageSha256'] or len(data)!=report['bytes']:raise ValueError('archive changed')
    return report,data
if __name__=='__main__':
    r=make();print(json.dumps({k:r[k] for k in ('packageSha256','bytes','hardwareRequests')}))
