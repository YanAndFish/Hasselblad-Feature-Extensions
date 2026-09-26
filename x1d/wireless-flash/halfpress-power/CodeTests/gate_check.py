from pathlib import Path
import sys,os,json
HERE=Path(__file__).resolve().parent.parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'x1d/wireless-flash/build/ui-test-python'))
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import QUrl,QMetaObject
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlEngine,QQmlComponent
out=HERE/'build/gate-test';out.mkdir(parents=True,exist_ok=True)
(out/'HalfPressExposureGate.qml').write_text((HERE/'HalfPressExposureGate.qml').read_text(encoding='utf8'),encoding='utf8')
qml='''import QtQuick 2.5
Item {
 property int shots:0
 property int checks:0
 property var errors:[]
 property var requests:[]
 function check(ok,label){checks++;if(!ok)errors=errors.concat([label])}
 QtObject {id:a;property bool connected:true;property bool masterEnabled:true;property int lastFlushToken:0;property int flushAckToken:0;property int flushResult:0;property string command:"";onCommandChanged:requests=requests.concat([JSON.parse(command)])}
 HalfPressExposureGate {id:g;nativeAdapter:a;contextValid:true;exposureUs:8000;onContinueExposure:shots++}
 function latest(){return requests[requests.length-1]}
 function exercise(){
  for(var mode=0;mode<2;mode++) {
   g.electronic=!!mode;g.halfPowerEnabled=false;requests=[]
   g.prepareHalfPress();check(requests.length===0,"off half no power");g.begin(false)
   check(latest().op==="flush" && latest().electronic===!!mode,"off full sync only")
   g.shotEnded();g.halfReleased();g.halfPowerEnabled=true;requests=[]
   g.prepareHalfPress();check(latest().op==="prepare" && latest().electronic===!!mode,"half mode")
   var count=requests.length;g.prepareHalfPress();check(requests.length===count,"hold no repeat")
   g.exposureUs=16000;check(g.activeToken>0,"metering change retains sent power")
   var before=shots;g.begin(false);check(shots===before+1 && latest().op==="queueSync" && latest().exposureUs===16000,"full immediate current exposure")
   g.cancel();g.halfReleased();check(latest().op==="queueSync","full release keeps shot")
   a.flushAckToken=g.activeToken;g.checkAcknowledgement();check(shots===before+1,"ack no exposure")
   g.shotEnded();check(latest().op==="shotEnd","shot end")
   g.prepareHalfPress();g.halfReleased();check(latest().op==="shotEnd" && !g.activeToken,"half release cancels")
   g.prepareHalfPress();g.halfPowerEnabled=false;check(!g.activeToken,"disable cancels prepared")
   count=requests.length;g.halfPowerEnabled=true;g.prepareHalfPress();check(requests.length===count,"toggle held no resend")
   g.halfReleased();g.prepareHalfPress();g.contextValid=false;check(!g.activeToken,"context invalid")
   g.contextValid=true;g.halfReleased();g.prepareHalfPress();a.connected=false;check(!g.activeToken,"disconnect cancels")
   count=requests.length;before=shots;g.begin(false);check(shots===before+1 && requests.length===count,"disconnected capture immediate")
   g.halfReleased();a.connected=true;g.prepareHalfPress();a.flushResult=1;a.flushAckToken=g.activeToken;g.checkAcknowledgement();check(!g.activeToken,"error ack clears")
   before=shots;g.begin(false);check(shots===before+1 && latest().op==="flush","failed prepare falls back sync")
   g.shotEnded();g.begin(false);check(latest().op==="flush","another full within half hold sync")
   g.shotEnded();g.halfReleased();a.flushResult=0
  }
 }
}'''
(out/'Harness.qml').write_text(qml,encoding='utf8')
app=QGuiApplication([]);engine=QQmlEngine();c=QQmlComponent(engine,QUrl.fromLocalFile(str(out/'Harness.qml')))
root=c.create();assert root is not None,[e.toString() for e in c.errors()]
assert QMetaObject.invokeMethod(root,'exercise')
errors=root.property('errors').toVariant();assert not errors,errors
print(json.dumps({'passed':True,'checks':root.property('checks'),'hardwareRequests':0}))
