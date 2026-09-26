import QtQuick 2.5
import com.hasselblad.camera 1.0

FlashPage {
    id: nativePage
    readonly property var adapter: typeof hblNative!=="undefined" ? hblNative : null
    connected: adapter ? adapter.connected : false
    masterEnabled: adapter ? adapter.masterEnabled : false
    busy: adapter ? adapter.busy : false
    canTest: adapter ? adapter.ready && !adapter.busy && !adapter.shotActive : false
    supportedGroupCount: adapter ? adapter.supportedGroupCount : 16
    modelingLampAvailable: adapter ? adapter.connected && adapter.masterEnabled : false
    channel: adapter ? adapter.channel : 5
    wirelessId: adapter ? adapter.wirelessId : 5
    errorText: adapter ? adapter.errorText : ""
    batterySource: "qrc:/components/BatteryIndicatorScaled.qml"
    apertureText: typeof cambody!=="undefined" && !cambody.AV_out_of_range ? "F/"+cambody.aperture : "F/—"
    shutterSpeedText: {
        if (typeof cambody==="undefined" || cambody.TV_out_of_range) return "—"
        var text=String(cambody.shutterSpeed)
        return /^[0-9]+$/.test(text) && Number(text)>0 ? "1/"+text : text
    }
    isoText: {
        if (typeof Camera==="undefined" || typeof guiconfig==="undefined") return "ISO —"
        var value=guiconfig.fromIsoVal(Camera.iso)
        return value==="Auto" ? "ISO A "+(typeof cambody!=="undefined" ? cambody.autoIso : "—") : "ISO "+value
    }
    syncText: adapter && adapter.masterEnabled ? (sendFlashSync ? "无线" : "热靴") : "—"
    shutterText: typeof configstore!=="undefined" ? (configstore.eshutter ? "电子快门" : "机械快门") : "—"
    function send(value) { if (adapter) adapter.command=JSON.stringify(value) }
    onEnabledRequested: send({op:"options",master:value,power:sendPowerUpdates,sync:sendFlashSync})
    onDeliveryOptionsChanged: send({op:"options",master:adapter ? adapter.masterRequested : false,power:powerUpdates,sync:flashSync})
    onWirelessConfigurationRequested: send({op:"wireless",channel:channel,id:wirelessId})
    onModelingLampDraftChanged: send({op:"lamp",group:group,on:value})
    onAdjustmentStepRequested: send({op:"step",thirds:thirdStops})
    // 每次编辑交给 native 排队；忙时也保留最新编辑，原始 UI request 信号不重复发送。
    onGroupDraftChanged: send({op:"group",group:group,active:active,tenthStops:tenthStops})
    onTestRequested: send({op:"test"})
    Component.onCompleted: {
        if (!adapter) return
        sendPowerUpdates=adapter.sendPowerUpdates; sendFlashSync=adapter.sendFlashSync
        setAdjustmentStep(adapter.adjustmentThirds,false)
        var states=[]
        for (var i=0;i<16;i++) {
            setGroup(i,adapter["active"+i],adapter["tenthStops"+i],false)
            states.push(adapter["lamp"+i])
        }
        lampStates=states
    }
    Component.onDestruction: send({op:"cancelCurrent"})
}
