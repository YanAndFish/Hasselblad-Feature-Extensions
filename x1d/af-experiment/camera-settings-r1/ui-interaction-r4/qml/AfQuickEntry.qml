import QtQuick 2.5

Item {
    id: entry
    objectName: "AfQuickEntry"
    property bool available: true
    readonly property bool pageOpen: pageLoader.active
    function openPage() { if (available && visible) pageLoader.active = true }
    function closePage() { pageLoader.active = false }
    onAvailableChanged: if (!available) closePage()
    onVisibleChanged: if (!visible) closePage()

    Rectangle {
        objectName: "AfQuickEntryButton"
        anchors.centerIn: parent
        width: 112; height: 48; radius: 6
        visible: entry.available && !entry.pageOpen
        color: buttonArea.pressed ? "#252525" : "#101010"
        border.color: "#626262"; border.width: 1
        Text {
            anchors.centerIn: parent
            text: "AF 设置"; color: "#dddddd"; font.pixelSize: 22
        }
        MouseArea {
            id: buttonArea
            anchors.fill: parent
            onClicked: entry.openPage()
        }
    }
    Loader {
        id: pageLoader
        objectName: "AfQuickPageLoader"
        anchors.fill: parent
        active: false
        visible: active
        focus: active
        source: "qrc:/af-settings/AfSettingsHost.qml"
        onLoaded: {
            item.afCloseRequested.connect(entry.closePage)
            item.populateModel("cameraSettingsAdvancedAF")
            item.forceActiveFocus()
        }
    }
}
