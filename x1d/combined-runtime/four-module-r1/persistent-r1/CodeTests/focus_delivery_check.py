"""Execute production QML against a deliberately delayed camera proxy.

This validates queue/gesture ordering, not physical camera latency.
"""
import sys, os, json, hashlib
from pathlib import Path
sys.dont_write_bytecode = True
P = Path(__file__).resolve().parents[1]
ROOT = P.parents[3]
sys.path.insert(0, str(ROOT / 'x1d/wireless-flash/build/ui-test-python'))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtCore import QObject, Property, Signal, Slot, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlEngine, QQmlComponent
from PySide6.QtTest import QTest

class Camera(QObject):
    focus_pointChanged = Signal()
    def __init__(self):
        super().__init__()
        self.actual = 5000 * 65536 + 5000
        self.writes = []
        self.operations = []
    @Slot(bool)
    @Slot(bool, bool)
    def startSession(self, show, force=None): self.operations.append(('session', self.actual, show, force))
    @Slot(bool)
    def startExposing(self, show): self.operations.append(('exposure', self.actual, show))
    @Slot()
    def stopSession(self): self.operations.append(('stopSession',))
    @Slot()
    def stopExposing(self): self.operations.append(('stopExposing',))
    @Property(float, notify=focus_pointChanged)
    def focus_point(self): return self.actual
    @focus_point.setter
    def focus_point(self, value): self.writes.append(value)
    def acknowledge(self, value):
        self.actual = value
        self.focus_pointChanged.emit()

app = QGuiApplication([])
engine = QQmlEngine()
camera = Camera()
engine.rootContext().setContextProperty('Camera', camera)
source = (P / 'qml/common/FocusDelivery.qml').read_text()
test_source = source.replace('import com.hasselblad.camera 1.0', '')
component = QQmlComponent(engine)
component.setData(test_source.encode(), QUrl('file:///FocusDelivery.qml'))
obj = component.create()
assert obj, [e.toString() for e in component.errors()]
engine.globalObject().setProperty('delivery', engine.newQObject(obj))
def js(code):
    result = engine.evaluate(code)
    assert not result.isError(), result.toString()
    return result.toVariant()
def reset():
    js('delivery.abortDelivery(); delivery.failed=false; events=[]')
    camera.writes.clear()
    camera.acknowledge(5000 * 65536 + 5000)
def point(x, y=5000): return x * 65536 + y
checks = []

js('var events=[]')
js(f'delivery.beginDrag();delivery.select({point(5200)});delivery.pump()')
camera.acknowledge(point(5200))
camera.acknowledge(point(5100))
assert js('delivery.displayed') == point(5200), 'late completed echo must not pull frame back during drag'
js('delivery.endDrag();delivery.pump()')
assert camera.writes[-1] == point(5200)
camera.acknowledge(point(5200))
assert not js('delivery.pending')
checks.append('drag holds preview across acknowledgement and late old echo; release confirms final point')
reset()
js(f'delivery.select({point(5100)});delivery.pump()')
assert camera.writes == [point(5100)]
for x in range(5101, 5301): js(f'delivery.select({point(x)})')
assert camera.writes == [point(5100)]
assert js('delivery.displayed') == point(5300)
assert camera.actual != js('delivery.displayed')
js('delivery.afterCoordinates("session",function(){events.push(delivery.displayed)})')
assert js('events.length') == 0
camera.acknowledge(point(5100))
assert js('delivery.displayed') == point(5300)
QTest.qWait(35)
assert camera.writes == [point(5100), point(5300)]
camera.acknowledge(point(5200))  # stale/intermediate notification
assert js('delivery.inFlight') and js('events.length') == 0
camera.acknowledge(point(5300))
assert js('events') == [point(5300)]
assert not js('delivery.pending')
checks.append('201 moves -> two submissions; stale echo cannot move frame or release AF')

reset()
js(f'delivery.select({point(5050)})')
QTest.qWait(35)  # no release event at all
assert camera.writes == [point(5050)]
camera.acknowledge(point(5050))
assert js('delivery.displayed') == camera.actual and not js('delivery.pending')
checks.append('missing release still delivers final ROI')

reset()
js(f'delivery.select({point(5200)});delivery.afterCoordinates("session",function(){{events.push("AF")}});delivery.cancel("session")')
camera.acknowledge(point(5200))
assert js('events.length') == 0
checks.append('released AF button cancels deferred AF')

reset()
js(f'delivery.select({point(5200)});delivery.afterCoordinates("exposure",function(){{events.push("expose")}});delivery.cancel("exposure")')
camera.acknowledge(point(5200))
assert js('events.length') == 0
checks.append('released exposure button cancels deferred exposure')

reset()
js(f'delivery.select({point(5200)});delivery.afterCoordinates("session",function(){{events.push("AF")}});delivery.abortDelivery()')
assert js('events.length') == 0 and js('delivery.failed')
assert js('delivery.displayed') == camera.actual
camera.acknowledge(point(5200))
assert js('events.length') == 0
checks.append('timeout and late echo cannot start deferred operation')

reset()
js(f'delivery.select({point(5000)});delivery.afterCoordinates("session",function(){{events.push("AF")}})')
assert js('events') == ['AF'] and camera.writes == []
checks.append('unchanged ROI has no added round trip')

reset()
js(f'delivery.select({point(5200)});delivery.afterCoordinates("session",function(){{events.push("AF")}});delivery.afterCoordinates("exposure",function(){{events.push("expose")}})')
camera.acknowledge(point(5200))
assert js('events') == ['AF', 'expose']
checks.append('coordinate acknowledgement precedes original session/exposure order')

reset()
js(f'delivery.select({point(5200)});delivery.pump();delivery.select({point(5000)})')
assert js('delivery.pending')
camera.acknowledge(point(5200)); QTest.qWait(35)
assert camera.writes == [point(5200), point(5000)]
camera.acknowledge(point(5000))
assert not js('delivery.pending')
checks.append('reverse to initial coordinate does not prematurely complete')

main = (P / 'qml/main.qml').read_text()
assert all('Camera.'+name+'(' not in main for name in ['startSession','startExposing','stopSession','stopExposing'])
for name in ['liveview/LiveViewOverlay.qml','liveview/Touchpad.qml']:
    text = (P/'qml'/name).read_text()
    assert 'focusDelivery.select(' in text
    assert 'Camera.focus_point =' not in text
assert 'focusDelivery.displayed' in (P/'qml/liveview/AFIndicator.qml').read_text()
assert not any(x in source for x in ['FocusMode','Lens.','findOngoing','inSession'])
checks.append('both input surfaces and indicator share destination; no lens/AF eligibility gate')

out=P/'build/focus-delivery-repair'
out.mkdir(exist_ok=True)
# Load the real GlobalStateInfo wrapper and its local child component together.
# Only proprietary module imports / singleton registration are replaced on host.
harness=out/'host';harness.mkdir(exist_ok=True)
(harness/'FocusDelivery.qml').write_text(test_source,encoding='utf-8')
global_source=(P/'qml/common/GlobalStateInfo.qml').read_text().replace('pragma Singleton','').replace('import com.hasselblad.camera 1.0','')
(harness/'GlobalHarness.qml').write_text(global_source,encoding='utf-8')
gc=QQmlComponent(engine,QUrl.fromLocalFile(str((harness/'GlobalHarness.qml').resolve())))
global_obj=gc.create();assert global_obj,[e.toString() for e in gc.errors()]
engine.globalObject().setProperty('g',engine.newQObject(global_obj))
camera.operations.clear()
js(f'g.focusDelivery.select({point(5600)});g.focusStartSession(true,true);g.focusStartExposing(false)')
assert camera.operations==[]
camera.acknowledge(point(5600))
assert camera.operations==[('session',point(5600),True,True),('exposure',point(5600),False)]
camera.operations.clear()
js(f'g.focusDelivery.select({point(5700)});g.focusStartSession(false);g.focusStopSession()')
camera.acknowledge(point(5700))
assert camera.operations==[('stopSession',)]
checks.append('production singleton wrappers preserve arguments and cancellation')
(out/'validation.json').write_text(json.dumps(dict(passed=True,checks=checks,hardwareRequests=0,
    physicalLatencyMeasured=False,sourceSha256=hashlib.sha256(source.encode()).hexdigest()),indent=2),encoding='utf-8')
print(json.dumps(dict(passed=True,checks=checks),ensure_ascii=False))
obj.deleteLater()
app.processEvents()
