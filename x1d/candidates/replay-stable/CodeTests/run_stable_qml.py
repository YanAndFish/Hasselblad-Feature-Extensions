"""宿主 Qt6 执行候选图层片段；检查实际 RCC 解包，不代表目标 GPU 行为。"""
import os,sys,json
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'x1d/wireless-flash/build/ui-test-python'))
os.environ.update(QT_QPA_PLATFORM='offscreen',QT_QUICK_BACKEND='software',QML_DISABLE_DISK_CACHE='1')
from PySide6.QtCore import QUrl,QResource,QFile,QIODevice,QObject
from PySide6.QtGui import QGuiApplication,QImage,QColor
from PySide6.QtQml import QQmlEngine,QQmlComponent
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtTest import QTest
from hashlib import sha256

def balanced(s,start):
    at=s.index('{',start);depth=1;end=at+1
    while depth:
        depth+=(s[end]=='{')-(s[end]=='}');end+=1
    return end
class Images(QQuickImageProvider):
    def __init__(self):super().__init__(QQuickImageProvider.Image)
    def requestImage(self,id,size,requested):
        if id=='fail':return QImage()
        result=QImage(16,16,QImage.Format_RGB32);result.fill(QColor('red' if id=='preview' else 'blue'))
        size.setWidth(16);size.setHeight(16);return result

def run():
    app=QGuiApplication.instance() or QGuiApplication([]);engine=QQmlEngine();engine.addImageProvider('fixture',Images())
    source=(HERE/'artifacts/session/MediaBrowseView.qml').read_text(encoding='utf-8')
    start=source.index('            Image {\n                id: flick_img')
    end=balanced(source,source.index('            Image {\n                id: flick_fullimg'))
    fragment=source[start:end]
    while 'CropOverlay {' in fragment:
        a=fragment.index('CropOverlay {');b=balanced(fragment,a);fragment=fragment[:a]+fragment[b:]
    fragment=fragment.replace('id: flick_img','id: flick_img\n                objectName: "preview"\n                source: "image://fixture/preview"')
    fragment=fragment.replace('id: flick_fullimg','id: flick_fullimg\n                objectName: "full"')
    text='import QtQuick 2.5\nItem {\n id: root\n width: 100; height: 100\n QtObject { id: flick; property int contentWidth: 100; property int contentHeight: 100; property int contentX: 0; property int contentY: 0 }\n function loadFull(path) { flick_fullimg.source=path }\n function isLoading() { return flick_fullimg.status===Image.Loading }\n function clearFull() { flick_fullimg.source="" }\n'+fragment+'\n}'
    comp=QQmlComponent(engine);comp.setData(text.encode(),QUrl('file:///StableLayers.qml'));assert not comp.isError(),[e.toString() for e in comp.errors()]
    root=comp.create();assert root;preview=root.findChild(QObject,'preview');full=root.findChild(QObject,'full');cases=[]
    def settle():
        for _ in range(40):
            QTest.qWait(25)
            if not root.isLoading():return
        raise AssertionError('image did not settle')
    def done(name):cases.append(name)
    root.loadFull('image://fixture/full');settle();assert preview.property('visible') and full.property('visible')
    assert not preview.property('cache') and not full.property('cache');done('ready-full-keeps-preview-underneath-with-cache-disabled')
    root.loadFull('image://fixture/fail');settle();assert preview.property('visible') and not full.property('visible');done('failed-full-reveals-correct-preview')
    root.clearFull();settle();assert str(full.property('source').toString())=='' and preview.property('visible');done('cleared-full-retains-preview')
    rcc=HERE/'artifacts/session/replay-ui.rcc';assert QResource.registerResource(str(rcc))
    for name,path in [('main.qml','main.qml'),('components/MediaBrowseView.qml','MediaBrowseView.qml')]:
        file=QFile(':/'+name);assert file.open(QIODevice.ReadOnly);assert bytes(file.readAll())==(HERE/'artifacts/session'/path).read_bytes();file.close()
    QResource.unregisterResource(str(rcc));done('both-rcc-files-decompress-to-exact-candidate-sources')
    report={'passed':True,'cases':cases,'runtime':'host Qt6, selected actual QML image properties; CropOverlay omitted','targetQt55Executed':False,'cameraAccess':False,
        'rccSha256':sha256(rcc.read_bytes()).hexdigest(),'sourceHashes':{p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),HERE/'tools/build_session.py']}}
    out=HERE/'artifacts/stable-tests';out.mkdir(parents=True,exist_ok=True);(out/'qml.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps({'passed':True,'cases':len(cases)}))
if __name__=='__main__':run()
