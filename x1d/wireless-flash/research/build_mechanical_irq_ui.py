"""独立构建双来源界面，保留延时；按最新要求移除同程序开关。未安装。"""
from pathlib import Path
import hashlib
import importlib.util
import json

HERE = Path(__file__).resolve().parents[1]
OUT = HERE/'build/mechanical-irq-candidate'
BASE = HERE/'build/mechanical-options-candidate'


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('界面基线不匹配: '+old[:80])
    return text.replace(old, new)


def build():
    if Path.cwd().resolve() != HERE.parents[1]:
        raise RuntimeError('工作区不匹配')
    files = {'/'+p.relative_to(BASE/'qml').as_posix(): p.read_text(encoding='utf-8')
             for p in (BASE/'qml').rglob('*.qml')}
    spec = importlib.util.spec_from_file_location('irq_ui_assets', HERE/'build.py')
    assets = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(assets)
    original = assets.rcc(files)
    if original != (BASE/'package-files/ui.rcc').read_bytes():
        raise ValueError('双开关版本的 QML 与已构建资源不一致')
    page = files['/controlscreen/MechanicalFlashPage.qml']
    toggle = page.index('                color: mainRoot.hblRfSameProcess')
    toggle_start = page.rfind('            Rectangle {', 0, toggle)
    toggle_end = page.index('\n            }', toggle)+len('\n            }')
    page = page[:toggle_start]+page[toggle_end:]
    page = page.replace('width: (parent.width-16*panel.unit)/3; height: parent.height; radius: 4',
                        'width: (parent.width-8*panel.unit)/2; height: parent.height; radius: 4')
    start = page.index('        Grid {')
    end = page.index('        Row {', start)
    page = page[:start]+'''        Row {
            width: parent.width; height: 54 * panel.unit; spacing: 8 * panel.unit
            Repeater {
                model: [2, 3]
                delegate: Rectangle {
                    width: (panel.width - 40 * panel.unit) / 2
                    height: 54 * panel.unit; radius: 4
                    color: mainRoot.hblRfSource === modelData ? "#805829" : "#303030"
                    border.color: mainRoot.hblRfSource === modelData ? "#E3A156" : "#303030"
                    Text {
                        anchors.centerIn: parent
                        text: modelData === 2 ? "启动保持" : "退出空闲"
                        color: "white"; font.pixelSize: 23 * panel.unit
                    }
                    MouseArea {
                        anchors.fill: parent
                        onClicked: mainRoot.hblRfSelectSource(modelData)
                    }
                }
            }
        }
        Text {
            width: parent.width; height: 28 * panel.unit
            text: "CH 5 · ID 5 · D 组"; color: "#AAA"; font.pixelSize: 17 * panel.unit
        }
'''+page[end:]
    files['/controlscreen/MechanicalFlashPage.qml'] = page
    main = files['/main.qml']
    main = once(main, '    property bool hblRfSameProcess: hblRfAvailable && hblNative.sameProcess\n', '')
    main = once(main, '    function hblRfToggleProcess() { if (hblRfAvailable) hblNative.command="process " + (hblRfSameProcess ? "0" : "1"); }\n', '')
    main = once(main, '    function hblRfSelectSource(source) {',
                '    function hblRfSelectSource(source) {\n        if (source !== 2 && source !== 3) return;')
    files['/main.qml'] = main
    OUT.mkdir(exist_ok=True)
    for name, text in files.items():
        p = OUT/'qml'/name.lstrip('/')
        p.parent.mkdir(exist_ok=True, parents=True)
        p.write_text(text, encoding='utf-8')
    artifact = assets.rcc(files)
    (OUT/'ui.rcc').write_bytes(artifact)
    # 使用原编号 2/3，不能把两项界面下标 0/1 发给原接收器。
    assert 'model: [2, 3]' in page and 'hblRfSelectSource(modelData)' in page
    assert 'hblRfSourceDelays[source]' in main and 'hblRfSourceDelays.slice(0)' in main
    for label in ('自动引闪：', '每次准备：'):
        assert page.count(label) == 1
    assert '同一程序处理' not in page and 'hblRfToggleProcess' not in page
    removed = ['A 首次同步', 'B 首次同步', '状态 1 置位', '状态 3 置位', '返回空闲']
    assert all(label not in page for label in removed)
    report = {'built': True, 'installed': False, 'hardwareRequests': 0,
              'visibleSources': [{'id': 2, 'label': '启动保持'}, {'id': 3, 'label': '退出空闲'}],
              'independentDelaysRetained': True, 'toggleCount': 2,
              'processModeToggleRemoved': True, 'interruptModeToggleAdded': False,
              'sourceNumberingRetained': True, 'targetQmlRuntimeChecked': False,
              'baselineRccSha256': hashlib.sha256(original).hexdigest(),
              'rccSha256': hashlib.sha256(artifact).hexdigest(), 'rccBytes': len(artifact),
              'removedSourceObservation': {'labels': removed, 'description': '快门结束后触发',
                  'evidenceKind': '用户试拍反馈及标注要求', 'physicalTimingMeasured': False},
              'sourceSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (OUT/'ui-build.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    print(json.dumps(build(), ensure_ascii=False))
