from pathlib import Path
import sys, json, hashlib, tarfile, io
sys.dont_write_bytecode = True
P = Path(__file__).resolve().parent
ROOT = P.parents[3]
sys.path[:0] = [str(P.parent), str(ROOT/'x1d/candidates/ui-resident/tools')]
from compose import read_rcc
from resource_bundle import rcc
def sha(data): return hashlib.sha256(data).hexdigest()
old=P/'build/continuous-touch-repair'
out=P/'build/focus-delivery-repair'
stage=out/'stage';(stage/'files').mkdir(parents=True,exist_ok=True)
proof=json.loads((out/'validation.json').read_text())
assert proof['passed'] and proof['sourceSha256']==sha((P/'qml/common/FocusDelivery.qml').read_bytes())
values=read_rcc((old/'stage/files/af-ui.rcc').read_bytes())
changed=['common/FocusDelivery.qml','common/GlobalStateInfo.qml','liveview/AFIndicator.qml',
         'liveview/LiveViewOverlay.qml','liveview/Touchpad.qml','main.qml','components/buttons/ExposureButton.qml']
for name in changed: values['/'+name]=(P/'qml'/name).read_text(encoding='utf-8')
blob=rcc(values);assert read_rcc(blob)==values
(stage/'files/af-ui.rcc').write_bytes(blob)
(stage/'files/baseline.sha256').write_bytes((old/'stage/files/baseline.sha256').read_bytes())
manifest=(old/'stage/files/manifest.sha256').read_text()
lines=[]
for line in manifest.splitlines():
    h,name=line.split('  ',1)
    if name=='af-ui.rcc': h=sha(blob)
    lines.append(h+'  '+name)
new_manifest=('\n'.join(lines)+'\n').encode()
(stage/'files/manifest.sha256').write_bytes(new_manifest)
oldpin=sha((old/'stage/files/manifest.sha256').read_bytes());newpin=sha(new_manifest)
(stage/'old-pin').write_text(oldpin+'\n',newline='\n')
(stage/'new-pin').write_text(newpin+'\n',newline='\n')
script=(old/'stage/repair.sh').read_text().replace('.continuous-touch-repair-backup','.focus-delivery-repair-backup')
(stage/'repair.sh').write_text(script,newline='\n')
(stage/'run.sh').write_bytes((old/'stage/run.sh').read_bytes())
members=['files/af-ui.rcc','files/baseline.sha256','files/manifest.sha256','old-pin','new-pin','repair.sh','run.sh']
sm=''.join(sha((stage/n).read_bytes())+'  '+n+'\n' for n in sorted(members))
for name in ['manifest.sha256','repair-manifest.sha256']:(stage/name).write_text(sm,newline='\n')
members+=['manifest.sha256','repair-manifest.sha256']
with tarfile.open(out/'repair.tgz','w:gz') as tar:
    for n in members:
        data=(stage/n).read_bytes();info=tarfile.TarInfo(n);info.size=len(data);info.mode=0o600;tar.addfile(info,io.BytesIO(data))
data=(out/'repair.tgz').read_bytes()
package=dict(bytes=len(data),packageSha256=sha(data),oldPin=oldpin,newPin=newpin,cropScaling=False,
             sourceHashes={n:sha((P/'qml'/n).read_bytes()) for n in changed},physicalLatencyMeasured=False)
(out/'package.json').write_text(json.dumps(package,indent=2),encoding='utf-8')
installer=(old/'install.py').read_text().replace('continuous-touch-repair','focus-delivery-repair').replace('/tmp/hbl-cont-touch','/tmp/hbl-focus-delivery')
(out/'install.py').write_text(installer,newline='\n')
print(json.dumps(package))
