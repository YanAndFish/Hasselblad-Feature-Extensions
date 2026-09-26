import QtQuick 2.5
import "qrc:/components" as HblUi
import "CaptureIdentity.js" as CaptureIdentity

// Own presentation shared by automatic and manual replay. A native adapter
// supplies the existing catalogue and decides when to enter/leave a session.
Rectangle {
    id: page
    objectName:"PhotoPlaybackPage"
    color:"black"
    property bool presented:false
    property bool selectionReady:false
    property bool currentPreviewReady:false
    property bool storageReady:true
    property var sourceResolver:null
    property var metadataResolver:null
    readonly property var currentMetadata:metadataResolver?metadataResolver(currentIndex,automatic?captureFileName:""):({})
    property bool automatic:false
    property string captureFileName:""
    property url captureImageSource:""
    property var catalogue:null
    property string directory:""
    property int requestedIndex:-1
    property bool gridMode:false
    property real zoom:1
    property bool allowNavigation:true
    property alias currentIndex:photos.currentIndex
    signal currentPresented(bool available)
    signal selected(int index)
    signal backRequested()
    signal interaction()
    signal openItem(int index)
    signal directoryUp()
    visible:presented
    enabled:presented
    function enter(index,preview){selectionReady=false;currentPreviewReady=false;automatic=preview;captureFileName="";captureImageSource="";requestedIndex=index;zoom=1;gridMode=false;presented=true;if(!preview)selectTimer.restart()}
    function leave(){presented=false;captureFileName="";captureImageSource="";zoom=1;gridMode=false;requestedIndex=-1}
    function beginCapture(){captureFileName="";captureImageSource="";zoom=1}
    // Only a capture-completion identity may call this. Never infer it from
    // the last directory entry: that may still belong to a previous exposure.
    function captureArrived(name){if(presented && automatic && sourceFor(name)!==""){captureFileName=name;captureImageSource=sourceFor(name);automaticPhoto.reload()}}
    function captureWriteProgress(){if(presented && automatic && captureFileName!==""){
        var path=CaptureIdentity.pathFromEvent(captureFileName)
        captureImageSource=path?(sourceResolver?sourceResolver(path):CaptureIdentity.providerSource(path)):sourceFor(captureFileName)
        automaticPhoto.reload()
    }}
    function captureEvent(value){
        var path=CaptureIdentity.pathFromEvent(value)
        if(!presented || !automatic || !path)return
        captureFileName=path
        captureImageSource=sourceResolver?sourceResolver(path):CaptureIdentity.providerSource(path)
        automaticPhoto.reload()
    }
    function sourceFor(name){
        if(!name || name.indexOf('/')>=0 || name.indexOf('\\')>=0)return ""
        if(!/\.(3fr|jpg)$/i.test(name))return ""
        return sourceResolver?sourceResolver(directory+"/"+name):"image://hbljpeg/"+encodeURIComponent(directory+"/"+name)
    }
    Timer {id:selectTimer;interval:0;onTriggered:{
        photos.currentIndex=Math.max(-1,Math.min(page.requestedIndex<0?photos.count-1:page.requestedIndex,photos.count-1))
        photos.positionViewAtIndex(photos.currentIndex,ListView.Center)
        page.selectionReady=true
    }}
    ListView {
        id:photos;objectName:"OwnPlaybackList";anchors.fill:parent
        model:page.presented && !page.automatic?page.catalogue:null
        orientation:ListView.Horizontal;snapMode:ListView.SnapOneItem
        highlightMoveVelocity:-1;highlightMoveDuration:200
        maximumFlickVelocity:width*6;flickDeceleration:3500
        cacheBuffer:0;displayMarginBeginning:width*3;displayMarginEnd:width*2;pressDelay:0
        highlightRangeMode:ListView.StrictlyEnforceRange
        preferredHighlightBegin:0;preferredHighlightEnd:width
        boundsBehavior:Flickable.StopAtBounds
        visible:!page.gridMode
        interactive:page.allowNavigation && page.zoom===1
        clip:true
        onCurrentIndexChanged:{page.zoom=1;page.currentPreviewReady=false;page.selected(currentIndex)}
        delegate:Item {
            id:photoDelegate
            objectName:"ReplayCell"+index
            property bool admitted:false
            readonly property bool inWindow:index>=photos.currentIndex-3 && index<=photos.currentIndex+2
            function updateAdmission(){
                if(!inWindow){admitted=false;picture.zoomFactor=1}
                else if(page.selectionReady && (index===photos.currentIndex || page.currentPreviewReady))admitted=true
                if(index!==photos.currentIndex){picture.nativeZoomPending=false;picture.zoomFactor=1}
                else if(picture.imageStatus===Image.Ready)page.currentPreviewReady=true
            }
            Component.onCompleted:updateAdmission()
            onInWindowChanged:updateAdmission()
            Connections {target:page;onSelectionReadyChanged:photoDelegate.updateAdmission();onCurrentPreviewReadyChanged:photoDelegate.updateAdmission();onCurrentIndexChanged:photoDelegate.updateAdmission()}
            width:photos.width;height:photos.height
            JpegPlaybackSurface {
                id:picture;anchors.fill:parent
                loadRequested:page.presented && !page.gridMode && photoDelegate.admitted && photoDelegate.inWindow
                ioReady:page.storageReady
                jpegComplete:true // provider, not the UI, verifies the JPEG stream
                jpegSource:page.sourceFor(model.display)
                acceptInteractions:true
                nativeWidth:typeof model.imageWidth!=="undefined"?Number(model.imageWidth):0
                nativeHeight:typeof model.imageHeight!=="undefined"?Number(model.imageHeight):0
                onZoomFactorChanged:if(index===photos.currentIndex)page.zoom=zoomFactor
                onTapped:page.interaction()
                onDoubleTapped:{picture.toggleNativeZoom();page.interaction()}
                onImageStatusChanged:if(index===photos.currentIndex && (imageStatus===Image.Ready || imageStatus===Image.Error)){page.currentPreviewReady=imageStatus===Image.Ready;page.currentPresented(imageStatus===Image.Ready)}
            }
            Timer {
                property int attempts:0
                interval:1000;repeat:true
                running:page.presented && page.storageReady && !page.automatic && !page.gridMode && index===photos.currentIndex && picture.imageStatus===Image.Error && attempts<3
                onTriggered:{attempts++;picture.reload()}
            }
        }
    }
    JpegPlaybackSurface {
        id:automaticPhoto;objectName:"AutomaticJpegPlayback";anchors.fill:parent
        visible:page.automatic
        loadRequested:page.presented && page.storageReady && page.automatic && page.captureFileName!==""
        jpegComplete:true
        jpegSource:page.captureImageSource
        // A missing/incomplete file is not completion of automatic playback.
        onImageStatusChanged:if(page.automatic && imageStatus===Image.Ready)page.currentPresented(true)
    }
    Timer {
        interval:500;repeat:true
        running:page.presented && page.storageReady && page.automatic && page.captureFileName!=="" && automaticPhoto.imageStatus===Image.Error
        onTriggered:page.captureWriteProgress()
    }
    GridView {
        id:thumbnails;anchors.fill:parent;anchors.topMargin:64
        visible:page.gridMode;clip:true;cellWidth:width/3;cellHeight:height/3
        model:page.presented && page.gridMode && !page.automatic?page.catalogue:null
        delegate:Item {
            width:thumbnails.cellWidth;height:thumbnails.cellHeight
            JpegPlaybackSurface {anchors.fill:parent;anchors.margins:2;thumbnail:true;loadRequested:page.presented && page.storageReady && page.gridMode;jpegComplete:true;jpegSource:page.sourceFor(model.display)}
            Text {anchors.centerIn:parent;text:page.sourceFor(model.display)===""?model.display:"";color:"white";font.pixelSize:20;width:parent.width-12;elide:Text.ElideRight;horizontalAlignment:Text.AlignHCenter}
            MouseArea {anchors.fill:parent;onClicked:{page.openItem(index);page.interaction()}}
        }
    }
    MouseArea {
        anchors.right:parent.right;y:0;width:64;height:64;visible:!page.automatic
        onClicked:{page.gridMode=!page.gridMode;page.interaction()}
        Text {anchors.centerIn:parent;text:"▦";font.pixelSize:32;color:"white"}
    }
    MouseArea {
        x:72;y:0;width:64;height:64;visible:page.gridMode
        onClicked:{page.directoryUp();page.interaction()}
        Text {anchors.centerIn:parent;text:"..";font.pixelSize:32;color:"white"}
    }
    MouseArea {
        x:0;y:0;width:64;height:64
        onClicked:page.backRequested()
        HblUi.NavigationChevron {anchors.centerIn:parent}
    }
    Rectangle {
        x:64;y:0;width:parent.width-128;height:52;color:"#B0000000";visible:!page.gridMode
        Text {x:8;y:2;width:parent.width-16;height:24;color:"white";font.pixelSize:20;elide:Text.ElideMiddle;text:page.currentMetadata.name || ""}
        Text {x:8;y:27;width:parent.width-16;height:22;color:"white";font.pixelSize:16;elide:Text.ElideRight;text:String(page.currentMetadata.date || "").replace('T',' ')}
    }
    Rectangle {
        anchors.bottom:parent.bottom;width:parent.width;height:34;color:"#B0000000";visible:!page.gridMode && page.zoom===1
        Text {anchors.centerIn:parent;color:"white";font.pixelSize:22;text:(page.currentMetadata.aperture?"f/"+page.currentMetadata.aperture+"    ":"")+(page.currentMetadata.shutter || "")+(page.currentMetadata.iso?"    ISO "+page.currentMetadata.iso:"")}
    }
}
