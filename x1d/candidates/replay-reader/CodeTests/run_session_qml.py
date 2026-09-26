"""在本机 Qt 中执行实际注入的活动 Timer，并独立读取生成 RCC；无相机。"""
from pathlib import Path
import hashlib
import json
import os
import sys
HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'x1d/wireless-flash/build/ui-test-python'))
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['QT_QUICK_BACKEND']='software'
os.environ['QML_DISABLE_DISK_CACHE']='1'
from PySide6.QtCore import QUrl,QResource,QFile,QIODevice
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlEngine,QQmlComponent,QQmlPropertyMap
from PySide6.QtTest import QTest

def sha(b):return hashlib.sha256(b).hexdigest()
def run():
    app=QGuiApplication.instance() or QGuiApplication([])
    engine=QQmlEngine()
    source=HERE/'session/hold.qml.inc'
    text='''import QtQuick 2.5
Item {
 id: root
 property int activityCount: 0
 property int badArguments: 0
 property var x1dReplaySession: nativeState
 QtObject { id: nativeState; property bool installationHold: false; property bool installPulse: false }
 QtObject { id: control; property string state: "active" }
 QtObject { id: mainWindow; property int status: Loader.Ready; property var item: touch }
 QtObject {
  id: touch; property bool sleeping: false
  function idleWakeupOrForceOff(onlyNotify) { if (onlyNotify!==true) root.badArguments++; root.activityCount++ }
 }
 function setCase(kind) {
  control.state=kind==="control-sleep" ? "sleeping" : "active"
  mainWindow.status=kind==="not-loaded" ? Loader.Loading : Loader.Ready
  mainWindow.item=kind==="no-item" ? null : touch
  touch.sleeping=kind==="touch-sleep"
 }
 function setHold(on) { nativeState.installationHold=on }
 function pulse() { replayInstallHoldTimer.triggered() }
 function lastPulse() { return nativeState.installPulse }
''' + source.read_text(encoding='utf-8')+'\n}'
    maps={}
    for name,values in {'System':{'system_state':2,'StateUp':2},'Errors':{'ErrorNone':0},'ErrorControl':{'code':0},'Camera':{'inSession':False,'exposing':False}}.items():
        obj=QQmlPropertyMap();maps[name]=obj
        for key,value in values.items():obj.insert(key,value)
        engine.rootContext().setContextProperty(name,obj)
    component=QQmlComponent(engine);component.setData(text.encode(),QUrl('file:///ReplayHoldHarness.qml'))
    assert not component.isError(),[e.toString() for e in component.errors()]
    root=component.create();assert root
    checks=[]
    def check(name,value):assert value,name;checks.append(name)
    root.setHold(True);QTest.qWait(10)
    check('active-notification',root.property('activityCount')>=1 and root.lastPulse())
    for kind in ['control-sleep','not-loaded','no-item','touch-sleep']:
        root.setCase(kind);before=root.property('activityCount');root.pulse()
        check(kind,root.property('activityCount')==before and not root.lastPulse())
    root.setCase('normal')
    for name,key,bad,good in [('System','system_state',4,2),('System','system_state',6,2),('ErrorControl','code',1000,0),('Camera','inSession',True,False),('Camera','exposing',True,False)]:
        maps[name].insert(key,bad);before=root.property('activityCount');root.pulse()
        check(name+'-'+key+str(bad),root.property('activityCount')==before and not root.lastPulse());maps[name].insert(key,good)
    root.pulse();check('healthy-resumes',root.lastPulse())
    root.setHold(False);before=root.property('activityCount');QTest.qWait(600)
    check('released-timer-stops',root.property('activityCount')==before)
    check('only-notify-argument',root.property('badArguments')==0)
    rcc=HERE/'artifacts/session/replay-ui.rcc'
    assert QResource.registerResource(str(rcc))
    f=QFile(':/main.qml');assert f.open(QIODevice.ReadOnly)
    check('rcc-actual-qt-decompression',bytes(f.readAll())==(HERE/'artifacts/session/main.qml').read_bytes());f.close()
    QResource.unregisterResource(str(rcc))
    sources=[Path(__file__),source,HERE/'session/session_runtime.cpp',HERE/'session/session_policy.h',HERE/'tools/build_session.py']
    report={'passed':True,'checks':checks,'checkCount':len(checks),'cameraAccess':False,'runtime':'host Qt6 / original injected Timer; proprietary context objects are substitutes',
            'targetQt55Executed':False,'rccSha256':sha(rcc.read_bytes()),
            'sourceHashes':{p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in sources}}
    out=HERE/'artifacts/session-tests';out.mkdir(parents=True,exist_ok=True)
    (out/'qml.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'qmlChecks':len(checks),'cameraAccess':False}))

if __name__=='__main__':run()
