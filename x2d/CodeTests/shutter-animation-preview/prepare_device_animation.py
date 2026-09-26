"""基于固定原菜单 QML 生成增量候选；仅本地，不执行安装或连接设备。"""
import hashlib
import json
from pathlib import Path
import re

D = Path(__file__).resolve().parent
BASE_SHA = '7bd57701e10d6ffb4d04164fb9718c5d1b92f8cb6143aa1b4be5b2ed171709d7'
GUI_SHA = '16391452abdc69de9e0807e065c0f4ab3f1ccb5fc288f6fc4e6f5cb3bdca12e0'


def prepare():
    candidate = D.parent / 'temporary_af_speed_probe/original-menu-candidate'
    source = (candidate / 'Bootstrap.qml').read_text(encoding='utf-8').replace('../menu-candidate/flash-ui', '.')
    names = dict(Bootstrap='X2dNativeMenuBootstrap', FlashMenuModel='X2dNativeMenuModel',
                 FlashMenuRoute='X2dNativeMenuRoute', ResidentFlashHost='X2dNativeMenuHost')
    for path in (candidate.parent/'menu-candidate/flash-ui').glob('*.qml'):
        names[path.stem] = 'X2d'+path.stem
    source = re.sub(r'\b('+'|'.join(names)+r')\b', lambda m: names[m[0]], source)
    if hashlib.sha256(source.encode()).hexdigest() != BASE_SHA:
        raise ValueError('菜单基线变化，停止生成，不能覆盖未知版本')
    out = D/'outputs/device-package'
    out.mkdir(parents=True, exist_ok=True)
    (out/'X2dNativeMenuBootstrap.qml.before-shutter').write_text(source, encoding='utf-8', newline='\n')
    source = source.replace('import QtQuick\n', 'import QtQuick\nimport QtQuick.Window\n', 1)
    addition = '''
    // 独立观察拍摄页面状态；不修改菜单路由、焦点或曝光流程。
    Loader {
        objectName: "X2dShutterLoader"
        parent: root.Window.window ? root.Window.window.contentItem : null
        anchors.fill: parent
        z: 1000
        active: root.attached && parent !== null
        source: "file:///system/etc/X2dShutterAnimation.qml"
        onLoaded: { item.stateSource = root.drawer; console.info("X2D_SHUTTER_ATTACHED") }
    }
'''
    source = source.rstrip()
    if not source.endswith('}'):
        raise ValueError('Unexpected root end')
    source = source[:-1]+addition+'}\n'
    (out/'X2dNativeMenuBootstrap.qml').write_text(source, encoding='utf-8', newline='\n')
    (out/'X2dShutterAnimation.qml').write_bytes((D/'X2dShutterAnimation.qml').read_bytes())
    entries = []
    for name in ['X2dNativeMenuBootstrap.qml', 'X2dShutterAnimation.qml']:
        raw = (out/name).read_bytes()
        entries.append(dict(source=name, target='/system/etc/'+name, sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw)))
    manifest = dict(model='X2D 100C', firmware='4.2.0', guiSha256=GUI_SHA,
                    originalBootstrapSha256=BASE_SHA, files=entries,
                    nativeLibraryUnchanged=True, bootConfigurationUnchanged=True,
                    deviceValidated=False)
    (out/'package.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    return manifest


if __name__ == '__main__':
    print(json.dumps(prepare(), indent=2))
