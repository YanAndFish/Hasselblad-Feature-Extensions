"""Host-only 1.25.0 viewfinder checks. No camera transport is opened."""

from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parent
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QT_QUICK_BACKEND'] = 'software'
sys.path.insert(0, str(ROOT.parents[1] / 'wireless-flash/build/ui-test-python'))
sys.path.insert(0, str(ROOT.parents[1] / 'patch-distribution'))

from PySide6.QtCore import QObject, QPointF, Property, Signal, Slot, QUrl
from PySide6.QtGui import QGuiApplication, QFont, QFontDatabase
from PySide6.QtQuick import QQuickView
from PySide6.QtTest import QTest
from PySide6.QtQml import QJSEngine


class CameraStub(QObject):
    focusSizeChanged = Signal()
    focusStateChanged = Signal()

    def __init__(self):
        super().__init__()
        self._focus_size = QPointF(.11, .15)

    @Property(QPointF, notify=focusSizeChanged)
    def focus_size(self):
        return self._focus_size

    @Property(bool, notify=focusStateChanged)
    def findOngoing(self):
        return False

    @Property(int, notify=focusStateChanged)
    def lastAfResult(self):
        return 0

    @Property(int, constant=True)
    def LastAfResultFound(self):
        return 1

    @Property(int, constant=True)
    def LastAfResultNotFound(self):
        return 2

    @Slot(QPointF, result=float)
    def firstComponent(self, point):
        return point.x()

    @Slot(QPointF, result=float)
    def secondComponent(self, point):
        return point.y()


class DeliveryStub(QObject):
    displayedChanged = Signal()

    def __init__(self):
        super().__init__()
        self._displayed = QPointF(.5, .5)

    @Property(QPointF, notify=displayedChanged)
    def displayed(self):
        return self._displayed

    def set_displayed(self, x, y):
        self._displayed = QPointF(x, y)
        self.displayedChanged.emit()


class StateStub(QObject):
    def __init__(self, delivery):
        super().__init__()
        self.delivery = delivery

    @Property(QObject, constant=True)
    def focusDelivery(self):
        return self.delivery


app = QGuiApplication([])
QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
app.setFont(QFont('Microsoft YaHei'))
build = ROOT / 'build/viewfinder-review'
build.mkdir(parents=True, exist_ok=True)
focus_source = (ROOT / 'OwnFocusFrame.qml').read_text(encoding='utf-8')
focus_source = focus_source.replace('import com.hasselblad.camera 1.0\n', '')
focus_source = focus_source.replace('import com.hasselblad.globalstateinfo 1.0\n', '')
focus_file = build / 'HostFocusFrame.qml'
focus_file.write_text(focus_source, encoding='utf-8')

camera = CameraStub()
delivery = DeliveryStub()
state = StateStub(delivery)
view = QQuickView()
view.rootContext().setContextProperty('Camera', camera)
view.rootContext().setContextProperty('GlobalStateInfo', state)
view.setSource(QUrl.fromLocalFile(str(focus_file)))
assert view.status() == QQuickView.Ready, [e.toString() for e in view.errors()]
view.setResizeMode(QQuickView.SizeRootObjectToView)
view.resize(640, 480)
view.show()
QTest.qWait(50)
frame = view.rootObject()
box = frame.findChild(QObject, 'OwnViewfinderFocusBox')
assert box is not None
assert abs(box.property('x') + box.property('width') / 2 - 320) < 1
assert abs(box.property('y') + box.property('height') / 2 - 240) < 1
frame.setProperty('previewX', .8)
frame.setProperty('previewY', .65)
frame.setProperty('previewActive', True)
QTest.qWait(20)
assert abs(box.property('x') + box.property('width') / 2 - 512) < 1
assert abs(box.property('y') + box.property('height') / 2 - 312) < 1
frame.setProperty('dragging', False)
delivery.set_displayed(.8, .65)
QTest.qWait(20)
assert not frame.property('previewActive'), 'accepted position clears preview without a jump'
view.grabWindow().save(str(build / 'focus-frame.png'))

hud_view = QQuickView()
hud_view.setSource(QUrl.fromLocalFile(str(ROOT / 'OwnViewfinderHud.qml')))
assert hud_view.status() == QQuickView.Ready, [e.toString() for e in hud_view.errors()]
hud_view.setResizeMode(QQuickView.SizeRootObjectToView)
hud_view.resize(640, 480)
hud_view.show()
hud = hud_view.rootObject()
hud.setProperty('textFont', 'Microsoft YaHei')
for name, value in {
    'apertureText': 'f/4', 'shutterText': '1/60', 'isoText': 'ISO 800',
    'remainingText': '1155', 'focusText': 'AF', 'whiteBalanceText': 'AWB',
    'batteryLevel': 63, 'exposureScaleValid': True, 'exposureValue': .7,
}.items():
    assert hud.setProperty(name, value), name
QTest.qWait(40)
assert hud.findChild(QObject, 'OwnViewfinderExposureScale').property('visible')
hud_view.grabWindow().save(str(build / 'viewfinder-hud.png'))

from build_viewfinder_modes import read_rcc
resources = read_rcc((ROOT / 'build/flash-ui.rcc').read_bytes())
overlay = resources['/liveview/LiveViewOverlay.qml']
image = resources['/liveview/LiveViewImage.qml']
live = resources['/liveview/LiveView.qml']
assert 'OwnViewfinderHud {' in overlay
assert 'OwnFocusFrame {' in overlay
assert 'function moveFocusDrag(px, py)' in overlay
assert 'GlobalStateInfo.focusDelivery.select' not in overlay.split(
    'function moveFocusDrag(px, py) {', 1)[1].split('function endFocusDrag', 1)[0], \
    'pointer movement must never send camera focus commands'
assert 'if (focusDragging) info.endFocusDrag(mouse.x, mouse.y, movedFocus)' in image
assert 'filterChildren: !liveViewImage.focusDragging' in live
assert 'import com.hasselblad.video 1.0' in live
assert 'import com.hasselblad.systemmanager 1.0' in live
assert 'newReplayEnabled": false' in (ROOT / 'build/ui-features.json').read_text(encoding='utf-8')

# Execute the exact QML focus mapping functions against a synthetic 4:3 crop
# and focus grid. The stream, lens and camera are never touched.
focus_functions = overlay.split('    function focusTouchAllowed() {', 1)[1].split(
    '    // Representing the area where live view will be seen.', 1)[0]
focus_functions = 'function focusTouchAllowed() {' + focus_functions
js = QJSEngine()
setup = '''
var root={inActiveWindow:true,isInHDMI:false};
var GlobalStateInfo={evfActive:false,afSelectionActive:false,afSselectedIndex:0,
    focusDelivery:{calls:0,last:null,select:function(point){this.calls++;this.last=point}}};
var VideoControl={View:1,AF:2,videoMode:1};
var Camera={findOngoing:false,combine:function(x,y){return {x:x,y:y}}};
var liveViewVideoArea={x:0,y:0,width:640,height:480};
var crop={cropWidth:0,cropHeight:0};
var directFocusGrid={afItemWidth:80,afItemHeight:80,xCount:7,yCount:5,
    gridXMargin:40,gridYMargin:40};
var focusDragOffsetX=0,focusDragOffsetY=0;
var focusFrame={visible:true,focusX:.5,focusY:.5,boxWidth:70,boxHeight:70,
    dragging:false,preview:function(x,y){this.focusX=x;this.focusY=y;this.dragging=true},
    releasePreview:function(){this.dragging=false},cancelPreview:function(){this.dragging=false}};
var Qt={point:function(x,y){return {x:x,y:y}}};
'''
result = js.evaluate(setup + focus_functions)
assert not result.isError(), result.toString()
assert js.evaluate('beginFocusDrag(320,240)').toBool()
js.evaluate('moveFocusDrag(450,300)')
assert js.evaluate('GlobalStateInfo.focusDelivery.calls').toInt() == 0
assert abs(js.evaluate('focusFrame.focusX').toNumber() - 450/640) < 1e-6
js.evaluate('endFocusDrag(450,300,true)')
assert js.evaluate('GlobalStateInfo.focusDelivery.calls').toInt() == 1
assert abs(js.evaluate('GlobalStateInfo.focusDelivery.last.y').toNumber() - 300/480) < 1e-6
assert not js.evaluate('beginFocusDrag(10,10)').toBool()
js.evaluate('root.inActiveWindow=false')
assert not js.evaluate('beginFocusDrag(450,300)').toBool()
js.evaluate('root.inActiveWindow=true;focusFrame.focusX=.5;focusFrame.focusY=.5')
assert js.evaluate('beginFocusDrag(320,240)').toBool()
js.evaluate('moveFocusDrag(800,700)')
assert abs(js.evaluate('focusFrame.focusX').toNumber() - 560/640) < 1e-6
assert abs(js.evaluate('focusFrame.focusY').toNumber() - 400/480) < 1e-6
print('PASS: own HUD and reticle render, visual drag preview, accepted-position handoff, '
      'crop clamping, single release commit, parent swipe isolation, original RAW replay retained')
