import QtQuick 2.5
import "qrc:/components" as HblUi
import com.hasselblad.config 1.0
import com.hasselblad.cambody 1.0
import com.hasselblad.bodysync 1.0
import com.hasselblad.camera 1.0
import com.hasselblad.systemmanager 1.0
import com.hasselblad.video 1.0
import com.hasselblad.upgrade 1.0
import com.hasselblad.suc 1.0
import "qrc:///settings/scripts/MenuItemImporter.js" as MenuItems
import "qrc:///scripts/Keys.js" as MKeys

// RAM candidate: one target loader, no intermediate category page.
Rectangle {
    id: home
    objectName: "DirectMainMenu"
    color: "black"
    property bool listOpen: false
    property bool returnToList: false
    property bool opening: false
    property bool closing: false
    property real startedAt: 0
    property string targetLabel: ""
    property string failureText: ""
    property int translationRevision:0
    property var languageIndex:configstore.languageIndex
    onLanguageIndexChanged:languageRefresh.restart()
    function tr(text){var revision=translationRevision;return qsTranslate("MENUS",text)+(guiconfig.emptyString || "")}
    function customLabel(text,zh,ru){
        var translated=tr(text)
        if(translated!==text)return translated
        var exposure=tr("Exposure")
        if(exposure==="曝光")return zh
        if(exposure.toLowerCase().indexOf("экспоз")===0)return ru
        return text
    }
    function pageTitle(key){
        for(var i=0;i<shortcuts.length;i++)if(shortcuts[i][1]===key)return shortcuts[i][0]
        var row=entry(key);return row?tr(row.itemText):""
    }
    Timer {
        id:languageRefresh;interval:0
        onTriggered:{
            if(typeof MenuItems.refreshResidentTranslations==="function")MenuItems.refreshResidentTranslations()
            home.translationRevision++
            for(var key in target.slots){
                var object=target.slots[key].item
                if(object && typeof object.menuLabel!=="undefined")object.menuLabel=home.pageTitle(key)
            }
        }
    }
    signal closeRequested()
    readonly property var shortcuts: [
        [tr("Exposure"),"cameraSettingsExposure","LargeIconExposure"],
        [customLabel("Focus","对焦","Фокусировка"),"cameraSettingsAutofocus","LargeIconAutofocus"],
        [tr("Quality"),"cameraSettingsQuality","LargeIconQuality"],
        [tr("Image"),"cameraSettingsImage","LargeIconImage"],
        [tr("Flash"),"flash","FlashStatus"],
        [tr("Display"),"generalSettingsDisplay","LargeIconDisplay"],
        [customLabel("Power","电源","Питание"),"generalSettingsPowerTimeouts","LargeIconPowerTimeouts"],
        [tr("Storage"),"generalSettingsStorage","LargeIconStorage"],
        ["","",""],[tr("Wi-Fi"),"generalSettingsWiFi","LargeIconWiFi"],
        [customLabel("Settings","设置","Настройки"),"settings","settings_icon"],["","",""]]
    function allEntries() {return MenuItems.cameraMenuItems.concat(MenuItems.videoMenuItems,MenuItems.settingsMenuItems)}
    function entry(key) {
        var rows=allEntries()
        for(var i=0;i<rows.length;i++)if(rows[i].settingsList===key)return rows[i]
        return null
    }
    function isShortcut(key) {
        if(key==="cameraSettingsManualFocus")return true
        for(var i=0;i<shortcuts.length;i++)if(shortcuts[i][1]===key)return true
        return false
    }
    function eligible(v) {
        if(v.demo && guiconfig.hideDemoItems)return false
        if(typeof v.enableCond!=="undefined" && !eval(String(v.enableCond)))return false
        return true
    }
    function sections() {
        var revision=translationRevision
        var result=[], lists=[MenuItems.cameraMenuItems,MenuItems.videoMenuItems,MenuItems.settingsMenuItems]
        var titles=[qsTranslate("MainScreen","CAMERA SETTINGS"),qsTranslate("MainScreen","VIDEO SETTINGS"),qsTranslate("MainScreen","GENERAL SETTINGS")]
        for(var i=0;i<lists.length;i++){
            var part=[]
            for(var j=0;j<lists[i].length;j++){
                var e=lists[i][j]
                if(!isShortcut(e.settingsList) && eligible(e))part.push({title:qsTranslate("MENUS",e.itemText),key:e.settingsList,icon:e.settingsList,heading:false})
            }
            if(part.length){result.push({title:titles[i],key:"",icon:"",heading:true});result=result.concat(part)}
        }
        return result
    }
    function openPage(key,label,fromList) {
        if(opening || closing || target.active)return
        if(key==="settings"){listOpen=true;return}
        if(!key)return
        var e=entry(key)
        if(key!=="flash" && (!e || !eligible(e)))return
        returnToList=fromList;targetLabel=label;startedAt=Date.now();opening=true;failureText=""
        target.x=width
        var properties={}
        var url=key==="flash"?"qrc:///controlscreen/NativeFlashPage.qml":e.itemFile
        if(key!=="flash" && String(url).indexOf("SettingsGeneric.qml")>=0)
            properties={itemValues:key,menuLabel:label,upperMenuLabel:fromList?"设置":"主菜单"}
        if(String(url).indexOf("SettingsGeneric.qml")>=0 && customSupported(key))url="qrc:///settings/NativeSettingsPage.qml"
        // Only shortcuts are warmed at startup. Other pages are created on
        // first use and retained afterwards, rather than rebuilt every visit.
        target.setPage(key,url,properties,true);target.active=true
    }
    property int warmIndex:0
    Timer {
        interval:150;repeat:true;running:System.system_state===System.StateUp && home.warmIndex<home.shortcuts.length && !home.opening
        onTriggered:{
            if(target.isLoading())return
            var pair=home.shortcuts[home.warmIndex++],key=pair[1]
            if(!key || key==="settings")return
            var e=home.entry(key)
            if(key!=="flash" && (!e || !home.eligible(e)))return
            var url=key==="flash"?"qrc:///controlscreen/NativeFlashPage.qml":e.itemFile
            var properties={}
            if(String(url).indexOf("SettingsGeneric.qml")>=0){
                properties={itemValues:key,menuLabel:pair[0],upperMenuLabel:"主菜单"}
                if(home.customSupported(key))url="qrc:///settings/NativeSettingsPage.qml"
            }
            target.warm(key,url,properties)
        }
    }
    function customSupported(key) {
        // Complex service actions and special selectors retain their proven path
        // until their adapters are implemented; never silently omit an option.
        var data=MenuItems.getSettingsList(key)
        if(key==="cameraSettingsAutofocus")data=data.concat(MenuItems.getSettingsList("cameraSettingsManualFocus"))
        for(var i=0;i<data.length;i++) {
            var e=data[i]
            if(e.demo && guiconfig.hideDemoItems)continue
            if([1,2,3,4,5,7,8,9].indexOf(e.editType)<0)return false
            if(e.editType!==9 && e.editType!==3 && !e.proxy)return false
            if(e.editType===3 && ["liveViewStart","saveLogData","fwUpdateRetry","cardFormatCard0","cardFormatCard1","checkForUpdate","defaultSettings","resetFileCounter","saveCustomMode1","saveCustomMode2","saveCustomMode3","License","Certification","Usage"].indexOf(e.name)<0)return false
        }
        return data.length>0
    }
    function back() {
        if(target.active){
            if(closing)return
            closing=true
            if(target.item)target.item.visible=true
            exitAnimation.restart()
        }else if(listOpen)listOpen=false
        else closeRequested()
    }
    function dismissPages() {
        // Closing the entire menu must not leave a cached child presented.
        enterAnimation.stop();exitAnimation.stop()
        if(target.item && typeof target.item.residentDeactivate==="function")target.item.residentDeactivate()
        target.active=false;opening=false;closing=false;listOpen=false
    }
    Text {anchors.horizontalCenter:parent.horizontalCenter;y:12;height:50;verticalAlignment:Text.AlignVCenter;text:listOpen?home.customLabel("Settings","设置","Настройки"):qsTranslate("MainScreen","MAIN MENU")+(guiconfig.emptyString || "");color:"white";font.pixelSize:28}
    Text {x:24;y:home.height-22;text:home.failureText;color:"#d97a00";font.pixelSize:16;z:5}
    HblUi.NavigationChevron {objectName:"MainMenuBack";x:22;y:19;visible:home.listOpen}
    MouseArea {objectName:"MainMenuBackTouch";x:0;y:0;width:70;height:70;visible:home.listOpen;onClicked:home.back()}
    Loader {
        objectName:"MainMenuBattery";x:home.width-64;y:9;width:26;height:50;rotation:90
        source:"qrc:///components/BatteryIndicatorScaled.qml"
        onLoaded:{item.batteryWidth=26;item.lineWidth=2;item.showCharge=false}
    }
    Canvas {
        objectName:"MainMenuCharge";x:home.width-100;y:19;width:19;height:26
        visible:suc.ext_power || (suc.usbChargeLevel!==Suc.UsbChargeOff && System.batteryStatus!==System.BatteryAux && System.batteryStatus!==System.BatteryUnknown)
        onPaint:{var c=getContext("2d");c.clearRect(0,0,width,height);c.fillStyle="white";c.beginPath();c.moveTo(12,0);c.lineTo(2,15);c.lineTo(9,15);c.lineTo(6,26);c.lineTo(18,10);c.lineTo(11,10);c.closePath();c.fill()}
        onVisibleChanged:if(visible)requestPaint()
    }
    Grid {
        x:8;y:70;columns:4;enabled:!home.listOpen
        Repeater {model:home.shortcuts
            Item {width:(home.width-16)/4;height:(home.height-78)/3
                Image {anchors.horizontalCenter:parent.horizontalCenter;y:modelData[1]==="settings"?-3:5;width:modelData[1]==="settings"?82:66;height:width;fillMode:Image.PreserveAspectFit;source:modelData[2]?"qrc:///icons/"+modelData[2]+".png":""}
                Text {anchors.horizontalCenter:parent.horizontalCenter;y:80;text:modelData[0];color:"white";font.pixelSize:24}
                MouseArea {anchors.fill:parent;enabled:modelData[1]!=="";onClicked:home.openPage(modelData[1],modelData[0],false)}
            }
        }
    }
    MouseArea {
        id:listSwipe;anchors.fill:parent;anchors.topMargin:70;enabled:home.listOpen && !target.active
        drag {target:combinedList;axis:Drag.XAxis;minimumX:20;maximumX:home.width+20;threshold:constants.dragThreshold;filterChildren:true}
        drag.onActiveChanged:if(!drag.active){if(combinedList.x>20+home.width/constants.swipeLengthDividor)listExit.restart();else combinedList.x=20}
        Connections {target:home;onListOpenChanged:if(home.listOpen)combinedList.x=20}
    ListView {
        id:combinedList
        objectName:"CombinedSettingsList"
        x:20;y:0;width:parent.width-40;height:parent.height;clip:true;visible:home.listOpen
        Behavior on x {enabled:!listSwipe.drag.active && !listExit.running;NumberAnimation {duration:constants.menuSwipeDuration;easing.type:Easing.InOutQuad}}
        Rectangle {anchors.fill:parent;color:"black";z:-1}
        model:home.listOpen?home.sections():[]
        delegate:Item {width:combinedList.width;height:combinedList.height/5
            Rectangle {width:parent.width;height:1;color:"#555";visible:modelData.heading && index>0}
            Image {x:8;anchors.verticalCenter:parent.verticalCenter;width:48;height:48;fillMode:Image.PreserveAspectFit;visible:!modelData.heading;source:modelData.icon?"qrc:///icons/"+modelData.icon+".png":""}
            Text {x:modelData.heading?8:76;anchors.verticalCenter:parent.verticalCenter;text:modelData.title;color:modelData.heading?"#aaa":"white";font.pixelSize:modelData.heading?24:36}
            MouseArea {anchors.fill:parent;enabled:!modelData.heading;onClicked:home.openPage(modelData.key,modelData.title,true)}
        }
    }
    NumberAnimation {id:listExit;target:combinedList;property:"x";to:home.width+20;duration:constants.menuSwipeDuration;easing.type:Easing.InOutQuad;onStopped:home.listOpen=false}
    }
    MouseArea {
        id:swipe;anchors.fill:parent;enabled:target.active && !home.opening && !home.closing
        readonly property bool childOwnsGesture:target.item && (target.item.preventSwipe || target.item.popupOpen || target.item.powerGestureActive)
        drag {target:swipe.childOwnsGesture?null:target;axis:Drag.XAxis;minimumX:0;maximumX:home.width;threshold:constants.dragThreshold;filterChildren:!swipe.childOwnsGesture}
        drag.onActiveChanged:if(!drag.active && !home.closing){if(target.x>home.width/constants.swipeLengthDividor)home.back();else enterAnimation.restart()}
        PagePool {
            id:target;objectName:"DirectMenuTarget";x:home.width;width:home.width;height:home.height;active:false;asynchronous:true
            focus: active
            onBackRequested:home.back()
            onControlRequested:{home.back();home.closeRequested()}
            Keys.onPressed: {
                if(MKeys.pressedFnAcc("ESCAPE",event) || (!guiconfig.isWedge && MKeys.pressedFnAcc("LEFT",event))) {
                    if(!swipe.childOwnsGesture){home.back();event.accepted=true}
                    else event.accepted=false
                } else event.accepted=false
            }
            onLoaded:{
                try {
                    if(!pageItem)throw new Error("missing page object")
                    if(typeof pageItem.residentActivate==="function")pageItem.residentActivate()
                    if(typeof pageItem.pageActive!=="undefined")pageItem.pageActive=true
                    pageItem.forceActiveFocus()
                } catch(error) {
                    console.log("HBL page activation failed",home.targetLabel,String(error))
                    home.opening=false;active=false
                    home.failureText="页面未能打开："+home.targetLabel
                    return
                }
                home.opening=false
                console.log("HBL direct menu ready",home.targetLabel,Date.now()-home.startedAt)
                enterAnimation.restart()
            }
            onLoadFailed:{home.opening=false;active=false;home.failureText="页面未能打开："+home.targetLabel}
            onStatusChanged:if(status===Loader.Error){home.opening=false;active=false;home.failureText="页面加载失败："+home.targetLabel;console.log("HBL direct menu load failed",home.targetLabel)}
        }
    }
    Item {
        objectName:"DirectTargetBack";x:target.x+4;y:8;width:60;height:56;z:10
        visible:target.active && target.item && target.item.objectName==="SettingsGeneric_root" && !swipe.childOwnsGesture
        HblUi.NavigationChevron {anchors.centerIn:parent}
        MouseArea {anchors.fill:parent;onClicked:home.back()}
    }
    MouseArea {
        objectName:"LegacyReturnEdge";x:target.x;y:70;width:24;height:home.height-70;z:11
        visible:target.active && target.item && ["SettingsGeneric_root","GreyBalanceTool_root"].indexOf(target.item.objectName)>=0 && !swipe.childOwnsGesture
        enabled:visible && !home.opening && !home.closing
        drag.target:target;drag.axis:Drag.XAxis;drag.minimumX:0;drag.maximumX:home.width;drag.threshold:constants.dragThreshold
        drag.onActiveChanged:if(!drag.active){if(target.x>home.width/constants.swipeLengthDividor)home.back();else enterAnimation.restart()}
    }
    NumberAnimation {id:enterAnimation;target:target;property:"x";to:0;duration:constants.menuSwipeDuration;easing.type:Easing.OutCubic}
    NumberAnimation {id:exitAnimation;target:target;property:"x";to:home.width;duration:constants.menuSwipeDuration;easing.type:Easing.InOutQuad
        onStopped:{
            if(!home.closing)return
            if(target.item && typeof target.item.residentDeactivate==="function")target.item.residentDeactivate()
            target.active=false;home.listOpen=home.returnToList;home.closing=false;home.opening=false
        }
    }
    Connections {target:target.item;ignoreUnknownSignals:true
        onBackRequested:home.back()
        onVisibleChanged:if(target.active && target.delivered && target.item && !target.item.visible && !home.opening && !home.closing)home.back()
    }
    Keys.onEscapePressed:home.back()
}
