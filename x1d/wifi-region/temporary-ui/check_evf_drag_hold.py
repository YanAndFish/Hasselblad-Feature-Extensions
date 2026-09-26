"""验证候选取景器触摸板的拖动保持与取消接线，不访问相机。"""
from pathlib import Path
import os,sys
P=Path(__file__).resolve().parent
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path[:0]=[str(P.parents[1]/'wireless-flash/build/ui-test-python'),str(P.parents[1]/'patch-distribution')]
from build_viewfinder_modes import read_rcc
from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlEngine,QQmlComponent
app=QGuiApplication([]);engine=QQmlEngine()
s=read_rcc((P/'build/flash-ui.rcc').read_bytes())['/liveview/Touchpad.qml']
s='\n'.join(l for l in s.splitlines() if not l.startswith('import com.') and not l.startswith('import "'))
s=s.replace('GlobalStateInfo','globalMock').replace('VideoControl','videoMock').replace('System','systemMock').replace('Camera','cameraMock').replace('Config','configMock')
s=s.replace('    id: root','''    id: root
    width:640;height:480
    property int starts:0
    property int finishes:0
    property var globalMock: ({touchpadZoomActive:false,afSselectedIndex:-1,focusDelivery:{displayed:0.5,beginDrag:function(){root.starts++},endDrag:function(){root.finishes++},select:function(p){root.globalMock.focusDelivery.displayed=p}}})
    property var cameraMock: ({firstComponent:function(p){return p},secondComponent:function(p){return p},combine:function(x,y){return x}})
    property var videoMock: ({videoMode:0,Zoom:1})
    property var systemMock: ({camera_mode:0,cameraMockModeImage:0})
    property var configstore: ({touchpad_position:0,ExpMode:0,evf_tp_move_focus:true,hdmi_tp_move_focus:false})
    property var configMock: ({ExpMode_FullAuto:1,TouchpadLeft:0,TouchpadRight:1,TouchpadTopLeft:2,TouchpadBottomLeft:3,TouchpadBottomRight:4})
''')
s=s.replace('AFCalc {','Item {property int xCount:10;property int yCount:8;property real gridXMargin:70;property real gridYMargin:40;property real afItemWidth:50;property real afItemHeight:50;property real screenWidth;property real screenHeight;property string idText;')
s=s.replace('ZoomCalc {','Item {property int minInterval;property var lastPos:Qt.point(0.5,0.5);')
c=QQmlComponent(engine);c.setData(s.encode(),QUrl('file:///evf-drag-harness.qml'))
r=c.create();assert r,[e.toString() for e in c.errors()]
engine.globalObject().setProperty('pad',engine.newQObject(r))
def run(code):
    answer=engine.evaluate(code);assert not answer.isError(),answer.toString()
run('pad.beginFocusDrag();pad.beginFocusDrag()')
assert r.property('starts')==1 and r.property('focusDragHeld')
run('pad.finishFocusDrag();pad.finishFocusDrag()')
assert r.property('finishes')==1 and not r.property('focusDragHeld')
run('pad.beginFocusDrag();pad.enabled=false')
assert r.property('finishes')==2 and not r.property('focusDragHeld')
run('pad.enabled=true;pad.acquireTouch([{pointId:7,x:100,y:100}]);pad.acquireTouch([{pointId:9,x:240,y:100}])')
assert r.property('activeTouchId')==7 and r.property('xLastPos')==100
run('pad.updateTouch([{pointId:9,x:240,y:100},{pointId:7,x:103,y:100}])')
assert abs(r.property('continuousFocusX')-.51)<.00001,'reordered second contact must not jump focus'
run('pad.releaseTouch([{pointId:9,x:240,y:100}])')
assert r.property('activeTouchId')==7 and r.property('focusDragHeld'),'another finger release must not end drag'
run('pad.updateTouch([{pointId:7,x:400,y:100}]);pad.updateTouch([{pointId:7,x:120,y:100}])')
assert abs(r.property('continuousFocusX')-.51)<.00001,'reentry rebases without jump'
run('pad.releaseTouch([{pointId:7,x:120,y:100}])')
assert r.property('activeTouchId')==-1 and not r.property('focusDragHeld')
print('PASS: EVF drag hold starts once, finishes once, disabled touchpad releases hold; candidate QML compiles')
print('PASS: second contact, contact reordering, unrelated release and touchpad reentry cannot reset drag destination')


