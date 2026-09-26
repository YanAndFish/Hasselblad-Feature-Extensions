"""离线 Qt Quick 手势与按钮测试；相机对象和无线发送均为显式替身。"""
import json
import hashlib
import os
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]
assert Path.cwd().resolve()==ROOT
sys.path.insert(0,str(HERE/'build/ui-test-python'))
sys.path.insert(0,str(HERE/'research'))
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['QT_QUICK_BACKEND']='software'
os.environ['PYTHONDONTWRITEBYTECODE']='1'
from PySide6.QtCore import QUrl,Qt,QPoint,QPointF,QObject,qVersion
from PySide6.QtGui import QGuiApplication,QFontDatabase,QFont
from PySide6.QtQuick import QQuickView
from PySide6.QtQml import QQmlPropertyMap
from PySide6.QtTest import QTest
from prepare_mechanical_ui import SWIPE

MOCK='''
import QtQuick 2.5
Item {
    id: mainRoot
    width: 640; height: 480
    QtObject {
        id: hblNative
        objectName: "MockNative"
        property bool enabled: true
        property int source: 3
        property int delayUs: 0
        property int powerIndex: 10
        property int progressThreshold: 0
        property bool radioBusy: false
        property bool radioReady: true
        property string status: "已就绪；引闪保持开启"
        property int sentRequests: 7
        property string command: ""
        property int configs: 0
        property int tests: 0
        onCommandChanged: {
            var fields=command.split(" ")
            if (fields[0]==="configure") {
                enabled=fields[1]==="1"; source=Number(fields[2]); delayUs=Number(fields[3]); configs++
            } else if (fields[0]==="test") tests++
            else if (fields[0]==="power") powerIndex=Number(fields[1])
        }
    }
    MouseArea {
        id: outerSwipe
        anchors.fill: parent
        enabled: !scope.preventSwipe
        drag.filterChildren: true
        drag.target: scope
        drag.axis: Drag.YAxis
        drag.minimumY: -scope.height
        drag.maximumY: 0
        drag.threshold: constants.dragThreshold
    Item {
        id: scope
        width: parent.width; height: parent.height
        clip: true
        property bool popupOpen: false
        property bool preventSwipe: popupOpen || Camera.inSession || hblRfSwipe.secondPage || hblRfSwipe.drag.active
        Rectangle {
            id: root
            objectName: "MockControlScreen"
            parent: hblRfTrack
            anchors.fill: parent
            color: "black"
            property int clicks: 0
            Text { anchors.centerIn: parent; text: "1/125     f/4     ISO 100"; color: "white"; font.pixelSize: 32 }
            MouseArea { anchors.fill: parent; onClicked: root.clicks++ }
            Text { id: evSetting; x: 20; y: 300; width: 180; height: 60; text: "EV 12.0"; color: "white"; font.pixelSize: 32 }
            Item {
                id: exposureAdjustSetting
                x: 620; y: 360
                Row {
                    id: flashAdjustRow
                    visible: false
                    anchors.right: parent.right; anchors.bottom: parent.bottom
                    spacing: 9
                    Text { text: "0.0  ⚡"; width: 170; height: 60; color: "white"; font.pixelSize: 40 }
                }
            }
        }
        @SWIPE@
    }
    }
    @MAIN@
}
'''

def run():
    app=QGuiApplication([])
    assert QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')>=0
    app.setFont(QFont('Microsoft YaHei'))
    view=QQuickView()
    camera=QQmlPropertyMap(); camera.insert('inSession',False)
    constants=QQmlPropertyMap(); constants.insert('dragThreshold',18)
    view.rootContext().setContextProperty('Camera',camera)
    view.rootContext().setContextProperty('constants',constants)
    warnings=[]
    view.engine().warnings.connect(lambda values:warnings.extend(str(v.toString()) for v in values))
    out=HERE/'build/mechanical-ui-test'; out.mkdir(exist_ok=True)
    (out/'MechanicalFlashPage.qml').write_bytes((HERE/'ui/MechanicalFlashPage.qml').read_bytes())
    main=(HERE/'ui/mechanical_main_additions.qml.inc').read_text(encoding='utf-8')
    (out/'Harness.qml').write_text(MOCK.replace('@SWIPE@',SWIPE).replace('@MAIN@',main),encoding='utf-8')
    view.setSource(QUrl.fromLocalFile(str(out/'Harness.qml')))
    assert view.status()==QQuickView.Ready, [e.toString() for e in view.errors()]
    view.resize(640,480); view.show(); QTest.qWait(150)
    root=view.rootObject()
    native=root.findChild(QObject,'MockNative')
    track=root.findChild(QObject,'MechanicalFlashTrack')
    control=root.findChild(QObject,'MockControlScreen')
    entry=root.findChild(QObject,'MechanicalFlashEntry')
    def drag(start,end):
        QTest.mousePress(view,Qt.LeftButton,Qt.NoModifier,QPoint(*start))
        for i in range(1,21):
            QTest.mouseMove(view,QPoint(round(start[0]+(end[0]-start[0])*i/20),round(start[1]+(end[1]-start[1])*i/20)),10)
        QTest.mouseRelease(view,Qt.LeftButton,Qt.NoModifier,QPoint(*end))
        QTest.qWait(250)
    def click(x,y):
        QTest.mouseClick(view,Qt.LeftButton,Qt.NoModifier,QPoint(x,y)); QTest.qWait(20)
    click(300,240); assert control.property('clicks')==1
    drag((260,240),(400,240))
    assert track.property('x')==640, track.property('x')
    assert control.property('clicks')==1, 'swipe must cancel parameter click'
    assert view.grabWindow().save(str(out/'second-page.png'))
    for source in range(7):
        click(16+(source%4)*154+73,118+(source//4)*54+24)
        assert native.property('source')==source, (source,native.property('source'))
        assert native.property('enabled'), 'source change must preserve enabled'
    click(558,245)
    assert native.property('delayUs')==10 and native.property('enabled')
    click(243,142)  # B delay is still 0
    assert native.property('source')==1 and native.property('delayUs')==0
    click(398,196)  # Return-to-idle delay is independently retained
    assert native.property('source')==6 and native.property('delayUs')==10
    before=native.property('configs')
    drag((400,340),(260,340))
    assert track.property('x')==0
    assert native.property('configs')==before and native.property('tests')==0
    assert native.property('enabled')
    # 小于翻页门槛的轻微移动留在原页。
    drag((260,240),(300,240)); assert track.property('x')==0
    # 拍摄会话不会屏蔽纯界面翻页；按钮也可直接打开。
    camera.insert('inSession',True)
    position=entry.mapToScene(QPointF(entry.width()/2,entry.height()/2))
    click(round(position.x()),round(position.y())); QTest.qWait(250); assert track.property('x')==640, (position,entry.isVisible(),entry.isEnabled(),entry.parentItem(),track.property('x'),control.property('clicks'))
    click(80,28); QTest.qWait(250); assert track.property('x')==0
    drag((260,240),(400,240)); assert track.property('x')==640
    click(80,28); QTest.qWait(250); assert track.property('x')==0
    assert view.grabWindow().save(str(out/'first-page-entry.png'))
    camera.insert('inSession',False)
    drag((60,240),(580,240)); assert track.property('x')==640
    click(80,28); QTest.qWait(250); assert track.property('x')==0
    assert native.property('enabled') and native.property('tests')==0
    assert not warnings,warnings
    report={'passed':True,'hostQt':qVersion(),
            'targetQt55StillRequired':True,'sources':7,'swipeRightLeft':True,'shortSwipe140px':True,'nestedFactorySwipe':True,'directEntryDuringSession':True,'sourceDelayKeepEnabled':True,
            'delayStepUs':10,'perSourceDelay':True,'gestureDoesNotClick':True,'hardwareRequests':0}
    report['sourceHashes']={str(p.relative_to(HERE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (
        Path(__file__),HERE/'ui/MechanicalFlashPage.qml',HERE/'ui/mechanical_main_additions.qml.inc',HERE/'research/prepare_mechanical_ui.py')}
    (out/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__':run()
