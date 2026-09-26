"""从候选提取实际提示控件，验证显示期间触摸与焦点仍归参数区。"""
from pathlib import Path
import os,sys,json
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['QSG_RHI_BACKEND']='software'
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
sys.path.insert(0,str(ROOT/'x1d/wireless-flash/build/ui-test-python'))
from PySide6.QtCore import QUrl,QPoint,Qt,QObject,QMetaObject,Q_ARG
from PySide6.QtGui import QGuiApplication,QFontDatabase,QFont
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

source=(HERE.parent/'qml/common/TouchWindow.qml').read_text(encoding='utf-8')
fragment=source[source.index('    function showEVFOnlyHint('):source.index('    function setTextTimer(')]
icon=ROOT/'x1d/candidates/ui-resident/revisions/full-pages-r2/build/host/r2-diagnostic/qml/icons/infoDialogIcon.png'
assert icon.is_file()
fragment=fragment.replace('qrc:/icons/infoDialogIcon.png',icon.as_uri())
qml='''import QtQuick 2.5
import QtQuick.Window 2.2
Window {
    width:640; height:480; visible:true; color:"#151515"
    property int presses:0
    QtObject { id:constants; property color menuBackgroundColor:"black"; property color hblOrange:"#de4200"; property color cameraViewNormalTextColor:"white" }
    Item { id:parameters; objectName:"parameters"; anchors.fill:parent; focus:true
        Text { anchors.top:parent.top; anchors.horizontalCenter:parent.horizontalCenter; color:"white"; font.pixelSize:32; text:"1/125     F/8     ISO 100" }
        MouseArea { anchors.fill:parent; onClicked:presses++ }
    }
    Component.onCompleted: { parameters.forceActiveFocus(); showEVFOnlyHint("实时取景仅用于电子取景器") }
'''+fragment+'\n}'
app=QGuiApplication([])
font_id=QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
assert font_id>=0
app.setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0]))
engine=QQmlApplicationEngine()
engine.loadData(qml.encode(),QUrl('file:///evf-hint-check.qml'))
assert engine.rootObjects()
window=engine.rootObjects()[0];QTest.qWait(100)
hint=window.findChild(QObject,'EVFOnlyCenterHint');parameters=window.findChild(QObject,'parameters')
assert hint.property('visible') and hint.property('y')==(480-hint.property('height'))/2
hint_text=window.findChild(QObject,'EVFOnlyHintText')
hint_icon=window.findChild(QObject,'EVFOnlyHintIcon')
assert hint_text.property('lineCount')==2
assert hint_icon.property('width')==40 and hint_icon.property('x')==20
assert hint_text.property('x')==76 and hint_text.property('y')==16
assert hint_text.property('width')+hint_text.property('x')==hint.property('width')-20
assert hint.property('width')<=window.width()-24
assert parameters.property('activeFocus')
QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,QPoint(320,14))
QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,QPoint(320,240))
assert window.property('presses')==2 and parameters.property('activeFocus')
out=HERE/'evf-hint-output';out.mkdir(exist_ok=True)
assert window.grabWindow().save(str(out/'preview.png'))
QTest.qWait(1000);assert hint.property('visible')
QTest.qWait(1050);assert not hint.property('visible')
proof={'passed':True,'placement':'center','lines':2,'hintHeight':hint.property('height'),'fontPixels':24,'iconPixels':40,'horizontalPadding':20,'verticalPadding':16,'iconTextGap':16,'borderPixels':2,'durationMs':2000,'touchPassThrough':True,'focusPreserved':True,'autoHides':True,'hardwareRequests':0,'targetValidated':False}
(out/'validation.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof))
window.close();engine.deleteLater();app.processEvents()
