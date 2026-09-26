import QtQuick 2.5
import "qrc:/components" as HblUi

// Presentation owns no device interface. The adapter supplies live row values
// and validates edits before committing them through the original interfaces.
Rectangle {
    id: page
    objectName: "CustomSettingsPage"
    color: "black"
    property string title: ""
    property string fontName:""
    property var rows: []
    onRowsChanged:syncRows()
    ListModel {id:rowModel;dynamicRoles:true}
    function syncRows() {
        // Preserve delegates and their scroll position when only values change.
        for(var i=0;i<rows.length;i++) {
            var item={kind:"text",label:"",enabled:true,value:false,valueText:"",description:"",numberValue:0,minimum:0,maximum:1,step:1}
            for(var key in rows[i])item[key]=rows[i][key]
            if(i<rowModel.count)rowModel.set(i,item)
            else rowModel.append(item)
        }
        if(rowModel.count>rows.length)rowModel.remove(rows.length,rowModel.count-rows.length)
    }
    property real dragOffset: 0
    property bool returning: false
    property int rowHeight: (height-80)/5
    property int swipeThreshold: 20
    property int swipeDivisor: 5
    property bool adjusting:false
    signal backRequested()
    signal editRequested(int rowIndex)
    signal toggleRequested(int rowIndex, bool value)
    signal valueRequested(int rowIndex, real value)
    x: dragOffset

    function finishDrag() {
        returning=dragOffset>width/swipeDivisor
        settle.to=returning?width:0
        settle.restart()
    }
    NumberAnimation {
        id:settle;target:page;property:"dragOffset";duration:200;easing.type:Easing.OutCubic
        onStopped:if(page.returning){page.returning=false;page.backRequested()}
    }
    MouseArea {
        anchors.fill:parent
        drag.target:page.adjusting?null:page;drag.axis:Drag.XAxis;drag.minimumX:0;drag.maximumX:page.width
        drag.threshold:page.swipeThreshold;drag.filterChildren:true
        drag.onActiveChanged: {
            if(drag.active)settle.stop()
            else {page.dragOffset=page.x;page.x=Qt.binding(function(){return page.dragOffset});page.finishDrag()}
        }
        Text {
            x:70;y:8;width:parent.width-140;height:56
            text:page.title;color:"white";font.pixelSize:28;font.family:page.fontName
            horizontalAlignment:Text.AlignHCenter;verticalAlignment:Text.AlignVCenter
        }
        Item {
            x:4;y:8;width:60;height:56
            HblUi.NavigationChevron {anchors.centerIn:parent}
            MouseArea {anchors.fill:parent;onClicked:page.backRequested()}
        }
        ListView {
            id:list;objectName:"CustomSettingsList"
            x:24;y:80;width:parent.width-48;height:parent.height-y
            clip:true;model:rowModel;flickableDirection:Flickable.VerticalFlick
            boundsBehavior:Flickable.StopAtBounds
            delegate:Item {
                id:row
                property var entry:rowModel.get(index)
                property bool heading:entry.kind==="heading"
                property bool toggle:entry.kind==="toggle"
                property bool slider:entry.kind==="slider"
                property bool action:entry.kind==="action"
                property bool available:entry.enabled!==false
                width:list.width
                height:heading?54:page.rowHeight+(slider?46:0)+(entry.description?26:0)
                Rectangle {y:4;width:parent.width;height:1;color:"#555";visible:row.heading && index>0}
                Text {
                    id:rowLabel
                    x:0;y:row.heading?15:0
                    width:row.heading || row.slider?parent.width:row.action?Math.min(330,parent.width):row.toggle?parent.width-110:valueLabel.x-24
                    height:row.heading?34:page.rowHeight
                    text:row.entry.label || "";color:row.heading?"#aaa":"white"
                    opacity:row.available?1:0.45
                    font.pixelSize:row.heading?24:36
                    font.family:page.fontName
                    verticalAlignment:Text.AlignVCenter
                    elide:Text.ElideRight
                    horizontalAlignment:row.action?Text.AlignHCenter:Text.AlignLeft
                }
                Rectangle {
                    x:0;y:10;width:Math.min(330,parent.width);height:page.rowHeight-20
                    color:"transparent";border.width:2;border.color:row.available?"#e5783f":"#555"
                    visible:row.action
                }
                Text {
                    id:valueLabel
                    x:Math.min(parent.width*0.55,rowLabel.implicitWidth+24);width:parent.width-x;height:page.rowHeight
                    text:row.entry.valueText || "";visible:!row.heading && !row.toggle && !row.slider && !row.action
                    color:"white";opacity:row.available?1:0.45;font.pixelSize:36;font.family:page.fontName
                    horizontalAlignment:Text.AlignRight;verticalAlignment:Text.AlignVCenter
                    elide:Text.ElideRight
                }
                SettingsToggle {
                    x:parent.width-width;y:(page.rowHeight-height)/2
                    visible:row.toggle;checked:!!row.entry.value;available:row.available
                }
                Text {
                    x:0;y:(page.rowHeight+rowLabel.font.pixelSize)/2+8;width:parent.width;height:28
                    visible:!row.heading && !!row.entry.description
                    text:row.entry.description || "";color:"#aaa";font.pixelSize:18;font.family:page.fontName;elide:Text.ElideRight
                }
                MouseArea {
                    anchors.fill:parent;enabled:!row.heading && row.available && row.entry.kind!=="text" && !row.slider
                    onClicked:if(row.toggle)page.toggleRequested(index,!row.entry.value);else page.editRequested(index)
                }
                Item {
                    x:0;y:page.rowHeight+(row.entry.description?26:0);width:parent.width;height:46
                    visible:row.slider
                    Rectangle {x:12;width:parent.width-24;height:2;anchors.verticalCenter:parent.verticalCenter;color:"#aaa"}
                    Rectangle {
                        objectName:"SettingSliderKnob"
                        width:28;height:28;radius:14;color:"white";anchors.verticalCenter:parent.verticalCenter
                        x:12-14+(parent.width-24)*Math.max(0,Math.min(1,((sliderTouch.pressed || sliderTouch.awaitingValue?sliderTouch.previewValue:row.entry.numberValue)-row.entry.minimum)/(row.entry.maximum-row.entry.minimum || 1)))
                    }
                    MouseArea {
                        id:sliderTouch
                        property real previewValue:0
                        property bool awaitingValue:false
                        property double readbackDeadline:0
                        anchors.fill:parent;enabled:row.available;preventStealing:true
                        Timer {
                            interval:50;repeat:true;running:sliderTouch.awaitingValue && !sliderTouch.pressed
                            onTriggered:if(Math.abs(row.entry.numberValue-sliderTouch.previewValue)<0.00001 || Date.now()>sliderTouch.readbackDeadline)sliderTouch.awaitingValue=false
                        }
                        function updateValue(px){
                            var lo=row.entry.minimum,hi=row.entry.maximum,step=row.entry.step || 1
                            var value=lo+Math.max(0,Math.min(1,(px-12)/(width-24)))*(hi-lo)
                            previewValue=Math.max(lo,Math.min(hi,lo+Math.round((value-lo)/step)*step))
                            awaitingValue=true;readbackDeadline=Date.now()+2000
                            page.valueRequested(index,previewValue)
                        }
                        onPressed:{page.adjusting=true;updateValue(mouse.x)}
                        onPositionChanged:if(pressed)updateValue(mouse.x)
                        onReleased:page.adjusting=false
                        onCanceled:page.adjusting=false
                    }
                }
            }
        }
    }
}

