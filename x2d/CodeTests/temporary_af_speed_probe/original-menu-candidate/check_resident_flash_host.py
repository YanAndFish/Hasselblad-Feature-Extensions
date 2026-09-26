"""真实桌面 Qt 生命周期检查；不执行相机工具，不宣称原厂集成已完成。"""
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
if sys.version_info[:2] != (3, 11):
    raise SystemExit('Use py -3.11 -B: the existing Qt runtime is validated with Python 3.11.')
D = Path(__file__).resolve().parent
ROOT = D.parents[3]
sys.path.insert(0, str(ROOT / 'x2d/outputs/4.2.0/temporary-wifi-button/qt-runtime'))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QT_QUICK_BACKEND'] = 'software'
os.environ['QML_DISABLE_DISK_CACHE'] = '1'
from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest
from shiboken6 import getCppPointer, isValid


def main():
    app = QGuiApplication([])
    engine = QQmlApplicationEngine()
    errors = []
    engine.warnings.connect(lambda ws: errors.extend(str(w) for w in ws))
    source = '''import QtQuick
import QtQuick.Window
Window {
    visible: false; width: 1024; height: 768
    ResidentFlashHost { objectName: "host"; anchors.fill: parent }
}'''
    engine.loadData(source.encode(), QUrl.fromLocalFile(str(D / 'host.qml')))
    assert engine.rootObjects(), errors
    window = engine.rootObjects()[0]
    host = window.findChild(QQuickItem, 'host')
    assert host is not None
    page = host.findChild(QQuickItem, 'FormalFlashPage')
    assert page is not None
    pointer = getCppPointer(page)[0]
    destroyed = []
    page.destroyed.connect(lambda: destroyed.append(True))
    returned = []
    host.mainMenuRequested.connect(lambda: returned.append(True))
    assert not host.property('showing') and not window.isVisible()
    assert host.openFlash() is False
    window.setVisible(True)
    host.setProperty('menuActive', True)
    host.setProperty('mediaProcessing', True)
    assert host.openFlash() is False
    host.setProperty('mediaProcessing', False)
    host.setProperty('stockSubmenuActive', True)
    assert host.openFlash() is False
    host.setProperty('stockSubmenuActive', False)
    assert host.openFlash() is True
    QTest.qWait(50)
    page.setProperty('channel', 7)
    page.openGroup(2)
    QTest.keyClick(window, Qt.Key_Escape)
    assert page.property('screen') == 'groups' and host.property('showing')
    QTest.keyClick(window, Qt.Key_Escape)
    assert not host.property('showing') and len(returned) == 1
    for _ in range(100):
        assert host.openFlash() is True
        host.back()
        assert not host.property('showing')
        assert isValid(page) and getCppPointer(host.findChild(QQuickItem, 'FormalFlashPage'))[0] == pointer
    assert not destroyed and page.property('channel') == 7
    assert host.openFlash() is True
    host.setProperty('menuActive', False)
    assert not host.property('showing') and not host.property('flashOpen')
    host.setProperty('menuActive', True)
    assert not host.property('showing')  # 半按退出后重进菜单不得自动弹回引闪页。
    assert host.openFlash() is True
    host.setProperty('stockSubmenuActive', True)
    assert not host.property('showing')
    host.setProperty('stockSubmenuActive', False)
    assert not host.property('showing')
    assert not page.property('connected') and not page.property('canTest')
    assert not errors, errors
    print(json.dumps(dict(result='PASS', cycles=100, samePageInstance=True,
                          hiddenAtCreation=True, nestedBack=True,
                          stockExitClearsVisibility=True, cameraAccesses=0,
                          limitation='Desktop Qt candidate only; no original GUI integration or device latency validation')))


if __name__ == '__main__':
    main()
