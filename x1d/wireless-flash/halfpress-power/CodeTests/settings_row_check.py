from pathlib import Path
import sys,os,json
HERE=Path(__file__).resolve().parent.parent;ROOT=HERE.parents[2]
sys.path[:0]=[str(ROOT/'x1d/patch-distribution'),str(ROOT/'x1d/wireless-flash/build/ui-test-python')]
os.environ['QT_QPA_PLATFORM']='offscreen'
from build_viewfinder_modes import read_rcc
from PySide6.QtCore import QUrl,QPoint,Qt
from PySide6.QtGui import QGuiApplication,QFontDatabase
from PySide6.QtQml import QQmlPropertyMap
from PySide6.QtQuick import QQuickView
from PySide6.QtTest import QTest
r=read_rcc((HERE/'build/gui/flash-ui.rcc').read_bytes())
p=r['/controlscreen/FlashPage.qml'];start=p.index('            Item {\n                objectName:"HalfPressPowerSetting"')
end=p.index('            Repeater {model:[224,328,512];',start)
row=p[start:end].replace('y:616','y:0')
out=HERE/'build/settings-row-test';out.mkdir(parents=True,exist_ok=True)
for name in ['FlashText.qml','FlashStyle.qml','SettingsToggle.qml']:
 (out/name).write_text(r['/controlscreen/'+name],encoding='utf8')
(out/'Harness.qml').write_text('import QtQuick 2.5\nRectangle {id:page;width:608;height:110;color:"black";property string fontName:"Microsoft YaHei"\n'+row+'\n}',encoding='utf8')
app=QGuiApplication([])
assert QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')>=0
state=QQmlPropertyMap();state.insert('enabled',False);state.insert('error','')
view=QQuickView();view.rootContext().setContextProperty('_hblHalfPress',state)
view.setSource(QUrl.fromLocalFile(str(out/'Harness.qml')))
assert view.status()==QQuickView.Ready,[x.toString() for x in view.errors()]
view.show();QTest.qWait(40)
for position in [QPoint(560,40),QPoint(160,40)]:
 before=state.value('enabled');QTest.mouseClick(view,Qt.LeftButton,Qt.NoModifier,position);QTest.qWait(20)
 assert state.value('enabled') is not before
view.grabWindow().save(str(out/'preview.png'))
print(json.dumps({'passed':True,'actualComponents':True,'switchAndLabelClickable':True,'hardwareRequests':0}))
