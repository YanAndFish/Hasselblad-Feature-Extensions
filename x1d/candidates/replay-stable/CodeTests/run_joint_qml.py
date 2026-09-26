"""实际执行组合后的被动 QML 回执，不构造原厂业务页或设备对象。"""
from pathlib import Path
import hashlib
import json
import os
import sys
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path.insert(0,str(HERE/'tools'));sys.path.insert(0,str(ROOT/'x1d/wireless-flash/build/ui-test-python'))
os.environ.update(QT_QPA_PLATFORM='offscreen',QT_QUICK_BACKEND='software',QML_DISABLE_DISK_CACHE='1')
from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlEngine,QQmlComponent,QQmlPropertyMap
from compose_joint_resources import compose

def run():
    app=QGuiApplication.instance() or QGuiApplication([])
    original='''import QtQuick 2.5
Item {
 objectName: "mainRoot"
 property int rootCompletions: 0
 Component.onCompleted: rootCompletions++
}
'''
    text=compose({'/main.qml':original})['/main.qml'];checks=[]
    for available in (False,True):
        engine=QQmlEngine();state=QQmlPropertyMap();changes=[]
        state.insert('resourceReady',False)
        state.valueChanged.connect(lambda k,v:changes.append((k,v)))
        if available:engine.rootContext().setContextProperty('x1dReplaySession',state)
        component=QQmlComponent(engine);component.setData(text.encode(),QUrl('file:///ReplayJointHarness.qml'))
        assert not component.isError(),[e.toString() for e in component.errors()]
        root=component.create();assert root
        assert root.property('rootCompletions')==1;checks.append('root-completion-retained-'+str(available))
        assert changes==([('resourceReady',True)] if available else []);checks.append('single-local-receipt-'+str(available))
        assert bool(state.value('resourceReady'))==available;checks.append('native-property-'+str(available))
        root.deleteLater();engine.deleteLater()
    report={'passed':True,'checks':checks,'cameraAccess':False,'targetQt55Executed':False,'runtime':'host Qt6; passive QML receipt only',
            'sourceHashes':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),HERE/'tools/compose_joint_resources.py']}}
    out=HERE/'artifacts/joint-tests';out.mkdir(parents=True,exist_ok=True)
    (out/'qml.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'jointQmlChecks':len(checks),'cameraAccess':False}))

if __name__=='__main__':run()
