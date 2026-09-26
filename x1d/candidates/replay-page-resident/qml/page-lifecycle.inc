    // resident_idle: 页面骨架存在，照片 delegate/请求未接入。
    // residentEnter/Leave 为唯一会话边界；编号使旧 delegate 失效。
    property bool residentConstructed: false
    property bool residentSessionActive: false
    property bool residentActivating: false
    property bool residentImagesEnabled: false
    property bool residentVideoRequested: false
    property int residentEpoch: 0
    property int residentEntries: 0
    property int residentExits: 0
    property alias residentListCount: media_list.count
    property alias residentGridCount: media_grid.count
    property alias residentZoomSource: flick_fullimg.source
    property alias residentZoomPreviewSource: flick_img.source
    Connections {
        target: root.residentSessionActive ? ContentModel : null
        onCurrentWorkingDirChanged: addFolderTimer.stopTimer()
    }

    function residentEnter(preview, evf, index) {
        if (!residentConstructed) return false
        if (residentSessionActive) {
            isInstantPreview = preview
            return true
        }
        residentActivating = true
        residentEpoch++
        usedInEVF = evf
        isInstantPreview = preview
        initIndex = index
        nextIndex = -1
        hasLoadedCurrent = false
        fromBrowseDir = false
        keepStateGridOnSizeChange = false
        fromVideoPlayback = false
        isInStartState = true
        allowDimming = true
        directoryUpHighLight = false
        addFolderHighLight = false
        filterButtonHighLight = false
        imageRatingActive = false
        pinching = false
        previousActiveCard = (ContentModel.browseVolume !== 255) ? ContentModel.browseVolume : 0
        SortedContentModel.showOnlyImages(false)
        residentSessionActive = true
        media_grid.currentIndex = media_grid.count - 1
        state = (model.source.pathType === ContentModel.PATH_TYPE_FILES) && (model.listSize > 0) ? "list" : "grid"
        if (!usedInEVF) checkNewImage()
        var entryIndex = Math.max(-1, Math.min(media_list.currentIndex, media_list.count - 1))
        residentActivating = false
        // when 状态重新接通可能再次运行 list 脚本；恢复本次已选中的索引后才开放图像。
        if (state === "list") {
            media_list.currentIndex = entryIndex
            media_list.positionViewAtIndex(entryIndex, ListView.Center)
        }
        if (!usedInEVF) GlobalStateInfo.mediaIndex = media_list.currentIndex
        GlobalStateInfo.greyBalanceIndex = SortedContentModel.proxyToSrcIndex(media_list.currentIndex)
        if (media_list.currentIndex !== media_list.count - 1) {
            isInStartState = false
            if (SortedContentModel.getData(media_list.count-1, ContentModel.RatingRole) === Config.RatingLastExposure)
                ContentModel.clearRatingLastExposure()
        }
        if (usedInEVF) GlobalStateInfo.evfBrowseViewState = state
        is9ViewActive = state === "grid"
        isIn9View(is9ViewActive)
        residentImagesEnabled = true
        residentEntries++
        return true
    }

    function residentLeave() {
        if (!residentSessionActive) return
        var wasVideo = state === "video_playback" || residentVideoRequested
        var oldVideo = video_overlay.fileName
        residentImagesEnabled = false
        residentSessionActive = false
        residentEpoch++
        residentActivating = false
        allowDimming = false
        // 先使旧回调失效，再停原页面动作和解除照片引用。
        xAnimation.stop()
        yAnimation.stop()
        zoomScaleAnimation.stop()
        listviewXAnimation.stop()
        zoom_timeout.stop()
        autoZoomLongPressTimer.stop()
        zoomTimer.stop()
        enableClickTimer.stop()
        flickDblClickTimer.stop()
        addFolderTimer.stop()
        overexpose_behaviour.set = false
        deletePopupLoader.deleteFile = false
        deletePopupLoader.active = false
        createFolderConfirmDialog.active = false
        browseSelectLoader.active = false
        imageRateFailedPopup.openInternal = false
        imageRateFailedPopup.error = 0
        addFolderPopup.visible = false
        flick_img.source = ""
        flick_fullimg.source = ""
        flick.resizeContent(root.width, root.height, Qt.point(0, 0))
        flick.contentX = 0
        flick.contentY = 0
        flick.knownWidth = 0
        flick.knownHeight = 0
        zoomScaleAnimation.requestOngoing = false
        zoomIndicator.opacity = 0
        state = "resident_idle"
        hasLoadedCurrent = false
        nextIndex = -1
        initIndex = -1
        imageRatingActive = false
        pinching = false
        is9ViewActive = false
        isIn9View(false)
        if (usedInEVF) GlobalStateInfo.evfBrowseViewState = ""
        if (wasVideo) {
            VideoControl.setVideoPlaybackState(false, oldVideo, 0)
            preventIdleTimeout(false)
        }
        video_overlay.fileName = ""
        residentVideoRequested = false
        video_overlay.metaImgName = ""
        video_overlay.metaDateTime = ""
        ContentModel.clearRatingLastExposure()
        residentExits++
    }
