"""干净基线 AF r5 完整包；冻结 r3 AF、r4 UI 与 bus-r3 来源分别核验。"""
import hashlib,io,json,sys,tarfile
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;AF=HERE.parent;ROOT=HERE.parents[3]
PROOFS={
    'delivery-r5/validation.json':'f6e95e55a2a201042f38c5ec462bb64b9dd1a5463a7993b66e1cc3ca6939d2b4',
    'bus-reply-r5/validation.json':'df01384809309baaa2fdec4030cd8cc89f108b76c833487eb784ca10da997ca4'}

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def frozen_inputs():
    for name,digest in PROOFS.items():
        path=AF/name
        if sha(path)!=digest:raise ValueError('frozen upstream proof changed: '+name)
        proof=read(path)
        if not proof.get('passed'):raise ValueError('upstream not passed')
        for source,expected in proof['sources'].items():
            p=(ROOT/source).resolve()
            if not p.is_relative_to(ROOT) or sha(p)!=expected:raise ValueError('upstream source changed: '+source)
    sys.path.insert(0,str(AF))
    from af_only_bus_r2_loader import runtime
    if not runtime.readiness():raise ValueError('original AF contract changed')
def verify():
    proof=read(HERE/'validation.json')
    if not proof.get('passed'):raise ValueError('r6 offline validation required')
    for name,digest in proof['sources'].items():
        path=(ROOT/name).resolve()
        if not path.is_relative_to(ROOT) or sha(path)!=digest:raise ValueError('r6 source changed: '+name)
    frozen_inputs()
    report=read(HERE/'inputs/package.json');data=(HERE/'inputs/af-only.tar.gz').read_bytes()
    if hashlib.sha256(data).hexdigest()!=report['packageSha256'] or len(data)!=report['bytes']:raise ValueError('r6 archive changed')
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        members=archive.getmembers()
        if any(not m.isfile() for m in members) or len({m.name for m in members})!=len(members):raise ValueError('r6 archive members')
        actual={m.name:hashlib.sha256(archive.extractfile(m).read()).hexdigest() for m in members}
    if actual!=report['files']:raise ValueError('r6 archive file identity')
    return report,data
