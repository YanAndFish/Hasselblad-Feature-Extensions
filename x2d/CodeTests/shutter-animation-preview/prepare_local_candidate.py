"""本地 800 ms + 曝光设置候选，只产出文件清单，不生成可执行安装事务。"""
import hashlib
import json
from pathlib import Path
from prepare_device_animation import prepare

D = Path(__file__).resolve().parent

def main():
    baseline = prepare()  # Existing exact bootstrap guard remains in force.
    out = D / 'outputs/device-package'
    path = out / 'X2dNativeMenuBootstrap.qml'
    text = path.read_text(encoding='utf-8')
    needle = 'objectName: "X2dShutterLoader"'
    assert text.count(needle) == 1
    text = text.replace(needle, 'id: shutterLoader\n        ' + needle)
    hook = '''
    X2dExposureSettings {
        searchRoot: root.menu
        preferences: shutterLoader.item ? shutterLoader.item.preferences : null
        active: root.attached && root.originalLoader !== null && root.originalLoader.active
    }
'''
    text = text.rstrip()[:-1] + hook + '}\n'
    path.write_text(text, encoding='utf-8', newline='\n')
    names = ['X2dNativeMenuBootstrap.qml', 'X2dShutterAnimation.qml',
             'X2dEffectPreferences.qml', 'X2dExposureOption.qml', 'X2dExposureSettings.qml']
    for name in names[2:]:
        (out/name).write_bytes((D/name).read_bytes())
    files = [dict(source=name, target='/system/etc/'+name,
                  sha256=hashlib.sha256((out/name).read_bytes()).hexdigest()) for name in names]
    manifest = dict(model='X2D 100C', firmware='4.2.0', sourceCommit='91b48ce',
                    animationMs=800, states=['关', '动画', '动画与声音'], defaultState=2,
                    guiSha256=baseline['guiSha256'], files=files,
                    requiresUpdatedAudioService=True, requiresUpdatedLauncher=True,
                    installable=False, deviceValidated=False)
    (out/'local-candidate.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    # Do not leave a misleading old installation manifest beside the expanded candidate.
    (out/'package.json').write_text(json.dumps(dict(installable=False,
        reason='Local 800ms settings candidate; use local-candidate.json for offline review.'), indent=2)+'\n')
    print('Prepared local review candidate only; no installation or device access.')

if __name__ == '__main__':
    main()
