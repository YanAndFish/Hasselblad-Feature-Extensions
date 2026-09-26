"""Qt5 桌面无照片替身：保留对象、清除图像，以及隐藏不释放的负例。"""
from pathlib import Path
import json, os, sys, time
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'x1d/candidates/ui-resident/fixes/card-format-r1/build/python-qt515'))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PyQt5.QtCore import QUrl, qVersion
from PyQt5.QtGui import QGuiApplication, QImage, QColor
from PyQt5.QtQml import QQmlEngine, QQmlComponent
from PyQt5.QtQuick import QQuickImageProvider

class Provider(QQuickImageProvider):
    def __init__(self):
        super().__init__(QQuickImageProvider.Image)
        self.requests = []
    def requestImage(self, name, size):
        self.requests.append(name)
        if name.startswith('delayed'):
            time.sleep(0.12)
        data = QImage(32, 24, QImage.Format_RGB32)
        data.fill(QColor('red'))
        return data, data.size()

def run():
    app = QGuiApplication([])
    engine = QQmlEngine()
    provider = Provider()
    engine.addImageProvider('fixture', provider)
    def wait(predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            app.processEvents()
            if predicate(): return
            time.sleep(0.005)
        raise AssertionError('等待超时')
    def settle(seconds=0.2):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents(); time.sleep(0.005)
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(HERE / 'qml/ResidentPhotoSurface.qml')))
    obj = component.create()
    assert obj is not None, [e.toString() for e in component.errors()]
    pixels = obj.findChild(type(obj), 'residentPixels')
    # QObject 子类包装类型不固定，按子对象名定位。
    if pixels is None: pixels = next(c for c in obj.children() if c.objectName() == 'residentPixels')
    checks = []
    def check(name, condition):
        assert condition, name
        checks.append(name)
    settle()
    check('预建没有请求图像', not provider.requests and obj.property('imageStatus') == 0)
    obj.setProperty('selectedSource', QUrl('image://fixture/first'))
    settle()
    check('隐藏时设置URL仍不读图', not provider.requests)
    obj.setProperty('presented', True)
    wait(lambda: obj.property('imageStatus') == 1)
    check('打开后正常载入替身图像', len(provider.requests) == 1)
    obj.setProperty('presented', False)
    wait(lambda: obj.property('imageStatus') == 0)
    check('退出清空URL且保留Image对象', obj.property('imageSource').isEmpty() and obj.property('selectedSource').isEmpty() and pixels in obj.children())
    obj.setProperty('selectedSource', QUrl('image://fixture/first'))
    obj.setProperty('presented', True)
    wait(lambda: obj.property('imageStatus') == 1)
    check('再次打开重新请求无额外图像缓存', len(provider.requests) == 2)
    obj.setProperty('presented', False)
    obj.setProperty('selectedSource', QUrl('image://fixture/delayed-old'))
    obj.setProperty('presented', True)
    wait(lambda: 'delayed-old' in provider.requests)
    obj.setProperty('presented', False)
    settle(0.3)
    check('退出后迟到结果不能恢复旧图', obj.property('imageStatus') == 0 and obj.property('imageSource').isEmpty())
    for index in range(20):
        obj.setProperty('selectedSource', QUrl('image://fixture/cycle-' + str(index)))
        obj.setProperty('presented', True)
        wait(lambda: obj.property('imageStatus') == 1)
        obj.setProperty('presented', False)
        wait(lambda: obj.property('imageStatus') == 0)
    check('20次进出后对象仍相同且没有图像引用', pixels in obj.children() and obj.property('imageSource').isEmpty())
    negative = QQmlComponent(engine)
    negative.setData(b'import QtQuick 2.5; Image { visible: false; cache: false; asynchronous: true; source: "image://fixture/hidden-negative" }', QUrl())
    hidden = negative.create()
    assert hidden is not None
    wait(lambda: hidden.property('status') == 1)
    check('负例仅visible=false仍载入并保持图像', hidden.property('source').toString().endswith('hidden-negative'))
    hidden.setProperty('source', QUrl())
    obj.deleteLater(); hidden.deleteLater(); settle()
    output = {'passed': True, 'checks': checks, 'hostQt': qVersion(), 'providerRequests': len(provider.requests),
              'cameraRequests': 0, 'realPhotos': 0, 'productionIntegrated': False, 'targetQt55Verified': False,
              'gpuTextureReleaseVerified': False, 'osCacheClearedClaim': False}
    (HERE / 'artifacts').mkdir(exist_ok=True)
    (HERE / 'artifacts/lifecycle.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(output, ensure_ascii=False))

if __name__ == '__main__': run()
