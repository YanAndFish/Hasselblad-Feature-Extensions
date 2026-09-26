"""干净基线 AF r5 完整包；冻结 r3 AF、r4 UI 与 bus-r3 来源分别核验。"""
import hashlib,io,json,sys,tarfile
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;AF=HERE.parent;ROOT=HERE.parents[3]
PROOFS={
    'delivery-r3/validation.json':'cf2eb05b6b1927e8c95e2efa49cd54dcd9038355475211f1aed13b0ecc001cfd',
    'ui-interaction-r4/validation.json':'f48a91561ac45f7583e764fce3cc12b9dd37ce1d4741ab4c30bf680fcdb89cbe',
    'bus-roundtrip-r3/validation.json':'07934c4d9a20e853cb0411f380b6e2b674bda580ec2cfc4db2eb46faec0aa834'}
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
    if not proof.get('passed'):raise ValueError('r5 offline validation required')
    for name,digest in proof['sources'].items():
        path=(ROOT/name).resolve()
        if not path.is_relative_to(ROOT) or sha(path)!=digest:raise ValueError('r5 source changed: '+name)
    frozen_inputs()
    report=read(HERE/'inputs/package.json');data=(HERE/'inputs/af-only.tar.gz').read_bytes()
    if hashlib.sha256(data).hexdigest()!=report['packageSha256'] or len(data)!=report['bytes']:raise ValueError('r5 archive changed')
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        members=archive.getmembers()
        if any(not m.isfile() for m in members) or len({m.name for m in members})!=len(members):raise ValueError('r5 archive members')
        actual={m.name:hashlib.sha256(archive.extractfile(m).read()).hexdigest() for m in members}
    if actual!=report['files']:raise ValueError('r5 archive file identity')
    return report,data
