import QtQuick 2.5
import com.hasselblad.config 1.0
import com.hasselblad.camera 1.0
import com.hasselblad.systemmanager 1.0
import com.hasselblad.storage 1.0
import com.hasselblad.upgrade 1.0
import "qrc:///components"

// Firmware 1.25 action adapters. No action is executed by construction/loading.
Item {
    id:root
    property bool busy:dialog.active || inform.visible
    property string owner:""
    property var pending:null
    property bool allowReturn:false
    visible:busy
    function close(){dialog.active=false;inform.visible=false;pending=null;owner=""}
    function show(url,properties,canReturn){
        allowReturn=!!canReturn;dialog.x=0
        dialog.setSource(url,properties || {});dialog.active=true
    }
    function notify(text){show("qrc:///settings/NotificationMessage.qml",{headingText:text,showtime:4000},true)}
    function run(e){
        pending=e;owner=e.name
        switch(e.name){
        case "versionID":guiconfig.wantToSeeFWUpdateRetryClicked();break
        case "defaultSettings":show("qrc:///settings/ConfirmDefaultSettings.qml");break
        case "resetFileCounter":show("qrc:///settings/ConfirmResetImageCounter.qml");break
        case "checkForUpdate":show("qrc:///components/popups/UpgradeCheck.qml");break
        case "fwUpdateRetry":show("qrc:///components/GenericConfirm.qml",{largeHeaderText:true,headerText:e.text1+"?",rightText:qsTr("Retry")});break
        case "cardFormatCard0":case "cardFormatCard1":
            var first=e.name==="cardFormatCard0"
            if((first?ContentModel.card0Status:ContentModel.card1Status)===ContentModel.STORAGE_ABSENT)notify(qsTr("No card available.<br>Can not format card."))
            else show("qrc:///common/CardFormat.qml",{cardToFormat:first?Config.Card0:Config.Card1,subText:e.text2 || ""})
            break
        case "saveLogData":
            if(ContentModel.card0Status===ContentModel.STORAGE_ABSENT && ContentModel.card1Status===ContentModel.STORAGE_ABSENT){notify(qsTr("No card available.<br>Can not save log file."));break}
            System.collectLogs()
            show("qrc:///components/popups/PopoverBusy.qml",{heading:qsTranslate("MENUS","SERVICE"),centerText:qsTr("Saving log"),icon:"qrc:///icons/exclamationMark.png",bottomText:qsTr("Do not remove card!")})
            dialog.active=Qt.binding(function(){return System.collecting_logs!==0});break
        case "ram_only_mode":
            if(e.proxy[e.name])e.proxy[e.name]=false
            else show("qrc:///components/GenericConfirm.qml",{largeHeaderText:true,headerText:e.text1+"?",infoText:e.text2 || "",rightText:qsTr("Deactivate")})
            break
        case "saveCustomMode1":case "saveCustomMode2":case "saveCustomMode3":
            show("qrc:///components/GenericConfirm.qml",{largeHeaderText:true,headerText:qsTr("Save to ")+"C"+e.name.slice(-1)+"?",infoText:qsTr("Previous settings will be overwritten!"),rightText:qsTr("Save")});break
        case "License":show("qrc:///settings/LicenseViewer.qml",{headingText:qsTranslate("MENUS","LICENSES")},true);break
        case "Usage":show("qrc:///settings/NativeSettingsPage.qml",{itemValues:"generalSettingsUsage",menuLabel:qsTranslate("MENUS","Usage"),upperMenuLabel:""},true);break
        case "Certification":
            show("qrc:///settings/CertificationScreen.qml",{headingText:qsTranslate("MENUS","CERTIFICATION"),contentText1:qsTranslate("MENUS","CONTAINS FCC ID: 2AEFAX1311<br>CONTAINS IC: 20193-X1311"),contentText2:qsTranslate("MENUS","CONTAINS"),contentText3:qsTranslate("MENUS","007-AE0260"),contentText4:qsTranslate("MENUS","TA-2016/2340"),image1Source:"qrc:///icons/Cert_Korea.png",image2Source:"qrc:///icons/Cert_ICASA.png"},true);break
        case "liveViewStart":Camera.setLiveViewState(true);break
        default:notify(qsTr("Unsupported action"));break
        }
    }
    MouseArea {
        anchors.fill:parent
        drag.target:root.allowReturn?dialog:null;drag.axis:Drag.XAxis
        drag.minimumX:0;drag.maximumX:width;drag.threshold:constants.dragThreshold
        drag.filterChildren:root.allowReturn
        drag.onActiveChanged:if(!drag.active && root.allowReturn){settle.to=dialog.x>width/constants.swipeLengthDividor?width:0;settle.restart()}
        Loader {
            id:dialog;active:false;visible:active;width:parent.width;height:parent.height;focus:active
            function closeSubDialog(){root.close()}
            function closeConfirmDialog(){root.close()}
            onLoaded:if(typeof item.residentActivate==="function")item.residentActivate()
        }
    }
    NumberAnimation {id:settle;target:dialog;property:"x";duration:200;easing.type:Easing.OutCubic;onStopped:if(to>0)root.close()}
    Connections {
        target:dialog.item;ignoreUnknownSignals:true
        onBackRequested:root.close()
        onRightSelected:{
            if(!root.pending)return
            if(root.owner==="fwUpdateRetry")Upgrader.upgradeNodes()
            else if(root.owner==="ram_only_mode")root.pending.proxy[root.owner]=true
            else if(root.owner.indexOf("saveCustomMode")===0){
                configstore.saveDbTemplateFromCurrent("c"+root.owner.slice(-1))
                inform.title=qsTr("Custom mode saved");inform.info=qsTr("Saved to Mode %1").arg("C"+root.owner.slice(-1));inform.timeVisible=4000;inform.buttonText=qsTr("OK");inform.visible=true
            }
        }
    }
    Connections {
        target:root.owner==="resetFileCounter"?farm:null
        onResetGlobalImageSequenceCounterSucceeded:{
            inform.title=qsTr("Image Sequence Reset");inform.info=qsTr("The image sequence number was reset.")+(newDir!==""?qsTr("<br><br>New folder is:<br>")+newDir:"");inform.timeVisible=0;inform.buttonText=qsTr("OK");inform.visible=true
        }
    }
    GenericInform {id:inform;visible:false}
}
