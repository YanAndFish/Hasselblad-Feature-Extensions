    Rectangle {
        id: persistentProbeButton
        objectName: "hblPersistentWifiProbeButton"
        visible: root.itemValues === "generalSettingsWiFi"
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 14
        width: 300
        height: 58
        radius: 5
        color: probeMouse.pressed ? "#454545" : "#252525"
        border.color: "#a0a0a0"
        border.width: 1
        z: 10
        Text {
            anchors.centerIn: parent
            text: "Persistence test"
            color: "white"
            font.pixelSize: 26
        }
        MouseArea {
            id: probeMouse
            objectName: "hblPersistentWifiProbeMouse"
            anchors.fill: parent
            // 空按钮：仅按压外观，无点击回调，不访问相机属性。
        }
    }
