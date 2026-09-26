"""New popup renderers with firmware option adapters; all values synthetic."""
exec((__import__('pathlib').Path(__file__).parent/'check_settings_page.py').read_text().split('app=QGuiApplication')[0])
import re
from PySide6.QtQml import QQmlPropertyMap
from PySide6.QtCore import QObject
sys.path.insert(0,str(P));sys.path.insert(0,str(P.parents[1]/'patch-distribution'))
from build_viewfinder_modes import read_rcc
from parameter_popovers import apply_parameter_popovers
resources=read_rcc((P/'build/flash-ui.rcc').read_bytes())
folder=P/'build/parameter-popover-test';folder.mkdir(exist_ok=True)
original=P.parents[1]/'candidates/replay-page-resident/build/original-page'
for path,source in resources.items():
    if '/OwnPopover' not in path and not path.startswith('/components/popups/Parameter'):continue
    source=re.sub(r'^import com\.hasselblad\.[^\n]+\n','',source,flags=re.M)
    source=source.replace('import "qrc:///components/buttons"','').replace('import "qrc:///components/controls"','').replace('import "qrc:/settings/components"','import "."')
    source=source.replace('id: grid\n','id: grid\n            objectName:"OptionGrid"\n')
    source=source.replace('qrc:///scripts/Keys.js',QUrl.fromLocalFile(str(original/'scripts/Keys.js')).toString())
    source=source.replace('qrc:///icons/',original.as_uri()+'/icons/')
    (folder/Path(path).name).write_text(source,encoding='utf-8')
choice=(P/'SettingsChoicePopup.qml').read_text().replace('import com.hasselblad.settings 1.0','').replace('qrc:///scripts/Keys.js',QUrl.fromLocalFile(str(original/'scripts/Keys.js')).toString())
(folder/'SettingsChoicePopup.qml').write_text(choice,encoding='utf-8')
app=QGuiApplication([])
contexts={}
for name in ['Config','Camera','cambody','configstore','guiconfig','BodySync','System','Cambody','constants']:
    contexts[name]=QQmlPropertyMap()
all_source='\n'.join(p.read_text(encoding='utf-8') for p in folder.glob('*.qml'))
for name,obj in contexts.items():
    for index,prop in enumerate(sorted(set(re.findall(r'\b'+name+r'\.([A-Za-z_][A-Za-z_0-9]*)',all_source)))):obj.insert(prop,index)
for prop,value in dict(isWedge=True,usingUnicodeLanguage=False,emptyString='').items():contexts['guiconfig'].insert(prop,value)
for prop,value in dict(ExpModeList=65535,LMModeListAsInt=65535).items():contexts['cambody'].insert(prop,value)
for prop,value in dict(popupGridSpacing=10,popupSideMargins=20,popupTextColor='white',popupFadeoutColor='black',fadeOutOpacity=.6,popupBackgroundColor='black',popupBorderColor='gray',popupBorderWidth=2,popupHeaderTextSize=28,outerBoxRadius=8,highlightColor='orange',fadeOutDuration=150,numberOfItemsVisibleInList=5,highlightItemColor='white',itemColor='white',listViewSizeIncreaseFactor=.2,listSelectorYOffsetUnicode=0,listSelectorYOffsetAscii=0,menuItemFontName='Arial',popoverListViewShadingStartColor='black').items():contexts['constants'].insert(prop,value)
for name in ['ExposureMode','FocusMode','MeterMethod','DriveMode','WhiteBalance']:
    file=folder/('OwnPopover'+name+'.qml')
    source=file.read_text(encoding='utf-8')
    source=re.sub(r'\bConfig\.([A-Za-z_][A-Za-z_0-9]*)',lambda m:str(contexts['Config'].value(m.group(1))),source)
    file.write_text(source,encoding='utf-8')
    view=QQuickView()
    for key,obj in contexts.items():view.rootContext().setContextProperty(key,obj)
    view.setSource(QUrl.fromLocalFile(str(folder/('OwnPopover'+name+'.qml'))))
    assert view.status()==QQuickView.Ready,[e.toString() for e in view.errors()]
    view.setResizeMode(QQuickView.SizeRootObjectToView);view.resize(640,480);view.show();QTest.qWait(100)
    root=view.rootObject();assert root.property('visible')
    grid=root.findChild(QObject,'OptionGrid');assert grid and grid.property('count')>0,name
    target,prop={'ExposureMode':('configstore','ExpMode'),'FocusMode':('Camera','FocusMode'),'MeterMethod':('Camera','LMMode'),'DriveMode':('Camera','DriveMode'),'WhiteBalance':('Camera','WBMode')}[name]
    contexts[target].insert(prop,-999)
    grid.setProperty('currentIndex',0);grid.setSelected();QTest.qWait(20)
    assert contexts[target].value(prop)!=-999,(name,'selected option not written')
    assert not root.property('visible'),(name,'selection did not close')
    view.close()
contexts['Camera'].insert('PropEVADJ',1);contexts['Camera'].insert('PropFlashEVADJ',2)
contexts['Camera'].insert('canChange',3)
contexts['Camera'].insert('EVADJ',0);contexts['Camera'].insert('FLASH_EVADJ',0)
contexts['configstore'].insert('CustomOption_AdjStepsInc',4)
view=QQuickView()
for key,obj in contexts.items():view.rootContext().setContextProperty(key,obj)
view.setSource(QUrl.fromLocalFile(str(folder/'ParameterExposureAdjust.qml')))
assert view.status()==QQuickView.Ready,[e.toString() for e in view.errors()]
view.setResizeMode(QQuickView.SizeRootObjectToView);view.resize(640,480);view.show();QTest.qWait(40)
root=view.rootObject();root.adjust(0,1);root.adjust(1,-1)
assert contexts['Camera'].value('FLASH_EVADJ')==4 and contexts['Camera'].value('EVADJ')==-4
for _ in range(30):root.adjust(0,1);root.adjust(1,-1)
assert contexts['Camera'].value('FLASH_EVADJ')==36 and contexts['Camera'].value('EVADJ')==-60
contexts['Camera'].insert('canChange',1);QTest.qWait(30)
contexts['Camera'].insert('EVADJ',0);root.adjust(0,1)
assert contexts['Camera'].value('EVADJ')==4,'single-slider mapping'
root.close();assert not root.property('visible')
view.close()
print('PASS six own popovers: render, allowed options, selection writes, compensation bounds/steps and exit; synthetic interfaces only')
