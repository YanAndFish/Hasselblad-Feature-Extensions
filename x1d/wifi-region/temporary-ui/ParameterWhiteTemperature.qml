import QtQuick 2.5
import "qrc:/settings/components"

SettingsChoicePopup {
    id:root;mode:"parameter"
    popupAnchor {leftMargin:root.width/2-30;rightMargin:90;topMargin:30;bottomMargin:30}
    function open(caller){
        var items=[],current=Number(configstore.WBManualTemp)
        for(var n=2000;n<=10000;n+=100){items.push(String(n));if(current>n && current<n+100)items.push(String(current))}
        present(caller,items,String(current))
    }
    onSelectedParameter:{
        var n=Number(value)
        if(n!==configstore.WBManualTemp && configstore.WBManualTemp%100!==0)configstore.WBManualTint=0
        configstore.WBManualTemp=n
    }
}
