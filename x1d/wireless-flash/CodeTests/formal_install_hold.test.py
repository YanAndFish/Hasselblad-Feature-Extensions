"""运行实际注入 Timer 的 QML 替身，覆盖睡眠/错误/曝光/退出保持；无设备请求。"""
from pathlib import Path
import hashlib
import json
import os
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]
assert Path.cwd().resolve()==ROOT
sys.path.insert(0,str(HERE/'build/ui-test-python'))
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['QT_QUICK_BACKEND']='software'
from PySide6.QtCore import QObject,QUrl,QMetaObject,Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlEngine,QQmlComponent,QQmlPropertyMap
from PySide6.QtTest import QTest

def run():
    app=QGuiApplication.instance() or QGuiApplication([])
    engine=QQmlEngine()
    source=HERE/'ui/formal-runtime/main_formal_runtime.qml.inc'
    timer=source.read_text(encoding='utf-8').split('    FormalExposureGate {',1)[0]
    timer=timer.replace('id: formalInstallHoldTimer','id: formalInstallHoldTimer; objectName: "InstallTimer"')
    text='''import QtQuick 2.5
Item {
    id: root
    property int activityCount: 0
    property int badArguments: 0
    property var hblNative: nativeState
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
    function pulse() { formalInstallHoldTimer.triggered() }
    function lastPulse() { return nativeState.installPulse }
''' + timer + '\n}'
    maps={}
    for name,values in {'System':{'system_state':2,'StateUp':2},'Errors':{'ErrorNone':0},'ErrorControl':{'code':0},'Camera':{'inSession':False,'exposing':False}}.items():
        obj=QQmlPropertyMap();maps[name]=obj
        for key,value in values.items():obj.insert(key,value)
        engine.rootContext().setContextProperty(name,obj)
    component=QQmlComponent(engine)
    component.setData(text.encode(),QUrl('file:///InstallHoldHarness.qml'))
    assert not component.isError(),[e.toString() for e in component.errors()]
    root=component.create();assert root
    checks=[]
    def check(label,condition):
        assert condition,label
        checks.append(label)
    root.setHold(True);QTest.qWait(10)
    check('健康已醒界面发原厂活动通知',root.property('activityCount')>=1 and root.lastPulse())
    for kind in ('control-sleep','not-loaded','no-item','touch-sleep'):
        root.setCase(kind);before=root.property('activityCount');root.pulse()
        check(kind,root.property('activityCount')==before and not root.lastPulse())
    root.setCase('normal')
    for name,key,bad,good in [('System','system_state',4,2),('System','system_state',6,2),('ErrorControl','code',1000,0),('Camera','inSession',True,False),('Camera','exposing',True,False)]:
        maps[name].insert(key,bad);before=root.property('activityCount');root.pulse()
        check(name+'-'+key+'-'+str(bad),root.property('activityCount')==before and not root.lastPulse())
        maps[name].insert(key,good)
    root.pulse();check('恢复健康才能重新确认脉冲',root.lastPulse())
    root.setHold(False);before=root.property('activityCount');QTest.qWait(600)
    check('截止或释放后Timer停止',root.property('activityCount')==before)
    check('只传只通知参数',root.property('badArguments')==0)
    sources=[source,HERE/'native/formal_runtime.cpp',HERE/'native/formal_install_hold.h',HERE/'native/formal_system_check.cpp',Path(__file__)]
    out=HERE/'CodeTests/formal_hold_output';out.mkdir(exist_ok=True)
    report={'passed':True,'checks':checks,'checkCount':len(checks),'hardwareRequests':0,'targetQt55RuntimeTested':False,
            'sourceHashes':{p.relative_to(HERE).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}
    (out/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':len(checks),'hardwareRequests':0},ensure_ascii=False))

if __name__=='__main__':run()
