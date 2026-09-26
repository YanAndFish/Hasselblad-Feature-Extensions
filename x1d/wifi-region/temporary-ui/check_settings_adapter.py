exec((__import__('pathlib').Path(__file__).parent/'check_settings_page.py').read_text().split('app=QGuiApplication')[0])
from PySide6.QtCore import QObject,Slot
from PySide6.QtQml import QQmlPropertyMap
app=QGuiApplication([])
out=P/'build/settings-adapter-test';out.mkdir(exist_ok=True)
(out/'SettingsPage.qml').write_bytes((P/'SettingsPage.qml').read_bytes())
(out/'SettingsToggle.qml').write_bytes((P/'SettingsToggle.qml').read_bytes())
source=(P/'NativeSettingsPage.qml').read_text()
source='\n'.join(l for l in source.splitlines() if not l.startswith('import com.hasselblad') and l!='import "qrc:///settings/components"')
source=source.replace('qrc:///settings/scripts/MenuItemImporter.js','Items.js')
(out/'NativeSettingsPage.qml').write_text(source)
(out/'Items.js').write_text('function getSettingsList(k){return [{editType:2,name:"testFlag",text1:"Flag",proxy:configstore},{editType:1,name:"testValue",text1:"Value",proxy:configstore}];}')
(out/'ListSelectorSettings.qml').write_text('import QtQuick 2.5\nItem {property alias popupAnchor:panel.anchors;visible:false;Item{id:panel} function open(p,o,n){visible=true} function close(){visible=false} }')
(out/'RadioListSelector.qml').write_bytes((out/'ListSelectorSettings.qml').read_bytes())
(out/'NativeSettingsActions.qml').write_text('import QtQuick 2.5\nItem {property bool busy:false; function close(){} function run(e){busy=true} }')
class Settings(QObject):
    @Slot(str,'QVariant',result=str)
    def getDisplayValue(self,n,v):return str(v)
    @Slot(str,'QVariant',result=str)
    def getUntranslatedDisplayValue(self,n,v):return str(v)
store=QQmlPropertyMap();store.insert('testFlag',False);store.insert('testValue',3)
config=QQmlPropertyMap();config.insert('hideDemoItems',True)
constants=QQmlPropertyMap();constants.insert('dragThreshold',20);constants.insert('swipeLengthDividor',5)
settings=Settings();v=QQuickView()
for k,o in [('configstore',store),('guiconfig',config),('constants',constants),('Settings',settings)]:v.rootContext().setContextProperty(k,o)
v.setSource(QUrl.fromLocalFile(str(out/'NativeSettingsPage.qml')))
assert v.status()==QQuickView.Ready,[e.toString() for e in v.errors()]
v.setResizeMode(QQuickView.SizeRootObjectToView);v.resize(640,480);v.show();QTest.qWait(150)
QTest.mouseClick(v,Qt.LeftButton,Qt.NoModifier,QPoint(540,110));QTest.qWait(50)
assert store.value('testFlag') is True,'adapter toggle write'
QTest.mouseClick(v,Qt.LeftButton,Qt.NoModifier,QPoint(540,200));QTest.qWait(50)
assert any(c.property('visible') for c in v.rootObject().childItems() if 'ListSelector' in c.metaObject().className()),'selector opens'
print('PASS adapter: live rows, toggle proxy write, selector request')
