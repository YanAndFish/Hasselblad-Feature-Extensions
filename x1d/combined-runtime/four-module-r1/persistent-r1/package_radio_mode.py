"""基于已装 Q95 清单的无线三状态增量。"""
from pathlib import Path
import hashlib,io,json,tarfile,sys
sys.dont_write_bytecode=True
P=Path(__file__).resolve().parent;O=P/'build/radio-three-state';stage=O/'stage';files=stage/'files'
files.mkdir(parents=True,exist_ok=True)
def sha(b):return hashlib.sha256(b).hexdigest()
prior=P/'build/jpeg-quality95/stage/files'
assert json.loads((O/'build.json').read_text())['compiled']
assert json.loads((O/'qml-validation.json').read_text())['passed']
h=json.loads((O/'helper-validation.json').read_text());assert h['passed'] and h['scriptSha256']==sha((P/'radio-mode.sh').read_bytes())
updated={'af-ui.rcc':(O/'af-ui.rcc').read_bytes(),
         'libhbl-af-ui.so':(O/'gui/libhbl-four-module.so').read_bytes(),
         'libhbl-af-loader.so':(O/'libhbl-af-loader.so').read_bytes(),
         'coordinate.sh':(O/'coordinate.sh').read_bytes(),
         'baseline.sha256':(prior/'baseline.sha256').read_bytes(),
         'radio-mode.sh':(P/'radio-mode.sh').read_bytes()}
old=(prior/'manifest.sha256').read_bytes();lines=[]
for line in old.decode().splitlines():
    h,n=line.split('  ',1);lines.append((sha(updated[n]) if n in updated else h)+'  '+n)
lines.append(sha(updated['radio-mode.sh'])+'  radio-mode.sh')
manifest=('\n'.join(lines)+'\n').encode();updated['manifest.sha256']=manifest
for n,b in updated.items():(files/n).write_bytes(b)
(stage/'old-pin').write_text(sha(old)+'\n',newline='\n');(stage/'new-pin').write_text(sha(manifest)+'\n',newline='\n')
s=(P/'build/focus-delivery-repair/stage/repair.sh').read_text(encoding='utf-8')
s=s.replace('.focus-delivery-repair-backup','.radio-three-state-backup')
s=s.replace("oldfiles='af-ui.rcc baseline.sha256 manifest.sha256'", "oldfiles='af-ui.rcc libhbl-af-ui.so libhbl-af-loader.so coordinate.sh baseline.sha256 manifest.sha256'")
s=s.replace("added=''", "added='radio-mode.sh'")
s=s.replace('verify && pin\nsync','chmod 700 "$dest/radio-mode.sh"\nverify && pin\nsync',1)
(stage/'repair.sh').write_text(s,encoding='utf-8',newline='\n')
(stage/'run.sh').write_text('#!/bin/sh\nexit 0\n',newline='\n')
members=['files/'+n for n in updated]+['old-pin','new-pin','repair.sh','run.sh']
checks=''.join(sha((stage/n).read_bytes())+'  '+n+'\n' for n in sorted(members))
for n in ['manifest.sha256','repair-manifest.sha256']:(stage/n).write_text(checks,newline='\n')
members+=['manifest.sha256','repair-manifest.sha256']
with tarfile.open(O/'repair.tgz','w:gz') as t:
    for n in members:
        b=(stage/n).read_bytes();info=tarfile.TarInfo(n);info.size=len(b);info.mode=0o600;t.addfile(info,io.BytesIO(b))
r=dict(bytes=(O/'repair.tgz').stat().st_size,packageSha256=sha((O/'repair.tgz').read_bytes()),oldPin=sha(old),newPin=sha(manifest),installed=False,jpegQuality=95)
(O/'package.json').write_text(json.dumps(r,indent=2))
s=(P/'build/full-jpeg-output/install.py').read_text(encoding='utf-8').replace('full-jpeg-output','radio-three-state').replace('jpegQuality=85','jpegQuality=95')
s=s.replace('fullJpegOutput=True,','fullJpegOutput=True,radioThreeState=True,radioSwitchOnCameraVerified=False,')
(O/'install.py').write_text(s,encoding='utf-8',newline='\n')
print(json.dumps(r))
