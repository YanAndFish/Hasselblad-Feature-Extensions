"""冻结组合总包；仅本地文件与已验证报告，不连接设备。"""
from pathlib import Path, PurePosixPath
import gzip
import hashlib
import io
import json
import sys
import tarfile

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
AF=ROOT/'x1d/af-experiment/camera-settings-r1'
FLASH=ROOT/'x1d/wireless-flash'
REPLAY=ROOT/'x1d/candidates/replay-next/artifacts/joint/fixed/module-57b90e6e02913758'
STABLE=FLASH/'build/formal-flash-package/stable-success-20260912T125921Z'
MAIN_SHA='7adb70915d798fbf24004c512c3fa0ffaf3e331a1721416172b45250bb23ea76'
CHECK_SHA='e373262db5b23f567b22060f1a61687c723cbbbae3c1e237e60728015d3ccca0'
FLASH_SHA='d7e06ad983915f77c1ffe87893457703f5b8ec6d6e706ff028590536f71feef9'
REPLAY_SHA='57b90e6e0291375857add74ee9eda730bea1b4d6d285f28cf4a00d5e242a301e'
FREEZE_SHA='38ff7b28f1791dfabe5d752634389b935838534262e708f210ab21b00fd6fd1c'
OUT=HERE/'build/package'

def digest(data):return hashlib.sha256(data).hexdigest()
def sha(path):return digest(path.read_bytes())
def read(path):return json.loads(path.read_text(encoding='utf-8'))
def safe(name):
    p=PurePosixPath(name)
    if not name or p.is_absolute() or '\\' in name or any(v in ('..','.') for v in name.split('/')):raise ValueError('unsafe member')
    return name
def verified_files(root, entries):
    for name, expected in entries.items():
        path=(root/name).resolve()
        if not path.is_relative_to(ROOT) or sha(path)!=expected:raise ValueError('changed input '+name)
def archive_files(path, expected):
    if sha(path)!=expected:raise ValueError('archive identity')
    files={}
    with tarfile.open(path,mode='r:gz') as archive:
        for member in archive.getmembers():
            name=safe(member.name)
            if name in files or not member.isfile():raise ValueError('duplicate or special archive member')
            data=archive.extractfile(member).read()
            if len(data)!=member.size:raise ValueError('short archive member')
            files[name]=data
    return files

def build():
    if Path.cwd().resolve()!=ROOT:raise RuntimeError('workspace mismatch')
    af=read(AF/'build/delivery-validation.json')
    if not all(af.get(k) is True for k in ('passed','offlineFirstInstallReady','offlineRollbackReady')):raise ValueError('AF incomplete')
    verified_files(AF,af['files'])
    resources=read(HERE/'build/resources/manifest.json')
    qmlproof=read(HERE/'CodeTests/output/resources.json')
    if (qmlproof.get('passed') is not True or qmlproof['rccSha256']!=resources['rccSha256'] or resources['mainSha256']!=MAIN_SHA
        or qmlproof['resourceHashes']!=resources['qml'] or qmlproof['testSha256']!=sha(HERE/'CodeTests/test_resources.py')):raise ValueError('QML validation mismatch')
    verified_files(ROOT,resources['sourceHashes']);verified_files(FLASH,resources['formalSourceHashes'])
    shell=read(HERE/'CodeTests/output/install.json')
    if shell.get('passed') is not True or shell['testSha256']!=sha(HERE/'CodeTests/test_install.py'):raise ValueError('installation validation mismatch')
    verified_files(ROOT,shell['sources'])
    transfer=read(HERE/'CodeTests/output/transfer.json')
    if transfer.get('passed') is not True:raise ValueError('transfer validation mismatch')
    verified_files(ROOT,transfer['sources'])
    native=read(HERE/'build/native/build.json')
    if not native.get('compiled') or not all(native['legacyDefaultsByteIdentical'].values()):raise ValueError('native validation mismatch')
    verified_files(ROOT,native['sources'])
    verified_files(HERE/'build/native',{k:v['sha256'] for k,v in native['outputs'].items()})
    if sha(REPLAY/'freeze.json')!=FREEZE_SHA:raise ValueError('replay freeze changed')
    frozen=read(REPLAY/'freeze.json');verified_files(REPLAY,frozen['files'])
    replay=read(REPLAY/'package.json')
    if replay['mainQmlSha256']!=MAIN_SHA or replay['coordinatorCheckerSha256']!=CHECK_SHA or not replay['modulePackageReady']:raise ValueError('replay root binding')
    replays=archive_files(REPLAY/'replay-module.tar.gz',REPLAY_SHA)
    if {k:digest(v) for k,v in replays.items()}!=replay['files']:raise ValueError('replay archive members')
    flash=archive_files(STABLE/'session-package.tar.gz',FLASH_SHA)
    files={'flash/'+name:data for name,data in flash.items()}
    files.update({'replay/'+name:data for name,data in replays.items()})
    for name in ('common.sh','install.sh','restore.sh','run.sh'):
        files[name]=(HERE/name).read_bytes()
        if b'\r' in files[name]:raise ValueError('shell line endings')
    for name in ('libhbl-af-ui.so','libhbl-af-bus.so'):files['af/'+name]=(AF/'linux-build'/name).read_bytes()
    for name in ('libhbl-combined.so','system-check'):files[name]=(HERE/'build/native'/name).read_bytes()
    files['combined-ui.rcc']=(HERE/'build/resources/combined-ui.rcc').read_bytes()
    files['hold-file.check']=(HERE/'build/fixed/install-window-e373262db5b23f56/hold-file.check').read_bytes()
    if digest(files['system-check'])!=CHECK_SHA or digest(files['combined-ui.rcc'])!=resources['rccSha256']:raise ValueError('runtime resource identity')
    files['baseline.sha256']=('\n'.join([
        'd29c62402091c3ad40f6f247c03ce55f248ca79e92531889b1670edeb014ed9b  /usr/bin/victory-gui',
        '2d834be366ba5a78cf370e679f28a5bb171b8dc5944fe2f69e81c2a170ddc263  /usr/lib/libappscommon.so.1.0.0',
        '988bf67864d09e6183b86b65a2e0ad5b60b18df84c2a06076da96ebff84d6eb1  /usr/bin/msg2dbus'])+'\n').encode()
    files['manifest.sha256']=''.join(digest(data)+'  '+safe(name)+'\n' for name,data in sorted(files.items())).encode()
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w',format=tarfile.USTAR_FORMAT) as archive:
        # 显式目录权限；目标程序权限不依赖提取进程的默认 umask。
        directories=sorted({str(parent) for name in files for parent in PurePosixPath(name).parents if str(parent)!='.'})
        for name in directories:
            member=tarfile.TarInfo(name);member.type=tarfile.DIRTYPE;member.mode=0o700;member.uid=member.gid=0;member.mtime=0;archive.addfile(member)
        for name,data in sorted(files.items()):
            member=tarfile.TarInfo(name);member.size=len(data);member.mode=0o700 if (name.endswith('.sh') or '/payload/' in name or name.endswith('-check') or name.endswith('-probe') or name.endswith('-owners')) else 0o600
            member.uid=member.gid=0;member.mtime=0;archive.addfile(member,io.BytesIO(data))
    blob=gzip.compress(stream.getvalue(),compresslevel=9,mtime=0)
    package_sha=digest(blob)
    directory=OUT/package_sha[:16];directory.mkdir(parents=True,exist_ok=True)
    path=directory/'combined.tar.gz'
    if path.exists() and path.read_bytes()!=blob:raise ValueError('fixed archive collision')
    path.write_bytes(blob)
    # 真实重读 tar；没有符号链接、设备节点或目标目录外成员。
    with tarfile.open(path) as archive:
        recovered={m.name:archive.extractfile(m).read() for m in archive.getmembers() if m.isfile()}
        if recovered!=files:raise ValueError('archive roundtrip')
    proof_paths=[Path(__file__),HERE/'build/native/build.json',HERE/'build/resources/manifest.json',HERE/'CodeTests/output/install.json',
                 HERE/'CodeTests/output/resources.json',HERE/'CodeTests/output/transfer.json',AF/'build/delivery-validation.json',REPLAY/'freeze.json']
    report={'kind':'x1d-combined-fixed-package','packageSha256':package_sha,'bytes':len(blob),
            'archive':path.relative_to(ROOT).as_posix(),'files':{k:digest(v) for k,v in files.items()},
            'proofs':{p.relative_to(ROOT).as_posix():sha(p) for p in proof_paths},
            'mainSha256':MAIN_SHA,'rccSha256':resources['rccSha256'],'checkerSha256':CHECK_SHA,
            'flashArchiveSha256':FLASH_SHA,'replayArchiveSha256':REPLAY_SHA,
            'afFirstInstallContractSha256':af['firstInstallContractSha256'],'afActualTimingActionsConnected':False,
            'hardwareRequests':0,'installed':False,'targetValidated':False}
    (directory/'package.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (OUT/'current.json').write_text(json.dumps({'packageReport':(directory/'package.json').relative_to(ROOT).as_posix()},indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('archive','bytes','packageSha256','hardwareRequests','installed')}))
    return report

def verify():
    report=read(ROOT/read(OUT/'current.json')['packageReport'])
    verified_files(ROOT,report['proofs'])
    data=(ROOT/report['archive']).read_bytes()
    if len(data)!=report['bytes'] or digest(data)!=report['packageSha256']:raise ValueError('fixed total package changed')
    return report,data

if __name__=='__main__':build()
