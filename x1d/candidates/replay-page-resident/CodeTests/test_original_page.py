"""运行完整原厂回放页候选；Qt5 宿主，业务接口与图像为无设备替身。"""
from pathlib import Path
import hashlib, json, os, re, sys, time
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]; ROOT = HERE.parents[2]
sys.path.insert(0,str(ROOT/'x1d/candidates/ui-resident/fixes/card-format-r1/build/python-qt515'))
sys.path.insert(0,str(HERE/'tools'))
os.environ.update(QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software', QML_DISABLE_DISK_CACHE='1')
from PyQt5.QtCore import QObject, QUrl, Qt, QTimer, QEvent, QModelIndex, QAbstractListModel, pyqtSignal, pyqtProperty, pyqtSlot, qVersion
from PyQt5.QtGui import QGuiApplication, QImage, QColor
from PyQt5.QtQml import QQmlComponent, QQmlPropertyMap
from PyQt5.QtQuick import QQuickView, QQuickImageProvider
import transform

class Model(QAbstractListModel):
    changed = pyqtSignal()
    imageAdded = pyqtSignal()
    listSizeChanged = pyqtSignal(int)
    card0AvailableChanged = pyqtSignal()
    card1AvailableChanged = pyqtSignal()
    currentWorkingDirChanged = pyqtSignal()
    isBrowsingPossibleChanged = pyqtSignal()
    browseVolumeChanged = pyqtSignal()
    card0StatusChanged = pyqtSignal()
    card1StatusChanged = pyqtSignal()
    roles = ['fileType','image','fullsizeImage','display','fileSize','date','imageWidth','imageHeight','histogram','imageRating',
             'iso','aperture','shutterSpeed','focalLength','lightMeterMode','whiteBalanceMode','exposureMode','evAdjust','volume','cropX','cropY',
             'exposureBias','whiteBalance','apertureValue','timeValue','exposureStatus']
    def __init__(self):
        super().__init__(); self.items = []; self.calls = []; self.pending = -1
        self.info = QQmlPropertyMap(); self.info.insert('pathType',1); self.info.insert('parentAvailable',True)
    def rowCount(self, parent=QModelIndex()): return 0 if parent.isValid() else len(self.items)
    def roleNames(self): return {Qt.UserRole+i+1: n.encode() for i,n in enumerate(self.roles)}
    def data(self,index,role):
        if not index.isValid() or not 0 <= index.row() < len(self.items): return None
        k = role-Qt.UserRole-1
        return self.items[index.row()].get(self.roles[k],0) if 0<=k<len(self.roles) else None
    @pyqtProperty(QObject, constant=True)
    def source(self): return self.info
    @pyqtProperty(int,notify=changed)
    def listSize(self): return len(self.items)
    @pyqtProperty(str,constant=True)
    def path(self): return '/fixture'
    @pyqtProperty(int,constant=True)
    def browseVolume(self): return 0
    @pyqtProperty(bool,constant=True)
    def isBrowsingPossible(self): return True
    @pyqtProperty(bool,constant=True)
    def card0Available(self): return True
    @pyqtProperty(bool,constant=True)
    def card1Available(self): return True
    @pyqtProperty(int,constant=True)
    def card0Status(self): return 1
    @pyqtProperty(int,constant=True)
    def card1Status(self): return 1
    @pyqtProperty(bool,constant=True)
    def isDeleting(self): return False
    @pyqtProperty(bool,constant=True)
    def isBrowsingActiveVolume(self): return True
    @pyqtProperty(int,constant=True)
    def PATH_TYPE_FILES(self): return 1
    @pyqtProperty(int,constant=True)
    def PATH_TYPE_DIRECTORIES(self): return 2
    @pyqtProperty(int,constant=True)
    def STORAGE_ABSENT(self): return 0
    @pyqtProperty(int,constant=True)
    def Image(self): return 1
    @pyqtProperty(int,constant=True)
    def Video(self): return 2
    @pyqtProperty(int,constant=True)
    def Directory(self): return 3
    @pyqtProperty(int,constant=True)
    def RatingRole(self): return self.roles.index('imageRating')+Qt.UserRole+1
    @pyqtProperty(int,constant=True)
    def TypeRole(self): return Qt.UserRole+1
    @pyqtProperty(int,constant=True)
    def DisplayRole(self): return self.roles.index('display')+Qt.UserRole+1
    @pyqtSlot(bool)
    def showOnlyImages(self,v): self.calls.append(['showOnlyImages',v])
    @pyqtSlot(result=int)
    def getAckAddedImage(self):
        self.calls.append(['ack',self.pending]); n=self.pending; self.pending=-1; return n
    @pyqtSlot()
    def clearRatingLastExposure(self): self.calls.append(['clearRating'])
    @pyqtSlot(int,result=int)
    def proxyToSrcIndex(self,n): return n
    @pyqtSlot(int,int,result='QVariant')
    def getData(self,n,role): return self.data(self.index(n),role)
    @pyqtSlot(int,result=float)
    def getCropX(self,n): return 0
    @pyqtSlot(int,result=float)
    def getCropY(self,n): return 0
    @pyqtSlot()
    def updateListSize(self): self.calls.append(['updateListSize'])
    @pyqtSlot(int)
    def remove(self,n): self.calls.append(['FORBIDDEN-remove',n])
    @pyqtSlot()
    def createNewFolder(self): self.calls.append(['FORBIDDEN-create'])
    def reset(self,n):
        self.beginResetModel()
        self.items=[{'fileType':1,'image':'image://fixture/photo-'+str(i),'fullsizeImage':'image://fixture/full-'+str(i),
            'display':'fixture-'+str(i),'fileSize':123,'date':'2000-01-01T00:00:00','imageWidth':32,'imageHeight':24,'histogram':[],
            'imageRating':0,'iso':'100','aperture':'4','shutterSpeed':'1/100','apertureValue':'4','timeValue':'1/100'} for i in range(n)]
        self.endResetModel(); self.changed.emit(); self.listSizeChanged.emit(n)

class Provider(QQuickImageProvider):
    def __init__(self): super().__init__(QQuickImageProvider.Image); self.calls=[]
    def requestImage(self,name,size):
        self.calls.append(name)
        if 'slow' in name: time.sleep(.15)
        data=QImage(32,24,QImage.Format_RGB32); data.fill(QColor('red')); return data,data.size()

def native_mock(name,props,methods,defaults,log):
    attrs={'changed':pyqtSignal()}
    if name == 'farm':attrs['imageRatingStatusChanged']=pyqtSignal()
    def init(self):
        QObject.__init__(self);self.values={key:defaults.get(key,0) for key in props};self.values.update(defaults)
    attrs['__init__']=init
    for key in props|set(defaults):
        def getter(self,k=key):return self.values[k]
        def setter(self,v,k=key):
            if self.values.get(k)!=v:
                self.values[k]=v;log.append([name,'write',k,v]);self.changed.emit()
        attrs[key]=pyqtProperty('QVariant',getter,setter,notify=attrs['changed'])
    for key in methods:
        def method(self,*args,k=key):
            if k=='isRunningSimulation':return True
            if k in ['storageSlotLetter','getDisplayValue','stringTranslated','getUntranslatedDisplayValue']:return 'fixture'
            log.append([name,k,list(args)])
            if k=='setVideoPlaybackState':
                self.videoEpoch=getattr(self,'videoEpoch',0)+1;epoch=self.videoEpoch
                def finish():
                    if epoch!=self.videoEpoch:return
                    self.values['videoMode']=2 if args[0] else 0
                    self.values['pipelineState']=1 if args[0] else 0
                    self.changed.emit()
                QTimer.singleShot(20,finish)
            return 0
        method.__name__=key
        for argc in range(5):method=pyqtSlot(*(['QVariant']*argc),result='QVariant',name=key)(method)
        attrs[key]=method
    return type(name+'Mock',(QObject,),attrs)()

def prepare():
    original=transform.qml_files(transform.ArmElf.load('usr/bin/victory-gui'))
    values=transform.transform_all(original); work=HERE/'build/original-page'; work.mkdir(parents=True,exist_ok=True)
    for name,text in values.items():
        text=re.sub(r'^import com\.hasselblad\..*\n','',text,flags=re.M)
        text=re.sub(r'qrc:/+(?=[\w])',work.as_uri()+'/',text)
        if name == '/components/MediaBrowseView.qml':
            # 测试专用驱动仅发实际 delegate 的缩放/播放信号；不替换处理代码。
            text=transform.once(text,'    id: root','''    id: root
    function fixtureZoom() { media_list.currentItem.initPinching() }
    function fixtureVideo() { video_overlay.startPlayback(media_list.currentIndex, "fixture-video", 123, "2000-01-01T00:00:00") }
    function fixturePendingDelete() { deleteImage(); deletePopupLoader.deleteFile = true }
''')
        p=work/name.lstrip('/'); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(text,encoding='utf-8')
    # 只补无业务作用的图标，不使用任何真实照片。
    pixel=QImage(2,2,QImage.Format_ARGB32); pixel.fill(QColor('white'))
    for text in values.values():
        for relative in re.findall(r'qrc:/+(icons/[^"\s]+\.(?:png|jpg))',text):
            p=work/relative;p.parent.mkdir(parents=True,exist_ok=True)
            if not p.exists():pixel.save(str(p))
    harness='''import QtQuick 2.5
import "components"
import "common"
Item {
 id: harness; width: 640; height: 480
 property bool preventControlScreenSwipe: false
 GlobalConstants { id: constants }
 MediaBrowseView { id: replay; anchors.fill: parent }
 function enter(preview, evf, index) { return replay.residentEnter(preview, evf, index) }
 function leave() { replay.residentLeave() }
 function mode(value) { replay.state=value }
}'''
    (work/'Harness.qml').write_text(harness,encoding='utf-8')
    return work,values

def run():
    app=QGuiApplication([]); work,values=prepare()
    view=QQuickView(); engine=view.engine(); warnings=[]
    engine.warnings.connect(lambda errors:warnings.extend(e.toString() for e in errors))
    model=Model(); model.reset(3); provider=Provider();engine.addImageProvider('fixture',provider)
    engine.rootContext().setContextProperty('ContentModel',model);engine.rootContext().setContextProperty('SortedContentModel',model)
    # 普通属性和业务函数均为明确本地对象；写值/调用计数由脚本核对。
    alltext='\n'.join(values.values()); holders=[]; maps={}; business=[]
    defaults={
        'guiconfig':{'isWedge':True,'isCFV':False,'emptyString':'','usingUnicodeLanguage':False,'maxImageXSize':8272,'isH6':False},
        'configstore':{'MetaDataOverlayIndex':0,'OverExposureWarning':False,'crop_mode_opacity':100,'imageRating':False,'imageRateFilter':0},
        'VideoControl':{'videoMode':0,'pipelineState':0,'Off':0,'Playback':2,'PipelineOff':0,'PipelineLocal':1},
        'Config':{'RatingLastExposure':99,'MaskRatingAll':0}, 'System':{'isTethered':False,'batteryStatus':1,'BatteryNormal':1},
        'GlobalStateInfo':{'mediaIndex':-7,'greyBalanceIndex':-7,'evfBrowseViewState':''},
        'BodySync':{'PLAY':5,'currentState':0}}
    for name in ['guiconfig','configstore','GlobalStateInfo','System','Config','VideoControl','BodySync','farm','Farm','SoundControl','Camera','Settings','suc','Suc','prodinfo','Errors','ErrorControl','cambody']:
        props=set(re.findall(r'\b'+name+r'\.(\w+)',alltext)); methods=set(re.findall(r'\b'+name+r'\.(\w+)\s*\(',alltext))
        for method in methods:props.discard(method)
        obj=native_mock(name,props,methods,defaults.get(name,{}),business)
        holders.append(obj);maps[name]=obj;engine.rootContext().setContextProperty(name,obj)
    def wait(pred,timeout=3):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            app.processEvents()
            app.sendPostedEvents(None,QEvent.DeferredDelete)
            if pred():return
            time.sleep(.005)
        raise AssertionError('等待超时')
    def settle(sec=.15):
        end=time.monotonic()+sec
        while time.monotonic()<end:
            app.processEvents();app.sendPostedEvents(None,QEvent.DeferredDelete);time.sleep(.005)
    view.setSource(QUrl.fromLocalFile(str(work/'Harness.qml')))
    if view.status()==QQuickView.Error:
        print('\n'.join(e.toString() for e in view.errors()));raise SystemExit(1)
    root=view.rootObject(); page=root.findChild(QObject,'MediaBrowseView_root');assert page
    def visual(obj):
        result=[obj]
        if hasattr(obj,'childItems'):
            for child in obj.childItems():result.extend(visual(child))
        return result
    def sources():
        return [v.property('source').toString() for v in visual(page) if isinstance(v.property('source'),QUrl) and v.property('source').scheme()=='image']
    def quiet():
        shader_refs=[v for v in visual(page) if v.property('src') is not None]
        return not page.property('residentSessionActive') and page.property('residentListCount')==0 and page.property('residentGridCount')==0 and not sources() and not shader_refs
    checks=[]
    def check(name,value):
        assert value,name;checks.append(name)
    settle()
    occupancy={'pagePrewarmVisualItems':len(visual(page)), 'pagePrewarmQObjectDescendants':len(page.findChildren(QObject)), 'photoSources':len(sources()), 'hostQt':qVersion(), 'targetRamBytes':None}
    check('完整原页预建不请求照片或消费模型', not model.calls and not provider.calls)
    check('预建无BodySync或其他业务写入',not [c for c in business if c[1]=='write'])
    model.pending=2;model.imageAdded.emit();settle()
    check('隐藏新图信号不消费ack',model.pending==2 and not model.calls)
    root.enter(False,False,-1);wait(lambda:page.property('hasLoadedCurrent'));settle()
    check('手动回放激活并选择新图',page.property('state')=='list' and page.property('mediaListCurrentIndex')==2 and model.pending==-1)
    check('激活恰好一次筛选和ack',model.calls==[['showOnlyImages',False],['ack',2]])
    photos=[v for v in visual(page) if isinstance(v.property('source'),QUrl) and v.property('source').scheme()=='image']
    destroyed=[]
    for obj in photos:obj.destroyed.connect(lambda:destroyed.append(True))
    root.leave();settle()
    check('退出完整原页仍存在且全部照片源已空',page is root.findChild(QObject,'MediaBrowseView_root') and quiet())
    check('照片delegate销毁且存活Shader不持图',len(photos)>0 and len(destroyed)==len(photos) and quiet())
    check('退出清评级一次',model.calls[-1]==['clearRating'] and sum(c[0]=='clearRating' for c in model.calls)==1)
    before=len(model.calls);root.leave();settle()
    check('重复退出不重复清理',len(model.calls)==before)
    model.reset(4);model.pending=3;model.imageAdded.emit();settle()
    check('隐藏模型变化无照片请求与ack消费',quiet() and model.pending==3 and len(model.calls)==before)
    root.enter(False,True,1);wait(lambda:page.property('hasLoadedCurrent'));settle()
    check('EVF指定索引保留且不消费LCDack',page.property('mediaListCurrentIndex')==1 and model.pending==3)
    check('EVF呈现同步状态',maps['GlobalStateInfo'].values['evfBrowseViewState']=='list')
    root.leave();settle()
    check('EVF退出清空状态和图片',quiet() and maps['GlobalStateInfo'].values['evfBrowseViewState']=='')
    root.enter(True,False,-1);wait(lambda:page.property('hasLoadedCurrent'));settle()
    check('自动回放消费最新图且标记即时预览',page.property('isInstantPreview') and page.property('mediaListCurrentIndex')==3 and model.pending==-1)
    page.setProperty('mediaListCurrentIndex',1);settle()
    check('呈现期间可以切图',page.property('mediaListCurrentIndex')==1)
    root.mode('grid');settle()
    check('九宫格有图且保持原BodySync激活',page.property('state')=='grid' and maps['BodySync'].values['currentState']==5 and len(sources())>0)
    root.leave();settle()
    check('九宫格退出释放所有照片源',quiet())
    root.enter(False,False,-1);wait(lambda:page.property('hasLoadedCurrent'));settle()
    page.fixtureZoom();settle(.3)
    check('原delegate缩放信号载入全图',page.property('state')=='zooming' and not page.property('residentZoomSource').isEmpty() and any(c.startswith('full-') for c in provider.calls))
    root.leave();settle()
    check('全图退出释放两路图像',quiet() and page.property('residentZoomSource').isEmpty() and page.property('residentZoomPreviewSource').isEmpty())
    root.enter(False,False,-1);wait(lambda:page.property('hasLoadedCurrent'));settle()
    page.fixtureVideo();settle()
    check('视频原调用进入播放',page.property('state')=='video_playback')
    before=sum(c[0]=='VideoControl' and c[1]=='setVideoPlaybackState' and c[2][0] is False for c in business)
    root.leave();settle()
    after=sum(c[0]=='VideoControl' and c[1]=='setVideoPlaybackState' and c[2][0] is False for c in business)
    check('退出视频恰好停播一次',quiet() and after==before+1)
    root.enter(False,False,-1);wait(lambda:page.property('hasLoadedCurrent'))
    page.fixtureVideo();root.leave();settle()
    check('视频启动回复未到也发停止并保持退出',quiet() and maps['VideoControl'].values['videoMode']==0)
    model.items[-1]['image']='image://fixture/slow-old'
    root.enter(False,False,-1);wait(lambda:'slow-old' in provider.calls)
    root.leave();model.reset(2);root.enter(False,False,-1)
    wait(lambda:page.property('hasLoadedCurrent'));settle(.3)
    check('迟到图像不覆盖快速重入后的当前图',page.property('mediaListCurrentIndex')==1 and not any('slow-old' in v for v in sources()))
    root.leave();settle()
    root.enter(False,False,-1);root.leave();settle(.3)
    check('加载过程中立即退出不保留图像',quiet())
    root.enter(False,True,99);wait(lambda:page.property('hasLoadedCurrent'));settle()
    check('EVF过期索引收敛到有效末项',page.property('mediaListCurrentIndex')==model.rowCount()-1)
    root.leave();settle()
    root.enter(False,False,-1);wait(lambda:page.property('hasLoadedCurrent'))
    page.fixturePendingDelete();root.leave();settle()
    check('带确认状态退出不误删除照片',quiet() and not any(c[0]=='FORBIDDEN-remove' for c in model.calls))
    for _ in range(10):
        root.enter(False,False,-1);wait(lambda:page.property('hasLoadedCurrent'))
        root.leave();settle(.03)
    check('十轮进出保留同一原页且退出引用为空',quiet() and page is root.findChild(QObject,'MediaBrowseView_root'))
    check('未触发删除或创建目录',not any(c[0].startswith('FORBIDDEN') for c in model.calls))
    model.reset(0);root.enter(False,False,-1);settle()
    check('空目录呈现原页且没有照片源',page.property('state')=='grid' and not sources())
    root.leave();settle();check('空目录退出保持原页',quiet())
    # 直接执行生产变换后的两个真实 Loader 块，周围窗口接口仅为局部替身。
    def loader_block(path,ident):
        text=values[path];start=text.rindex('        Loader {',0,text.index('            id: '+ident))
        end=transform.closing(text,text.index('{',start))
        return re.sub(r'qrc:/+(?=[\w])',work.as_uri()+'/',text[start:end+1])
    shell='''import QtQuick 2.5
import "common"
Item {
 id: root; width: 640; height: 480
 property bool simulation: true
 property bool browseIn9View: false
 property bool mediaBrowseDeleteOnLoad: false
 property bool showPreview: false
 property int notices: 0
 property alias lcdPage: media_browse_loader.item
 property alias evfPage: preView.item
 property alias evfTimerRunning: evfPreviewTimer.running
 function notifyCurrentImageLoaded() { notices++ }
 GlobalConstants { id: constants }
 QtObject { id: idle_detect; signal onTouchEvent() }
 Timer { id: evfPreviewTimer; interval: 10000 }
 @LCD@
 Connections {
   target: media_browse_loader.presented ? media_browse_loader.item : null
   onCurrentItemLoaded: root.notifyCurrentImageLoaded()
 }
 Item { id: scope; anchors.fill: parent; @EVF@ }
 function openLCD(preview) { media_browse_loader.isInstantPreview=preview; media_browse_loader.presented=true }
 function closeLCD() { media_browse_loader.presented=false }
 function openEVF(index,timed) { preView.startIndex=index;preView.startTimer=timed;preView.presented=true }
 function closeEVF() { preView.presented=false }
}'''.replace('@LCD@',loader_block('/common/TouchWindow.qml','media_browse_loader')).replace('@EVF@',loader_block('/liveview/EVFWindow.qml','preView'))
    shellfile=work/'LoaderHarness.qml';shellfile.write_text(shell,encoding='utf-8')
    shellcomponent=QQmlComponent(engine,QUrl.fromLocalFile(str(shellfile)));shellroot=shellcomponent.create()
    assert shellroot,[e.toString() for e in shellcomponent.errors()]
    before=len(model.calls);beforeimages=len(provider.calls)
    wait(lambda:shellroot.property('lcdPage') is not None and shellroot.property('evfPage') is not None);settle()
    lcd=shellroot.property('lcdPage');evfpage=shellroot.property('evfPage')
    occupancy['lcdPrewarmVisualItems']=len(visual(lcd));occupancy['evfPrewarmVisualItems']=len(visual(evfpage))
    check('两个真实Loader提前创建完整页面且静默',len(model.calls)==before and len(provider.calls)==beforeimages and not lcd.property('residentSessionActive') and not evfpage.property('residentSessionActive'))
    model.reset(3);model.pending=2
    shellroot.openLCD(True);wait(lambda:lcd.property('hasLoadedCurrent'));settle()
    check('真实LCD入口激活即时预览',lcd.property('isInstantPreview') and lcd.property('mediaListCurrentIndex')==2 and shellroot.property('notices')>=1)
    shellroot.closeLCD();settle()
    check('真实LCD退出保留原页实例',shellroot.property('lcdPage') is lcd and not lcd.property('residentSessionActive') and lcd.property('residentListCount')==0)
    shellroot.openEVF(1,True);wait(lambda:evfpage.property('hasLoadedCurrent'));settle()
    check('真实EVF入口传递索引并启动原定时流程',evfpage.property('usedInEVF') and evfpage.property('mediaListCurrentIndex')==1 and shellroot.property('evfTimerRunning'))
    shellroot.closeEVF();settle()
    check('真实EVF退出保留原页且停止计时',shellroot.property('evfPage') is evfpage and not evfpage.property('residentSessionActive') and not shellroot.property('evfTimerRunning'))
    shellroot.openLCD(False);wait(lambda:lcd.property('hasLoadedCurrent'));shellroot.closeLCD();settle()
    check('真实LCD再次呈现复用完整原页',shellroot.property('lcdPage') is lcd and lcd.property('residentEntries')==2 and lcd.property('residentExits')==2)
    shellroot.deleteLater();settle()
    unexpected=list(set(w for w in warnings if 'deprecated' not in w))
    if unexpected: print(json.dumps({'unexpectedWarnings':unexpected},ensure_ascii=False))
    check('完整用例没有QML运行错误',not unexpected)
    print(json.dumps({'checks':checks,'warnings':unexpected,'entries':page.property('residentEntries'),'exits':page.property('residentExits')},ensure_ascii=False))
    report={'passed':True,'checks':checks,'warnings':unexpected,'hostQt':qVersion(),'cameraRequests':0,'realPhotos':0,'targetQt55Verified':False,'gpuTextureReleaseVerified':False,'fullOriginalPageExecuted':True,'actualWindowLoadersExecuted':True}
    report['sources']={p.relative_to(HERE).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),HERE/'tools/transform.py',HERE/'qml/page-lifecycle.inc']}
    baseline=transform.qml_files(transform.ArmElf.load('usr/bin/victory-gui'))
    report['candidateQml']={p:hashlib.sha256(t.encode()).hexdigest() for p,t in values.items() if baseline.get(p)!=t}
    report['occupancy']=occupancy
    report['hostAdaptations']=['去除专用业务插件import并使用显式本地对象','qrc路径改为本候选工作副本','非照片图标为2x2占位','附加仅驱动原页方法或delegate信号的测试函数','VideoControl回复由本地20ms定时器模拟','显式处理DeferredDelete以模拟完整Qt事件循环']
    (HERE/'artifacts/original-page.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    view.close();view.deleteLater();settle()

if __name__=='__main__':run()
