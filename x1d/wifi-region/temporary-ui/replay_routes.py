"""X1D 1.25 回放入口候选补丁。尚未接入默认装载构建。"""

def once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('回放入口基线不匹配: '+old[:80])
    return source.replace(old, new, 1)


def apply_replay_routes(source):
    source = once(source, 'property int photosAddedInSession: 0', '''property int photosAddedInSession: 0
    property bool jpegAutomaticEntry:false
    property string jpegCaptureIdentity:""
    function enterCaptureReplay(state) {
        jpegAutomaticEntry=true
        if(media_browse_loader.item) {
            media_browse_loader.item.prepareCapture(jpegCaptureIdentity)
            if(media_browse_loader.presented) {
                media_browse_loader.item.residentEnter(true,false,-1)
                media_browse_loader.item.captureCompleted(jpegCaptureIdentity)
            }
        }
        setState(state)
    }
    Connections {
        target:Camera
        onExposingChanged:if(Camera.exposing) {
            root.jpegCaptureIdentity=""
            if(media_browse_loader.item)media_browse_loader.item.prepareCapture("")
        }
    }''')
    source = once(source, 'states.state = state\n    }', '''states.state = state
        if(state!=="browse_view" && state!=="instant_preview")jpegAutomaticEntry=false
    }''')
    # Both capture-triggered paths can enter browse_view on X1D. Mark their
    # origin explicitly without changing ordinary manual browse navigation.
    for begin, end in [('    onPhotosAddedInSessionChanged:', '\n    Timer {'),
                       ('        onImageAdded: {', '\n        // When a card')]:
        a=source.index(begin);b=source.index(end,a)
        part=source[a:b]
        part=part.replace('setState("browse_view")', 'enterCaptureReplay("browse_view")')
        part=part.replace('setState("instant_preview")', 'enterCaptureReplay("instant_preview")')
        if 'onImageAdded' in begin:
            part=part.replace('onImageAdded: {', '''onImageAdded: {
            root.jpegCaptureIdentity=String(ContentModel.getAddedImageName() || "")''',1)
        source=source[:a]+part+source[b:]
    source=once(source, 'source: "qrc:///components/MediaBrowseView.qml"',
                'source: "qrc:///components/NativePhotoPlayback.qml"')
    source=once(source, 'item.residentEnter(isInstantPreview, false, -1)', '''item.prepareCapture(root.jpegCaptureIdentity)
                    item.residentEnter(root.jpegAutomaticEntry || isInstantPreview, false, -1)''')
    source=once(source, 'if (presented && item) item.isInstantPreview = isInstantPreview',
                'if (presented && item) residentPresent()')
    source=once(source, 'onCurrentItemLoaded: root.notifyCurrentImageLoaded()', '''onCurrentItemLoaded: root.notifyCurrentImageLoaded()
        onCloseRequested: setToControl()''')
    return source


def apply_evf_replay(resources):
    source=resources['/liveview/EVFWindow.qml']
    source=once(source,'function openPreView(showLastItem, startTimer)',
                'function openPreView(showLastItem, startTimer, captureIdentity)')
    source=once(source,'preView.startIndex = showLastItem ? -1 : GlobalStateInfo.mediaIndex',
                '''preView.automatic = captureIdentity !== undefined
        preView.captureIdentity = String(captureIdentity || "")
        preView.startIndex = showLastItem ? -1 : GlobalStateInfo.mediaIndex''')
    source=once(source,'property bool startTimer: false','property bool startTimer: false\n            property bool automatic:false\n            property string captureIdentity:""')
    source=once(source,'source: "qrc:///components/MediaBrowseView.qml"','source: "qrc:///components/NativePhotoPlayback.qml"')
    source=once(source,'item.residentEnter(false, true, startIndex)','item.prepareCapture(captureIdentity)\n                    item.residentEnter(automatic, true, startIndex)')
    source=once(source,'if (startTimer) {','if (startTimer && item.hasLoadedCurrent) {')
    start=source.index('//                onCurrentItemLoaded: {')
    end=source.index('                onKeyPressed:',start)
    source=source[:start]+'''                onCurrentItemLoaded: {
                    if(preView.startTimer){preView.startTimer=false;evfPreviewTimer.restart()}
                }
                onCloseRequested:root.closePreView()
'''+source[end:]
    resources['/liveview/EVFWindow.qml']=source
    source=resources['/main.qml']
    source=once(source,'mainWindow.item.photosAddedInSession++',
                'mainWindow.item.jpegCaptureIdentity=String(ContentModel.getAddedImageName() || "")\n                mainWindow.item.photosAddedInSession++')
    source=once(source,'evfWindow.item.openPreView(true, configstore.EVFPreviewTimeout > 0)',
                'evfWindow.item.openPreView(true, configstore.EVFPreviewTimeout > 0, String(ContentModel.getAddedImageName() || ""))')
    source=once(source,'evfWindow.item.openPreView(false, false)',
                'evfWindow.item.openPreView(false, false, mainWindow.item.jpegCaptureIdentity)')
    resources['/main.qml']=source
