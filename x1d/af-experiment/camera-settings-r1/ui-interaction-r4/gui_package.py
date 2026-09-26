"""冻结 GUI-only 增量；默认仅校验，不执行设备动作。"""
import gzip,hashlib,io,json,sys,tarfile
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def make():
    if Path.cwd().resolve()!=ROOT:raise ValueError('workspace required')
    files={n:(HERE/n).read_bytes() for n in ('common.sh','apply.sh','restore.sh','run.sh','95-hbl-af-ui-r4.conf')}
    files['libhbl-af-ui.so']=(HERE/'linux-build/libhbl-af-ui.so').read_bytes()
    files['af-only-ui.rcc']=(HERE/'build/resources/af-only-ui.rcc').read_bytes()
    files['manifest.sha256']=''.join(hashlib.sha256(v).hexdigest()+'  '+k+'\n' for k,v in sorted(files.items())).encode()
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w',format=tarfile.USTAR_FORMAT) as archive:
        for name,data in sorted(files.items()):
            m=tarfile.TarInfo(name);m.size=len(data);m.mtime=0;m.mode=0o700 if name.endswith('.sh') else 0o600
            archive.addfile(m,io.BytesIO(data))
    blob=gzip.compress(stream.getvalue(),mtime=0);out=HERE/'build/package';out.mkdir(parents=True,exist_ok=True)
    (out/'af-ui-r4.tar.gz').write_bytes(blob)
    report={'revision':'af-ui-interaction-r4','guiOnly':True,'packageSha256':hashlib.sha256(blob).hexdigest(),'bytes':len(blob),
        'files':{k:hashlib.sha256(v).hexdigest() for k,v in files.items()},'hardwareRequests':0,'afRamChanged':False,'busChanged':False}
    (out/'package.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report
def verify():
    proof=read(HERE/'validation.json')
    if not proof['passed']:raise ValueError('GUI validation required')
    for name,digest in proof['sources'].items():
        p=(ROOT/name).resolve()
        if not p.is_relative_to(ROOT) or sha(p)!=digest:raise ValueError('frozen GUI input changed: '+name)
    report=read(HERE/'build/package/package.json');data=(HERE/'build/package/af-ui-r4.tar.gz').read_bytes()
    if hashlib.sha256(data).hexdigest()!=report['packageSha256'] or len(data)!=report['bytes']:raise ValueError('GUI archive changed')
    return report,data
if __name__=='__main__':print(json.dumps(make()))
