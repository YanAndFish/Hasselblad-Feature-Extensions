"""只读播放配置探针：固定旧镜像重建，不改变现有 UI、worker 或发送流程。"""
from pathlib import Path
import hashlib, json, tarfile
P=Path(__file__).resolve().parent
ROOT=P.parents[3]
O=P/'build/playback-probe'
S=O/'install-stage'
(S/'files').mkdir(parents=True,exist_ok=True)
def sha(b):return hashlib.sha256(b).hexdigest()
def put(p,s):p.write_text(s,encoding='utf-8',newline='\n')
W=ROOT/'x1d/wireless-flash/build'
a=(W/'formal-flash-candidate/formal-wltest.bin').read_bytes()
b=(W/'playback-probe/formal-wltest.bin').read_bytes()
proof=json.loads((W/'playback-probe/probe-validation.json').read_text())
assert proof['passed'] and proof['firmwareSha256']==sha(b)
assert sha(a)=='86d10d4131bcaa90dd0781545cec918ab10e56fd3d808c2dc85a019ee9edba98'
assert len(a)==len(b)
changed=[i for i in range(len(a)) if a[i]!=b[i]]
start,end=min(changed),max(changed)+1
delta=b[start:end]
assert a[:start]+delta+a[end:]==b
(S/'radio.delta').write_bytes(delta)
old=P/'build/halfpress-ui/install-stage/files'
original=(old/'manifest.sha256').read_bytes()
assert sha(original)=='75951cd87b1f1e4b5a3bac63cc4caa21cf8ec3a952ca25e2344be6238b3bc095'
manifest='\n'.join(sha(b)+'  radio.bin' if x.endswith('  radio.bin') else x for x in original.decode().splitlines())+'\n'
put(S/'files/manifest.sha256',manifest)
(S/'files/baseline.sha256').write_bytes((old/'baseline.sha256').read_bytes())
script=(P/'build/halfpress-ui/install-stage/repair.sh').read_text(encoding='utf-8')
script=script.replace('.halfpress-batch-backup','.playback-probe-backup')
script=script.replace("oldfiles='libhbl-af-loader.so libhbl-af-ui.so baseline.sha256 manifest.sha256'","oldfiles='radio.bin baseline.sha256 manifest.sha256'")
put(S/'repair.sh',script)
put(S/'old-pin',sha(original)+'\n');put(S/'new-pin',sha(manifest.encode())+'\n')
put(S/'reconstruct.sh',f'''#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
test "$(sha256sum /opt/hbl-af-only-v1/radio.bin | cut -d' ' -f1)" = {sha(a)}
test ! -e files/radio.bin && test ! -L files/radio.bin
cp /opt/hbl-af-only-v1/radio.bin files/radio.bin
dd if=radio.delta of=files/radio.bin bs=1 seek={start} conv=notrunc 2>/dev/null
test "$(sha256sum files/radio.bin | cut -d' ' -f1)" = {sha(b)}
echo probe-reconstructed
''')
put(S/'run.sh','#!/bin/sh\nexit 0\n')
members=[p for p in S.rglob('*') if p.is_file() and p.name not in ('repair-manifest.sha256','manifest.sha256')]+[S/'files/manifest.sha256']
put(S/'repair-manifest.sha256',''.join(sha(p.read_bytes())+'  '+p.relative_to(S).as_posix()+'\n' for p in sorted(members))+sha(b)+'  files/radio.bin\n')
members.append(S/'repair-manifest.sha256')
put(S/'manifest.sha256',''.join(sha(p.read_bytes())+'  '+p.relative_to(S).as_posix()+'\n' for p in sorted(members)))
with tarfile.open(O/'install.tgz','w:gz') as t:
 for p in sorted(S.rglob('*')):
  if p.is_file():t.add(p,arcname=p.relative_to(S).as_posix())
r=dict(bytes=(O/'install.tgz').stat().st_size,packageSha256=sha((O/'install.tgz').read_bytes()),oldManifest=sha(original),newManifest=sha(manifest.encode()),installed=False,probeOnly=True,deltaStart=start,deltaBytes=len(delta))
put(O/'package.json',json.dumps(r,indent=2)+'\n')
print(json.dumps(r))
