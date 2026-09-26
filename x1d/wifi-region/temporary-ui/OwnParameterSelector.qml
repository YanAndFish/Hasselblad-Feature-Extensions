import QtQuick 2.5
import com.hasselblad.bodysync 1.0
import "qrc:/settings/components"

SettingsChoicePopup {
    id:selector
    anchors.fill:parent
    property var model:[]
    property string currentlySelectedValue:""
    property bool isToLeft:true
    signal selectedValueChanged(string value)
    mode:"parameter";parameterStyle:true
    popupAnchor {leftMargin:isToLeft?30:0;rightMargin:isToLeft?0:30;topMargin:30;bottomMargin:30}
    Component.onCompleted:{BodySync.currentState=BodySync.MENU;present(null,model,currentlySelectedValue)}
    onSelectedParameter:selectedValueChanged(value)
    onClosed:BodySync.currentState=BodySync.MAIN
}
