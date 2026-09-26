"""生成成对 UI/worker 更新事务，不安装。"""
from pathlib import Path
import hashlib,json,tarfile
P=Path(__file__).resolve().parent;O=P/'build/halfpress-ui';S=O/'install-stage'
S.mkdir(exist_ok=True);(S/'files').mkdir(exist_ok=True)
def sha(b):return hashlib.sha256(b).hexdigest()
def put(p,s):p.write_text(s,encoding='utf-8',newline='\n')
old=P/'build/flash-timeline-probe/stage/files'
manifest=(old/'manifest.sha256').read_bytes()
files={'libhbl-af-loader.so':O/'worker/libhbl-combined-loader.so','libhbl-af-ui.so':O/'gui/libhbl-combined-ui.so','baseline.sha256':old/'baseline.sha256'}
for name,path in files.items():
    if not path.exists() and name=='libhbl-af-ui.so':
        candidates=list((O/'gui').glob('*.so'));assert len(candidates)==1;path=candidates[0]
    data=path.read_bytes();(S/'files'/name).write_bytes(data)
    lines=manifest.decode().splitlines()
    assert sum(line.split('  ',1)[1]==name for line in lines)==1
    manifest=('\n'.join(sha(data)+'  '+name if line.split('  ',1)[1]==name else line for line in lines)+'\n').encode()
(S/'files/manifest.sha256').write_bytes(manifest)
script=(P/'build/flash-timeline-probe/repair-flash-timeline.sh').read_text(encoding='utf-8')
script=script.replace('.flash-timeline-backup','.halfpress-batch-backup').replace("oldfiles='libhbl-af-loader.so baseline.sha256 manifest.sha256'","oldfiles='libhbl-af-loader.so libhbl-af-ui.so baseline.sha256 manifest.sha256'")
put(S/'repair.sh',script);put(S/'run.sh','#!/bin/sh\nexit 0\n')
put(S/'old-pin',sha((old/'manifest.sha256').read_bytes())+'\n');put(S/'new-pin',sha(manifest)+'\n')
members=[p for p in S.rglob('*') if p.is_file() and p.name not in ('repair-manifest.sha256','manifest.sha256')]
members.append(S/'files/manifest.sha256')
put(S/'repair-manifest.sha256',''.join(sha(p.read_bytes())+'  '+p.relative_to(S).as_posix()+'\n' for p in sorted(members)))
members.append(S/'repair-manifest.sha256')
put(S/'manifest.sha256',''.join(sha(p.read_bytes())+'  '+p.relative_to(S).as_posix()+'\n' for p in sorted(members)))
with tarfile.open(O/'install.tgz','w:gz') as tar:
    for p in sorted(S.rglob('*')):
        if p.is_file():tar.add(p,arcname=p.relative_to(S).as_posix())
data=(O/'install.tgz').read_bytes()
r=dict(bytes=len(data),packageSha256=sha(data),oldManifest=sha((old/'manifest.sha256').read_bytes()),newManifest=sha(manifest),installed=False)
put(O/'package.json',json.dumps(r,indent=2));print(json.dumps(r))
