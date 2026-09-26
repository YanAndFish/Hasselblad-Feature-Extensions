import "qrc:///scripts/Keys.js" as MKeys
import QtQuick 2.0

// Slider
Rectangle {
    id: sliderWrapper
    objectName: "settingsSlider"
    color: "transparent"
    property color lineColor: enabled ? "white" : "grey"
    property color markerColor: "black"
    property real value: 1
    signal userEdited(real editedValue)
    function commitUserValue(editedValue) {
        if (!visible || !enabled || editedValue === value) return
        userEdited(editedValue)
    }
    property int tickCount: Math.min((maxValue - minValue) / stepValue, 10) + 1
    property int maxValue: 5
    property int minValue: -5
    property int stepValue: 1
    property real realValue: Math.round((minValue + ((slidingMarker.x - horizontalLine.x + slidingMarker.width / 2) / horizontalLine.width * (maxValue - minValue))) / stepValue) * stepValue
    property int markerSize: 36
    property int zeroMarkerSize: 13
    property real stepSize: 0.5
    property int lineThickness: constants.sliderThickness

    property int sideMargin: (width - 60)/ 10 * (11 - tickCount) / 2 + 30

    Keys.onPressed: {
        var newValue = value
        if(MKeys.pressedFn("NAVLEFT", event.key)) {
            console.log("Slider got key event")
            event.accepted = true
            newValue = newValue - 0.5
            if(newValue < minValue)
            {
                newValue = minValue;
            }
            commitUserValue(newValue)
        }
        else if(MKeys.pressedFn("NAVRIGHT", event.key))
        {
            event.accepted = true
            newValue = newValue + 0.5
            if(newValue > maxValue)
            {
                newValue = maxValue;
            }
            commitUserValue(newValue)
        }
    }

    // Icon
    Item {
        id: slider
        anchors.fill: parent

        // Horizontal line
        Rectangle {
            color: lineColor
            id: horizontalLine
            height: lineThickness
            anchors {
                left: parent.left
                right: parent.right
                verticalCenter: slidingMarker.verticalCenter
            }
        }
/*
        // Ticks, variable amount. Create dynamically, since we have variable number of ticks
        property string sc: "import QtQuick 2.0; Rectangle {
                width: 5;
                height: 20;
                color: lineColor;
                anchors.verticalCenter: horizontalLine.verticalCenter
                property int index
                x: horizontalLine.width / (tickCount - 1) * index - width / 2 + horizontalLine.x
            }"
        Component.onCompleted: {
            for (var iTick = 0; iTick < tickCount; ++iTick){
                var tick = Qt.createQmlObject(sc, slider, 'tick' + iTick);
                tick.index = iTick
                console.log("tick: ", iTick, tick.x)
            }
        }
*/
        // Zero marker
        Rectangle {
            width: lineThickness;
            height: zeroMarkerSize;
            color: lineColor
            anchors.centerIn: horizontalLine
        }

        // Sliding marker
        Rectangle {
            id: slidingMarker
            anchors.verticalCenter: parent.verticalCenter
            z: 1
            color: sliderMouseArea.containsPress || sliderMouseArea.drag.active ? constants.highlightColor : markerColor
            border.width: lineThickness
            border.color: lineColor
            radius: markerSize / 2
            width: markerSize
            height: markerSize
            x: horizontalLine.x - width / 2 + horizontalLine.width / (maxValue - minValue) * (value - minValue)
        }

        MouseArea {
            id: sliderMouseArea
            onClicked: { }

            preventStealing: true
            anchors {
                verticalCenter: slidingMarker.verticalCenter
                horizontalCenter: slidingMarker.horizontalCenter
            }
            height: slidingMarker.height * 2.4
            width: height * 1.5
            propagateComposedEvents: false
            drag {
                target: slidingMarker
                axis: Drag.XAxis
                minimumX: horizontalLine.x - slidingMarker.width / 2
                maximumX: horizontalLine.x + horizontalLine.width - slidingMarker.width / 2
            }

            drag.onActiveChanged: {
                if (!drag.active) {
                    // Calculate corresponding value, correct placement of slider
                    commitUserValue(realValue)
                }
            }
        }
    }
}
