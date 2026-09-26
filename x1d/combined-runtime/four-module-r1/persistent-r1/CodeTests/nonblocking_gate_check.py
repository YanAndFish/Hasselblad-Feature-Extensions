from pathlib import Path
import sys,os,importlib.util,json
sys.dont_write_bytecode=True
P=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(P.parents[3]/'x1d/wireless-flash/build/ui-test-python'))
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import QUrl,QMetaObject
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlEngine,QQmlComponent
spec=importlib.util.spec_from_file_location('candidate',P/'build_nonblocking_ui.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
o=P/'build/nonblocking-ui/gate-test';o.mkdir(exist_ok=True)
(o/'FormalExposureGate.qml').write_text(m.values['/FormalExposureGate.qml'],encoding='utf-8')
qml='''import QtQuick 2.5
Item {
 property int shots: 0
 property int failures: 0
 QtObject {id: a; property bool connected:true;property bool masterEnabled:true;property bool masterRequested:true;property int lastFlushToken:0;property int flushAckToken:0;property int flushResult:0;property string command:""}
 FormalExposureGate {id:g;nativeAdapter:a;contextValid:true;exposureUs:8000;onContinueExposure:parent.shots++}
 function exercise(){
  g.begin(false);if(shots!==1 || g.pending || g.activeToken!==1)failures++;
  g.cancel();if(shots!==1 || g.activeToken!==1)failures++;
  a.flushAckToken=1;g.checkAcknowledgement();if(shots!==1)failures++;
  g.shotEnded();g.begin(false);if(shots!==2)failures++;
  a.flushResult=3;a.flushAckToken=2;g.checkAcknowledgement();if(shots!==2 || g.activeToken!==0)failures++;
  a.connected=false;g.begin(false);if(shots!==3)failures++;
  a.connected=true;a.masterEnabled=false;g.begin(false);if(shots!==4)failures++;
  g.contextValid=false;g.begin(false);if(shots!==4)failures++;
 }
}'''
(o/'Harness.qml').write_text(qml,encoding='utf-8')
app=QGuiApplication([]);engine=QQmlEngine();c=QQmlComponent(engine,QUrl.fromLocalFile(str(o/'Harness.qml')));root=c.create()
assert root is not None,[x.toString() for x in c.errors()]
assert QMetaObject.invokeMethod(root,'exercise')
assert root.property('failures')==0,root.property('failures')
print(json.dumps({'passed':True,'shots':root.property('shots'),'hardwareRequests':0,'cases':['immediate','release-no-cancel','late-ack-no-double','failed-ack','disconnected','disabled','invalid-context']}))
