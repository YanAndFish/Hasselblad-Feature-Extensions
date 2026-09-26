"""真实桌面 Qt 检验：默认隐藏、十二格、纯 UI 引闪页与返回。"""
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
ROOT = D.parents[2]
sys.path.insert(0, str(ROOT / 'x2d/outputs/4.2.0/temporary-wifi-button/qt-runtime'))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QT_QUICK_BACKEND'] = 'software'
os.environ['QML_DISABLE_DISK_CACHE'] = '1'
from PySide6.QtCore import QUrl, Qt, QPoint, QTranslator
from PySide6.QtGui import QGuiApplication, QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest


def main():
    assets = D / 'menu-candidate/assets'
    app = QGuiApplication([])
    for path in assets.glob('*.ttf'):
        assert QFontDatabase.addApplicationFont(str(path)) >= 0
    translator = QTranslator()
    assert translator.load(str(assets / 'camera_zh_CN.qm'))
    app.installTranslator(translator)
    engine = QQmlApplicationEngine()
    errors = []
    engine.warnings.connect(lambda items: errors.extend(str(e) for e in items))
    source = D / 'menu-candidate/CustomMainMenu.qml'
    if '--inline' in sys.argv:
        # Validate the actual single-file device bundle with host icon URLs.
        bundle_dir = D / ('input-candidate' if '--input' in sys.argv else 'menu-candidate')
        text = (bundle_dir / 'x2d-menu-v1-main.qml').read_text(encoding='utf-8')
        text = text.replace('qrc:/icons/', assets.as_uri() + '/')
        source = D / 'menu-candidate/inline-host.qml'
        source.write_text(text, encoding='utf-8')
    engine.load(QUrl.fromLocalFile(str(source)))
    assert len(engine.rootObjects()) == 1, errors
    window = engine.rootObjects()[0]
    window.setWidth(1024)
    window.setHeight(768)
    assert not window.isVisible()
    visible_events = []
    window.visibleChanged.connect(visible_events.append)
    QTest.qWait(300)
    assert not window.isVisible() and not visible_events
    order = json.loads((D / 'menu-candidate/asset-evidence.json').read_text(encoding='utf-8'))['order']
    clicks = []
    window.settingsRequested.connect(clicks.append)
    window.setVisible(True)
    QTest.qWait(250)
    assert window.isVisible()
    # Keyboard navigation belongs to this window, including initial selection.
    QTest.keyClick(window, Qt.Key_Right)
    assert window.property('selectedIndex') == 0
    QTest.keyClick(window, Qt.Key_Down)
    assert window.property('selectedIndex') == 4
    QTest.keyClick(window, Qt.Key_Left)
    assert window.property('selectedIndex') == 3
    QTest.keyClick(window, Qt.Key_Escape)
    assert window.property('selectedIndex') == -1
    image = window.grabWindow()
    assert not image.isNull()
    assert image.save(str(D / 'menu-candidate/menu-preview.png'))
    cells = []
    def visual_child(item, name):
        if item.objectName() == name:
            return item
        for child in item.childItems():
            result = visual_child(child, name)
            if result is not None:
                return result
        return None
    for i, key in enumerate(order):
        touch = visual_child(window.contentItem(), 'menuTouch_' + key)
        assert touch is not None, key
        point = touch.mapToScene(touch.boundingRect().center())
        cells.append([key, round(point.x(), 2), round(point.y(), 2)])
        before = len(clicks)
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(round(point.x()), round(point.y())))
        QTest.qWait(5)
        if key == 'customTest':
            assert len(clicks) == before
            assert window.property('flashPageOpen') is True
            QTest.qWait(100)
            flash = visual_child(window.contentItem(), 'FormalFlashPage')
            assert flash is not None and flash.isVisible()
            assert not flash.property('connected') and not flash.property('masterEnabled')
            assert not flash.property('canTest')
            assert window.grabWindow().save(str(D / 'menu-candidate/flash-preview.png'))
            back = visual_child(window.contentItem(), 'FlashBack')
            pos = back.mapToScene(back.boundingRect().center())
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(round(pos.x()), round(pos.y())))
            QTest.qWait(10)
            assert not window.property('flashPageOpen')
            assert not flash.isVisible()
        else:
            assert clicks[-1] == key and len(clicks) == before + 1
        assert engine.rootObjects()[0] is window
    for _ in range(10):
        window.setVisible(False)
        QTest.qWait(1)
        assert not window.isVisible()
        window.setVisible(True)
        QTest.qWait(1)
        assert window.isVisible() and engine.rootObjects()[0] is window
    window.setVisible(False)
    assert not errors, errors
    report = dict(source='host Qt 6.4.1', deviceAccesses=0, deployed=False,
                  initiallyHidden=True, sameWindowAcrossToggles=True,
                  menuRequests=clicks, flashNavigationAndReturn=True,
                  noDeviceAdapter=True, singleFileBundle='--inline' in sys.argv, cells=cells,
                  remaining=['Camera page bridge is not connected',
                             'Factory settings return interception is not implemented',
                             'Host rendering is not a camera visual match validation'])
    (D / 'menu-candidate/host-validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
