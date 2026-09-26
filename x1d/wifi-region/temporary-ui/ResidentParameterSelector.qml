import QtQuick 2.5
import com.hasselblad.camera 1.0
import com.hasselblad.settings 1.0
import com.hasselblad.bodysync 1.0
import "qrc:/settings/components"

// One resident rendering instance; values are fetched when each kind opens.
SettingsChoicePopup {
    id:selector
    anchors.fill:parent
    objectName:"ResidentParameterSelector"
    property string parameterKind:""
    mode:"parameter"
    parameterStyle:true
    function openParameter(kind,returnItem){
        parameterKind=kind
        popupAnchor.topMargin=30;popupAnchor.bottomMargin=30
        popupAnchor.leftMargin=kind==="aperture"?30:kind==="iso"?width/2:width*0.4
        popupAnchor.rightMargin=kind==="aperture"?width/2:30
        var values=kind==="aperture"?Settings.apertureValues:kind==="iso"?Settings.isoValues:Settings.shutterspeedValues
        var current=kind==="aperture"?cambody.aperture:kind==="iso"?guiconfig.fromIsoVal(Camera.iso):cambody.shutterSpeed
        BodySync.currentState=BodySync.MENU
        present(returnItem,values,current)
    }
    onSelectedParameter:{
        if(parameterKind==="aperture")cambody.aperture=value
        else if(parameterKind==="iso")Camera.iso=guiconfig.toIsoVal(value)
        else if(parameterKind==="shutterspeed")cambody.shutterSpeed=value
    }
    onClosed:BodySync.currentState=BodySync.MAIN
}
