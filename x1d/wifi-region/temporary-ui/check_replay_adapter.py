"""Native adapter and capture routing, entirely synthetic and without hardware."""
exec((__import__('pathlib').Path(__file__).parent/'check_settings_page.py').read_text().split('app=QGuiApplication')[0])
from PySide6.QtCore import QObject
import re
sys.path.insert(0,str(P));sys.path.insert(0,str(P.parents[1]/'patch-distribution'))
from replay_routes import apply_replay_routes
from build_viewfinder_modes import read_rcc
resources=read_rcc((P/'build/flash-ui.rcc').read_bytes())
source=resources['/common/TouchWindow.qml']
assert 'if (presented && item) item.isInstantPreview = isInstantPreview' not in source
assert 'root.jpegCaptureIdentity=String(ContentModel.getAddedImageName() || "")' in source
assert 'item.residentEnter(root.jpegAutomaticEntry || isInstantPreview, false, -1)' in source
out=P/'build/replay-adapter-test';out.mkdir(exist_ok=True)
original=P.parents[1]/'candidates/replay-page-resident/build/original-page'
for name in ['PhotoPlaybackPage.qml','JpegPlaybackSurface.qml','CaptureIdentity.js','NavigationChevron.qml']:
    text=(P/name).read_text().replace('import "qrc:/components" as HblUi','import "." as HblUi')
    (out/name).write_text(text,encoding='utf-8')
text=(P/'NativePhotoPlayback.qml').read_text()
text=re.sub(r'^import com\.hasselblad\..*\n','',text,flags=re.M)
text=text.replace('qrc:///scripts/Keys.js',(original/'scripts/Keys.js').as_uri())
for name,replacement in [('SortedContentModel','catalog'),('ContentModel','storage'),('GlobalStateInfo','state'),('System','system'),('VideoControl','video')]:
    text=re.sub(r'\b'+name+r'\b',replacement,text)
(out/'NativePhotoPlayback.qml').write_text(text,encoding='utf-8')
(out/'Main.qml').write_text('''import QtQuick 2.5
Item {width:640;height:480
 QtObject {id:storage;property string path:"/fixture";property int pathType:1;property int pATH_TYPE_FILES:1;property int typeRole:2;property int displayRole:0;property int directory:0;property bool isBrowsingPossible:true;property bool isBrowsing:false
  function rowCount(){return 3} function index(i,col){return i}
  property int sizeRole:4
  function data(i,role){return role===4?8192:["first.3fr","second.3fr","second.JPG"][i]}
 }
 QtObject {id:video;objectName:"video";property int videoMode:0;property int playback:1;property int pipelineState:1;property int pipelineOff:0}
 QtObject {id:system;property bool isTethered:false}
 QtObject {id:state;property int mediaIndex:-1;property int greyBalanceIndex:-1}
 ListModel {id:catalog;property int listSize:count;ListElement {display:"first.3fr"} ListElement {display:"second.3fr"}
  function proxyToSrcIndex(i){return i}
  function getData(i,role){return role===2?1:get(i).display}
  function enterDir(name){} function exitDir(){}
 }
 NativePhotoPlayback {id:page;anchors.fill:parent}
}''',encoding='utf-8')
# QML identifiers cannot start uppercase; production enum names remain unchanged.
text=(out/'NativePhotoPlayback.qml').read_text()
text=text.replace('video.Playback','video.playback').replace('video.PipelineOff','video.pipelineOff')
for name in ['PATH_TYPE_FILES','TypeRole','DisplayRole','Directory','SizeRole']:
    text=text.replace('storage.'+name,'storage.'+name[0].lower()+name[1:])
(out/'NativePhotoPlayback.qml').write_text(text,encoding='utf-8')
app=QGuiApplication([]);view=QQuickView();view.setSource(QUrl.fromLocalFile(str(out/'Main.qml')))
assert view.status()==QQuickView.Ready,[e.toString() for e in view.errors()]
view.show();QTest.qWait(30)
root=view.rootObject().findChild(QObject,'OwnNativePhotoPlayback')
photo=root.findChild(QObject,'PhotoPlaybackPage')
video=view.rootObject().findChild(QObject,'video')
assert root.jpegSourceFor('/fixture/second.3fr').endswith('second.JPG'),'use exact JPEG spelling from cached directory'
assert '/bytes/8192/' in root.jpegSourceFor('/fixture/second.3fr'),'pass exact cached JPEG length, not RAW length'
assert 'second.3fr' in root.jpegSourceFor('/different/second.3fr'),'other directory cannot supply the pair'
root.residentEnter(True,False,-1);QTest.qWait(30)
assert photo.property('automatic') and photo.property('captureFileName')==''
root.captureCompleted('image://imagestore/preview/card0/DCIM/capture.3FR');QTest.qWait(20)
assert photo.property('captureFileName')=='/card0/DCIM/capture.3FR'
surface=photo.findChild(QObject,'AutomaticJpegPlayback')
assert not surface.property('loadRequested'),'must wait for live pipeline to stop'
video.setProperty('pipelineState',0);QTest.qWait(20)
assert surface.property('loadRequested'),'ready transition must start exact capture read'
root.prepareCapture('');assert photo.property('captureFileName')==''
root.residentLeave();root.residentEnter(False,False,0);QTest.qWait(40)
assert not photo.property('automatic') and photo.property('currentIndex')==0
root.residentLeave();assert not photo.property('presented')
print('PASS replay adapter: manual entry, exact capture wait/reset, release and event routing; no camera reads')
