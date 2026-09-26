"""提取固定官方 GUI 的菜单视觉资产到本实验目录；没有设备访问。"""
import hashlib
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
from inspect_menu_resources import load_gui, resources, GUI_SHA
from firmware_image import system_file

D = Path(__file__).resolve().parent / 'menu-candidate'
ORDER = ['exposureMenu', 'focusMenu', 'qualityMenu', 'cropModesMenu',
         'flashMenu', 'displayMenu', 'powerMenu', 'storageMenu',
         'ibisMenu', 'wifiMenu', 'generalMenu']


def main():
    gui = load_gui()
    data = dict(resources(gui))
    out = D / 'assets'
    out.mkdir(parents=True, exist_ok=True)
    evidence = []

    def save(name, content, source):
        (out / name).write_bytes(content)
        evidence.append(dict(file=name, source=source, bytes=len(content),
                             sha256=hashlib.sha256(content).hexdigest()))

    for name in ORDER:
        path = ':/icons/' + name + '.svg'
        save(name + '.svg', data[path], path)
    save('camera_zh_CN.qm', data[':/translations/camera_zh_CN.qm'],
         ':/translations/camera_zh_CN.qm')
    for name in ['AvenirNext-Regular-08.ttf', 'AvenirNext-Bold-01.ttf', 'DroidSansFallback.ttf']:
        path = '/lib64/qt/lib/fonts/' + name
        save(name, system_file(path), path)
    report = dict(firmware='X2D 100C 4.2.0', guiSha256=GUI_SHA,
                  deviceAccesses=0, deployed=False,
                  order=ORDER + ['customTest'], baseScreen=[1024, 768],
                  orderEvidence='MenuX2d::topMenus 0x358b38; initializer 0x2ba4a0..0x2ba678, eleven 32-byte records',
                  visualEvidence='MainScreen.qml, ScaledImage.qml, FramedItem.qml, GlobalConstants.qml',
                  assets=evidence)
    (D / 'asset-evidence.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(files=len(evidence), order=report['order'], deployed=False)))


if __name__ == '__main__':
    main()
