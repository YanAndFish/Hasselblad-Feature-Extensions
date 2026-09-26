"""绑定离线证据并生成可回退更新包；不访问相机。"""
from pathlib import Path
import hashlib,json,tarfile,io,re
P=Path(__file__).resolve().parent;ROOT=P.parents[3];assert Path.cwd().resolve()==ROOT
out=P/'build/resident-init';old=P/'build/controller-first/installed-package'
sha=lambda b:hashlib.sha256(b).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
runtime=read(out/'runtime-build.json');model=read(out/'lifecycle-validation.json');arm=read(out/'arm-validation.json');build=read(out/'build.json')
assert all(r['passed'] for r in (runtime,model,arm))
for report in (runtime,model,build):
 for name,h in report['sources'].items():assert sha((P/name).read_bytes())==h,name
assert runtime['sha256']==sha((out/'libhbl-af-loader.so').read_bytes())
assert arm['initializerSha256']==sha((out/'initializer.bin').read_bytes())==build['sha256']
proof=read(P/'CodeTests/cache-pair-repair-validation.json')
script=(P/'repair-af-cache-pair.sh').read_bytes()
assert proof['passed'] and proof['scriptSha256']==sha(script)
# 被省去的旧入口读取必须由首次写入前的精确依赖表完整覆盖。
def rows(text):return {(int(a,16),int(v,16)) for a,v in re.findall(r'\{0x([0-9a-f]+)u,0x([0-9a-f]+)u\}',text)}
entry=(P/'build/batch-model/adapter_data.h').read_text(encoding='utf-8').split('hbl_batch_entry_expected')[1]
early=(P/'build/controller-first/early_data.h').read_text(encoding='utf-8').split('earlyDependencies')[1]
assert rows(entry)<=rows(early)
original=(old/'manifest.sha256').read_bytes()
assert sha(original)=='f652d4dfcfe329e0dfeba0bd51ec29a84865c6bfcfda0a11e7ff6f297b6d3762'
lines=[]
for line in original.decode().splitlines():
 h,n=line.split('  ',1);assert sha((old/n).read_bytes())==h
 lines.append((runtime['sha256'] if n=='libhbl-af-loader.so' else h)+'  '+n+'\n')
manifest=''.join(lines).encode()
members={'install.sh':script,'files/libhbl-af-loader.so':(out/'libhbl-af-loader.so').read_bytes(),'files/manifest.sha256':manifest,'old-pin':(sha(original)+'\n').encode(),'new-pin':(sha(manifest)+'\n').encode()}
members['repair-manifest.sha256']=''.join(sha(b)+'  '+n+'\n' for n,b in sorted(members.items())).encode()
with tarfile.open(out/'update.tgz','w:gz') as tf:
 for n,b in members.items():
  info=tarfile.TarInfo(n);info.size=len(b);info.mode=0o700 if n=='install.sh' else 0o600;tf.addfile(info,io.BytesIO(b))
inputs=[Path(__file__),P/'install_af_resident.py',P/'repair-af-cache-pair.sh',out/'runtime-build.json',out/'lifecycle-validation.json',out/'arm-validation.json',out/'transport-arm-validation.json',out/'libhbl-af-loader.so',P/'CodeTests/cache-pair-repair-validation.json']
report=dict(sha256=sha((out/'update.tgz').read_bytes()),oldManifest=sha(original),newManifest=sha(manifest),sourceHashes={str(p.relative_to(P)):sha(p.read_bytes()) for p in inputs},installed=False,coldBootVerified=False)
(out/'update.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
