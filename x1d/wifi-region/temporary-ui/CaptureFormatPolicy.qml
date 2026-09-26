import QtQuick 2.5
import com.hasselblad.config 1.0
import com.hasselblad.systemmanager 1.0
import com.hasselblad.camera 1.0

// Enforce through the existing config interface, never through a replacement
// encoder. Wait until initialization/capture is finished before correcting it.
Item {
    property var actualFormat: configstore.image_format
    property bool canApply: System.system_state === System.StateUp && !Camera.inSession && !Camera.exposing
    onActualFormatChanged: apply.restart()
    onCanApplyChanged: apply.restart()
    Component.onCompleted: apply.restart()
    Timer {
        id: apply; interval: 0
        onTriggered: {
            if (canApply && actualFormat !== undefined && actualFormat !== Config.RawJpg)
                configstore.image_format = Config.RawJpg
        }
    }
}
