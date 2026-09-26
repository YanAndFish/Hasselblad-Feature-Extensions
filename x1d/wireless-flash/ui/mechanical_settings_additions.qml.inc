
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
            text: "机械快门 · FPGA 试验"
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
                Text { text: "FPGA 信号试验"; color: "white"; font.pixelSize: 23 * hblRfPanel.unit }
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
                    text: "自动引闪：" + (mainRoot.hblRfEnabled ? "开 · 点击关闭" : "关 · 点击开启")
                    color: "white"; font.pixelSize: 21 * hblRfPanel.unit
                }
                MouseArea {
                    anchors.fill: parent
                    onClicked: { if (mainRoot.hblRfEnabled || (mainRoot.hblRfReady && !mainRoot.hblRfBusy)) mainRoot.hblRfConfigure(!mainRoot.hblRfEnabled, mainRoot.hblRfDelayUs) }
                }
            }
            Text {
                text: "触发信号 · 开启后每拍最多一次"
                color: "white"; font.pixelSize: 21 * hblRfPanel.unit
            }
            Grid {
                columns: 2; spacing: 8 * hblRfPanel.unit
                Repeater {
                    model: ["A 路首次同步", "B 路首次同步", "启动保持置位", "退出空闲", "状态 1 置位", "状态 3 置位", "返回空闲"]
                    delegate: Rectangle {
                        width: (hblRfContent.width - 8*hblRfPanel.unit)/2
                        height: 52*hblRfPanel.unit; radius: 4
                        color: mainRoot.hblRfSource===index ? "#805829" : "#303030"
                        Text { anchors.centerIn: parent; text: modelData; color: "white"; font.pixelSize: 20*hblRfPanel.unit }
                        MouseArea { anchors.fill: parent; onClicked: mainRoot.hblRfSelectSource(index) }
                    }
                }
            }
            Text {
                text: "本信号延迟：" + (mainRoot.hblRfDelayUs/1000).toFixed(2) + " ms"
                color: "#E3A156"; font.pixelSize: 22*hblRfPanel.unit
            }
            Row {
                spacing: 8*hblRfPanel.unit
                Repeater {
                    model: ["−"+mainRoot.hblRfStepUs, "归零", "+"+mainRoot.hblRfStepUs]
                    delegate: Rectangle {
                        width: (hblRfContent.width-16*hblRfPanel.unit)/3; height: 52*hblRfPanel.unit
                        color: "#303030"; radius: 4
                        Text { anchors.centerIn: parent; text: modelData; color: "white"; font.pixelSize: 22*hblRfPanel.unit }
                        MouseArea { anchors.fill: parent; onClicked: mainRoot.hblRfAdjustDelay(index===1 ? 0 : mainRoot.hblRfDelayUs+(index===0 ? -1:1)*mainRoot.hblRfStepUs) }
                    }
                }
            }
            Row {
                spacing: 8*hblRfPanel.unit
                Repeater {
                    model: [10,100,1000]
                    delegate: Rectangle {
                        width: (hblRfContent.width-16*hblRfPanel.unit)/3; height: 44*hblRfPanel.unit
                        color: mainRoot.hblRfStepUs===modelData ? "#68451D" : "#242424"
                        Text { anchors.centerIn: parent; text: "步长 "+modelData+" us"; color: "white"; font.pixelSize: 18*hblRfPanel.unit }
                        MouseArea { anchors.fill: parent; onClicked: mainRoot.hblRfStepUs=modelData }
                    }
                }
            }
            Text {
                width: parent.width; wrapMode: Text.WordWrap
                text: "开启一次即可连续测试；切换信号和延迟保持开启，下次拍摄生效。每项延迟单独保留。\n状态 1、3 的物理含义待确认；未读到变化则跳过本次。"
                color: "#BBBBBB"; font.pixelSize: 17*hblRfPanel.unit
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
                text: "CH 5 · ID 5 · D 组"
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
