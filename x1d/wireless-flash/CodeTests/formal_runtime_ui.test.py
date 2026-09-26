"""真实 QML 替身测试：曝光续行/取消及 native 接线；0 相机与无线请求。"""
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
sys.path.insert(0,str(HERE/'research'))
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['QT_QUICK_BACKEND']='software'
from PySide6.QtCore import QObject,QUrl,Qt,QPoint,QResource,qVersion
from PySide6.QtGui import QGuiApplication,QFontDatabase,QFont
from PySide6.QtQuick import QQuickView
from PySide6.QtQml import QQmlPropertyMap
from PySide6.QtTest import QTest
from prepare_formal_runtime_ui import build_resources,OUT,EXPOSURE

HARNESS='''import QtQuick 2.5
import com.hasselblad.camera 1.0
import com.hasselblad.systemmanager 1.0
import "controlscreen"
Item {
    id: test; width: 640; height: 480
    property int exposures: 0
    property int cancels: 0
    property bool lastLiveview: false
    function setTestIso(value) { Camera.iso=value }
    function setTestBattery(level,status) { System.batteryLevel=level; System.batteryStatus=status }
    QtObject { id: gui; function fromIsoVal(value) { return value===-1 ? "Auto" : String(value) } }
    property var guiconfig: gui
    QtObject {
        id: adapter; objectName: "MockNative"
        property string command: ""
        property bool connected: true
        property bool masterRequested: false
        property bool masterEnabled: false
        property bool sendPowerUpdates: true
        property bool sendFlashSync: true
        property bool adjustmentThirds: true
        property bool busy: false
        property bool ready: true
        property bool shotActive: false
        property int supportedGroupCount: 16
        property int channel: 5
        property int wirelessId: 5
        property string errorText: ""
        property int flushAckToken: 0
        property int lastFlushToken: 0
        property int flushResult: 5
        property bool active0: false
        property int tenthStops0: 40
        property bool lamp0: false
        property bool active1: false
        property int tenthStops1: 40
        property bool lamp1: false
        property bool active2: false
        property int tenthStops2: 40
        property bool lamp2: false
        property bool active3: false
        property int tenthStops3: 40
        property bool lamp3: false
        property bool active4: false
        property int tenthStops4: 40
        property bool lamp4: false
        property bool active5: false
        property int tenthStops5: 40
        property bool lamp5: false
        property bool active6: false
        property int tenthStops6: 40
        property bool lamp6: false
        property bool active7: false
        property int tenthStops7: 40
        property bool lamp7: false
        property bool active8: false
        property int tenthStops8: 40
        property bool lamp8: false
        property bool active9: false
        property int tenthStops9: 40
        property bool lamp9: false
        property bool active10: false
        property int tenthStops10: 40
        property bool lamp10: false
        property bool active11: false
        property int tenthStops11: 40
        property bool lamp11: false
        property bool active12: false
        property int tenthStops12: 40
        property bool lamp12: false
        property bool active13: false
        property int tenthStops13: 40
        property bool lamp13: false
        property bool active14: false
        property int tenthStops14: 40
        property bool lamp14: false
        property bool active15: false
        property int tenthStops15: 40
        property bool lamp15: false
    }
    property var hblNative: adapter
    Item { id: owner }
    FormalExposureGate {
        id: gate; nativeAdapter: adapter; contextValid: true; contextOwner: owner
        exposureUs: 8000
        onContinueExposure: { test.exposures++; test.lastLiveview=liveviewAfterExposure }
        onCancelled: test.cancels++
    }
    NativeFlashPage {
        id: page; width: 640; height: 480; pageActive: true
        iconBase: "@ICONS@/"; fontName: "Arial"
    }
    function ack(token,result) { adapter.flushResult=result; adapter.flushAckToken=token }
    function off() { adapter.masterRequested=false; adapter.masterEnabled=false }
    function on() { adapter.connected=true; adapter.masterRequested=true; adapter.masterEnabled=true }
    function changeOwner() { gate.contextOwner=test }
    function destroyPendingGate() {
        var source='import QtQuick 2.5; FormalExposureGate { nativeAdapter: hblNative; contextValid: true; exposureUs: 8000; onContinueExposure: test.exposures++ }'
        var temporary=Qt.createQmlObject(source,test,"TemporaryGate")
        temporary.nextToken=100
        temporary.begin(false)
        temporary.destroy()
    }
    function destroyFlashPage() {
        var temporary=Qt.createQmlObject('import QtQuick 2.5; import "controlscreen"; NativeFlashPage { width: 640; height: 480; iconBase: page.iconBase; fontName: "Arial" }',test,"TemporaryFlashPage")
        temporary.destroy()
    }
}
'''


def run():
    manifest=build_resources()
    source=HARNESS.replace('@ICONS@',(OUT/'baseline-assets').as_uri())
    qml=OUT/'qml/FormalRuntimeHarness.qml'; qml.write_text(source,encoding='utf-8')
    app=QGuiApplication([])
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
    app.setFont(QFont('Microsoft YaHei'))
    view=QQuickView(); warnings=[]
    # 原厂 Camera 是需要逐文件导入的 QML singleton，不能用全局 context property 掩盖缺失导入。
    mock_root=OUT/'test-qml'
    mock_camera=mock_root/'com/hasselblad/camera'
    mock_camera.mkdir(parents=True,exist_ok=True)
    (mock_camera/'qmldir').write_text('module com.hasselblad.camera\nsingleton Camera 1.0 Camera.qml\n',encoding='utf-8')
    (mock_camera/'Camera.qml').write_text('pragma Singleton\nimport QtQuick 2.5\nQtObject { property int iso: 100 }\n',encoding='utf-8')
    for module,name,body_text in [
        ('systemmanager','System','enum BatteryState { BatteryNormal, BatteryLow, BatteryExhausted, BatteryAux, BatteryUnknown } property int batteryStatus: 0; property real batteryLevel: 72'),
        ('suc','Suc','enum UsbChargeState { UsbChargeOff, UsbChargeLow, UsbChargeMid, UsbChargeHigh }')]:
        folder=mock_root/('com/hasselblad/'+module);folder.mkdir(parents=True,exist_ok=True)
        (folder/'qmldir').write_text('module com.hasselblad.'+module+'\nsingleton '+name+' 1.0 '+name+'.qml\n',encoding='utf-8')
        (folder/(name+'.qml')).write_text('pragma Singleton\nimport QtQuick 2.5\nQtObject { '+body_text+' }\n',encoding='utf-8')
    view.engine().addImportPath(str(mock_root))
    import build as common
    original=common.qml_files(common.ArmElf((common.BASELINE/'usr/bin/victory-gui').read_bytes()))
    factory_battery=OUT/'factory-battery-test.rcc'
    factory_battery.write_bytes(common.rcc({'/components/BatteryIndicatorScaled.qml':original['/components/BatteryIndicatorScaled.qml']}))
    assert QResource.registerResource(str(factory_battery))
    suc=QQmlPropertyMap();suc.insert('usbChargeLevel',0);suc.insert('ext_power',False)
    view.rootContext().setContextProperty('suc',suc)
    body=QQmlPropertyMap()
    for key,value in {'AV_out_of_range':False,'TV_out_of_range':False,'aperture':'4.0','shutterSpeed':'125','autoIso':3200}.items():body.insert(key,value)
    view.rootContext().setContextProperty('cambody',body)
    view.engine().warnings.connect(lambda values: warnings.extend(v.toString() for v in values))
    view.setSource(QUrl.fromLocalFile(str(qml)))
    assert view.status()==QQuickView.Ready,[x.toString() for x in view.errors()]
    view.resize(640,480);view.show();QTest.qWait(100)
    root=view.rootObject(); gate=root.findChild(QObject,'FormalExposureGate')
    native=root.findChild(QObject,'MockNative');page=root.findChild(QObject,'FormalFlashPage')
    checks=[]
    def check(label,condition):
        assert condition,label
        checks.append(label)
    def command(): return json.loads(native.property('command'))
    def click(x,y):
        QTest.mouseClick(view,Qt.LeftButton,Qt.NoModifier,QPoint(x,y));QTest.qWait(20)
    def ack(result=0):
        token=gate.property('pendingToken');root.ack(token,result);QTest.qWait(10)
        return token

    check('启动不开启不试闪',root.property('exposures')==0 and native.property('command')=='')
    check('实时曝光摘要使用机身格式',page.property('apertureText')=='F/4.0' and page.property('shutterSpeedText')=='1/125' and page.property('isoText')=='ISO 100')
    body.setProperty('aperture','32');body.setProperty('shutterSpeed','2000');root.setTestIso(-1);QTest.qWait(10)
    check('参数变化立即更新且保留自动ISO',page.property('apertureText')=='F/32' and page.property('shutterSpeedText')=='1/2000' and page.property('isoText')=='ISO A 3200')
    line=page.findChild(QObject,'FlashExposureLine');summary=page.findChild(QObject,'FlashExposureSummary')
    check('单行曝光摘要不越过CH且不增高顶部',summary.property('x')+summary.property('width')<326 and summary.property('y')+summary.property('height')<76 and line.property('paintedWidth')<=line.property('width') and line.property('lineCount')==1 and page.findChild(QObject,'FlashGroupList').property('y')==86)
    battery=page.findChild(QObject,'FlashBattery')
    check('加载原厂电池组件并保留真实电量状态绑定',battery.property('item') is not None and battery.property('item').property('batteryWidth')==19 and battery.property('item').property('showBattery'))
    root.setTestBattery(12,1);QTest.qWait(30)
    check('原厂低电量警示状态随电量更新',battery.property('item').property('isWarning'))
    root.setTestBattery(0,4);QTest.qWait(30)
    check('原厂未知电量不伪装有电',not battery.property('item').property('showBattery'))
    root.setTestBattery(72,0);QTest.qWait(30)
    native.setProperty('channel',32);native.setProperty('wirelessId',0);QTest.qWait(30)
    trial=page.findChild(QObject,'FlashTest');choose=page.findChild(QObject,'FlashChooseGroups')
    check('试闪移到选择分组左侧且不重叠',trial.property('y')==choose.property('y') and trial.property('x')+trial.property('width')<choose.property('x'))
    view.grabWindow().save(str(OUT/'exposure-header-preview.png'))
    native.setProperty('channel',5);native.setProperty('wirelessId',5)
    body.setProperty('shutterSpeed','16m39s');body.setProperty('TV_out_of_range',True);QTest.qWait(10)
    check('曝光越界不显示旧快门值',page.property('shutterSpeedText')=='—')
    body.setProperty('TV_out_of_range',False);QTest.qWait(10)
    check('长曝光原厂单位保留',page.property('shutterSpeedText')=='16m39s')
    check('主开关关闭保留原厂即时曝光',gate.begin(True) and root.property('exposures')==1 and root.property('lastLiveview'))
    native.setProperty('masterRequested',True)
    check('未获主开关确认不误拍',not gate.begin(False) and root.property('exposures')==1)
    root.on();before=root.property('exposures')
    check('全按发flush并异步等待',gate.begin(False) and gate.property('pending') and command()['op']=='flush' and root.property('exposures')==before)
    check('完整flush输入模式及名义档位',command()['electronic'] is False and command()['exposureUs']==8000)
    check('等待中重复全按拒绝',not gate.begin(True))
    root.ack(gate.property('pendingToken')+1,0)
    check('错误token不可续拍',gate.property('pending') and root.property('exposures')==before)
    token=ack()
    check('成功ACK只续拍一次',not gate.property('pending') and root.property('exposures')==before+1 and not root.property('lastLiveview'))
    root.ack(token,0);gate.checkAcknowledgement()
    check('重复ACK不可重复拍摄',root.property('exposures')==before+1)
    gate.shotEnded();check('曝光结束释放对应token',command()=={'op':'shotEnd','token':token})
    gate.begin(False);token=gate.property('pendingToken');gate.cancel();root.ack(token,0)
    check('松开取消后迟到ACK不可曝光',not gate.property('pending') and command()['op']=='cancel' and root.property('exposures')==before+1)
    for result in range(1,7):
        gate.begin(False);ack(result)
        check('失败ACK不续拍-'+str(result),not gate.property('pending') and root.property('exposures')==before+1)
    for prop,new,old in [('contextValid',False,True),('electronic',True,False),('exposureUs',6250,8000)]:
        gate.begin(False);token=gate.property('pendingToken');gate.setProperty(prop,new);root.ack(token,0)
        check('上下文变更撤销-'+prop,not gate.property('pending') and root.property('exposures')==before+1)
        gate.setProperty(prop,old)
    gate.begin(False);token=gate.property('pendingToken');root.changeOwner();root.ack(token,0)
    check('页面对象替换撤销',not gate.property('pending') and root.property('exposures')==before+1)
    gate.begin(False);token=gate.property('pendingToken');native.setProperty('connected',False);root.ack(token,0)
    check('worker断联撤销',not gate.property('pending') and root.property('exposures')==before+1)
    root.on();gate.begin(False);token=gate.property('pendingToken');QTest.qWait(6600);root.ack(token,0)
    check('有界6.5秒超时且迟到成功无效',not gate.property('pending') and root.property('exposures')==before+1)
    root.destroyPendingGate();QTest.qWait(30);root.ack(101,0)
    check('组件销毁取消且不得延迟拍摄',command()=={'op':'cancel','token':101} and root.property('exposures')==before+1)
    native.setProperty('lastFlushToken',200);gate.begin(False)
    check('重建或重连使用未重用token',gate.property('pendingToken')==201)
    gate.cancel();native.setProperty('lastFlushToken',2147483646)
    check('token耗尽拒绝绕回旧编号',not gate.begin(False))
    native.setProperty('lastFlushToken',201)
    root.destroyFlashPage();QTest.qWait(30)
    check('引闪页销毁只取消pending不关总功能',command()=={'op':'cancelCurrent'} and page.property('masterEnabled'))
    root.off();click(535,36)
    check('点击开启发选项并等待nativeACK',command()=={'op':'options','master':True,'power':True,'sync':True} and not page.property('masterEnabled'))
    root.on();check('native确认后开启显示',page.property('masterEnabled'))
    # 用户设置同时控制三个调节入口。只切换偏好，不修改草稿或发送功率。
    page.setProperty('screen','settings');QTest.qWait(20)
    values=[page.groupPower(i) for i in range(5)]
    click(540,225)
    check('设置选择十分之一档不改变功率',not page.property('thirdStopSteps') and command()=={'op':'step','thirds':False} and values==[page.groupPower(i) for i in range(5)])
    click(405,225)
    check('设置选择三分之一档',page.property('thirdStopSteps') and command()=={'op':'step','thirds':True})
    page.setProperty('screen','groups');page.setGroup(0,True,0,False)
    actual=[]
    for i in range(24):
        page.quickAdjust(0,1);actual.append(page.groupPower(0))
    expected=[int(i*10/3+0.5) for i in range(1,25)]
    check('三分之一档从最低到最高没有累计0.9误差',actual==expected)
    actual=[]
    for i in range(24):
        page.quickAdjust(0,-1);actual.append(page.groupPower(0))
    check('三分之一档可逐档减回最低',actual==list(reversed([0]+expected[:-1])))
    page.setGroup(0,True,40,False);click(460,115)
    check('主页面加减采用三分之一档',page.groupPower(0)==43 and command()=={'op':'group','group':0,'active':True,'tenthStops':43})
    page.setProperty('selectedGroup',0);page.setProperty('screen','power');QTest.qWait(20);click(510,329)
    check('详情页共用步长到0.7',page.groupPower(0)==47)
    page.setProperty('screen','groups')
    for i in range(5):page.setGroup(i,True,40,False)
    offsets=[]
    for i in range(3):
        click(270,432);offsets.append(page.groupAdjustmentText())
    check('统一加减同样按三分之一档且累计正确',offsets==['+0.3','+0.7','+1.0'] and all(page.groupPower(i)==50 for i in range(5)))
    for i in range(3):click(50,432)
    check('三分之一档统一减回初值',all(page.groupPower(i)==40 for i in range(5)) and page.groupAdjustmentText()=='0.0')
    page.setAdjustmentStep(False,True);page.quickAdjust(0,1)
    check('切到十分之一档立即共用',page.groupPower(0)==41 and command()['tenthStops']==41)
    for i in range(5):page.setGroup(i,False,40,False)
    page.setGroup(0,True,43,True)
    check('单组编辑直接发送功率命令',command()=={'op':'group','group':0,'active':True,'tenthStops':43})
    native.setProperty('busy',True);page.setGroup(1,True,35,True)
    check('busy时保留编辑给native合并',command()=={'op':'group','group':1,'active':True,'tenthStops':35})
    native.setProperty('busy',False)
    for power,sync in [(True,False),(False,False),(False,True),(True,True)]:
        page.setDeliveryOptions(power,sync)
        check('两个选项独立-'+str((power,sync)),command()=={'op':'options','master':True,'power':power,'sync':sync})
    check('F与数字组可选择并下发',page.toggleVisibleGroup(5) and page.toggleVisibleGroup(6) and page.setGroup(15,True,40,True) and command()=={'op':'group','group':15,'active':True,'tenthStops':40})
    check('造型灯开关发送本组请求',page.toggleLamp(0) and command()=={'op':'lamp','group':0,'on':True})
    check('试闪就绪',page.requestTest() and command()=={'op':'test'})
    native.setProperty('shotActive',True);check('曝光期间试闪禁用',not page.requestTest())
    native.setProperty('shotActive',False);page.setDeliveryOptions(True,False);check('同步关闭时试闪禁用',not page.requestTest())
    for i in range(16):page.setGroup(i,False,40,False)
    page.setDeliveryOptions(True,True);previous=native.property('command')
    check('全部组关闭后试闪不产生请求',not page.requestTest() and native.property('command')==previous)
    page.setProperty('screen','groups');click(393,36)
    check('点CH打开数字键盘',page.property('screen')=='wireless' and page.property('wirelessField')=='channel')
    page.wirelessKey('3');page.wirelessKey('3')
    check('CH33不能确认且原频道保留',not page.confirmWireless() and page.property('channel')==5)
    page.wirelessKey('退格');page.wirelessKey('2')
    check('CH32确认才发送配置',page.confirmWireless() and command()=={'op':'wireless','channel':32,'id':5})
    native.setProperty('channel',32);click(489,36)
    check('点ID打开数字键盘',page.property('screen')=='wireless' and page.property('wirelessField')=='id')
    page.wirelessKey('0')
    check('数字零不冒充有效ID',not page.confirmWireless())
    click(120,262)
    check('ID关闭使用单独选项',page.property('wirelessOff') and page.confirmWireless() and command()=={'op':'wireless','channel':32,'id':0})
    native.setProperty('wirelessId',0);click(489,36)
    page.wirelessKey('9');page.wirelessKey('9')
    check('ID99可确认并保留频道',page.confirmWireless() and command()=={'op':'wireless','channel':32,'id':99})
    previous=native.property('command');page.openWireless('channel');page.wirelessKey('1');page.requestBack()
    check('取消键盘不发送草稿',native.property('command')==previous and page.property('screen')=='groups')
    native.setProperty('errorText','请开启功率更新以同步分组开关');QTest.qWait(10)
    check('拒绝原因在页面可见且不挤占五行',page.findChild(QObject,'FlashError').property('visible') and page.findChild(QObject,'FlashError').property('text')==native.property('errorText') and page.findChild(QObject,'FlashGroupList').property('height')==290)
    native.setProperty('errorText','');page.openWireless('id');page.wirelessKey('9');page.wirelessKey('9');QTest.qWait(20)
    view.grabWindow().save(str(OUT/'wireless-keypad-preview.png'))
    page.requestBack()
    main=(OUT/'qml/main.qml').read_text(encoding='utf-8')
    check('只替换一次原厂曝光调用且续行原样',main.count(EXPOSURE)==1 and main.count('formalExposureGate.begin(liveviewAfterExposure)')==1)
    check('两处松开都有取消',main.count('formalExposureGate.cancel()')>=4)
    check('QML无阻塞等待',all(x not in main for x in ('waitForFinished','sleep(','while (')))
    check('保留v10橙色',(OUT/'qml/controlscreen/FlashStyle.qml').read_text(encoding='utf-8')==(HERE/'ui/formal/FlashStyle.qml').read_text(encoding='utf-8'))
    native_source=(HERE/'native/formal_runtime.cpp').read_text(encoding='utf-8')
    components=manifest['targetRuntimeComponentCompileChecks']
    check('全部安装验收组件存在且编译检查绑定固定资源',len(components)==3 and all(
        (OUT/'qml'/url.removeprefix('qrc:/')).is_file() and ('QStringLiteral("'+url+'")') in native_source
        for url in components))
    check('动态组件失败或未就绪不得写成功标记',all(
        text in native_source for text in ['flashPage.isError() || exposureGate.isError() || controlPage.isError()',
        '!flashPage.isReady() || !exposureGate.isReady() || !controlPage.isReady()',
        'report("formal-qml-component-failed")','report("formal-qml-component-unavailable")',
        'else report("formal-ui-loaded-default-off")']) and '.create(' not in native_source)
    fatal=[w for w in warnings if not any(text in w for text in ('deprecated','Parameter "','font family','Unable to assign [undefined]'))]
    check('QML无加载或运行错误: '+str(fatal),not fatal)
    source_hashes=dict(manifest['sources'])
    source_hashes[str(Path(__file__).resolve().relative_to(HERE)).replace('\\','/')]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report={'checks':len(checks),'passed':checks,'qtVersion':qVersion(),'targetQt55RuntimeTested':False,
            'nativeAdapter':'explicit-QML-test-double','hardwareRequests':0,'radioRequests':0,'rccSha256':manifest['rccSha256'],
            'warnings':warnings,'sourceHashes':source_hashes}
    (OUT/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    view.close();print(json.dumps({'passed':len(checks),'hardwareRequests':0,'radioRequests':0},ensure_ascii=False))


if __name__=='__main__': run()
