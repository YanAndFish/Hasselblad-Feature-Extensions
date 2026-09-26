"""Qt6 主机模拟属性桥执行候选 QML；原生核心来自编译 DLL，非 ARM 实机测试。"""
import sys,os,ctypes,json
from pathlib import Path
P=Path(__file__).resolve().parent;R=P.parents[2]
sys.dont_write_bytecode=True
sys.path.insert(0,str(R/'x1d/wireless-flash/build/ui-test-python'))
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import QObject,Property,Signal,Slot,QTimer,QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlEngine,QQmlComponent,QQmlPropertyMap
from PySide6.QtTest import QTest
class State(ctypes.Structure):
    _fields_=[('desired',ctypes.c_uint32),('sent',ctypes.c_uint32),('actual',ctypes.c_uint32)]+[(n,ctypes.c_int) for n in ['active','inFlight','failed','dragging','tickRunning']]+[('effects',ctypes.c_uint)]
lib=ctypes.CDLL(str(P/'build/native-focus-test/core.dll'))
lib.step.argtypes=[ctypes.POINTER(State),ctypes.c_int,ctypes.c_double]
reference=R/'x1d/combined-runtime/four-module-r1/persistent-r1/CodeTests/focus_delivery_check.py'
original=reference.read_text()
# Reuse the existing delayed Camera and regression assertions verbatim.
exec(original[original.index('class Camera(QObject):'):original.index('app = QGuiApplication([])')])
app=QGuiApplication([]);engine=QQmlEngine();camera=Camera()
engine.rootContext().setContextProperty('Camera',camera)
core=QQmlPropertyMap(engine);state=State()
tick=QTimer();tick.setSingleShot(True);tick.setInterval(16)
deadline=QTimer();deadline.setSingleShot(True);deadline.setInterval(3000)
for n in ['e0','e1','e2']:core.insert(n,0)
core.insert('p',0.0)
probe=QQmlPropertyMap(engine)
engine.rootContext().setContextProperty('_testState',probe)
core.insert('request',[])
def dispatch(command,value=0):
    lib.step(ctypes.byref(state),command,value);effects=state.effects
    if effects&2:tick.stop()
    if effects&1:tick.start()
    if effects&8:deadline.stop()
    if effects&4:deadline.start()
    for n in ['desired','sent','active','inFlight','failed','dragging']:
        probe.insert(n,float(getattr(state,n)) if n in ['desired','sent'] else bool(getattr(state,n)))
    core.insert('v',[float(state.desired if state.active or state.dragging and not state.failed else state.actual),bool(state.active and (state.inFlight or state.desired!=state.actual)),bool(state.dragging),bool(state.active)])
    for effect,n in [(64,'e2'),(16,'e0'),(32,'e1')]:
        if effects&effect:
            if effect==16:core.insert('p',float(state.sent))
            core.insert(n,core.value(n)+1)
def request(name,value):
    if name=='request':
        core.insert('request',[])
        if hasattr(value,'toVariant'):value=value.toVariant()
        dispatch(int(value[0]),float(value[1]))
core.valueChanged.connect(request)
tick.timeout.connect(lambda:dispatch(4));deadline.timeout.connect(lambda:dispatch(6))
dispatch(-1)
engine.rootContext().setContextProperty('_hblFocusCore',core)
source=(P/'NativeFocusDelivery.qml').read_text()
# Only the host harness exposes internal probes used by the old regression assertions.
source=source.replace('id: delivery','id: delivery\n readonly property bool failed: _testState.failed\n readonly property bool inFlight: _testState.inFlight')
component=QQmlComponent(engine)
component.setData(source.replace('import com.hasselblad.camera 1.0','').encode(),QUrl('file:///NativeFocusDelivery.qml'))
obj=component.create();assert obj,[e.toString() for e in component.errors()]
assert camera.writes==[], 'Creating the bridge must not submit a focus coordinate'
engine.globalObject().setProperty('delivery',engine.newQObject(obj))
tests=original[original.index('def js(code):'):original.index('main = (P /')]
tests=tests.replace('delivery.failed=false;','')
exec(tests)
report={'passed':True,'checks':checks,'hardwareRequests':0,'bridge':'Qt6 simulated QQmlPropertyMap adapter with compiled C core','armQt5BridgeRuntimeVerified':False}
(P/'build/native-focus-test/bridge-result.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))
