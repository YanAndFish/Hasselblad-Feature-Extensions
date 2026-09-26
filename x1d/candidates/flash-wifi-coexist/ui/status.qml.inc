    Rectangle {
        z: 1000
        anchors.top: parent.top
        anchors.horizontalCenter: parent.horizontalCenter
        width: 310; height: 28; radius: 4
        color: typeof hblCoexist!=="undefined" && hblCoexist.enabled ? "#124f40" : "#282828"
        visible: typeof hblCoexist!=="undefined" && mainWindow.status===Loader.Ready &&
                 mainWindow.item && !mainWindow.item.sleeping && control.state!=="sleeping"
        Text {
            anchors.centerIn: parent
            text: typeof hblCoexist!=="undefined" ? hblCoexist.statusText : ""
            color: "white";font.pixelSize: 13
        }
        MouseArea {
            anchors.fill: parent
            enabled: typeof hblCoexist!=="undefined" && !hblCoexist.busy && !Camera.exposing && !Camera.inSession
            onClicked: hblCoexist.command=JSON.stringify({op:"enable",on:!hblCoexist.enabled})
        }
    }
