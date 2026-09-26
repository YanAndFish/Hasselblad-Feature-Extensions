
    // Additional entry on the original Wi-Fi settings page.
    Rectangle {
        id: hblRfEntry
        visible: root.itemValues === "generalSettingsWiFi" && !hblRfPanel.visible
        anchors.horizontalCenter: listViewArea.horizontalCenter
        anchors.bottom: listViewArea.bottom
        anchors.bottomMargin: 12
        width: Math.min(listViewArea.width - 32, 440)
        height: 52
        color: "#242424"
        border.color: "#777777"
        radius: 6
        Text {
            anchors.centerIn: parent
            text: "电子快门引闪（临时）"
            color: "white"
            font.pixelSize: 22
        }
        MouseArea { anchors.fill: parent; onClicked: hblRfPanel.visible = true }
    }

    Rectangle {
        id: hblRfPanel
        anchors.fill: root
        visible: false
        z: 100
        color: constants.menuBackgroundColor
        property real unit: width / 640
        onVisibleChanged: {
            if (visible) mainRoot.hblRfPrepare()
            else {
                mainRoot.hblRfPageClosed()
            }
        }
        MouseArea { anchors.fill: parent }
        Row {
                id: hblRfHeader
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.margins: 12 * hblRfPanel.unit
                height: 52 * hblRfPanel.unit
                spacing: 16 * hblRfPanel.unit
                Rectangle {
                    width: 110 * hblRfPanel.unit; height: 48 * hblRfPanel.unit
                    color: "#303030"; radius: 4
                    Text { anchors.centerIn: parent; text: "返回"; color: "white"; font.pixelSize: 19 * hblRfPanel.unit }
                    MouseArea { anchors.fill: parent; onClicked: hblRfPanel.visible = false }
                }
                Text { text: "电子快门 · 自动引闪"; color: "white"; font.pixelSize: 23 * hblRfPanel.unit }
        }
        Flickable {
            id: hblRfScroll
            anchors.top: hblRfHeader.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: hblRfTestButton.top
            clip: true
            contentWidth: width
            contentHeight: hblRfContent.height + 24 * hblRfPanel.unit
            flickableDirection: Flickable.VerticalFlick
            interactive: contentHeight > height
            maximumFlickVelocity: list.maximumFlickVelocity
            flickDeceleration: list.flickDeceleration
            boundsBehavior: list.boundsBehavior
            pressDelay: list.pressDelay
        Column {
            id: hblRfContent
            x: 12 * hblRfPanel.unit
            y: 8 * hblRfPanel.unit
            width: hblRfScroll.width - 24 * hblRfPanel.unit
            spacing: 12 * hblRfPanel.unit
            Rectangle {
                width: parent.width; height: 58 * hblRfPanel.unit
                color: mainRoot.hblRfEnabled ? "#68451D" : "#242424"
                Text {
                    anchors.centerIn: parent
                    text: "自动引闪：" + (mainRoot.hblRfEnabled ? "开" : "关")
                    color: "white"; font.pixelSize: 21 * hblRfPanel.unit
                }
                MouseArea {
                    anchors.fill: parent
                    onClicked: mainRoot.hblRfConfigure(!mainRoot.hblRfEnabled, mainRoot.hblRfDelayMs)
                }
            }
            Text {
                width: parent.width; wrapMode: Text.WordWrap
                text: "按本次快门自动计算闪光时机\n1/4 秒及更快：亮区居中\n0.3、0.4、0.5 秒：对齐全开区\n超过 0.5 秒：不自动引闪"
                color: "#E3A156"; font.pixelSize: 21 * hblRfPanel.unit
            }
            Text {
                width: parent.width; wrapMode: Text.WordWrap
                text: "临时规则；关机后失效。依据本机实拍近似模型。"
                color: "#BBBBBB"; font.pixelSize: 17 * hblRfPanel.unit
            }
            Text {
                text: "无线发射功率 · 增益索引 " + mainRoot.hblRfPowerIndex
                color: "white"; font.pixelSize: 21 * hblRfPanel.unit
            }
            Row {
                spacing: 8 * hblRfPanel.unit
                Repeater {
                    model: ["减弱", "恢复默认 10", "增强"]
                    delegate: Rectangle {
                        width: (hblRfContent.width - 16 * hblRfPanel.unit) / 3
                        height: 58 * hblRfPanel.unit
                        color: powerTouch.pressed ? "#805829" : "#303030"
                        radius: 4
                        Text {
                            anchors.centerIn: parent; text: modelData
                            color: "white"; font.pixelSize: 20 * hblRfPanel.unit
                        }
                        MouseArea {
                            id: powerTouch
                            anchors.fill: parent
                            onClicked: mainRoot.hblRfSetPower(index === 1 ? 10 :
                                Math.max(10, Math.min(100, mainRoot.hblRfPowerIndex + (index === 0 ? 5 : -5))))
                        }
                    }
                }
            }
            Text {
                width: parent.width; wrapMode: Text.WordWrap
                text: "数值越小，发射越强；设置时准备，显示已就绪后直接发射。"
                color: "#BBBBBB"; font.pixelSize: 17 * hblRfPanel.unit
            }
            Text {
                text: "CH 5 · ID 5 · D 组    按键收到 " + mainRoot.hblRfCount("manualClicks") + " 次"
                color: "#BBBBBB"; font.pixelSize: 19 * hblRfPanel.unit
            }
            Text {
                width: parent.width; wrapMode: Text.WordWrap
                text: "同步记录 " + mainRoot.hblRfCount("fpgaSamples") +
                      "   有效 " + mainRoot.hblRfCount("fpgaSynced") +
                      "   未确认 " + mainRoot.hblRfCount("fpgaSkipped") + "\n" +
                      "自动排入 " + mainRoot.hblRfCount("automaticQueued") +
                      "   已提交 " + mainRoot.hblRfCount("sentRequests") +
                      "   失败 " + mainRoot.hblRfCount("radioFailures") + "\n" +
                      "已取消 " + mainRoot.hblRfCount("cancelledRequests") +
                      "   无线忙跳过 " + mainRoot.hblRfCount("busySkips")
                color: "#BBBBBB"; font.pixelSize: 19 * hblRfPanel.unit
            }
            Text {
                width: parent.width; wrapMode: Text.WordWrap
                text: mainRoot.hblRfStatus
                color: "#BBBBBB"; font.pixelSize: 16 * hblRfPanel.unit
            }
        }
        }
        Rectangle {
            id: hblRfTestButton
            anchors.left: parent.left
            anchors.bottom: parent.bottom
            anchors.margins: 12 * hblRfPanel.unit
            width: 190 * hblRfPanel.unit
            height: 80 * hblRfPanel.unit
            color: hblRfTestTouch.pressed ? "#B57930" : mainRoot.hblRfBusy ? "#494039" : "#68451D"
            border.color: "#E3A156"; border.width: 2; radius: 6
            Column {
                anchors.centerIn: parent
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: mainRoot.hblRfBusy ? "处理中…" : mainRoot.hblRfReady ? "单次试闪" : "尚未就绪"
                    color: "white"; font.pixelSize: 24 * hblRfPanel.unit
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "按键收到 " + mainRoot.hblRfCount("manualClicks") + " 次"
                    color: "#E0D1C1"; font.pixelSize: 17 * hblRfPanel.unit
                }
            }
            MouseArea { id: hblRfTestTouch; anchors.fill: parent; onClicked: mainRoot.hblRfTestOnce() }
        }
        Text {
            anchors.left: hblRfTestButton.right
            anchors.right: parent.right
            anchors.verticalCenter: hblRfTestButton.verticalCenter
            anchors.margins: 16 * hblRfPanel.unit
            text: "CH 5 · ID 5 · D 组\n" + mainRoot.hblRfStatus
            color: "#BBBBBB"; font.pixelSize: 18 * hblRfPanel.unit
            wrapMode: Text.WordWrap
        }
    }
    onItemValuesChanged: if (itemValues !== "generalSettingsWiFi") hblRfPanel.visible = false
