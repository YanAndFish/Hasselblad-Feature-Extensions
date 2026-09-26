"""Offline check of the actual parameter/flash track release component."""
from pathlib import Path
import os,sys
P=Path(__file__).resolve().parent
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['QT_QUICK_BACKEND']='software'
sys.path.insert(0,str(P.parents[1]/'wireless-flash/build/ui-test-python'))
sys.path.insert(0,str(P.parents[1]/'patch-distribution'))
from build_viewfinder_modes import read_rcc
from PySide6.QtCore import QUrl,QObject,QPoint,Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickView
from PySide6.QtTest import QTest
app=QGuiApplication([])
source=read_rcc((P/'build/flash-ui.rcc').read_bytes())['/controlscreen/ControlScreen.qml']
start=source.index('    MouseArea {\n        id: formalFlashSwipe')
fragment=source[start:source.rfind('}')]
fragment=fragment.replace('NativeFlashPage {','Item {\n property bool popupOpen:false\n property bool powerGestureActive:false\n property bool pageActive\n signal backRequested()')
qml='''import QtQuick 2.5
Item {id:scope;width:640;height:480;property bool popupOpen:false
QtObject {id:constants;property int dragThreshold:20}
'''+fragment+'\n}'
path=P/'build/outer-release-test.qml';path.write_text(qml,encoding='utf-8')
view=QQuickView();view.setSource(QUrl.fromLocalFile(str(path)))
assert view.status()==QQuickView.Ready,[e.toString() for e in view.errors()]
view.show();QTest.qWait(100)
root=view.rootObject();swipe=root.findChild(QObject,'FormalFlashSwipe');track=root.findChild(QObject,'FormalFlashTrack')
def drag(start,end,expect):
    QTest.mousePress(view,Qt.LeftButton,Qt.NoModifier,QPoint(start,240))
    for i in range(1,11):QTest.mouseMove(view,QPoint(start+(end-start)*i//10,240),15)
    before=track.property('x');old=swipe.property('secondPage')
    QTest.mouseRelease(view,Qt.LeftButton,Qt.NoModifier,QPoint(end,240))
    assert swipe.property('secondPage')==old,'state changed before settling'
    QTest.qWait(65)
    assert swipe.property('secondPage')==old,'state changed mid-animation'
    assert abs(track.property('x')-before)>1,'no release movement'
    QTest.qWait(220)
    assert swipe.property('secondPage')==expect
    assert abs(track.property('x')-(-640 if expect else 0))<1
drag(500,280,True)
drag(180,230,True)
drag(180,400,False)
print('PASS: parameter/flash forward, short rebound, return; state retained through middle frame')

