"""Candidate AF indicator: movement must not repaint or flip result artwork."""
from pathlib import Path
import os,sys
P=Path(__file__).resolve().parent
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['QT_QUICK_BACKEND']='software'
sys.path[:0]=[str(P.parents[1]/'wireless-flash/build/ui-test-python'),str(P.parents[1]/'patch-distribution')]
from build_viewfinder_modes import read_rcc
from PySide6.QtCore import QUrl,QObject
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickView
from PySide6.QtTest import QTest
app=QGuiApplication([])
s=read_rcc((P/'build/flash-ui.rcc').read_bytes())['/liveview/AFIndicator.qml']
s='\n'.join(l for l in s.splitlines() if not l.startswith('import com.'))
s=s.replace('GlobalStateInfo','globalMock').replace('Camera','cameraMock').replace('SoundControl','soundMock')
s=s.replace('    id: af_item','''    id: af_item
    width:640;height:480
    property int paints:0
    property alias delivery: deliveryMock
    property alias backend: cameraMock
    QtObject {id:deliveryMock;property real displayed:0.5;property bool pending:false;property bool dragging:false}
    property var globalMock: ({focusDelivery:deliveryMock})
    QtObject {id:cameraMock;property real focus_point:0.5;property real focus_size:0.1
        property bool findOngoing:false;property bool inSession:true
        property int lastAfResult:1;property int lastAfReturnStatus:0
        property int LastAfResultFound:1;property int LastAfResultOverride:2
        property int LastAfResultNotFound:3;property int LastAfResultJammed:4;property int LastAfResultError:5
        property int LastAfReturnStatusCanceled:6
        function firstComponent(p){return p} function secondComponent(p){return p}
    }
    property var configstore: ({afSucceededSound:false})
    property var soundMock: ({play:function(x){},SndAfFocusNotFound:0,SndAfFocusFound:1})
''')
# QML identifiers cannot start uppercase: only the mocked enum fields are renamed.
for name in ['LastAfResultFound','LastAfResultOverride','LastAfResultNotFound','LastAfResultJammed','LastAfResultError','LastAfReturnStatusCanceled']:
    s=s.replace(name,name[0].lower()+name[1:])
s=s.replace('id: af_symbol','id: af_symbol;objectName:"frame"',1)
s=s.replace('        onPaint: {','        onPaint: {af_item.paints++',1)
out=P/'build/focus-indicator-harness.qml';out.write_text(s,encoding='utf-8')
view=QQuickView();view.setSource(QUrl.fromLocalFile(str(out.resolve())))
assert view.status()==QQuickView.Ready,[e.toString() for e in view.errors()]
view.show();QTest.qWait(60)
r=view.rootObject();engine=view.engine();engine.globalObject().setProperty('root',engine.newQObject(r))
def run(code):
    result=engine.evaluate(code);assert not result.isError(),result.toString()
run('root.delivery.dragging=true');QTest.qWait(40)
assert r.property('state')=='idle'
before=r.property('paints')
for i in range(20):
    run('root.delivery.displayed='+str(.51+i*.005)+';root.backend.focus_point=0.4;root.delivery.pending='+('true' if i%2 else 'false'))
    QTest.qWait(5)
assert r.property('state')=='idle'
assert r.property('paints')==before,'movement or acknowledgement must not repaint unchanged artwork'
assert abs(r.findChild(QObject,'frame').property('x')-(.605*640-32))<.001,'frame still follows newest position'
run('root.delivery.pending=false;root.delivery.dragging=false');QTest.qWait(30)
assert r.property('state')=='hasfocus','AF result styling restored after drag'
print('PASS: 20 moves with stale feedback and alternating pending state: no artwork repaint; AF result restored on release')
