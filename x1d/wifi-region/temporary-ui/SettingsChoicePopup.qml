import QtQuick 2.5
import com.hasselblad.settings 1.0
import "qrc:///scripts/Keys.js" as MKeys

// Own rendering; firmware Settings remains the value conversion boundary.
FocusScope {
    id:root
    objectName:"SettingsChoicePopup"
    visible:false
    z:100
    property alias popupAnchor:panel.anchors
    property Item returnToItem
    property var theProxy
    property string thePropertyName:""
    property var choices:[]
    property var viewfinderChoices:["正常","电子取景器","屏幕取景"]
    property var radioChoices:["关","Wi-Fi","引闪"]
    property string mode:"setting"
    property bool parameterStyle:false
    signal selectedParameter(string value)
    signal closed()
    function present(returnItem, values, current) {
        returnToItem=returnItem;choices=values;visible=true;enabled=true
        list.currentIndex=Math.max(0,values.indexOf(current))
        list.positionViewAtIndex(list.currentIndex,ListView.Center)
        forceActiveFocus()
    }
    function open(returnItem, proxy, propertyName) {
        mode="setting";theProxy=proxy;thePropertyName=propertyName
        present(returnItem,Settings.getVariableListModel(propertyName),Settings.getUntranslatedDisplayValue(propertyName,proxy[propertyName]))
    }
    function openViewfinder(returnItem, currentMode) {
        mode="viewfinder";theProxy=undefined;thePropertyName=""
        present(returnItem,viewfinderChoices,viewfinderChoices[currentMode])
    }
    function openRadio(returnItem, currentMode) {
        mode="radio";theProxy=undefined;thePropertyName=""
        present(returnItem,radioChoices,radioChoices[currentMode])
    }
    function saveViewfinder(text) {
        var i=viewfinderChoices.indexOf(text)
        if(i<0 || typeof hblNative==="undefined")return
        hblNative.viewfinderMode=i
        if(hblNative.viewfinderMode===i)configstore.CustomOption_LiveViewEVFOnly=i===1
    }
    function itemSelected(value) {
        if(mode==="parameter")selectedParameter(String(value))
        else if(mode==="viewfinder")saveViewfinder(value)
        else if(mode==="radio") {
            var i=radioChoices.indexOf(value)
            if(i>=0 && typeof hblNative!=="undefined" && hblNative.radioModeVerified && !hblNative.radioModeBusy && i!==hblNative.radioMode)
                hblNative.command=JSON.stringify({op:"radioMode",mode:i})
        }else if(theProxy!==undefined)Settings.setSettingValue(theProxy,thePropertyName,value)
        close()
    }
    function setSelected(){if(list.currentIndex>=0 && list.currentIndex<choices.length)itemSelected(choices[list.currentIndex])}
    function close(){visible=false;focus=false;if(returnToItem && returnToItem!==root)returnToItem.forceActiveFocus();closed()}
    Keys.onPressed:{
        event.accepted=true
        if(MKeys.pressedFn("LISTUP",event.key))list.decrementCurrentIndex()
        else if(MKeys.pressedFn("LISTDOWN",event.key))list.incrementCurrentIndex()
        else if(MKeys.pressedFn("SELECT",event.key) || (parameterStyle && MKeys.pressedFn("POPACCEPT",event.key)))setSelected()
        else if(MKeys.pressedFn("ESCAPE",event.key) || (parameterStyle && (MKeys.pressedFn("MENU",event.key) || MKeys.pressedFn("PLAY",event.key))))close()
        else if(parameterStyle && MKeys.pressedFn("AF_MF",event.key)){}
        else event.accepted=false
    }
    Rectangle {
        anchors.fill:parent;color:constants.popupFadeoutColor;opacity:root.visible?constants.fadeOutOpacity:0
        Behavior on opacity {NumberAnimation {duration:constants.fadeOutDuration;easing.type:Easing.OutCubic}}
    }
    MouseArea {anchors.fill:parent;onClicked:root.setSelected()}
    Rectangle {
        id:panel;color:constants.popupBackgroundColor;radius:root.parameterStyle?constants.outerBoxRadius:0
        anchors {left:parent.left;right:parent.right;top:parent.top;bottom:parent.bottom;leftMargin:260;rightMargin:24;topMargin:82;bottomMargin:82}
        MouseArea {anchors.fill:parent}
        ListView {
            id:list;objectName:"OwnChoiceList";anchors.fill:parent;clip:true
            property real cellHeight:height/constants.numberOfItemsVisibleInList
            model:root.choices;boundsBehavior:Flickable.StopAtBounds
            highlightRangeMode:ListView.StrictlyEnforceRange
            preferredHighlightBegin:(height-cellHeight)/2;preferredHighlightEnd:(height+cellHeight)/2
            highlightMoveVelocity:800
            highlight:Rectangle {color:constants.highlightColor;height:list.cellHeight}
            delegate:Item {
                id:optionRow;width:list.width;height:list.cellHeight
                property real emphasis:Math.max(height-Math.abs(y-list.contentY-list.preferredHighlightBegin),0)/height*constants.listViewSizeIncreaseFactor
                Text {
                    width:parent.width;anchors.verticalCenter:parent.verticalCenter
                    anchors.verticalCenterOffset:root.parameterStyle?(height-baselineOffset)/2:(text.length>0 && text.charCodeAt(0)>255?constants.listSelectorYOffsetUnicode:constants.listSelectorYOffsetAscii)
                    text:root.mode==="setting"?Settings.stringTranslated(root.thePropertyName,modelData):modelData
                    color:optionRow.ListView.isCurrentItem?constants.highlightItemColor:constants.itemColor
                    font.family:constants.menuItemFontName;font.pixelSize:optionRow.height*0.6*(1+optionRow.emphasis)
                    Component.onCompleted:if(root.parameterStyle)font.pointSize=Qt.binding(function(){return 50*5/constants.numberOfItemsVisibleInList*(1+optionRow.emphasis)})
                    fontSizeMode:Text.HorizontalFit
                    horizontalAlignment:Text.AlignHCenter;verticalAlignment:Text.AlignVCenter
                }
                MouseArea {anchors.fill:parent;onClicked:root.itemSelected(modelData)}
            }
            Rectangle {
                anchors.left:parent.left;anchors.right:parent.right;anchors.top:parent.top;height:140
                gradient:Gradient {GradientStop {position:0;color:constants.popoverListViewShadingStartColor} GradientStop {position:1;color:"transparent"}}
            }
            Rectangle {
                anchors.left:parent.left;anchors.right:parent.right;anchors.bottom:parent.bottom;height:140
                gradient:Gradient {GradientStop {position:0;color:"transparent"} GradientStop {position:1;color:constants.popoverListViewShadingStartColor}}
            }
        }
        Rectangle {anchors.fill:parent;color:"transparent";border.width:2;border.color:constants.popupBorderColor;radius:panel.radius}
    }
}
