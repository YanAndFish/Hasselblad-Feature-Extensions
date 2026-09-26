import QtQuick 2.5
import "qrc:///scripts/Keys.js" as MKeys

// Implements only the navigation contract consumed by TouchWindow. No legacy
// favourites grid, three category loaders or edge targets are constructed.
Rectangle {
    id:root;objectName:"OwnMainScreen";color:"black";focus:true
    property bool simulation:false
    property bool acceptKeys:true
    property real childOpacity:1
    property bool hideStatusIcons:false
    property bool hideTopBatteryIcon:false
    signal closeMain()
    function closeMenu(){home.dismissPages()}
    function closeMainScreen(){closeMenu();closeMain()}
    function startMainWheelTimeout(){}
    function stopMainWheelTimeout(){}
    function loadCameraMenuItem(label,item){home.openPage("cameraSettingsConfiguration",label,true)}
    function loadProfilesMenu(){home.openPage("generalSettingsProfiles",home.pageTitle("generalSettingsProfiles"),true)}
    function loadGreyBalanceMenu(){home.openPage("cameraSettingsGreyBalanceTool",home.pageTitle("cameraSettingsGreyBalanceTool"),true)}
    DirectMainMenu {
        id:home;anchors.fill:parent;focus:true
        onCloseRequested:root.closeMainScreen()
    }
    Keys.onPressed:{
        if(!acceptKeys){event.accepted=false;return}
        event.accepted=true
        if(MKeys.pressedFn("F2",event.key)||MKeys.pressedFn("STAR",event.key)||MKeys.pressedFn("F4",event.key))home.openPage("settings","",false)
        else if(MKeys.pressedFn("MENU",event.key)||MKeys.pressedFn("ESCAPE",event.key))home.back()
        else event.accepted=false
    }
}
