"""为原厂 RAW 高清请求补充有限重试，不替换取图或解码器。"""
def apply_raw_replay_recovery(values, folder):
    key='/components/MediaBrowseView.qml'
    text=values[key]
    marker='    property alias residentZoomSource: flick_fullimg.source'
    assert text.count(marker)==1
    text=text.replace(marker,'''    FullResolutionRetry {
        objectName: "RawFullResolutionRetry"
        requestActive: root.residentSessionActive && root.residentImagesEnabled && root.state==="zooming"
        storageReady: ContentModel.isBrowsingPossible
        requestIdentity: String(root.residentEpoch)+":"+String(media_list.currentIndex)
        imageStatus: flick_fullimg.status
        imageWidth: flick_fullimg.sourceSize.width
        imageHeight: flick_fullimg.sourceSize.height
        expectedWidth: flick.knownWidth
        expectedHeight: flick.knownHeight
        onReloadRequested: {
            var original=flick_fullimg.source
            if(original.toString()==="")return
            flick_fullimg.source=""
            flick_fullimg.source=original
        }
    }
'''+marker)
    values[key]=text
    values['/components/FullResolutionRetry.qml']=(folder/'FullResolutionRetry.qml').read_text(encoding='utf-8')
