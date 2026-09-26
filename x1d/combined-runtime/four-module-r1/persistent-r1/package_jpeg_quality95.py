"""Q85 到 Q95 的单组件事务；保留已安装原厂服务入口及其他组件。"""
from pathlib import Path
import hashlib, io, json, tarfile, sys
sys.dont_write_bytecode=True
from build_jpeg_quality95 import build
P=Path(__file__).resolve().parent
O=P/'build/jpeg-quality95';stage=O/'stage';files=stage/'files'
files.mkdir(parents=True,exist_ok=True)
def sha(b):return hashlib.sha256(b).hexdigest()
jpeg,meta=build();old=P/'build/full-jpeg-output/stage/files'
(files/'jpeg-daemon-full').write_bytes(jpeg)
(files/'baseline.sha256').write_bytes((old/'baseline.sha256').read_bytes())
prior=(old/'manifest.sha256').read_bytes()
lines=[]
for line in prior.decode().splitlines():
    h,n=line.split('  ',1)
    lines.append((sha(jpeg) if n=='jpeg-daemon-full' else h)+'  '+n)
manifest=('\n'.join(lines)+'\n').encode();(files/'manifest.sha256').write_bytes(manifest)
(stage/'old-pin').write_text(sha(prior)+'\n',newline='\n')
(stage/'new-pin').write_text(sha(manifest)+'\n',newline='\n')
s=(P/'build/focus-delivery-repair/stage/repair.sh').read_text()
s=s.replace('.focus-delivery-repair-backup','.jpeg-quality95-r2-backup').replace("oldfiles='af-ui.rcc baseline.sha256 manifest.sha256'", "oldfiles='jpeg-daemon-full baseline.sha256 manifest.sha256'")
# 保留运行中可执行文件的 inode，避免替换后成为删除态而阻止 remount ro。
s=s.replace('if [ "$f" = libhbl-af-loader.so ]', 'if [ "$f" = jpeg-daemon-full ] || [ "$f" = libhbl-af-loader.so ]')
s=s.replace('verify && pin\nsync','chmod 700 "$dest/jpeg-daemon-full"\nverify && pin\nsync',1)
(stage/'repair.sh').write_text(s,newline='\n')
(stage/'run.sh').write_text('#!/bin/sh\nexit 0\n',newline='\n')
members=['files/jpeg-daemon-full','files/baseline.sha256','files/manifest.sha256','old-pin','new-pin','repair.sh','run.sh']
checks=''.join(sha((stage/n).read_bytes())+'  '+n+'\n' for n in sorted(members))
for n in ['manifest.sha256','repair-manifest.sha256']:(stage/n).write_text(checks,newline='\n')
members+=['manifest.sha256','repair-manifest.sha256']
with tarfile.open(O/'repair.tgz','w:gz') as t:
    for n in members:
        b=(stage/n).read_bytes();info=tarfile.TarInfo(n);info.size=len(b);info.mode=0o600;t.addfile(info,io.BytesIO(b))
package=dict(bytes=(O/'repair.tgz').stat().st_size,packageSha256=sha((O/'repair.tgz').read_bytes()),oldPin=sha(prior),newPin=sha(manifest),quality=95)
(O/'package.json').write_text(json.dumps(package,indent=2))
installer=(P/'build/full-jpeg-output/install.py').read_text().replace('full-jpeg-output','jpeg-quality95').replace('jpegQuality=85','jpegQuality=95')
installer=installer.replace("remote='/tmp/hbl-jpeg-quality95'", "remote='/tmp/hbl-jpeg-quality95-r2'")
(O/'install.py').write_text(installer,newline='\n')
print(json.dumps(package))
