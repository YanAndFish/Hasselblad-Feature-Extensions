"""真实 Qt 6.4.1 解析、绘制与空点击验证；不连接相机。"""
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / 'outputs/4.2.0/temporary-wifi-button'
sys.path.insert(0, str(OUT / 'qt-runtime'))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QT_QUICK_BACKEND'] = 'software'
os.environ['QML_DISABLE_DISK_CACHE'] = '1'
from PySide6.QtCore import QUrl, Qt, QPoint, QObject
from PySide6.QtGui import QGuiApplication, QFontDatabase, QFont
from PySide6.QtQuick import QQuickView, QQuickItem
from PySide6.QtTest import QTest
from build_candidate import FOOTER


def main():
    formatter = OUT / 'qt-runtime/PySide6/qmlformat.exe'
    parse = subprocess.run([str(formatter), '--ignore-settings', str(OUT / 'SettingsGeneric.qml')], capture_output=True)
    assert parse.returncode == 0, parse.stderr.decode(errors='replace')
    assert 'onClicked: {}' in FOOTER
    for forbidden in ['System.', 'Camera.', 'Phocus.', 'viewModel.', 'Qt.quit', 'onPressed:', 'onReleased:']:
        assert forbidden not in FOOTER
    qml = '''import QtQuick
Rectangle {
    id: root
    width: 960; height: 720; color: "black"
    property string menuLabel: "Wi-Fi"
    property real heightForItem: 100
    QtObject {
        id: constants
        property real settingsMenuSettingLeftMargin: 48
        property real scaleFactor: 1
        property string settingsMenuButtonFontName: "Microsoft YaHei"
    }
    Text { x: 48; y: 20; text: root.menuLabel; color: "white"; font.pixelSize: 40 }
    ListView {
        id: list
        x: 0; y: 90; width: parent.width; height: 580
        model: ["Wi-Fi", "Frequency", "Network", "Password"]
        delegate: Item {
            width: list.width; height: 100
            Text { anchors.verticalCenter: parent.verticalCenter; x: 48; text: modelData; color: "white"; font.pixelSize: 28 }
        }
''' + FOOTER.replace('Constants.', 'constants.') + '\n    }\n}\n'
    harness = OUT / 'footer-harness.qml'
    harness.write_text(qml, encoding='utf-8')
    app = QGuiApplication([])
    font_id = QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
    assert font_id >= 0
    app.setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0]))
    view = QQuickView()
    view.setSource(QUrl.fromLocalFile(str(harness)))
    assert view.status() == QQuickView.Ready, [str(e) for e in view.errors()]
    view.show()
    QTest.qWait(150)
    root = view.rootObject()
    footer = root.findChild(QQuickItem, 'temporaryWifiButtonFooter')
    button = root.findChild(QQuickItem, 'temporaryWifiButtonMouse')
    assert footer is not None and button is not None and footer.isVisible()
    assert footer.height() == 100
    point = button.mapToScene(button.boundingRect().center())
    before = (root.property('menuLabel'), footer.height(), footer.isVisible())
    for _ in range(5):
        QTest.mouseClick(view, Qt.LeftButton, Qt.NoModifier, QPoint(round(point.x()), round(point.y())))
    assert (root.property('menuLabel'), footer.height(), footer.isVisible()) == before
    screenshot = view.grabWindow()
    assert not screenshot.isNull() and screenshot.save(str(OUT / 'footer-preview.png'))
    for other in ['Power', 'Storage', 'Service']:
        root.setProperty('menuLabel', other)
        app.processEvents()
        assert not footer.isVisible() and footer.height() == 0
    root.setProperty('menuLabel', 'Wi-Fi')
    app.processEvents()
    assert footer.isVisible() and footer.height() == 100
    report = {'source': 'host-qt-6.4.1', 'wholeCandidateSyntax': 'pass', 'footerRendering': 'pass',
              'fiveEmptyClicks': 'pass', 'otherPagesHidden': 'pass', 'returnToWifi': 'pass',
              'cameraInstalled': False, 'nativeQmlCacheFallbackVerified': False}
    (OUT / 'host-validation.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))
    view.close()


if __name__ == '__main__':
    main()
