"""主菜单路由宿主检查：原生页面用只记录生命周期的替身。"""
exec((__import__('pathlib').Path(__file__).parent/'check_flash_interactions.py').read_text(encoding='utf-8').split("page.setProperty('screen','power');settle()")[0])
import json
testdir=P/'build/host-main-menu';testdir.mkdir(exist_ok=True)
target_source='''import QtQuick 2.5
Rectangle {objectName:"SettingsGeneric_root";color:"black";property string itemValues;property string menuLabel;property string upperMenuLabel
property bool preventSwipe:false;property bool prepared:false;property bool activated:false
property bool failActivation:false
signal backRequested()
function residentPrepare(){prepared=true}
function residentActivate(){if(failActivation)throw new Error("test activation failure");activated=true}
function residentDeactivate(){activated=false}
function originalExit(){closeMenu()}
}'''
(testdir/'SettingsGeneric.qml').write_text(target_source,encoding='utf-8')
url=QUrl.fromLocalFile(str(testdir/'SettingsGeneric.qml')).toString()
def item(key,label):return dict(settingsList=key,itemText=label,itemFile=url,largeIcon='')
camera=[item('cameraSettings'+a,a) for a in ['Exposure','Autofocus','ManualFocus','Quality','Image','SelfTimer']]
video=[item('videoSettingsVideoQuality','VideoQuality')]
general=[item('generalSettings'+a,a) for a in ['Display','PowerTimeouts','Storage','WiFi','Sound']]
(testdir/'MenuItems.js').write_text('function getSettingsList(key){return [];}\nvar cameraMenuItems='+json.dumps(camera)+';\nvar videoMenuItems='+json.dumps(video)+';\nvar settingsMenuItems='+json.dumps(general)+';',encoding='utf-8')
source=(P/'DirectMainMenu.qml').read_text(encoding='utf-8')
(testdir/'PagePool.qml').write_bytes((P/'PagePool.qml').read_bytes())
keys=P.parents[1]/'candidates/replay-page-resident/build/original-page/scripts/Keys.js'
source=source.replace('qrc:///scripts/Keys.js',QUrl.fromLocalFile(str(keys)).toString())
source='\n'.join(l for l in source.splitlines() if not l.startswith('import com.hasselblad'))
source=source.replace('"qrc:///settings/scripts/MenuItemImporter.js"','"MenuItems.js"').replace('"qrc:///controlscreen/NativeFlashPage.qml"',json.dumps(QUrl.fromLocalFile(str(host/'FlashPage.qml')).toString()))
(testdir/'DirectMainMenu.qml').write_text(source,encoding='utf-8')
config=QQmlPropertyMap();config.insert('hideDemoItems',True)
window=QQuickView();window.rootContext().setContextProperty('constants',constants);window.rootContext().setContextProperty('guiconfig',config)
store=QQmlPropertyMap();store.insert('languageIndex',0);window.rootContext().setContextProperty('configstore',store)
system=QQmlPropertyMap();system.insert('system_state',0);system.insert('StateUp',2);window.rootContext().setContextProperty('System',system)
(testdir/'RootKeys.js').write_text('function pressedFn(name,key){return (name==="F2"&&key===Qt.Key_F2)||(name==="STAR"&&key===Qt.Key_F3)||(name==="F4"&&key===Qt.Key_F4)||(name==="ESCAPE"&&key===Qt.Key_Escape);}')
(testdir/'OwnMainScreen.qml').write_text((P/'OwnMainScreen.qml').read_text().replace('qrc:///scripts/Keys.js','RootKeys.js'),encoding='utf-8')
window.setSource(QUrl.fromLocalFile(str(testdir/'OwnMainScreen.qml')))
assert window.status()==QQuickView.Ready,[e.toString() for e in window.errors()]
window.setResizeMode(QQuickView.SizeRootObjectToView);window.resize(640,480);window.show();settle()
home=window.rootObject().findChild(QObject,'DirectMainMenu');loader=home.findChild(QObject,'DirectMenuTarget')
assert window.rootObject().findChild(QObject,'menu_Loader') is None,'no original category loader constructed'
for key in [Qt.Key_F2,Qt.Key_F3,Qt.Key_F4]:
    window.rootObject().forceActiveFocus();QTest.keyClick(window,key);settle()
    assert home.property('listOpen'),'hardware category key must open own settings list'
    home.back();settle()
assert not home.findChild(QObject,'MainMenuBack').property('visible'),'no back icon on home'
def click(x,y):QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,QPoint(x,y));settle()
def swipe_back():
    QTest.mousePress(window,Qt.LeftButton,Qt.NoModifier,QPoint(230,240))
    for i in range(1,11):QTest.mouseMove(window,QPoint(230+20*i,240),15)
    QTest.mouseRelease(window,Qt.LeftButton,Qt.NoModifier,QPoint(430,240));settle()
click(80,140)
assert loader.property('active') and not home.property('returnToList'),'direct route'
loader.property('item').originalExit();settle()
assert not loader.property('active'),'original special-page exit contract'
click(80,140);home.dismissPages();settle()
assert not loader.property('active') and not home.property('listOpen'),'whole-menu exit clears presented child'
click(80,140)
swipe_back();assert not loader.property('active') and not home.property('listOpen'),'direct back'
click(400,405);assert home.property('listOpen'),'settings entry'
assert home.findChild(QObject,'MainMenuBack').property('visible'),'back icon in settings'
assert home.findChild(QObject,'MainMenuBattery') is not None,'battery loader must survive chevron replacement'
click(30,30);assert not home.property('listOpen'),'header back target'
click(400,405)
listing=home.findChild(QObject,'CombinedSettingsList')
assert listing.property('count')==6,'three headings plus remaining pages only'
click(100,185);assert loader.property('active') and home.property('returnToList'),'list route'
swipe_back();assert not loader.property('active') and home.property('listOpen'),'list back'
window.grabWindow().save(str(testdir/'combined-list.png'))
swipe_back();assert not home.property('listOpen'),'settings swipe to home'
click(80,270)
flash=loader.property('item');assert flash is not None,'real flash component in menu loader'
flash.setProperty('screen','power');settle()
click(85,120);assert flash.property('currentGroupEnabled'),'detail toggle through outer menu'
initial=flash.property('currentPower')
QTest.mousePress(window,Qt.LeftButton,Qt.NoModifier,QPoint(200,340))
for i in range(1,11):QTest.mouseMove(window,QPoint(200+19*i,340),15)
QTest.mouseRelease(window,Qt.LeftButton,Qt.NoModifier,QPoint(390,340));settle()
assert flash.property('currentPower')>initial,'nested power gesture'
assert flash.property('screen')=='power' and loader.property('active'),'outer menu must not steal power drag'
home.back();settle()
click(80,140);retained=loader.property('item');home.back();settle()
click(80,140);assert loader.property('item')==retained,'shortcut page instance must survive exit'
from PySide6.QtQml import QQmlExpression
home.back();settle()
visited=QQmlExpression(window.rootContext(),loader,'Object.keys(slots).join(",")').evaluate()[0].split(',')
system.insert('system_state',2);QTest.qWait(2600)
keys=QQmlExpression(window.rootContext(),loader,'Object.keys(slots).join(",")').evaluate()[0]
new_keys=set(keys.split(','))-set(visited)
assert 'cameraSettingsSelfTimer' not in new_keys and 'generalSettingsSound' not in new_keys,'non-shortcuts must not preload'
click(80,140)
assert loader.property('active') and not home.property('opening'),'prewarmed page must complete presentation'
home.back();settle();click(240,140)
assert loader.property('active') and not home.property('opening'),'second prewarmed shortcut remains clickable'
home.back();settle()
for x,y in [(80,140),(240,140),(400,140),(560,140),(80,270),(240,270),(400,270),(560,270),(240,405)]:
    click(x,y)
    assert loader.property('active') and not home.property('opening'),f'prewarmed shortcut {x},{y}'
    assert loader.property('item') is not None
    home.back();settle()
    assert not loader.property('active') and not home.property('closing')
click(80,140);loader.property('item').setProperty('failActivation',True)
home.back();settle();click(80,140)
assert not home.property('opening') and not loader.property('active'),'failed activation must unlock navigation'
click(240,140)
assert loader.property('active') and not home.property('opening'),'next entry must work after failure'
from PySide6.QtCore import QTranslator
class TestTranslations(QTranslator):
    def isEmpty(self):return False
    def translate(self,context,sourceText,disambiguation=None,n=-1):
        if context=='MENUS':return {'Exposure':'Экспозиция'}.get(sourceText,None)
        if context=='MainScreen':return {'CAMERA SETTINGS':'КАМЕРА','VIDEO SETTINGS':'ВИДЕО','GENERAL SETTINGS':'ОБЩИЕ'}.get(sourceText,None)
        return None
translation=TestTranslations();app.installTranslator(translation)
store.insert('languageIndex',1);settle()
assert home.pageTitle('cameraSettingsExposure')=='Экспозиция','shortcut translation'
assert home.pageTitle('cameraSettingsAutofocus')=='Фокусировка','custom focus translation'
assert loader.property('item').property('menuLabel')=='Фокусировка','retained page title translation'
home.back();settle();click(400,405)
assert 'КАМЕРА' in QQmlExpression(window.rootContext(),home,'JSON.stringify(sections())').evaluate()[0],'combined headings translation'
app.removeTranslator(translation);store.insert('languageIndex',0);settle()
assert home.pageTitle('cameraSettingsExposure')=='Exposure','language switch back'
print('PASS: navigation, preload, failure recovery, language change and retained titles')
