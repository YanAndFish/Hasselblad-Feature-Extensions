"""半按批量发射完整更新：UI 资源、worker、radio 和准备脚本同一事务。"""
from pathlib import Path
import hashlib,json,tarfile
P=Path(__file__).resolve().parent;ROOT=P.parents[3]
O=P/'build/batch-radio';S=O/'install-stage';S.mkdir(parents=True,exist_ok=True)
(S/'files').mkdir(exist_ok=True)
def sha(b):return hashlib.sha256(b).hexdigest()
def put(p,s):p.write_text(s,encoding='utf-8',newline='\n')
radio=ROOT/'x1d/wireless-flash/build/batch-flash-candidate'
proof=json.loads((radio/'batch-validation.json').read_text());assert proof['passed']
assert sha((radio/'formal-wltest.bin').read_bytes())==proof['firmwareSha256']
worker=P/'build/halfpress-ui/worker/libhbl-combined-loader.so'
assert sha(worker.read_bytes())==json.loads((worker.parent/'build.json').read_text())['sha256']
old=P/'build/halfpress-ui/install-stage/files'
manifest=(old/'manifest.sha256').read_bytes()
assert sha(manifest)=='75951cd87b1f1e4b5a3bac63cc4caa21cf8ec3a952ca25e2344be6238b3bc095'
files={'libhbl-af-loader.so':worker,
       'libhbl-af-ui.so':old/'libhbl-af-ui.so',
       'af-ui.rcc':P/'build/halfpress-ui/build/combined-ui.rcc',
       'radio.bin':radio/'formal-wltest.bin','baseline.sha256':old/'baseline.sha256'}
for name,path in files.items():(S/'files'/name).write_bytes(path.read_bytes())
prepare=(P/'build/radio-ready/stage/files/prepare-radio.sh').read_text(encoding='utf-8')
assert '0x5854' in prepare
put(S/'files/prepare-radio.sh',prepare.replace('5854','5855'))
for path in sorted((S/'files').iterdir()):
    lines=manifest.decode().splitlines();name=path.name
    assert sum(line.split('  ',1)[1]==name for line in lines)==1
    manifest=('\n'.join(sha(path.read_bytes())+'  '+name if line.split('  ',1)[1]==name else line for line in lines)+'\n').encode()
(S/'files/manifest.sha256').write_bytes(manifest)
script=(P/'build/halfpress-ui/install-stage/repair.sh').read_text(encoding='utf-8')
script=script.replace('.halfpress-batch-backup','.batch-radio-backup')
script=script.replace("oldfiles='libhbl-af-loader.so libhbl-af-ui.so baseline.sha256 manifest.sha256'",
                      "oldfiles='libhbl-af-loader.so libhbl-af-ui.so af-ui.rcc radio.bin prepare-radio.sh baseline.sha256 manifest.sha256'")
assert "af-ui.rcc radio.bin prepare-radio.sh" in script
put(S/'repair.sh',script);put(S/'run.sh','#!/bin/sh\nexit 0\n')
put(S/'old-pin',sha((old/'manifest.sha256').read_bytes())+'\n');put(S/'new-pin',sha(manifest)+'\n')
members=[p for p in S.rglob('*') if p.is_file() and p.name not in ('repair-manifest.sha256','manifest.sha256')]+[S/'files/manifest.sha256']
put(S/'repair-manifest.sha256',''.join(sha(p.read_bytes())+'  '+p.relative_to(S).as_posix()+'\n' for p in sorted(members)))
members.append(S/'repair-manifest.sha256')
put(S/'manifest.sha256',''.join(sha(p.read_bytes())+'  '+p.relative_to(S).as_posix()+'\n' for p in sorted(members)))
with tarfile.open(O/'install.tgz','w:gz') as t:
    for p in sorted(S.rglob('*')):
        if p.is_file():t.add(p,arcname=p.relative_to(S).as_posix())
with tarfile.open(O/'install.tgz') as t:
    for p in S.rglob('*'):
        if p.is_file():assert t.extractfile(p.relative_to(S).as_posix()).read()==p.read_bytes()
r=dict(bytes=(O/'install.tgz').stat().st_size,packageSha256=sha((O/'install.tgz').read_bytes()),
       oldManifest=sha((old/'manifest.sha256').read_bytes()),newManifest=sha(manifest),installed=False)
put(O/'package.json',json.dumps(r,indent=2));print(json.dumps(r))
