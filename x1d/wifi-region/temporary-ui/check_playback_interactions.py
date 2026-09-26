"""Synthetic provider verifies scheduling, retained neighbours, pinch and 1:1 ROI."""
exec((__import__('pathlib').Path(__file__).parent/'check_settings_page.py').read_text().split('app=QGuiApplication')[0])
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtGui import QImage,QColor,QInputDevice
from PySide6.QtCore import QSize
from urllib.parse import unquote
import time
def pump(ms):
    end=time.monotonic()+ms/1000
    while time.monotonic()<end:app.processEvents();time.sleep(0.005)
class Provider(QQuickImageProvider):
    def __init__(self):super().__init__(QQuickImageProvider.Image);self.reads=[]
    def requestImage(self,identity,size,requested):
        self.reads.append(unquote(identity))
        dimensions=requested if requested.isValid() else QSize(320,240)
        image=QImage(dimensions,QImage.Format_RGB32);image.fill(QColor('red'))
        size.setWidth(dimensions.width());size.setHeight(dimensions.height())
        return image
app=QGuiApplication([])
out=P/'build/playback-interaction-test';out.mkdir(exist_ok=True)
for name in ['PhotoPlaybackPage.qml','JpegPlaybackSurface.qml','CaptureIdentity.js']:(out/name).write_bytes((P/name).read_bytes())
elements='\n'.join('ListElement {display:"photo%d.3fr";imageWidth:1600;imageHeight:1200}'%i for i in range(10))
(out/'Main.qml').write_text('import QtQuick 2.5\nItem {width:640;height:480\n ListModel {id:catalog;'+elements+'}\n PhotoPlaybackPage {anchors.fill:parent;catalogue:catalog;directory:"/fixture"}\n}',encoding='utf-8')
v=QQuickView();provider=Provider();v.engine().addImageProvider('hbljpeg',provider)
v.setSource(QUrl.fromLocalFile(str(out/'Main.qml')));assert v.status()==QQuickView.Ready,[e.toString() for e in v.errors()]
v.show();p=v.rootObject().findChild(QObject,'PhotoPlaybackPage');listing=p.findChild(QObject,'OwnPlaybackList')
p.enter(5,False);pump(900)
assert provider.reads and provider.reads[0].endswith('photo5.3fr'),provider.reads
assert set(provider.reads)=={'/fixture/photo%d.3fr'%i for i in range(2,8)},provider.reads
before=provider.reads.count('/fixture/photo4.3fr')
p.setProperty('currentIndex',4);pump(500)
assert provider.reads.count('/fixture/photo4.3fr')==before,'cached previous photo re-read'
current=listing.property('currentItem');surface=current.findChild(QObject,'JpegPlaybackSurface')
assert surface and surface.property('displayReady')
# Double-tap switches to exact native pixel scale: 1600/640 = 2.5.
QTest.mouseDClick(v,Qt.LeftButton,Qt.NoModifier,QPoint(320,240));pump(250)
assert abs(surface.property('zoomFactor')-2.5)<0.01,surface.property('zoomFactor')
assert any(x.startswith('region/') for x in provider.reads),'missing region request'
surface.toggleNativeZoom();pump(100)
device=QTest.createTouchDevice(QInputDevice.DeviceType.TouchScreen)
QTest.touchEvent(v,device).press(0,QPoint(250,240),v).press(1,QPoint(390,240),v).commit();pump(30)
for delta in [20,40,70,100]:
 QTest.touchEvent(v,device).move(0,QPoint(250-delta,240),v).move(1,QPoint(390+delta,240),v).commit();pump(30)
assert surface.property('zoomFactor')>1.2,surface.property('zoomFactor')
QTest.touchEvent(v,device).release(0,QPoint(150,240),v).release(1,QPoint(490,240),v).commit();pump(50)
p.leave();pump(100)
assert listing.property('count')==0
print('PASS playback: selected first, six bounded previews, previous retained, double-tap 1:1 ROI, two-finger pinch, exit release')
