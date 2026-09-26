"""生产 QML 与候选 C 状态机的差分测试；只用模拟相机，不访问 USB。"""
import ctypes,os,sys,subprocess,random,json
from pathlib import Path
P=Path(__file__).resolve().parent;R=P.parents[2]
sys.dont_write_bytecode=True
sys.path.insert(0,str(R/'x1d/wireless-flash/build/ui-test-python'))
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import QObject,Property,Signal,QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlEngine,QQmlComponent

O=P/'build/native-focus-test';O.mkdir(parents=True,exist_ok=True)
source=O/'adapter.c'
source.write_text('#include "focus_core.h"\n__declspec(dllexport) void step(FocusCore *s,int c,double p){focus_dispatch(s,c,p);}\n')
zig=R/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
env=dict(os.environ)
env['ZIG_GLOBAL_CACHE_DIR']=str(R/'.research-cache/x1d-1.25.0/zig-global-cache')
env['ZIG_LOCAL_CACHE_DIR']=str(R/'.research-cache/x1d-1.25.0/zig-local-cache')
subprocess.run([str(zig),'cc','-shared','-O2','-I',str(P),str(source),'-o',str(O/'core.dll')],env=env,check=True)
class State(ctypes.Structure):
    _fields_=[('desired',ctypes.c_uint32),('sent',ctypes.c_uint32),('actual',ctypes.c_uint32)]+[(n,ctypes.c_int) for n in ['active','inFlight','failed','dragging','tickRunning']]+[('effects',ctypes.c_uint)]
lib=ctypes.CDLL(str(O/'core.dll'));lib.step.argtypes=[ctypes.POINTER(State),ctypes.c_int,ctypes.c_double]
class Camera(QObject):
    changed=Signal()
    def __init__(self):super().__init__();self.actual=0;self.writes=[]
    @Property(float,notify=changed)
    def focus_point(self):return self.actual
    @focus_point.setter
    def focus_point(self,value):self.writes.append(value)
app=QGuiApplication([]);engine=QQmlEngine();camera=Camera()
engine.rootContext().setContextProperty('Camera',camera)
old=(R/'x1d/combined-runtime/four-module-r1/persistent-r1/qml/common/FocusDelivery.qml').read_text().replace('import com.hasselblad.camera 1.0','')
component=QQmlComponent(engine);component.setData(old.encode(),QUrl('file:///Reference.qml'))
obj=component.create();assert obj,[e.toString() for e in component.errors()]
engine.globalObject().setProperty('delivery',engine.newQObject(obj))
def js(code):
    result=engine.evaluate(code)
    assert not result.isError(),result.toString()
    return result.toVariant()
state=State();rng=random.Random(1250);cases=0
def step(command,value=0):
    global cases
    camera.writes=[]
    lib.step(ctypes.byref(state),command,value)
    if command==0:
        camera.actual=value;camera.changed.emit()
    else:
        calls={1:'beginDrag()',2:'endDrag()',3:'select('+str(value)+')',4:'deliveryTick.stop();delivery.pump()',5:'pump()',6:'abortDelivery()',7:'deliveryTick.stop();delivery.pump()'}
        js('delivery.'+calls[command])
    for name in ['desired','sent','active','inFlight','failed','dragging']:
        assert js('delivery.'+name)==getattr(state,name),(cases,command,name)
    assert js('delivery.deliveryTick.running')==bool(state.tickRunning),(cases,'timer')
    displayed=state.desired if state.active or state.dragging and not state.failed else state.actual
    assert js('delivery.displayed')==displayed,(cases,'displayed')
    assert js('delivery.pending')==bool(state.active and (state.inFlight or state.desired!=state.actual))
    assert camera.writes==([state.sent] if state.effects&16 else []),(cases,'writes')
    cases+=1
# Known user failure: acknowledgement followed by an old value during drag.
for c,v in [(0,100),(1,0),(3,200),(4,0),(0,200),(0,150),(2,0),(4,0),(0,200)]:step(c,v)
for _ in range(5000):
    command=rng.randrange(8)
    value=rng.choice([0,1,4294967295,state.sent,state.desired,rng.randrange(4294967296)])
    step(command,value)
report={'passed':True,'stateTransitions':cases,'hardwareRequests':0,'reference':'current user-approved QML state machine','qtBridgeTested':False,'armRuntimeTested':False}
(O/'result.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))
