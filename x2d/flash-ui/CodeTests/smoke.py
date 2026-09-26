"""离线加载自绘图标与页面；不导入任何设备模块。"""
import argparse
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_QUICK_BACKEND', 'software')
os.environ['QML_DISABLE_DISK_CACHE'] = '1'
from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication, QFontDatabase, QFont
from PySide6.QtQuick import QQuickView
from PySide6.QtQml import QQmlEngine, QQmlExpression
from PySide6.QtTest import QTest

parser = argparse.ArgumentParser()
parser.add_argument('--screenshot', type=Path)
parser.add_argument('--font', type=Path, help='Optional installed font for headless platforms without font discovery')
args = parser.parse_args()
app = QGuiApplication([])
font_family = None
if args.font:
    font_id = QFontDatabase.addApplicationFont(str(args.font.resolve()))
    families = QFontDatabase.applicationFontFamilies(font_id)
    if font_id < 0 or not families:
        raise RuntimeError('Cannot load the supplied local font')
    font_family = families[0]
    app.setFont(QFont(font_family))
view = QQuickView()
view.setResizeMode(QQuickView.SizeRootObjectToView)
view.resize(640, 480)
view.setSource(QUrl.fromLocalFile(str(Path(__file__).resolve().parents[1] / 'Preview.qml')))
if view.status() != QQuickView.Ready:
    raise RuntimeError('\n'.join(e.toString() for e in view.errors()))
view.show()
QTest.qWait(250)
root = view.rootObject()
if font_family:
    assert root.setProperty('fontName', font_family)
    QTest.qWait(100)
assert root.property('connected') is False
assert root.property('canTest') is False
for screen in ['settings', 'selection', 'power', 'wireless', 'groups']:
    assert root.setProperty('screen', screen)
    QTest.qWait(25)
    assert root.property('screen') == screen

def children(item):
    for child in item.children():
        yield child
        yield from children(child)

images = [item for item in children(root) if item.inherits('QQuickImage') and not item.property('source').isEmpty()]
assert images, 'No icons were instantiated'
for item in images:
    check = QQmlExpression(QQmlEngine.contextForObject(item), item, 'status === Image.Ready')
    value = check.evaluate()
    if isinstance(value, tuple):
        value = value[0]
    assert not check.hasError() and value is True, 'Icon did not load: ' + item.property('source').toString()
if args.screenshot:
    args.screenshot.parent.mkdir(parents=True, exist_ok=True)
    assert view.grabWindow().save(str(args.screenshot))
print('PASS: five local pages; vector icons loaded; device adapter absent')
view.close()
