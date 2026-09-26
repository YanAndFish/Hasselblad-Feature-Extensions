    // 左滑：拍摄参数 → 引闪；右滑返回。只有界面动作，不触发准备或发射。
    MouseArea {
        id: formalFlashSwipe
        objectName: "FormalFlashSwipe"
        anchors.fill: parent
        drag.filterChildren: !scope.popupOpen && !formalFlashPage.popupOpen && !formalFlashPage.powerGestureActive
        drag.target: !scope.popupOpen && !formalFlashPage.popupOpen && !formalFlashPage.powerGestureActive ? formalFlashTrack : null
        drag.axis: Drag.XAxis
        drag.minimumX: -width
        drag.maximumX: 0
        drag.threshold: constants.dragThreshold
        property bool secondPage: false
        property real turnDistance: Math.min(width/5, 80)
        function openFlashPage() { secondPage=true; formalFlashTrack.x=-width }
        function closeFlashPage() { secondPage=false; formalFlashTrack.x=0 }
        drag.onActiveChanged: if (!drag.active) {
            secondPage=secondPage ? formalFlashTrack.x<=-width+turnDistance : formalFlashTrack.x < -turnDistance
            formalFlashTrack.x=secondPage ? -width : 0
        }
        Item {
            id: formalFlashTrack
            objectName: "FormalFlashTrack"
            width: scope.width; height: scope.height
            Behavior on x { enabled: !formalFlashSwipe.drag.active; NumberAnimation { duration: 180; easing.type: Easing.InOutQuad } }
            // 空白和只读文字也从本手势树内接收按下，原参数按钮保持在其上层。
            MouseArea {
                objectName: "FormalControlBlankArea"
                anchors.fill: parent
                z: -1
                enabled: !scope.popupOpen && !formalFlashPage.popupOpen
                onPressed: mouse.accepted=true
            }
            FlashPage {
                id: formalFlashPage
                x: width; width: scope.width; height: scope.height
                pageActive: scope.visible && formalFlashSwipe.secondPage
                onBackRequested: formalFlashSwipe.closeFlashPage()
            }
        }
    }
