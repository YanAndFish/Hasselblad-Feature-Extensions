import QtQuick 2.0
import com.hasselblad.camera 1.0
import com.hasselblad.globalstateinfo 1.0

// Only the reticle is drawn here. The camera still owns focus size, status,
// accepted position and the actual focus operation.
Item {
    id: frame
    objectName: "OwnViewfinderFocusFrame"
    property real sizeFactor: 1
    property bool previewActive: false
    property bool dragging: false
    property real previewX: 0.5
    property real previewY: 0.5
    readonly property real committedX: Camera.firstComponent(GlobalStateInfo.focusDelivery.displayed)
    readonly property real committedY: Camera.secondComponent(GlobalStateInfo.focusDelivery.displayed)
    readonly property real focusX: previewActive ? previewX : committedX
    readonly property real focusY: previewActive ? previewY : committedY
    readonly property real boxWidth: Math.max(28, Camera.firstComponent(Camera.focus_size) * width)
    readonly property real boxHeight: Math.max(28, Camera.secondComponent(Camera.focus_size) * height)
    readonly property color frameColor: Camera.findOngoing ? "#ffcf42" :
        Camera.lastAfResult === Camera.LastAfResultFound ? "#53d76a" :
        Camera.lastAfResult === Camera.LastAfResultNotFound ? "#ff6464" : "white"

    function preview(nx, ny) {
        previewX = Math.max(0, Math.min(1, nx))
        previewY = Math.max(0, Math.min(1, ny))
        previewActive = true
        dragging = true
        settleTimer.stop()
    }
    function releasePreview() {
        dragging = false
        settleTimer.restart()
    }
    function cancelPreview() {
        dragging = false
        previewActive = false
        settleTimer.stop()
    }
    onCommittedXChanged: {
        if (previewActive && !dragging &&
                Math.abs(committedX - previewX) < 0.005 &&
                Math.abs(committedY - previewY) < 0.005)
            cancelPreview()
    }
    onCommittedYChanged: {
        if (previewActive && !dragging &&
                Math.abs(committedX - previewX) < 0.005 &&
                Math.abs(committedY - previewY) < 0.005)
            cancelPreview()
    }
    Timer { id: settleTimer; interval: 1200; repeat: false; onTriggered: frame.cancelPreview() }

    Item {
        id: box
        objectName: "OwnViewfinderFocusBox"
        width: frame.boxWidth
        height: frame.boxHeight
        x: Math.max(0, Math.min(frame.width - width, frame.focusX * frame.width - width / 2))
        y: Math.max(0, Math.min(frame.height - height, frame.focusY * frame.height - height / 2))
        readonly property real arm: Math.max(9, Math.min(width, height) * 0.25)
        Repeater {
            model: 4
            delegate: Item {
                x: index % 2 ? box.width - width : 0
                y: index >= 2 ? box.height - height : 0
                width: box.arm
                height: box.arm
                Rectangle {
                    width: parent.width + 2
                    height: 4
                    x: -1
                    y: index >= 2 ? parent.height - height + 1 : -1
                    color: "black"
                }
                Rectangle {
                    width: 4
                    height: parent.height + 2
                    x: index % 2 ? parent.width - width + 1 : -1
                    y: -1
                    color: "black"
                }
                Rectangle {
                    width: parent.width
                    height: 2
                    y: index >= 2 ? parent.height - height : 0
                    color: frame.frameColor
                }
                Rectangle {
                    width: 2
                    height: parent.height
                    x: index % 2 ? parent.width - width : 0
                    color: frame.frameColor
                }
            }
        }
    }
}
