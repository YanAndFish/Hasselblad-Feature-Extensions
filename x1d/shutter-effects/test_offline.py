"""X1D 动画生命周期、资源及长音频的本地检查；不连接相机。"""
from pathlib import Path
import hashlib
import json
import os
import sys
import wave

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'x1d/wireless-flash/build/ui-test-python'))
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['QT_QUICK_BACKEND']='software'
from PySide6.QtCore import QObject,QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlEngine,QQmlComponent,QQmlPropertyMap
from PySide6.QtQuick import QQuickView
from PySide6.QtTest import QTest

app=QGuiApplication([])
engine=QQmlEngine()
component=QQmlComponent(engine,QUrl.fromLocalFile(str(HERE/'X1dShutterAnimation.qml')))
if component.isError():raise AssertionError([x.toString() for x in component.errors()])
obj=component.create()
if obj is None:raise AssertionError([x.toString() for x in component.errors()])
obj.setProperty('activeSurface',True)
obj.setProperty('effectMode',0)
obj.setProperty('exposing',True)
app.processEvents()
assert not obj.property('showing')
obj.setProperty('exposing',False)
obj.setProperty('effectMode',2)
obj.setProperty('exposing',True)
QTest.qWait(260)
assert obj.property('showing') and obj.property('playCount')==1
assert 0 < obj.property('progress') < 1
obj.setProperty('exposing',False)
app.processEvents()
assert not obj.property('showing')
obj.setProperty('exposing',True)
QTest.qWait(30)
assert obj.property('showing') and obj.property('playCount')==2
obj.setProperty('activeSurface',False)
app.processEvents()
assert not obj.property('showing')
audio=HERE/'audio/ciallo-yaoyao.wav'
with wave.open(str(audio),'rb') as sample:
    duration=sample.getnframes()/sample.getframerate()
    assert 1.0 < duration < 2.0 and sample.getnchannels()==1 and sample.getsampwidth()==2
sys.path.insert(0,str(ROOT/'x1d/patch-distribution'))
from build_viewfinder_modes import read_rcc
resources=read_rcc((HERE/'build/candidate/flash-ui.rcc').read_bytes())
assert all(token in resources['/main.qml'] for token in ['onExposingChanged','_hblShutterEffects.exposing'])
assert '曝光动画与声音' in resources['/settings/NativeSettingsPage.qml']
folder=HERE/'build/candidate/popup-test';folder.mkdir(parents=True,exist_ok=True)
popup=resources['/settings/components/SettingsChoicePopup.qml']
popup=popup.replace('import com.hasselblad.settings 1.0','')
keys=ROOT/'x1d/candidates/replay-page-resident/build/original-page/scripts/Keys.js'
popup=popup.replace('qrc:///scripts/Keys.js',QUrl.fromLocalFile(str(keys)).toString())
(folder/'SettingsChoicePopup.qml').write_text(popup,encoding='utf-8')
(folder/'Test.qml').write_text('import QtQuick 2.5\nSettingsChoicePopup {width:640;height:480}\n',encoding='utf-8')
view=QQuickView()
settings=QQmlPropertyMap();settings.insert('mode',2)
constants=QQmlPropertyMap()
for key,val in dict(popupFadeoutColor='black',fadeOutOpacity=.6,fadeOutDuration=150,
    popupBackgroundColor='black',numberOfItemsVisibleInList=5,highlightColor='orange',
    listViewSizeIncreaseFactor=.2,listSelectorYOffsetUnicode=0,listSelectorYOffsetAscii=0,
    highlightItemColor='white',itemColor='white',menuItemFontName='Arial',
    popoverListViewShadingStartColor='black',popupBorderColor='gray').items():constants.insert(key,val)
view.rootContext().setContextProperty('_hblShutterEffects',settings)
view.rootContext().setContextProperty('constants',constants)
view.setSource(QUrl.fromLocalFile(str(folder/'Test.qml')))
if view.status()!=QQuickView.Ready:raise AssertionError([e.toString() for e in view.errors()])
view.show();selector=view.rootObject()
selector.openShutterEffects(selector,2);QTest.qWait(50)
listing=selector.findChild(QObject,'OwnChoiceList')
assert listing.property('currentIndex')==2
selector.close();assert settings.value('mode')==2
selector.openShutterEffects(selector,2);QTest.qWait(50)
listing.setProperty('currentIndex',1);selector.setSelected()
assert settings.value('mode')==1
selector.openShutterEffects(selector,1);QTest.qWait(50)
listing.setProperty('currentIndex',0);selector.setSelected()
assert settings.value('mode')==0
report={'passed':True,'cameraRequests':0,'exposureTransitions':2,'settingModes':[0,1,2],
        'soundDurationSec':round(duration,6),'soundSha256':hashlib.sha256(audio.read_bytes()).hexdigest(),
        'qtHostVersion':'PySide6; target Qt 5.5.1 separately compiled'}
print(json.dumps(report,ensure_ascii=False,indent=2))
obj.deleteLater()
