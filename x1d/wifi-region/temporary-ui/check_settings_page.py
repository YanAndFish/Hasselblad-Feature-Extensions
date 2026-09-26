import os,sys
from pathlib import Path
P=Path(__file__).resolve().parent
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['QT_QUICK_BACKEND']='software'
sys.path.insert(0,str(P.parents[1]/'wireless-flash/build/ui-test-python'))
from PySide6.QtCore import QUrl,Qt,QPoint,QObject
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickView
from PySide6.QtQml import QQmlExpression
from PySide6.QtTest import QTest
from PySide6.QtCore import QResource
assert QResource.registerResource(str(P/'build/flash-ui.rcc'))
app=QGuiApplication([]);v=QQuickView()
v.setSource(QUrl.fromLocalFile(str(P/'SettingsPage.qml')))
assert v.status()==QQuickView.Ready,[e.toString() for e in v.errors()]
v.setResizeMode(QQuickView.SizeRootObjectToView);v.resize(640,480);v.show();p=v.rootObject()
e=QQmlExpression(v.rootContext(),p,"rows=[{kind:'toggle',label:'Test',value:false},{kind:'text',label:'Read only'}]")
e.evaluate();QTest.qWait(150)
events=[];p.toggleRequested.connect(lambda i,b:events.append((i,b)))
QTest.mouseClick(v,Qt.LeftButton,Qt.NoModifier,QPoint(550,110));QTest.qWait(50)
assert events==[(0,True)],events
back=[];p.backRequested.connect(lambda:back.append(True))
QTest.mousePress(v,Qt.LeftButton,Qt.NoModifier,QPoint(80,300))
for x in range(100,301,20):QTest.mouseMove(v,QPoint(x,300),15)
QTest.mouseRelease(v,Qt.LeftButton,Qt.NoModifier,QPoint(300,300));QTest.qWait(300)
assert back,'right swipe did not return'
p.setProperty('dragOffset',0)
QQmlExpression(v.rootContext(),p,"rows=[{kind:'slider',label:'Brightness',numberValue:2,minimum:0,maximum:10,step:1}]").evaluate()
QTest.qWait(100)
values=[];p.valueRequested.connect(lambda i,value:values.append(value));back.clear()
QTest.mousePress(v,Qt.LeftButton,Qt.NoModifier,QPoint(100,183))
for x in range(115,586,15):QTest.mouseMove(v,QPoint(x,183),15)
QTest.mouseRelease(v,Qt.LeftButton,Qt.NoModifier,QPoint(585,183));QTest.qWait(100)
assert len(values)>3 and values[-1]>values[0],values
assert not back and abs(p.property('dragOffset'))<1,'slider must not return page'
def visualItems(item):
    yield item
    for child in item.childItems():yield from visualItems(child)
knob=next(item for item in visualItems(p) if item.objectName()=='SettingSliderKnob')
assert knob.property('x')>500,'late readback must not restore old value on release'
QTest.qWait(250)
assert knob.property('x')>500,'hold preview while backend readback is pending'
QQmlExpression(v.rootContext(),p,"rows=Array.from({length:15},function(_,i){return {kind:'choice',label:'Row '+i,valueText:'Old'}})").evaluate()
QTest.qWait(100)
listing=p.findChild(QObject,'CustomSettingsList');listing.setProperty('contentY',600)
QTest.qWait(100);oldY=listing.property('contentY')
QQmlExpression(v.rootContext(),p,"var copy=rows.slice();copy[9]={kind:'choice',label:'Row 9',valueText:'New'};rows=copy").evaluate()
QTest.qWait(300)
assert abs(listing.property('contentY')-oldY)<1,'changing a lower-row value must preserve scroll offset'
assert any(item.property('text')=='New' for item in visualItems(p)),'updated value must render without replacing the list'
print('PASS independent page: toggle, swipe, slider and retained scroll after value update')
