"""正式引闪页离线 Qt Quick 交互/资源测试；显式替身，无相机或无线对象。"""
from pathlib import Path
import hashlib
import json
import os
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
assert Path.cwd().resolve() == ROOT
sys.path.insert(0, str(HERE/'build/ui-test-python'))
sys.path.insert(0, str(HERE/'research'))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QT_QUICK_BACKEND'] = 'software'
from PySide6.QtCore import QUrl, Qt, QPoint, QObject, qVersion
from PySide6.QtGui import QGuiApplication, QFontDatabase, QFont
from PySide6.QtQuick import QQuickView
from PySide6.QtTest import QTest
from prepare_formal_flash_ui import build, OUT

HARNESS = '''
import QtQuick 2.5
Item {
    id: harness
    width: 640; height: 480
    property int enableRequests: 0
    property int testRequests: 0
    property int draftRequests: 0
    property int lampDraftRequests: 0
    property int powerUpdateRequests: 0
    property int syncRequests: 0
    property int optionChanges: 0
    QtObject { id: constants; property int dragThreshold: 20 }
    MouseArea {
        anchors.fill: parent
        enabled: !scope.preventSwipe
        drag.target: scope
        drag.axis: Drag.YAxis
        drag.minimumY: -scope.height
        drag.maximumY: 0
        drag.filterChildren: true
        drag.threshold: 20
        Item {
            id: scope; width: 640; height: 480; clip: true
            property bool popupOpen: false
            property bool preventSwipe: popupOpen || formalFlashSwipe.secondPage || formalFlashSwipe.drag.active
            MouseArea { anchors.fill: parent }
            Rectangle {
                id: root; parent: formalFlashTrack
                objectName: "ControlStub"; width: 640; height: 480; color: "black"
                property int clicks: 0
                Text { anchors.centerIn: parent; text: "1/125     f/4     ISO 100"; color: "white"; font.pixelSize: 32 }
                Text { x: 60; y: 350; width: 180; height: 40; text: "EV 12.2"; color: "white"; font.pixelSize: 24 }
                MouseArea { x: 240; y: 200; width: 160; height: 80; onClicked: root.clicks++ }
            }
            @SWIPE@
        }
    }
    Connections {
        target: formalFlashPage
        function onEnabledRequested(value) { harness.enableRequests++ }
        function onTestRequested() { harness.testRequests++ }
        function onGroupDraftChanged(group, active, tenthStops) { harness.draftRequests++ }
        function onModelingLampDraftChanged(group, value) { harness.lampDraftRequests++ }
        function onPowerUpdateRequested(group, active, tenthStops) { harness.powerUpdateRequests++ }
        function onFlashSyncRequested() { harness.syncRequests++ }
        function onDeliveryOptionsChanged(powerUpdates, flashSync) { harness.optionChanges++ }
    }
}
'''


def run():
    manifest = build()
    app = QGuiApplication([])
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
    app.setFont(QFont('Microsoft YaHei'))
    testdir = OUT/'preview'
    testdir.mkdir(exist_ok=True)
    qml_dir = OUT/'qml/controlscreen'
    source = HARNESS.replace('@SWIPE@', (HERE/'ui/formal/ControlSwipe.qml.inc').read_text(encoding='utf-8'))
    source = source.replace('            FlashPage {', '            FlashPage {\n                iconBase: "@ICONS@/"\n                fontName: "Arial"')
    source = source.replace('@ICONS@', (OUT/'baseline-assets').as_uri())
    # Harness 与生产 QML 位于同一候选目录，生产资源和旧安装包均不改写。
    (qml_dir/'PreviewHarness.qml').write_text(source, encoding='utf-8')
    warnings = []
    view = QQuickView()
    view.engine().warnings.connect(lambda values: warnings.extend(v.toString() for v in values))
    view.setSource(QUrl.fromLocalFile(str(qml_dir/'PreviewHarness.qml')))
    assert view.status() == QQuickView.Ready, [e.toString() for e in view.errors()]
    view.resize(640, 480); view.show(); QTest.qWait(120)
    root = view.rootObject()
    page = root.findChild(QObject, 'FormalFlashPage')
    track = root.findChild(QObject, 'FormalFlashTrack')
    control = root.findChild(QObject, 'ControlStub')
    checks = []

    def check(label, condition):
        assert condition, label
        checks.append(label)

    def click(x, y):
        QTest.mouseClick(view, Qt.LeftButton, Qt.NoModifier, QPoint(x, y)); QTest.qWait(30)

    def drag(start, end):
        QTest.mousePress(view, Qt.LeftButton, Qt.NoModifier, QPoint(*start))
        for i in range(1, 21):
            QTest.mouseMove(view, QPoint(round(start[0]+(end[0]-start[0])*i/20), round(start[1]+(end[1]-start[1])*i/20)), 7)
        QTest.mouseRelease(view, Qt.LeftButton, Qt.NoModifier, QPoint(*end)); QTest.qWait(220)

    for label,start,end in [('参数页空白',(130,400),(20,400)),('只读EV文字',(200,370),(60,370)),('参数按钮',(320,240),(130,240))]:
        drag(start,end)
        check(label+'均可左滑进入且不误点',track.property('x')==-640 and control.property('clicks')==0)
        page.requestBack();QTest.qWait(220)
    click(300, 240)
    check('参数页普通点击保留', control.property('clicks') == 1)
    drag((450,240),(250,240))
    check('左滑进入', track.property('x') == -640)
    check('翻页取消原参数点击', control.property('clicks') == 1)
    check('打开不启用不试闪', root.property('enableRequests') == root.property('testRequests') == 0)
    check('两个发送选项默认开且总功能默认关', page.property('sendPowerUpdates') and page.property('sendFlashSync') and not page.property('masterEnabled'))
    check('默认使用三分之一档',page.property('thirdStopSteps') and page.property('adjustmentStepText')=='0.3 EV')
    page.setAdjustmentStep(False,False)
    click(535, 36); click(370, 432)
    check('未接适配层时拒绝启用和试闪', root.property('enableRequests') == root.property('testRequests') == 0)
    # 场景数据仅用于设计预览，均为主机显式草稿，不是灯端读回值。
    for i, active, power in [(0,True,40),(1,True,33),(2,True,20),(3,True,10),(4,False,40)]:
        check('预览草稿组'+str(i), page.setGroup(i,active,power,False))
    QTest.qWait(100)
    check('预览数据装入不算硬件状态', not page.property('connected') and not page.property('hasDraftChanges'))
    assert view.grabWindow().save(str(testdir/'groups.png'))
    assert view.grabWindow().save(str(testdir/'groups-v10.png'))
    check('组调节初始显示零', page.property('groupAdjustmentTenths')==0)
    click(270,432); click(270,432); click(270,432)
    check('统一加三步中间显示累计0.3', page.property('groupAdjustmentTenths')==3 and page.groupAdjustmentText()=='+0.3' and page.groupPower(0)==43 and page.groupPower(1)==36)
    assert view.grabWindow().save(str(testdir/'groups-v10-offset.png'))
    click(50,432); click(50,432); click(50,432)
    check('统一减回原值时显示零', page.property('groupAdjustmentTenths')==0 and page.groupPower(0)==40 and page.groupPower(1)==33)
    click(460,115)
    check('主页面单组快加服从十分之一档设置', page.groupPower(0)==41 and page.property('screen')=='groups' and page.groupPower(1)==33)
    click(157,115)
    check('主页面单组快减', page.groupPower(0)==40 and page.property('screen')=='groups')
    drag((191,115),(311,115))
    check('从减号右侧空白开始也可连续滑动',page.groupPower(0)>40 and page.property('screen')=='groups' and track.property('x')==-640)
    page.setGroup(0,True,40,False)
    drag((205,115),(400,115))
    check('功率数字区右滑连续调节且不进入详情或翻页',page.groupPower(0)==80 and page.property('screen')=='groups' and track.property('x')==-640 and not page.property('powerGestureActive'))
    page.setGroup(0,True,40,False)
    drag((400,115),(205,115))
    check('功率数字区左滑连续调节且不翻页',page.groupPower(0)==0 and page.property('screen')=='groups' and track.property('x')==-640)
    page.setGroup(0,True,40,False)
    click(530,115)
    check('行内造型灯只改草稿', root.property('lampDraftRequests')==1 and root.property('testRequests')==0 and page.property('screen')=='groups')
    click(468,432)
    check('选择分组入口', page.property('screen')=='selection')
    click(242,155)
    check('可以隐藏任意中间组', page.property('visibleGroupCount')==4 and not page.groupIsVisible(1) and page.groupPower(1)==33)
    click(242,216); click(388,216)
    check('可选A至F和数字组', page.groupIsVisible(5) and page.groupIsVisible(6) and page.property('visibleGroupCount')==6)
    assert view.grabWindow().save(str(testdir/'selection-v10.png'))
    click(468,432)
    hidden_before=page.groupPower(1)
    click(270,432)
    check('全部快加只影响已选组', all(page.groupPower(i)==v for i,v in [(0,41),(2,21),(3,11),(4,41),(5,41),(6,41)]) and page.groupPower(1)==hidden_before)
    check('统一调整不自动开启关闭组', not page.groupActive(4) and not page.groupActive(5))
    click(50,432)
    check('全部快减保持组间差', page.groupPower(0)==40 and page.groupPower(2)==20 and page.groupPower(3)==10 and page.groupPower(1)==hidden_before)
    page.setGroup(0,True,80,False)
    before_all=[page.groupPower(i) for i in range(16)]
    click(270,432)
    check('任一已选组达到上限时整批及累计值保持', before_all==[page.groupPower(i) for i in range(16)] and page.property('groupAdjustmentTenths')==0)
    page.setGroup(0,True,0,False)
    before_all=[page.groupPower(i) for i in range(16)]
    click(50,432)
    check('任一已选组达到1/256下限时整批及累计值保持', before_all==[page.groupPower(i) for i in range(16)] and page.property('groupAdjustmentTenths')==0)
    page.setGroup(0,True,40,False)
    drag((350,330),(350,170))
    check('多于五组可纵向滚动且不误翻页', page.property('groupScrollY')>0 and track.property('x')==-640)
    # 恢复 A-E 预览选择，以便继续单组交互验证。
    page.toggleVisibleGroup(1); page.toggleVisibleGroup(5); page.toggleVisibleGroup(6)
    click(300, 115)
    check('点组进入功率页', page.property('screen') == 'power' and page.property('selectedGroup') == 0)
    drag((450,190),(250,190))
    check('调功率时不抢翻页手势', track.property('x') == -640 and page.property('screen') == 'power')
    before=root.property('draftRequests')
    click(510, 329)
    check('详情加功率服从统一设置且仅产生草稿', root.property('draftRequests') == before+1 and page.property('hasDraftChanges') and page.property('currentPower')==41)
    click(310, 329); click(510, 329)
    check('详情步长文字不再私自切换设置', not page.property('thirdStopSteps') and root.property('draftRequests') == before+2 and page.property('currentPower')==42)
    assert view.grabWindow().save(str(testdir/'power.png'))
    assert view.grabWindow().save(str(testdir/'power-v10.png'))
    check('非法功率被拒绝', not page.setGroup(0,True,81,True) and not page.setGroup(0,True,-1,True))
    check('非法组被拒绝', not page.setGroup(16,True,10,True))
    page.setGroup(0,True,80,False)
    check('满功率文本边界', page.powerText(80) == '1/1' and page.fractionText(80) == '')
    click(510,329)
    check('超过满功率不会越界', page.property('currentPower')==80)
    click(80,125)
    check('关闭组只产生草稿', root.property('testRequests') == 0 and root.property('enableRequests') == 0)
    click(30,35)
    check('详情返回分组', page.property('screen') == 'groups' and track.property('x') == -640)
    click(540,404)
    check('设置矩形边角也可打开', page.property('screen') == 'settings')
    QTest.qWait(30); assert view.grabWindow().save(str(testdir/'settings.png'))
    assert view.grabWindow().save(str(testdir/'settings-v10-defaults.png'))
    click(40,124)
    check('功率发送整行可切换且不改变同步', not page.property('sendPowerUpdates') and page.property('sendFlashSync'))
    click(605,200)
    check('同步开关可独立关闭', not page.property('sendPowerUpdates') and not page.property('sendFlashSync'))
    click(40,124)
    check('可以仅开启功率发送', page.property('sendPowerUpdates') and not page.property('sendFlashSync'))
    check('离线修改偏好不产生任何发送请求', root.property('powerUpdateRequests')==0 and root.property('syncRequests')==0 and root.property('testRequests')==0)
    click(30,35); drag((220,382),(440,382))
    check('右滑返回参数页', track.property('x') == 0)
    drag((420,240),(375,240))
    check('短滑不会误翻页', track.property('x') == 0)
    drag((450,240),(250,240))
    check('离开再进入保留独立发送偏好', page.property('sendPowerUpdates') and not page.property('sendFlashSync'))
    page.setDeliveryOptions(True,True)
    page.setProperty('connected',True); page.setProperty('canTest',True)
    click(535,36)
    check('主开关等待适配层确认', root.property('enableRequests') == 1 and not page.property('masterEnabled'))
    click(370,432)
    check('总功能未确认开启时两类发送和试闪均拒绝', root.property('testRequests') == 0 and not page.requestPowerUpdate(0) and not page.requestFlashSync())
    page.setProperty('masterEnabled',True)
    # 接口替身核对四种偏好组合，不连接相机、不调用无线库。
    for case, (power_on, sync_on) in enumerate([(True,True),(True,False),(False,True),(False,False)]):
        before_power=root.property('powerUpdateRequests')
        before_sync=root.property('syncRequests')
        before_test=root.property('testRequests')
        page.setDeliveryOptions(power_on,sync_on)
        check('组合'+str(case)+'切换偏好本身不发送', root.property('powerUpdateRequests')==before_power and root.property('syncRequests')==before_sync and root.property('testRequests')==before_test)
        page.setGroup(0,True,40+case,True)
        accepted_sync=page.requestFlashSync()
        click(370,432)
        check('组合'+str(case)+'功率与同步独立门控', root.property('powerUpdateRequests')==before_power+int(power_on) and root.property('syncRequests')==before_sync+int(sync_on) and accepted_sync==sync_on)
        check('组合'+str(case)+'试闪服从同步开关', root.property('testRequests')==before_test+int(sync_on))
    page.setDeliveryOptions(True,True)
    check('非法组不会形成发送请求', not page.requestPowerUpdate(-1) and not page.requestPowerUpdate(16) and not page.requestPowerUpdate(0.5))
    check('非法选项拒绝且保留原值', not page.setDeliveryOptions('on',False) and page.property('sendPowerUpdates') and page.property('sendFlashSync'))
    before_power=root.property('powerUpdateRequests')
    before_sync=root.property('syncRequests')
    before_test=root.property('testRequests')
    for unavailable in ('busy','connected','masterEnabled'):
        page.setProperty(unavailable, unavailable=='busy')
        accepted_power=page.requestPowerUpdate(0)
        accepted_sync=page.requestFlashSync()
        click(370,432)
        check(unavailable+'禁止两类发送及重复试闪', not accepted_power and not accepted_sync and root.property('testRequests')==before_test and root.property('powerUpdateRequests')==before_power and root.property('syncRequests')==before_sync)
        page.setProperty(unavailable, unavailable!='busy')
    page.setProperty('canTest',False)
    check('缺少试闪能力时拒绝显式接口调用', not page.requestTest() and root.property('testRequests')==before_test)
    page.setProperty('canTest',True)
    page.setDeliveryOptions(True,False)
    click(540,404)
    QTest.qWait(30); assert view.grabWindow().save(str(testdir/'settings-v10-power-only.png'))
    check('关闭同步后仍可请求功率且试闪禁用', page.property('powerUpdateAllowed') and not page.property('flashSyncAllowed') and not page.requestTest())
    check('重开选项不补发旧事件', root.property('powerUpdateRequests')==before_power and root.property('syncRequests')==before_sync and root.property('testRequests')==before_test)
    page.setProperty('screen','groups')
    for i in range(16):
        if not page.groupIsVisible(i):page.toggleVisibleGroup(i)
    power_before=[page.groupPower(i) for i in range(16)]
    scrolling=root.findChild(QObject,'FlashGroupList');scrolling.setProperty('contentY',0)
    QTest.mousePress(view,Qt.LeftButton,Qt.NoModifier,QPoint(350,300))
    QTest.mouseMove(view,QPoint(350,268),120);QTest.qWait(150)
    QTest.mouseRelease(view,Qt.LeftButton,Qt.NoModifier,QPoint(350,268));QTest.qWait(200)
    check('慢滚后自动对齐完整行且不改功率',page.property('groupScrollY')==58 and power_before==[page.groupPower(i) for i in range(16)])
    QTest.mousePress(view,Qt.LeftButton,Qt.NoModifier,QPoint(350,320))
    for y in range(310,209,-10):
        QTest.mouseMove(view,QPoint(350,y));QTest.qWait(10)
    QTest.mouseRelease(view,Qt.LeftButton,Qt.NoModifier,QPoint(350,210));QTest.qWait(20)
    check('快滚松手保留惯性',scrolling.property('flicking'))
    QTest.qWait(1300)
    check('惯性停下同样对齐五行窗口',round(page.property('groupScrollY'))%58==0 and scrolling.property('height')==290 and power_before==[page.groupPower(i) for i in range(16)])
    assert not warnings, warnings
    check('无QML资源或运行警告', True)
    report = {
        'passed': True, 'checks': checks, 'hostQt': qVersion(),
        'targetQt55StillRequired': True, 'cameraRequests': 0, 'radioRequests': 0,
        'mockInterfaceTestSignals': root.property('testRequests'),
        'mockPowerUpdateSignals': root.property('powerUpdateRequests'),
        'mockFlashSyncSignals': root.property('syncRequests'),
        'deviceAdapterImplemented': False, 'installed': False,
        'previewValues': 'explicit-host-drafts-not-lamp-readback',
        'previewLatinFont': 'Arial fallback; target uses Helvetica Neue LT Std',
        'rccSha256': manifest['rccSha256'],
        'sourceHashes': {str(p.relative_to(HERE)):hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in [Path(__file__),HERE/'research/prepare_formal_flash_ui.py',*(HERE/'ui/formal').iterdir()] if p.is_file()},
    }
    (OUT/'validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'passed':True,'checks':len(checks),'cameraRequests':0,'radioRequests':0,'installed':False}))


if __name__ == '__main__':
    run()
