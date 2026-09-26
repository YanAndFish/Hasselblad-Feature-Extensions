import QtQuick 2.5
import com.hasselblad.bodysync 1.0
import "qrc:///scripts/Keys.js" as MKeys

FocusScope {
    id:root;anchors.fill:parent;z:100
    property alias heading:title.text
    property alias headingSize:title.font.pixelSize
    property alias content:body.children
    property int headingTopMargin:29
    property int contentWidth:502
    property int contentHeight:361
    property bool updateBodySyncState:true
    property Item contentItem
    property bool preloadOnly:false
    function openProcessing(){}
    function popupHeight(){return title.implicitHeight+contentHeight}
    function popupWidth(){return contentWidth}
    function close(){if(updateBodySyncState)BodySync.currentState=BodySync.MAIN;focus=false;visible=false}
    function present(){visible=true;openProcessing();if(contentItem && typeof contentItem.updateFocus==="function")contentItem.updateFocus();if(updateBodySyncState)BodySync.currentState=BodySync.MENU;forceActiveFocus()}
    function setSelected(){if(contentItem && typeof contentItem.setSelected==="function")contentItem.setSelected()}
    Component.onCompleted:if(preloadOnly)visible=false;else present()
    Keys.onPressed:{
        event.accepted=true
        if(MKeys.pressedFn("ESCAPE",event.key)||MKeys.pressedFn("MENU",event.key)||MKeys.pressedFn("BROWSE",event.key))close()
        else if(contentItem && MKeys.pressedFn("POPACCEPT",event.key))contentItem.setSelected()
        else if(contentItem && (MKeys.pressedFn("NAVLEFT",event.key)||MKeys.pressedFn("UP",event.key)))contentItem.moveCurrentIndexLeft()
        else if(contentItem && (MKeys.pressedFn("NAVRIGHT",event.key)||MKeys.pressedFn("DOWN",event.key)))contentItem.moveCurrentIndexRight()
        else if(!MKeys.pressedFn("AF_MF",event.key))event.accepted=false
    }
    Rectangle {anchors.fill:parent;color:constants.popupFadeoutColor;opacity:constants.fadeOutOpacity}
    MouseArea {anchors.fill:parent;onClicked:root.close()}
    Rectangle {
        anchors.centerIn:parent;width:root.popupWidth();height:root.popupHeight()
        color:constants.popupBackgroundColor;radius:constants.outerBoxRadius
        border.color:constants.popupBorderColor;border.width:constants.popupBorderWidth
        MouseArea {anchors.fill:parent}
        Text {
            id:title;x:0;y:root.headingTopMargin;width:parent.width;height:implicitHeight*1.2
            horizontalAlignment:Text.AlignHCenter;color:constants.popupTextColor
            font.pixelSize:constants.popupHeaderTextSize;font.capitalization:Font.AllUppercase
        }
        Item {id:body;anchors.left:parent.left;anchors.right:parent.right;anchors.top:title.bottom;anchors.bottom:parent.bottom}
    }
}
