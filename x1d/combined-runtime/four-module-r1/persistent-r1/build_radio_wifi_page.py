"""纠正三状态入口：修改原 Wi-Fi 设置行，撤销参数页新增按钮。"""
from pathlib import Path
import sys,json,hashlib,io,tarfile
sys.dont_write_bytecode=True
P=Path(__file__).resolve().parent;ROOT=P.parents[3]
sys.path[:0]=[str(P.parent),str(ROOT/'x1d/candidates/ui-resident/tools')]
from compose import read_rcc
from resource_bundle import rcc
O=P/'build/radio-wifi-page';stage=O/'stage';files=stage/'files';files.mkdir(parents=True,exist_ok=True)
def sha(b):return hashlib.sha256(b).hexdigest()
prior=P/'build/radio-three-state/stage/files'
values=read_rcc((prior/'af-ui.rcc').read_bytes())
original=read_rcc((P/'build/focus-delivery-repair/stage/files/af-ui.rcc').read_bytes())
values['/controlscreen/ControlScreen.qml']=original['/controlscreen/ControlScreen.qml']
for n in ['RadioModeButton.qml','RadioModeSettingsRow.qml']:
    values['/common/'+n]=(P/'qml/common'/n).read_text(encoding='utf-8')
s=values['/settings/SettingsGeneric.qml']
s=s.replace('import QtQuick 2.0','import QtQuick 2.0\nimport "../common"',1)
a='                    sourceComponent: {\n                        switch(editType) {'
assert s.count(a)==1
s=s.replace(a,'''                    sourceComponent: {
                        if (name === "WIFI_power" && typeof hblNative!=="undefined")
                            return wifiModeDelegate
                        switch(editType) {''')
a='                // Delegates for different edit rows'
assert s.count(a)==1
s=s.replace(a,'''                Component {
                    id: wifiModeDelegate
                    RadioModeSettingsRow {
                        title: text1
                        fontName: constants.menuItemFontName
                        textSize: itemTextSize
                        textColor: constants.menuItemColor
                        labelMargin: constants.subSettingDropDownXMargin
                        switchSpacing: constants.subSettingDropDownSpacing
                    }
                }
'''+a)
values['/settings/SettingsGeneric.qml']=s
blob=rcc(values);assert read_rcc(blob)==values
(files/'af-ui.rcc').write_bytes(blob)
(files/'baseline.sha256').write_bytes((prior/'baseline.sha256').read_bytes())
old=(prior/'manifest.sha256').read_bytes();lines=[]
for line in old.decode().splitlines():
    h,n=line.split('  ',1);lines.append((sha(blob) if n=='af-ui.rcc' else h)+'  '+n)
manifest=('\n'.join(lines)+'\n').encode();(files/'manifest.sha256').write_bytes(manifest)
for n,b in [('old-pin',sha(old)),('new-pin',sha(manifest))]:(stage/n).write_text(b+'\n',newline='\n')
s=(P/'build/focus-delivery-repair/stage/repair.sh').read_text(encoding='utf-8').replace('.focus-delivery-repair-backup','.radio-wifi-page-backup')
(stage/'repair.sh').write_text(s,encoding='utf-8',newline='\n')
(stage/'run.sh').write_text('#!/bin/sh\nexit 0\n',newline='\n')
members=['files/af-ui.rcc','files/baseline.sha256','files/manifest.sha256','old-pin','new-pin','repair.sh','run.sh']
checks=''.join(sha((stage/n).read_bytes())+'  '+n+'\n' for n in sorted(members))
for n in ['manifest.sha256','repair-manifest.sha256']:(stage/n).write_text(checks,newline='\n')
members+=['manifest.sha256','repair-manifest.sha256']
with tarfile.open(O/'repair.tgz','w:gz') as t:
    for n in members:
        b=(stage/n).read_bytes();i=tarfile.TarInfo(n);i.size=len(b);i.mode=0o600;t.addfile(i,io.BytesIO(b))
r=dict(bytes=(O/'repair.tgz').stat().st_size,packageSha256=sha((O/'repair.tgz').read_bytes()),oldPin=sha(old),newPin=sha(manifest),installed=False)
(O/'package.json').write_text(json.dumps(r,indent=2))
s=(P/'build/radio-three-state/install.py').read_text(encoding='utf-8').replace('radio-three-state','radio-wifi-page')
(O/'install.py').write_text(s,encoding='utf-8',newline='\n')
print(json.dumps(r))
