"""只读复用 X1D 引闪纯 UI，在当前 X2D 测试目录生成无设备适配层副本。"""
import hashlib
import json
import re
from pathlib import Path

D = Path(__file__).resolve().parent
ROOT = D.parents[2]
SOURCE = ROOT / 'x1d/wireless-flash/ui/formal'
OUT = D / 'menu-candidate/flash-ui'
NAMES = ('FlashStyle', 'FlashText', 'FlashValueText', 'FlashIconButton',
         'FlashToggleRow', 'FlashLampIcon', 'FlashPage')

def prepare():
    OUT.mkdir(exist_ok=True)
    evidence = {'cameraAdapter': False, 'radioAdapter': False, 'sources': {}, 'icons': {}}
    page = (SOURCE / 'FlashPage.qml').read_text(encoding='utf-8')
    icons = sorted(set(re.findall(r'page\.iconBase\+"([^"]+)"', page)))
    data = {}
    for name in icons:
        # 宿主需先注册其资源；本工具不提取或嵌入宿主图片。
        if '/' in name or '\\' in name or '..' in name:
            raise ValueError('Invalid host icon resource name')
        data[name] = 'qrc:/icons/' + name
        evidence['icons'][name] = {'source': data[name], 'bundled': False}
    for name in NAMES:
        raw = (SOURCE / (name + '.qml')).read_bytes()
        evidence['sources'][name] = hashlib.sha256(raw).hexdigest()
        text = raw.decode('utf-8')
        assert not any(token in text for token in ('XMLHttpRequest', 'hblNative', 'doDo_exposure', 'Qt.openUrlExternally'))
        if name == 'FlashPage':
            for icon, url in data.items():
                text = text.replace('page.iconBase+"' + icon + '"', json.dumps(url))
        (OUT / (name + '.qml')).write_text(text, encoding='utf-8', newline='\n')
    (OUT / 'provenance.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    return evidence

if __name__ == '__main__':
    result = prepare()
    print(json.dumps({'components': len(result['sources']), 'icons': len(result['icons']), 'cameraAdapter': False}))
