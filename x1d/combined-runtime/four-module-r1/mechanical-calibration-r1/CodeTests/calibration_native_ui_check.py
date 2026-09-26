"""用真实 NativeFlashPage 验证标定命令字段及适配器值回显。"""
import json
import calibration_ui_check as ui
from PySide6.QtQml import QQmlApplicationEngine,QQmlPropertyMap,qmlRegisterModule
from PySide6.QtCore import QUrl,QObject
from PySide6.QtTest import QTest
qmlRegisterModule('com.hasselblad.camera',1,0)
adapter=QQmlPropertyMap()
values={'command':'','connected':True,'masterEnabled':False,'masterRequested':False,'busy':False,'ready':True,'shotActive':False,
        'supportedGroupCount':16,'channel':5,'wirelessId':5,'errorText':'','sendPowerUpdates':True,'sendFlashSync':True,'adjustmentThirds':True}
for i in range(16):values.update({'active'+str(i):False,'tenthStops'+str(i):40,'lamp'+str(i):False})
for i,v in enumerate([5000,5000,6300,6900,6900]):values['mechanicalDelay'+str(i)]=v
for name,value in values.items():adapter.insert(name,value)
commands=[]
def changed(key,value):
    if key!='command':return
    command=json.loads(value);commands.append(command)
    if command['op']=='calibration':
        assert set(command)=={'op','delay0','delay1','delay2','delay3','delay4'}
        for i in range(5):adapter.insert('mechanicalDelay'+str(i),command['delay'+str(i)])
adapter.valueChanged.connect(changed)
engine=QQmlApplicationEngine();errors=[]
engine.warnings.connect(lambda items:errors.extend(e.toString() for e in items))
engine.rootContext().setContextProperty('hblNative',adapter)
qml='''import QtQuick 2.5
import QtQuick.Window 2.2
import "@COMPONENTS@"
Window { width:640; height:480; visible:true
    NativeFlashPage { anchors.fill:parent; pageActive:true; screen:"settings"; batterySource:""; iconBase:"@ICONS@"; fontName:"@FONT@" }
}'''.replace('@COMPONENTS@',(ui.WORK/'qml/controlscreen').as_uri()).replace('@ICONS@',ui.asset).replace('@FONT@',ui.family)
engine.loadData(qml.encode(),QUrl('file:///native-calibration-check.qml'))
assert engine.rootObjects(),errors
ui.window=engine.rootObjects()[0];QTest.qWait(50)
ui.click('FlashCalibrationOpen');ui.click('FlashDelayPlus0')
assert commands[-1]=={'op':'calibration','delay0':5100,'delay1':5000,'delay2':6300,'delay3':6900,'delay4':6900},commands
ui.click('FlashDelayValue2')
for key in ['8','.','1','2']:ui.click('FlashDelayKey'+key)
ui.click('FlashDelayConfirm')
assert commands[-1]=={'op':'calibration','delay0':5100,'delay1':5000,'delay2':8120,'delay3':6900,'delay4':6900},commands
assert adapter.value('mechanicalDelay2')==8120
adapter.insert('shotActive',True);before=len(commands);ui.click('FlashDelayPlus0');assert len(commands)==before
assert not errors,errors
proof={'passed':True,'realNativeFlashPage':True,'fiveMicrosecondFields':True,'adapterReadback':True,'activeShotBlocksEditing':True,'qmlWarnings':errors,'hardwareRequests':0}
(ui.HERE/'calibration-ui-output/native-validation.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof))
ui.window.close();engine.deleteLater();ui.app.processEvents()
