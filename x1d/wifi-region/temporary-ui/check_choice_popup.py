"""Own selector input, scrolling and commit contracts with a synthetic Settings service."""
from pathlib import Path
import os,sys
P=Path(__file__).resolve().parent
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['QT_QUICK_BACKEND']='software'
sys.path.insert(0,str(P.parents[1]/'wireless-flash/build/ui-test-python'))
from PySide6.QtCore import QObject,Slot,QUrl,QPoint,Qt,QResource
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlPropertyMap
from PySide6.QtQuick import QQuickView
from PySide6.QtTest import QTest
app=QGuiApplication([])
assert QResource.registerResource(str(P/'build/flash-ui.rcc'))
class SettingsMock(QObject):
    def __init__(self):super().__init__();self.saved=[]
    @Slot(str,result='QVariantList')
    def getVariableListModel(self,name):return [str(i) for i in range(12)]
    @Slot(str,'QVariant',result=str)
    def getUntranslatedDisplayValue(self,name,value):return str(value)
    @Slot(str,str,result=str)
    def stringTranslated(self,name,value):return value
    @Slot('QVariant',str,str)
    def setSettingValue(self,proxy,name,value):self.saved.append((name,value))
settings=SettingsMock();proxy=QQmlPropertyMap();proxy.insert('test','5')
folder=P/'build/choice-popup-test';folder.mkdir(exist_ok=True)
source=(P/'SettingsChoicePopup.qml').read_text(encoding='utf-8').replace('import com.hasselblad.settings 1.0','')
source=source.replace('qrc:///scripts/Keys.js',QUrl.fromLocalFile(str(P.parents[1]/'candidates/replay-page-resident/build/original-page/scripts/Keys.js')).toString())
(folder/'SettingsChoicePopup.qml').write_text(source,encoding='utf-8')
(folder/'Test.qml').write_text('''import QtQuick 2.5
SettingsChoicePopup {width:640;height:480;property string savedStep:""
function saveViewfinder(text){savedStep=text}
}''',encoding='utf-8')
view=QQuickView();view.rootContext().setContextProperty('Settings',settings)
constants=QQmlPropertyMap()
for k,val in dict(popupFadeoutColor='black',fadeOutOpacity=.6,fadeOutDuration=150,popupBackgroundColor='black',numberOfItemsVisibleInList=5,highlightColor='orange',listViewSizeIncreaseFactor=.2,listSelectorYOffsetUnicode=0,listSelectorYOffsetAscii=0,highlightItemColor='white',itemColor='white',menuItemFontName='Arial',popoverListViewShadingStartColor='black',popupBorderColor='gray').items():constants.insert(k,val)
view.rootContext().setContextProperty('constants',constants)
view.setSource(QUrl.fromLocalFile(str(folder/'Test.qml')))
assert view.status()==QQuickView.Ready,[e.toString() for e in view.errors()]
view.show();root=view.rootObject()
root.open(root,proxy,'test');QTest.qWait(250)
listing=root.findChild(QObject,'OwnChoiceList')
assert listing.property('currentIndex')==5
root.close();assert settings.saved==[], 'cancel must not commit'
root.open(root,proxy,'test');QTest.qWait(200)
QTest.mouseClick(view,Qt.LeftButton,Qt.NoModifier,QPoint(430,240));QTest.qWait(150)
assert settings.saved==[('test','5')] and not root.property('visible')
root.open(root,proxy,'test');QTest.qWait(200)
QTest.mousePress(view,Qt.LeftButton,Qt.NoModifier,QPoint(430,270))
for y in range(260,130,-10):QTest.mouseMove(view,QPoint(430,y),20)
QTest.mouseRelease(view,Qt.LeftButton,Qt.NoModifier,QPoint(430,130));QTest.qWait(600)
assert len(settings.saved)==1 and root.property('visible'),'scroll must not commit'
assert listing.property('currentIndex')>5,'scroll follows movement'
root.setSelected();assert len(settings.saved)==2
root.openViewfinder(root,1);QTest.qWait(200);root.setSelected()
assert root.property('savedStep')=='电子取景器'
print('PASS: own selector, current value, cancel, click, scroll and special-choice dispatch')
body=QQmlPropertyMap();body.insert('MENU',1);body.insert('MAIN',0);body.insert('currentState',0)
wrapper=(P/'OwnParameterSelector.qml').read_text(encoding='utf-8').replace('import com.hasselblad.bodysync 1.0','').replace('import "qrc:/settings/components"','import "."')
(folder/'OwnParameterSelector.qml').write_text(wrapper,encoding='utf-8')
(folder/'Parameter.qml').write_text('''import QtQuick 2.5
Item {width:640;height:480
OwnParameterSelector {objectName:"ParameterChooser";model:["100","200","400","800"];currentlySelectedValue:"400";isToLeft:false;popupAnchor.leftMargin:320}
}''')
constants.insert('outerBoxRadius',8)
other=QQuickView();other.rootContext().setContextProperty('constants',constants);other.rootContext().setContextProperty('BodySync',body)
other.setSource(QUrl.fromLocalFile(str(folder/'Parameter.qml')))
assert other.status()==QQuickView.Ready,[e.toString() for e in other.errors()]
other.show();QTest.qWait(200)
param=other.rootObject().findChild(QObject,'ParameterChooser');values=[];param.selectedValueChanged.connect(values.append)
assert param.findChild(QObject,'OwnChoiceList').property('currentIndex')==2
assert body.value('currentState')==1
param.setSelected();assert values==['400'] and body.value('currentState')==0
print('PASS parameter selector: initial value, commit signal, menu input state restored')
