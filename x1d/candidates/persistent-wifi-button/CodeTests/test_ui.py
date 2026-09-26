"""宿主 Qt 空按钮交互；业务接口为替身，不连接相机。"""
from pathlib import Path
import hashlib, json, os, re, sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'x1d/candidates/ui-resident/CodeTests'))
from test_original_pages import MOCKS, ITEMS, CameraMock
from build import baseline
from PySide6.QtCore import QObject,QUrl,Qt,QPoint,QPointF,Signal,qVersion,QResource,QFile,QIODevice
from PySide6.QtGui import QGuiApplication,QFontDatabase,QFont
from PySide6.QtQml import QQmlPropertyMap
from PySide6.QtQuick import QQuickView
from PySide6.QtTest import QTest

def main():
    assert Path.cwd().resolve()==ROOT
    app=QGuiApplication.instance() or QGuiApplication([])
    fontId=QFontDatabase.addApplicationFont('C:/Windows/Fonts/arial.ttf')
    assert fontId>=0
    app.setFont(QFont(QFontDatabase.applicationFontFamilies(fontId)[0]))
    out=HERE/'build/host';out.mkdir(parents=True,exist_ok=True)
    original=baseline();modified=(HERE/'build/SettingsGeneric.qml').read_text(encoding='utf-8')
    assert QResource.registerResource(str(HERE/'build/button.rcc'))
    f=QFile(':/settings/SettingsGeneric.qml');assert f.open(QIODevice.ReadOnly)
    assert bytes(f.readAll())==modified.encode('utf-8');f.close();del f
    assert QResource.unregisterResource(str(HERE/'build/button.rcc'))
    for name,value in original.items():
        if name=='/settings/SettingsGeneric.qml':value=modified
        value=re.sub(r'^import com\.hasselblad\..*\n','',value,flags=re.M)
        value=re.sub(r'^import QtGraphicalEffects.*\n','',value,flags=re.M)
        value=value.replace('qrc:///',out.as_uri()+'/')
        dest=out/name.lstrip('/');dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(value,encoding='utf-8')
    (out/'settings/components/BoundsEffectGradient.qml').write_text('import QtQuick 2.0\nItem { property color fadeColor; visible:false }',encoding='utf-8')
    items=ITEMS.replace('return [row(SettingType.TEXT,"testValue","Value",configstore)]','return [row(SettingType.TEXT,"testValue","Wi-Fi",configstore),row(SettingType.TEXT,"testValue","Mode",configstore)]')
    (out/'settings/scripts/MenuItemImporter.js').write_text(items,encoding='utf-8')
    harness='''import QtQuick 2.0
import "common"
import "settings"
Item {
    width:640; height:480
    @MOCKS@
    SettingsGeneric { id:page; anchors.fill:parent; upperMenuLabel:"GENERAL"; menuLabel:"Wi-Fi" }
    function openPage(name) { page.populateModel(name) }
}
'''.replace('@MOCKS@',MOCKS)
    (out/'Harness.qml').write_text(harness,encoding='utf-8')
    view=QQuickView();warnings=[];view.engine().warnings.connect(lambda es:warnings.extend(e.toString() for e in es))
    camera=CameraMock();maps=[]
    for n,vals in {'GlobalStateInfo':{'afSselectedIndex':0},'System':{'versionID':'fixture'},'DemoState':{'demoOn':False}}.items():
        m=QQmlPropertyMap();maps.append(m)
        for k,v in vals.items():m.insert(k,v)
        view.rootContext().setContextProperty(n,m)
    for n in ('Camera','Upgrader','Settings'):view.rootContext().setContextProperty(n,camera)
    class LensMock(QObject):lens_familyChanged=Signal()
    lens=LensMock();view.rootContext().setContextProperty('Lens',lens)
    view.setSource(QUrl.fromLocalFile(str(out/'Harness.qml')))
    assert view.status()==QQuickView.Ready,[e.toString() for e in view.errors()]
    view.show();QTest.qWait(100);root=view.rootObject()
    root.openPage('generalSettingsWiFi');QTest.qWait(100)
    button=root.findChild(QObject,'hblPersistentWifiProbeButton');page=root.findChild(QObject,'SettingsGeneric_root')
    assert button and button.property('visible')
    before=camera.writes,camera.upgrades,root.findChild(QObject,'configstore').property('testValue')
    pos=button.mapToScene(QPointF(button.width()/2,button.height()/2)).toPoint()
    QTest.mouseClick(view,Qt.LeftButton,Qt.NoModifier,pos);QTest.qWait(20)
    assert before==(camera.writes,camera.upgrades,root.findChild(QObject,'configstore').property('testValue'))
    assert button.property('visible') and page.property('itemValues')=='generalSettingsWiFi'
    assert view.grabWindow().save(str(out/'wifi-button.png'))
    root.openPage('generalSettingsDisplay');QTest.qWait(50);assert not button.property('visible')
    root.openPage('generalSettingsWiFi');QTest.qWait(50);assert button.property('visible')
    # 原厂字体/图片资源未复制到宿主，相关缺失仅限制视觉，不忽略 QML 类型/属性错误。
    allowed=('Implicitly defined onFoo properties in Connections are deprecated','Cannot open:','Cannot load font')
    unexpected=[w for w in warnings if not any(s in w for s in allowed)]
    assert not unexpected,unexpected
    report={'passed':True,'hostQt':qVersion(),'checks':['RCC roundtrip equals exact patched source','factory SettingsGeneric compiles with explicit business mocks','button visible only for Wi-Fi','click has no mock setting writes or upgrade actions','other page hides button','reenter shows button'],'cameraRequests':0,'targetQt55Validated':False,'qmlSha256':hashlib.sha256(modified.encode()).hexdigest(),'mockAdaptations':['business imports replaced','two text rows fixture','local resource paths','missing original font/image assets']}
    (HERE/'build/ui-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    view.setSource(QUrl());QTest.qWait(20)
    print(json.dumps({'passed':True,'checks':len(report['checks'])}))
if __name__=='__main__':main()
