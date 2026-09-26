import QtQuick 2.5
import com.hasselblad.storage 1.0
import com.hasselblad.camera 1.0
import com.hasselblad.video 1.0
import com.hasselblad.globalstateinfo 1.0
import com.hasselblad.systemmanager 1.0
import "qrc:///scripts/Keys.js" as MKeys

// The caller passes the current capture identity for automatic replay.
Item {
    id:root
    objectName:"OwnNativePhotoPlayback"
    property bool residentSessionActive:false
    property bool isInstantPreview:false
    property bool usedInEVF:false
    property bool simulation:false
    readonly property bool storageReady: VideoControl.videoMode!==VideoControl.Playback && VideoControl.pipelineState===VideoControl.PipelineOff && ContentModel.isBrowsingPossible && !ContentModel.isBrowsing
    onStorageReadyChanged:if(residentSessionActive)console.log("JpegGate ready="+storageReady)
    readonly property bool is9ViewActive:photo.gridMode
    onIs9ViewActiveChanged:isIn9View(is9ViewActive)
    property bool hasLoadedCurrent:false
    property string pendingCapture:""
    property var resolvedSources:({})
    property int releaseSequence:0
    Image {visible:false;cache:false;source:root.residentSessionActive?"":"image://hbljpeg/release/"+root.releaseSequence}
    signal currentItemLoaded()
    signal isIn9View(bool val)
    signal preventIdleTimeout(bool prevent)
    signal hideInstantAVTV()
    signal keyPressed()
    signal closeRequested()
    function metadataFor(index,capture){
        if(capture){
            var slash=capture.lastIndexOf('/');if(capture.substring(0,slash)!==String(ContentModel.path))return ({})
            var name=capture.substring(slash+1);index=-1
            for(var i=0;i<SortedContentModel.listSize;i++)if(String(SortedContentModel.getData(i,ContentModel.DisplayRole))===name){index=i;break}
        }
        if(index<0 || index>=SortedContentModel.listSize)return ({})
        return {name:String(SortedContentModel.getData(index,ContentModel.DisplayRole)||""),date:String(SortedContentModel.getData(index,ContentModel.DateRole)||""),iso:String(SortedContentModel.getData(index,ContentModel.IsoRole)||""),aperture:String(SortedContentModel.getData(index,ContentModel.AvRole)||""),shutter:String(SortedContentModel.getData(index,ContentModel.TvRole)||"")}
    }
    // Inspect only the existing directory model; never request a new browse.
    function jpegSourceFor(path) {
        if(resolvedSources[path])return resolvedSources[path]
        var slash=path.lastIndexOf('/'), folder=path.substring(0,slash)
        var stem=path.substring(slash+1).replace(/\.(3fr|jpg)$/i,"")
        var readable=typeof ContentModel.rowCount==="function" && typeof ContentModel.index==="function" && typeof ContentModel.data==="function"
        var sameDirectory=folder===String(ContentModel.path), match="", matches=0, fileBytes=0
        if(readable && sameDirectory && !ContentModel.isBrowsing){
            var count=ContentModel.rowCount()
            if(count>=0 && count<=4096)for(var i=0;i<count;i++){
                var name=String(ContentModel.data(ContentModel.index(i,0),0) || "")
                if(/\.jpg$/i.test(name) && name.substring(0,name.length-4)===stem && name.indexOf('/')<0 && name.indexOf('\\')<0){
                    match=name;matches++
                    if(typeof ContentModel.SizeRole!=="undefined")fileBytes=Number(ContentModel.data(ContentModel.index(i,0),ContentModel.SizeRole))
                }
            }
        }
        var sized=isFinite(fileBytes) && fileBytes>0 && fileBytes<=128*1024*1024 && Math.floor(fileBytes)===fileBytes
        console.log("JpegIdentity model="+readable+" directory="+sameDirectory+" matches="+matches+" sized="+sized+" small="+(sized && fileBytes<1024*1024))
        if(matches>1)return ""
        var source="image://hbljpeg/"+(matches===1 && sized?"bytes/"+fileBytes+"/":"")+encodeURIComponent(matches===1?folder+"/"+match:path)
        if(matches===1 && sized)resolvedSources[path]=source
        return source
    }
    visible:residentSessionActive
    enabled:residentSessionActive
    focus:residentSessionActive
    function prepareCapture(source){
        pendingCapture=String(source || "")
        if(pendingCapture==="" && residentSessionActive && isInstantPreview){hasLoadedCurrent=false;photo.beginCapture()}
    }
    function residentEnter(preview,evf,index){
        if(residentSessionActive && isInstantPreview===preview) {
            if(preview && pendingCapture!=="")photo.captureEvent(pendingCapture)
            return true
        }
        usedInEVF=evf;isInstantPreview=preview;hasLoadedCurrent=false
        residentSessionActive=true
        photo.enter(index,preview)
        if(!preview && ContentModel.pathType!==ContentModel.PATH_TYPE_FILES)photo.gridMode=true
        if(preview && pendingCapture!=="")photo.captureEvent(pendingCapture)
        return true
    }
    function residentLeave(){
        releaseSequence++;residentSessionActive=false;deletePopup.deleteFile=false;deletePopup.active=false
        photo.leave();pendingCapture="";hasLoadedCurrent=false;resolvedSources=({})
    }
    function deleteImage(){
        if(!residentSessionActive || isInstantPreview || System.isTethered || photo.currentIndex<0)return
        photo.zoom=1;deletePopup.targetIndex=photo.currentIndex
        deletePopup.deleteFile=false;deletePopup.active=true
    }
    function captureCompleted(source){
        pendingCapture=String(source || "")
        if(residentSessionActive && isInstantPreview)photo.captureEvent(pendingCapture)
    }
    PhotoPlaybackPage {
        id:photo;anchors.fill:parent
        storageReady:root.storageReady
        sourceResolver:root.jpegSourceFor
        metadataResolver:root.metadataFor
        catalogue:SortedContentModel
        directory:ContentModel.path
        onCurrentPresented:{root.hasLoadedCurrent=true;root.currentItemLoaded()}
        onSelected:if(index>=0 && root.residentSessionActive){
            if(!root.usedInEVF)GlobalStateInfo.mediaIndex=index
            GlobalStateInfo.greyBalanceIndex=SortedContentModel.proxyToSrcIndex(index)
        }
        onBackRequested:root.closeRequested()
        onInteraction:root.keyPressed()
        onOpenItem:{
            if(SortedContentModel.getData(index,ContentModel.TypeRole)===ContentModel.Directory){
                SortedContentModel.enterDir(SortedContentModel.getData(index,ContentModel.DisplayRole))
            }else{photo.currentIndex=index;photo.gridMode=false}
        }
        onDirectoryUp:SortedContentModel.exitDir()
    }
    Loader {
        id:deletePopup;anchors.fill:parent;z:200;active:false;focus:active
        property bool deleteFile:false
        property int targetIndex:-1
        source:"qrc:///components/popups/DeletePopup.qml"
        onLoaded:item.forceActiveFocus()
        onActiveChanged:if(!active && root.residentSessionActive){
            if(deleteFile && targetIndex===photo.currentIndex){
                SortedContentModel.remove(targetIndex)
                photo.currentIndex=Math.max(-1,Math.min(targetIndex,SortedContentModel.listSize-1))
            }
            deleteFile=false;root.forceActiveFocus()
        }
    }
    Connections {
        target:root.residentSessionActive?ContentModel:null
        onIsBrowsingPossibleChanged:photo.captureWriteProgress()
    }
    Keys.onPressed:{
        event.accepted=false
        if(MKeys.pressedFn("ESCAPE",event.key)){if(photo.gridMode)photo.gridMode=false;else root.closeRequested();event.accepted=true}
        else if(!root.isInstantPreview && MKeys.pressedFn("NAVLEFT",event.key)){
            photo.currentIndex=Math.max(0,photo.currentIndex-1);root.keyPressed();event.accepted=true
        }else if(!root.isInstantPreview && MKeys.pressedFn("NAVRIGHT",event.key)){
            photo.currentIndex=Math.min(SortedContentModel.listSize-1,photo.currentIndex+1);root.keyPressed();event.accepted=true
        }
    }
}
