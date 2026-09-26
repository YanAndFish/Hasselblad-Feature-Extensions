"""只含 GUI gate 继续脚本的小包；原 r4 大包保持不变。"""
import gzip,hashlib,io,json,sys,tarfile,importlib.util
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;PARENT=HERE.parent;ROOT=HERE.parents[4]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def previous():
    spec=importlib.util.spec_from_file_location('r4_original_package',PARENT/'gui_package.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.verify()
def make():
    previous()
    expected=read(HERE/'expected.json')
    (HERE/'prior.sha256').write_text(''.join(v+'  '+n+'\n' for n,v in expected.items()),encoding='ascii',newline='\n')
    files={n:(HERE/n).read_bytes() for n in ('common.sh','apply.sh','restore.sh','run.sh','prior.sha256')}
    files['manifest.sha256']=''.join(hashlib.sha256(v).hexdigest()+'  '+n+'\n' for n,v in sorted(files.items())).encode()
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w',format=tarfile.USTAR_FORMAT) as archive:
        for n,v in sorted(files.items()):
            m=tarfile.TarInfo(n);m.size=len(v);m.mtime=0;m.mode=0o700 if n.endswith('.sh') else 0o600;archive.addfile(m,io.BytesIO(v))
    data=gzip.compress(stream.getvalue(),mtime=0);out=HERE/'build';out.mkdir(exist_ok=True)
    (out/'continuation.tar.gz').write_bytes(data)
    report={'revision':'af-ui-r4-preflight-r1','packageSha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),
        'files':{n:hashlib.sha256(v).hexdigest() for n,v in files.items()},'hardwareRequests':0,'guiPayloadUnchanged':True}
    (out/'package.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');return report
def verify():
    previous();validation=read(HERE/'validation.json')
    if not validation['passed']:raise ValueError('continuation validation required')
    for name,digest in validation['sources'].items():
        path=(ROOT/name).resolve()
        if not path.is_relative_to(ROOT) or sha(path)!=digest:raise ValueError('changed continuation source: '+name)
    return read(HERE/'build/package.json'),(HERE/'build/continuation.tar.gz').read_bytes()
