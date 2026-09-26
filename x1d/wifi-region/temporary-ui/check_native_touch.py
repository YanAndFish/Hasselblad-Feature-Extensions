"""原生产触摸板和原生候选薄界面的输出差分；模拟双触点，不连接相机。"""
import os,sys,ctypes,subprocess,json,random
from pathlib import Path
P=Path(__file__).resolve().parent;R=P.parents[2]
sys.dont_write_bytecode=True;os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path[:0]=[str(P),str(R/'x1d/wireless-flash/build/ui-test-python'),str(R/'x1d/patch-distribution')]
from build_viewfinder_modes import read_rcc
from native_touch import apply_native_touch
from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlEngine,QQmlComponent,QQmlPropertyMap
O=P/'build/native-touch-test';O.mkdir(parents=True,exist_ok=True)
(O/'adapter.c').write_text('#include "touch_core.h"\n__declspec(dllexport) void step(TouchCore*s,int c,TouchPoint*p,int n,TouchFrame*f,TouchResult*r){*r=touch_dispatch(s,c,p,n,f);}\n')
env=dict(os.environ);env['ZIG_GLOBAL_CACHE_DIR']=str(R/'.research-cache/x1d-1.25.0/zig-global-cache');env['ZIG_LOCAL_CACHE_DIR']=str(R/'.research-cache/x1d-1.25.0/zig-local-cache')
subprocess.run([str(R/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'),'cc','-shared','-O2','-I',str(P),str(O/'adapter.c'),'-o',str(O/'touch.dll')],env=env,check=True)
class State(ctypes.Structure):
 _fields_=[(n,ctypes.c_int) for n in ['owner','inside','held']]+[(n,ctypes.c_double) for n in ['lastX','lastY','fx','fy']]
class Point(ctypes.Structure):_fields_=[('id',ctypes.c_int),('x',ctypes.c_double),('y',ctypes.c_double)]
class Frame(ctypes.Structure):
 _fields_=[(n,ctypes.c_int) for n in ['enabled','focus','zoom','zoomActive']]+[(n,ctypes.c_double) for n in ['left','top','padWidth','padHeight','width','height','xCount','yCount','marginX','marginY','itemWidth','itemHeight','currentX','currentY']]
class Result(ctypes.Structure):_fields_=[('effects',ctypes.c_uint)]+[(n,ctypes.c_double) for n in ['fx','fy','x','y']]
lib=ctypes.CDLL(str(O/'touch.dll'));lib.step.argtypes=[ctypes.POINTER(State),ctypes.c_int,ctypes.POINTER(Point),ctypes.c_int,ctypes.POINTER(Frame),ctypes.POINTER(Result)]
app=QGuiApplication([]);engine=QQmlEngine();core=QQmlPropertyMap(engine);states={};errors=[]
core.insert('request',[]);core.insert('result',[])
def request(name,value):
 if name!='request':return
 try:
  if hasattr(value,'toVariant'):value=value.toVariant()
  core.insert('request',[])
  owner,command,points,values=value
  if owner not in states:states[owner]=State(-1,0,0,0,0,0,0)
  frame=Frame(*[int(v) if i<4 else float(v) for i,v in enumerate(values)])
  data=(Point*len(points))(*[Point(*p) for p in points]);out=Result()
  lib.step(ctypes.byref(states[owner]),command,data,len(points),ctypes.byref(frame),ctypes.byref(out))
  core.insert('result',[out.effects,out.fx,out.fy,out.x,out.y])
 except Exception as e:errors.append(repr(e))
core.valueChanged.connect(request);engine.rootContext().setContextProperty('_hblTouchCore',core)
baseline=read_rcc((R/'x1d/patch-distribution/build/confirmed-ui-20260922-162530/stage/files/af-ui.rcc').read_bytes())['/liveview/Touchpad.qml']
objects=[];components=[]
for name,text in [('reference',baseline),('candidate',apply_native_touch(baseline))]:
 s='\n'.join(l for l in text.splitlines() if not l.startswith('import com.') and not l.startswith('import "'))
 s=s.replace('GlobalStateInfo','globalMock').replace('VideoControl','videoMock').replace('System','systemMock').replace('Camera','cameraMock').replace('Config','configMock')
 s=s.replace('    id: root','''    id: root
    width:640;height:480
    property int starts:0
    property int finishes:0
    property var moves:[]
    property var zoomMoves:[]
    property int timeouts:0
    property bool testZoom:false
    property bool testFocus:true
    property var globalMock: ({touchpadZoomActive:false,afSselectedIndex:-1,focusDelivery:{displayed:[0.5,0.5],beginDrag:function(){root.starts++},endDrag:function(){root.finishes++},select:function(p){root.globalMock.focusDelivery.displayed=p;root.moves=root.moves.concat([p])}}})
    property var cameraMock: ({firstComponent:function(p){return p[0]},secondComponent:function(p){return p[1]},combine:function(x,y){return [x,y]}})
    property var videoMock: ({restartLiveViewImageTimeout:function(){root.timeouts++}})
    property var configstore: ({touchpad_position:0})
    property var configMock: ({TouchpadLeft:0,TouchpadRight:1,TouchpadTopLeft:2,TouchpadBottomLeft:3,TouchpadBottomRight:4})
''')
 a=s.index('    property bool inZoomMode:');b=s.index('    property int zoomStepSize:',a)
 s=s[:a]+'    property bool inZoomMode:testZoom\n    property bool inFocusMode:testFocus&&!testZoom\n'+s[b:]
 s=s.replace('zoomCalc.lastPos = videoMock.zoomPoint','zoomCalc.lastPos = Qt.point(0.5,0.5)')
 s=s.replace('AFCalc {','Item {property int xCount:10;property int yCount:8;property real gridXMargin:70;property real gridYMargin:40;property real afItemWidth:50;property real afItemHeight:50;property real screenWidth;property real screenHeight;property string idText;')
 s=s.replace('ZoomCalc {','Item {property int minInterval;property var lastPos:Qt.point(0.5,0.5);function setZoomPoint(p){lastPos=p;root.zoomMoves=root.zoomMoves.concat([[p.x,p.y]])}')
 c=QQmlComponent(engine);c.setData(s.encode(),QUrl('file:///'+name+'.qml'));obj=c.create();assert obj,[e.toString() for e in c.errors()]
 components.append(c);objects.append(obj);engine.globalObject().setProperty(name,engine.newQObject(obj))
def js(code):
 r=engine.evaluate(code);assert not r.isError(),r.toString();assert not errors,errors;return r.toVariant()
checks=0
def compare(code):
 global checks
 for name in ['reference','candidate']:js(code.replace('$',name))
 for prop in ['starts','finishes','timeouts','moves','zoomMoves']:
  assert js('JSON.stringify(reference.'+prop+')')==js('JSON.stringify(candidate.'+prop+')'),(checks,prop,code)
 assert js('reference.globalMock.touchpadZoomActive')==js('candidate.globalMock.touchpadZoomActive')
 checks+=1
for command in ['$.acquireTouch([{pointId:7,x:100,y:100}])','$.acquireTouch([{pointId:9,x:240,y:100}])','$.updateTouch([{pointId:9,x:240,y:100},{pointId:7,x:103,y:100}])','$.releaseTouch([{pointId:9,x:240,y:100}])','$.updateTouch([{pointId:7,x:400,y:100}])','$.updateTouch([{pointId:7,x:120,y:100}])','$.updateTouch([{pointId:7,x:180,y:170}])','$.releaseTouch([{pointId:7,x:180,y:170}])']:compare(command)
rng=random.Random(1250)
for i in range(1800):
 if i%100==0:compare('$.testZoom='+str(bool(i%200)).lower())
 if i%137==0:compare('$.enabled=!$.enabled')
 points=[dict(pointId=rng.randrange(3),x=rng.randrange(-50,700),y=rng.randrange(-50,500)) for _ in range(rng.randrange(1,4))]
 compare('$.'+rng.choice(['acquireTouch','releaseTouch','updateTouch'])+'('+json.dumps(points)+')')
compare('$.finishFocusDrag()')
second=components[1].create();assert second
objects.append(second);engine.globalObject().setProperty('second',engine.newQObject(second))
js('candidate.enabled=true;candidate.testZoom=false;candidate.testFocus=true;candidate.acquireTouch([{pointId:1,x:100,y:100}]);candidate.updateTouch([{pointId:1,x:130,y:100}])')
before=js('JSON.stringify(candidate.moves)')
js('second.acquireTouch([{pointId:1,x:100,y:100}]);second.updateTouch([{pointId:1,x:110,y:100}]);second.finishFocusDrag()')
assert js('JSON.stringify(candidate.moves)')==before
assert states[objects[1]].owner==1 and states[second].owner==-1
js('candidate.updateTouch([{pointId:1,x:150,y:100}]);candidate.finishFocusDrag()')
assert js('JSON.stringify(candidate.moves)')!=before
report={'passed':True,'eventComparisons':checks,'perOwnerIsolation':True,'hardwareRequests':0,'hostBridgeSimulated':True,'armRuntimeVerified':False,'covers':['multicontact','reordered points','outside/reentry','focus mapping','zoom forwarding','disabled','mode change','release','separate surface state']}
(O/'result.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
