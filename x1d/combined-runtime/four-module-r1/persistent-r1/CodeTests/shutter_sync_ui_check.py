"""从当前已安装 RCC 同源文件检查参数页命令和不等待曝光；无相机访问。"""
from pathlib import Path
import os,sys,json,hashlib
sys.dont_write_bytecode=True
P=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(P.parent));import compose
sys.path.insert(0,str(P.parents[3]/'x1d/wireless-flash/build/ui-test-python'))
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import QUrl,QMetaObject
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlEngine,QQmlComponent,QQmlPropertyMap,qmlRegisterModule
data=(P/'build/nonblocking-ui/build/combined-ui.rcc').read_bytes()
assert hashlib.sha256(data).hexdigest()=='564bf95de49e3a30fdbc9e285b30426f6beb6bf32d398f46cba50c9a719d616a'
values=compose.read_rcc(data)
assert 'prepareHalfPress' not in values['/main.qml']
assert 'op:"prepare"' not in values['/FormalExposureGate.qml']
O=P/'build/shutter-sync/ui-test';O.mkdir(parents=True,exist_ok=True)
for name,value in values.items():
 if name.startswith('/controlscreen/') or name=='/FormalExposureGate.qml':
  f=O/name.lstrip('/');f.parent.mkdir(parents=True,exist_ok=True);f.write_text(value,encoding='utf-8')
qmlRegisterModule('com.hasselblad.camera',1,0)
app=QGuiApplication([]);engine=QQmlEngine();adapter=QQmlPropertyMap()
fields=dict(command='',connected=True,masterEnabled=True,masterRequested=True,busy=False,ready=True,shotActive=False,supportedGroupCount=16,channel=5,wirelessId=5,errorText='',sendPowerUpdates=True,sendFlashSync=True,adjustmentThirds=True,settingsRestoring=False,settingsError='',visibleGroupMask=31,lastFlushToken=0,flushAckToken=0,flushResult=0)
for i in range(16):fields.update({'active'+str(i):False,'tenthStops'+str(i):40,'lamp'+str(i):False})
for i,v in enumerate([5000,5000,6300,6900,6900]):fields['mechanicalDelay'+str(i)]=v
for k,v in fields.items():adapter.insert(k,v)
commands=[]
adapter.valueChanged.connect(lambda k,v:commands.append(json.loads(v)) if k=='command' else None)
engine.rootContext().setContextProperty('hblNative',adapter)
qml='''import QtQuick 2.5
import "controlscreen"
Item {
 property int shots:0
 NativeFlashPage {id:p;pageActive:true;batterySource:""}
 FormalExposureGate {id:g;nativeAdapter:hblNative;contextValid:true;exposureUs:8000;onContinueExposure:parent.shots++}
 function exercise(){
  p.setGroup(0,true,50,true);
  p.setGroup(0,false,50,true);
  p.setGroup(0,true,50,true);
  p.requestTest();
  g.begin(false);
  g.checkAcknowledgement();
 }
}'''
(O/'Harness.qml').write_text(qml,encoding='utf-8')
c=QQmlComponent(engine,QUrl.fromLocalFile(str(O/'Harness.qml')));root=c.create()
assert root is not None,[e.toString() for e in c.errors()]
commands.clear();assert QMetaObject.invokeMethod(root,'exercise')
assert commands==[{'op':'group','group':0,'active':True,'tenthStops':50},{'op':'group','group':0,'active':False,'tenthStops':50},{'op':'group','group':0,'active':True,'tenthStops':50},{'op':'test'},{'op':'flush','token':1,'electronic':False,'exposureUs':8000}],commands
assert root.property('shots')==1
r=dict(passed=True,hardwareRequests=0,installedRccSha256=hashlib.sha256(data).hexdigest(),checks=['single-group-power','single-group-OFF','test-command','fullpress-immediate','no-halfpress-power'])
(P/'build/shutter-sync/ui-validation.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
print(json.dumps(r))
