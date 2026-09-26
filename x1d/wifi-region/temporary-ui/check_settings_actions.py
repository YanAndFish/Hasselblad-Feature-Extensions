"""Offline action routing: mock all device APIs; never execute real actions."""
exec((__import__('pathlib').Path(__file__).parent/'check_settings_page.py').read_text().split('app=QGuiApplication')[0])
from PySide6.QtCore import QObject,Slot
from PySide6.QtQml import QQmlPropertyMap
import re
app=QGuiApplication([])
out=P/'build/actions-test';out.mkdir(exist_ok=True)
source=(P/'NativeSettingsActions.qml').read_text(encoding='utf-8')
source='\n'.join(l for l in source.splitlines() if not l.startswith('import com.hasselblad') and l!='import "qrc:///components"')
source=re.sub(r'qrc:///[^"\n]+\.qml','ActionDialog.qml',source)
(out/'NativeSettingsActions.qml').write_text(source,encoding='utf-8')
(out/'ActionDialog.qml').write_text('''import QtQuick 2.5
Item {property bool largeHeaderText:false; property string headerText;property string infoText;property string rightText;property string headingText;property int showtime;property string heading;property string centerText;property string icon;property string bottomText;property int cardToFormat;property string subText;signal rightSelected();signal backRequested()}
''')
(out/'GenericInform.qml').write_text('''import QtQuick 2.5
Item {property string title;property string info;property string buttonText;property int timeVisible}
''')
class Device(QObject):
    def __init__(self):super().__init__();self.calls=[]
    @Slot()
    def upgradeNodes(self):self.calls.append('upgrade')
    @Slot(str)
    def saveDbTemplateFromCurrent(self,value):self.calls.append('save')
device=Device();v=QQuickView()
constants=QQmlPropertyMap();constants.insert('dragThreshold',20);constants.insert('swipeLengthDividor',5)
for k,o in [('Upgrader',device),('configstore',device),('farm',device),('constants',constants)]:v.rootContext().setContextProperty(k,o)
v.setSource(QUrl.fromLocalFile(str(out/'NativeSettingsActions.qml')))
assert v.status()==QQuickView.Ready,[e.toString() for e in v.errors()]
v.setResizeMode(QQuickView.SizeRootObjectToView);v.resize(640,480);v.show();root=v.rootObject()
QTest.qWait(100);assert not device.calls and not root.property('busy')
for name in ['defaultSettings','resetFileCounter','fwUpdateRetry','saveCustomMode1','License']:
    expression=QQmlExpression(v.rootContext(),root,"run({name:'"+name+"',text1:'Test'})")
    expression.evaluate();assert not expression.hasError(),expression.error().toString()
    QTest.qWait(100)
    assert root.property('busy'),name
    assert not device.calls,'opening or cancelling must not commit an operation'
    root.close();QTest.qWait(30)
print('PASS actions: create, confirmation routes, cancel without device writes')
