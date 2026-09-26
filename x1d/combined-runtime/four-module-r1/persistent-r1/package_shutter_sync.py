"""全按仅同步引闪：原 UI/RCC/无线镜像已核对，只更新 worker 和清单。"""
from pathlib import Path
import json,hashlib,tarfile
P=Path(__file__).resolve().parent;O=P/'build/shutter-sync';S=O/'install-stage'
(S/'files').mkdir(parents=True,exist_ok=True)
def sha(b):return hashlib.sha256(b).hexdigest()
def put(p,s):p.write_text(s,encoding='utf-8',newline='\n')
worker=O/'worker/libhbl-combined-loader.so'
assert sha(worker.read_bytes())==json.loads((worker.parent/'build.json').read_text())['sha256']
assert json.loads((O/'ui-validation.json').read_text())['passed']
proof=json.loads((P/'CodeTests/formal_policy_output/validation.json').read_text());assert proof['passed']
for n,h in proof['sourceHashes'].items():assert sha((P/n).read_bytes())==h,n
old=P/'build/halfpress-ui/install-stage/files';original=(old/'manifest.sha256').read_bytes()
assert sha(original)=='75951cd87b1f1e4b5a3bac63cc4caa21cf8ec3a952ca25e2344be6238b3bc095'
(S/'files/libhbl-af-loader.so').write_bytes(worker.read_bytes())
(S/'files/baseline.sha256').write_bytes((old/'baseline.sha256').read_bytes())
manifest='\n'.join(sha(worker.read_bytes())+'  libhbl-af-loader.so' if x.endswith('  libhbl-af-loader.so') else x for x in original.decode().splitlines())+'\n'
put(S/'files/manifest.sha256',manifest)
script=(P/'build/halfpress-ui/install-stage/repair.sh').read_text(encoding='utf-8')
script=script.replace('.halfpress-batch-backup','.shutter-sync-backup')
script=script.replace("oldfiles='libhbl-af-loader.so libhbl-af-ui.so baseline.sha256 manifest.sha256'","oldfiles='libhbl-af-loader.so baseline.sha256 manifest.sha256'")
put(S/'repair.sh',script);put(S/'run.sh','#!/bin/sh\nexit 0\n')
put(S/'old-pin',sha(original)+'\n');put(S/'new-pin',sha(manifest.encode())+'\n')
members=[p for p in S.rglob('*') if p.is_file() and p.name not in ('repair-manifest.sha256','manifest.sha256')]+[S/'files/manifest.sha256']
put(S/'repair-manifest.sha256',''.join(sha(p.read_bytes())+'  '+p.relative_to(S).as_posix()+'\n' for p in sorted(members)))
members.append(S/'repair-manifest.sha256')
put(S/'manifest.sha256',''.join(sha(p.read_bytes())+'  '+p.relative_to(S).as_posix()+'\n' for p in sorted(members)))
with tarfile.open(O/'install.tgz','w:gz') as t:
 for p in sorted(S.rglob('*')):
  if p.is_file():t.add(p,arcname=p.relative_to(S).as_posix())
r=dict(bytes=(O/'install.tgz').stat().st_size,packageSha256=sha((O/'install.tgz').read_bytes()),oldManifest=sha(original),newManifest=sha(manifest.encode()),installed=False)
put(O/'package.json',json.dumps(r,indent=2)+'\n');print(json.dumps(r))
