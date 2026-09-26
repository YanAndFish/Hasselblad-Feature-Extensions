"""Page lifecycle and automatic/manual entry against a synthetic catalogue."""
exec((__import__('pathlib').Path(__file__).parent/'check_settings_page.py').read_text().split('app=QGuiApplication')[0])
from PySide6.QtCore import QObject
app=QGuiApplication([])
out=P/'build/photo-page-test';out.mkdir(exist_ok=True)
for name in ['PhotoPlaybackPage.qml','JpegPlaybackSurface.qml','CaptureIdentity.js']:(out/name).write_bytes((P/name).read_bytes())
(out/'Main.qml').write_text('''import QtQuick 2.5
Item {width:640;height:480
 ListModel {id:catalog;ListElement {display:"one.3fr"} ListElement {display:"two.3fr"}}
 PhotoPlaybackPage {id:page;anchors.fill:parent;catalogue:catalog;directory:"/test"}
}''')
v=QQuickView();v.setSource(QUrl.fromLocalFile(str(out/'Main.qml')))
assert v.status()==QQuickView.Ready,[e.toString() for e in v.errors()]
v.show();p=v.rootObject().findChild(QObject,'PhotoPlaybackPage');listing=p.findChild(QObject,'OwnPlaybackList')
assert listing.property('count')==0,'idle must not retain photo delegates'
p.enter(-1,True);QTest.qWait(100)
assert p.property('automatic') and listing.property('count')==0,'automatic must not select last directory image'
assert p.property('captureFileName')=='','wait for actual capture identity'
p.captureArrived('new-capture.3fr');QTest.qWait(20)
assert p.property('captureFileName')=='new-capture.3fr','use capture event filename'
p.captureWriteProgress();QTest.qWait(20)
assert p.property('captureFileName')=='new-capture.3fr','retry must retain exact capture identity'
p.captureEvent('image://imagestore/preview/card0/DCIM/new.3FR')
assert p.property('captureFileName')=='/card0/DCIM/new.3FR','capture-event identity'
p.setProperty('directory','/another-directory')
assert '/card0/' in p.property('captureImageSource').toString().replace('%2F','/'),'directory navigation must not change capture target'
p.captureEvent('/card0/../other.3FR')
assert p.property('captureFileName')=='/card0/DCIM/new.3FR','invalid event cannot replace current capture'
p.beginCapture();QTest.qWait(20)
assert p.property('captureFileName')=='' and p.property('captureImageSource').isEmpty(),'next exposure must clear previous capture while waiting'
assert p.findChild(QObject,'AutomaticJpegPlayback').property('displayedSource').isEmpty(),'previous capture must not remain bound'
p.leave();QTest.qWait(100)
assert listing.property('count')==0,'automatic exit releases delegates'
p.enter(0,False);QTest.qWait(100)
assert not p.property('automatic') and p.property('currentIndex')==0,'manual requested image'
assert p.sourceFor('../test.3fr')=='','reject path traversal from display role'
assert p.sourceFor('test.mov')=='','video must not reach JPEG provider'
p.leave();QTest.qWait(100)
assert listing.property('count')==0,'manual exit releases delegates'
print('PASS own photo page: automatic/manual entry, selection, release, source filtering; native adapter pending')
