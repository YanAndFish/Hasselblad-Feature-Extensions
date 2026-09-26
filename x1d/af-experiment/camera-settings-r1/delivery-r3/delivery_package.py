"""固定 AF-only Linux 包和 r3 主机来源核验；导入不写文件。"""
import hashlib, io, json, sys, tarfile
from pathlib import Path
HERE = Path(__file__).resolve().parent
AF = HERE.parent
ROOT = HERE.parents[3]
sys.dont_write_bytecode = True
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))
def verify():
    proof = read(HERE/'validation.json')
    if not proof.get('passed'):
        raise ValueError('r3 offline validation required')
    for name, digest in proof['sources'].items():
        path = (ROOT/name).resolve()
        if not path.is_relative_to(ROOT) or sha(path) != digest:
            raise ValueError('r3 source changed: '+name)
    sys.path.insert(0,str(AF))
    from af_only_bus_r2_loader import runtime
    if not runtime.readiness():
        raise ValueError('frozen AF source changed')
    report = read(HERE/'inputs/package.json')
    data = (HERE/'inputs/af-only.tar.gz').read_bytes()
    if hashlib.sha256(data).hexdigest() != report['packageSha256'] or len(data) != report['bytes']:
        raise ValueError('AF package changed')
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        members = archive.getmembers()
        if (any(not m.isfile() and not (m.isdir() and m.name=='af' and m.size==0) for m in members)
                or len({m.name for m in members}) != len(members)):
            raise ValueError('AF package members')
        actual = {m.name:hashlib.sha256(archive.extractfile(m).read()).hexdigest() for m in members if m.isfile()}
    if actual != report['files']:
        raise ValueError('AF package file identity')
    return report, data
