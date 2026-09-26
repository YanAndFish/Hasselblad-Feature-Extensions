import QtQuick 2.5
import com.hasselblad.settings 1.0
import com.hasselblad.config 1.0
import com.hasselblad.cambody 1.0
import com.hasselblad.camera 1.0
import com.hasselblad.lens 1.0
import com.hasselblad.suc 1.0
import com.hasselblad.bodysync 1.0
import com.hasselblad.systemmanager 1.0
import com.hasselblad.storage 1.0
import com.hasselblad.video 1.0
import com.hasselblad.upgrade 1.0
import com.hasselblad.globalstateinfo 1.0
import "qrc:///settings/scripts/MenuItemImporter.js" as MenuItems
import "qrc:///settings/components"

Item {
    id:root
    objectName:"NativeCustomSettings"
    property string itemValues
    property string menuLabel
    property string upperMenuLabel
    property bool preventSwipe:true
    property var entries:[]
    property string lastRows:""
    property bool ready:false
    property bool presented:false
    property bool formatLocked:false // Enabled only with the completed playback policy.
    property var specification:[]
    property var pendingSliderValues:({})
    signal backRequested()
    function residentActivate(){presented=true;page.dragOffset=0;page.returning=false;rebuild()}
    function residentDeactivate(){presented=false;chooser.close();radioChooser.close();actions.close()}
    function condition(value) {return value===undefined || value===null || value==="" || !!eval(String(value))}
    function rebuild() {
        if(page.adjusting)return
        var data=specification
        var out=[], bindings=[]
        for(var i=0;i<data.length;i++) {
            var e=data[i]
            if((e.demo && guiconfig.hideDemoItems) || !condition(e.validCheck))continue
            var enabled=condition(e.enableCond)
            if(e.editType===7 && !enabled)continue
            var heading=e.editType===9
            var special=e.name==="WIFI_power" || e.name==="CustomOption_LiveViewEVFOnly"
            var toggle=!special && (e.editType===2 || e.editType===4)
            var value=(!heading && e.editType!==3 && e.proxy)?e.proxy[e.name]:false
            if(e.editType===5 && pendingSliderValues[e.name]){
                var pending=pendingSliderValues[e.name]
                if(Math.abs(Number(value)-pending.value)<0.00001 || Date.now()>pending.deadline)delete pendingSliderValues[e.name]
                else value=pending.value
            }
            var display=(!heading && !toggle && e.editType!==3 && e.proxy)?Settings.getDisplayValue(e.name,value):""
            if(e.editType===8)display=value
            var unit=e.text2 || ""
            if(e.suppressUnitOn && e.proxy && Settings.getUntranslatedDisplayValue(e.name,value)===e.suppressUnitOn)unit=""
            var kind=heading?"heading":toggle?"toggle":e.editType===7?"text":e.editType===5?"slider":e.editType===3?"action":"choice"
            var row={kind:kind,label:qsTranslate("MENUS",e.text1),enabled:enabled,value:!!value,valueText:String(display)+(unit?" "+unit:""),description:toggle && e.text2?e.text2:""}
            if(e.name==="image_format" && root.formatLocked) {
                row.kind="text";row.enabled=false
                // Display the real value until the policy has taken effect.
                // Never pretend the camera is recording JPEG before it is.
            }
            if(special){
                row.kind="choice"
                if(e.name==="WIFI_power"){
                    row.valueText=typeof hblNative!=="undefined"?["关","Wi-Fi","引闪"][hblNative.radioMode]:"未就绪"
                    row.enabled=enabled && typeof hblNative!=="undefined" && hblNative.radioModeVerified && !hblNative.radioModeBusy
                    row.description=typeof hblNative!=="undefined"?(hblNative.radioModeBusy?"切换中":hblNative.radioModeError):""
                }else row.valueText=["正常","电子取景器","屏幕取景"][typeof hblNative!=="undefined" && hblNative.viewfinderMode>=0?hblNative.viewfinderMode:(value?1:0)]
            }
            if(kind==="slider") {row.numberValue=value;row.minimum=Settings.getMinValue(e.name);row.maximum=Settings.getMaxValue(e.name);row.step=Settings.getStepsForValue(e.name)}
            out.push(row)
            bindings.push(e)
        }
        entries=bindings
        var fingerprint=JSON.stringify(out)
        if(fingerprint!==lastRows){lastRows=fingerprint;page.rows=out}
    }
    function refreshSpecification(){
        specification=MenuItems.getSettingsList(itemValues)
        if(itemValues==="cameraSettingsAutofocus")specification=[{editType:9,text1:qsTranslate("MENUS","Auto Focus")}].concat(specification,[{editType:9,text1:qsTranslate("MENUS","Manual Focus")}],MenuItems.getSettingsList("cameraSettingsManualFocus"))
        rebuild()
    }
    property var languageIndex:configstore.languageIndex
    onLanguageIndexChanged:if(ready){
        if(typeof MenuItems.refreshResidentTranslations==="function")MenuItems.refreshResidentTranslations()
        refreshSpecification()
    }
    onItemValuesChanged:if(ready)refreshSpecification()
    Component.onCompleted:{ready=true;refreshSpecification()}
    Timer {interval:250;running:root.visible && root.presented;repeat:true;onTriggered:root.rebuild()}
    SettingsPage {
        id:page;width:parent.width;height:parent.height;title:root.menuLabel
        fontName:constants.menuItemFontName
        swipeThreshold:constants.dragThreshold;swipeDivisor:constants.swipeLengthDividor
        enabled:!chooser.visible && !radioChooser.visible && !actions.busy
        onBackRequested:root.backRequested()
        onToggleRequested:{
            var e=root.entries[rowIndex]
            if(e && e.proxy && root.condition(e.enableCond) && root.condition(e.validCheck)) {
                if(e.name==="ram_only_mode")actions.run(e)
                else e.proxy[e.name]=value
                root.rebuild()
            }
        }
        onEditRequested:{
            var e=root.entries[rowIndex]
            if(!e || (e.name==="image_format" && root.formatLocked) || !root.condition(e.enableCond) || !root.condition(e.validCheck))return
            if(e.editType===3 || e.editType===8)actions.run(e)
            else if(e.name==="WIFI_power"){
                if(typeof hblNative!=="undefined" && hblNative.radioModeVerified && !hblNative.radioModeBusy)radioChooser.openRadio(page,hblNative.radioMode)
            }else if(e.name==="CustomOption_LiveViewEVFOnly")chooser.openViewfinder(page,typeof hblNative!=="undefined" && hblNative.viewfinderMode>=0?hblNative.viewfinderMode:(e.proxy[e.name]?1:0))
            else if(e.proxy)chooser.open(page,e.proxy,e.name)
        }
        onValueRequested:{
            var e=root.entries[rowIndex]
            if(e && e.proxy && e.editType===5 && root.condition(e.enableCond) && root.condition(e.validCheck)){
                var lo=Settings.getMinValue(e.name),hi=Settings.getMaxValue(e.name),step=Settings.getStepsForValue(e.name) || 1
                var chosen=Math.max(lo,Math.min(hi,lo+Math.round((value-lo)/step)*step))
                root.pendingSliderValues[e.name]={value:chosen,deadline:Date.now()+2000}
                e.proxy[e.name]=chosen;root.rebuild()
            }
        }
    }
    ListSelectorSettings {
        id:chooser;anchors.fill:parent;z:20
        popupAnchor {topMargin:82;leftMargin:260;rightMargin:24;bottomMargin:82}
        onVisibleChanged:if(root.ready && !visible)root.rebuild()
    }
    RadioListSelector {
        id:radioChooser;anchors.fill:parent;z:21
        popupAnchor {topMargin:82;leftMargin:260;rightMargin:24;bottomMargin:82}
        onVisibleChanged:if(root.ready && !visible)root.rebuild()
    }
    NativeSettingsActions {id:actions;anchors.fill:parent;z:30}
    // Preserve the firmware 1.25 focus-grid update when the user changes size.
    // Hidden/preloaded pages must never react by writing camera settings.
    Connections {
        target:root.presented && root.itemValues==="cameraSettingsAutofocus"?configstore:null
        onFocusSizeChanged:{
            var sizeIndex=0
            for(var i=0;i<constants.focusSize.length;i++)if(configstore.focus_size===constants.focusSize[i]){sizeIndex=i;break}
            var nx=constants.focusSizeXCount[sizeIndex],ny=constants.focusSizeYCount[sizeIndex]
            var mx=constants.focusGridXMarginPercent,my=constants.focusGridYMarginPercent
            var w=(1-2*mx)/nx,h=(1-2*my)/ny
            var ix=Math.floor((Camera.firstComponent(Camera.focus_point)-mx)/w)
            var iy=Math.floor((Camera.secondComponent(Camera.focus_point)-my)/h)
            if(ix>=nx)ix=nx-1
            if(iy>=ny)iy=ny-1
            GlobalStateInfo.afSselectedIndex=ix+iy*nx
            Camera.focus_point=Camera.combine(mx+(ix+0.5)*w,my+(iy+0.5)*h)
        }
    }
}
