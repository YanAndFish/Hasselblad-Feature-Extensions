import QtQuick 2.5
import com.hasselblad.camera 1.0

FlashPage {
    id: nativePage
    readonly property var adapter: typeof hblNative!=="undefined" ? hblNative : null
    connected: adapter ? adapter.connected : false
    masterEnabled: adapter ? adapter.masterEnabled : false
    busy: adapter ? adapter.busy || adapter.settingsRestoring : false
    canTest: adapter ? adapter.ready && !adapter.busy && !adapter.shotActive : false
    supportedGroupCount: adapter ? adapter.supportedGroupCount : 16
    modelingLampAvailable: adapter ? adapter.connected && adapter.masterEnabled : false
    channel: adapter ? adapter.channel : 5
    wirelessId: adapter ? adapter.wirelessId : 5
    mechanicalDelays: adapter ? [adapter.mechanicalDelay0,adapter.mechanicalDelay1,adapter.mechanicalDelay2,adapter.mechanicalDelay3,adapter.mechanicalDelay4] : [5000,5000,6300,6900,6900]
    calibrationEditable: adapter && !adapter.busy && !adapter.shotActive
    errorText: adapter ? (adapter.settingsError || adapter.errorText) : ""
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
    onMechanicalCalibrationRequested: {
        var values=mechanicalDelays.slice(0)
        values[index]=microseconds
        send({op:"calibration",delay0:values[0],delay1:values[1],delay2:values[2],delay3:values[3],delay4:values[4]})
    }
    onModelingLampDraftChanged: send({op:"lamp",group:group,on:value})
    onVisibleGroupsRequested: {
        var mask=0;for(var i=0;i<indices.length;i++)mask|=(1<<indices[i]);send({op:"visible",mask:mask})
    }
    onAdjustmentStepRequested: send({op:"step",thirds:thirdStops})
    // 每次编辑交给 native 排队；忙时也保留最新编辑，原始 UI request 信号不重复发送。
    onGroupDraftChanged: send({op:"group",group:group,active:active,tenthStops:tenthStops})
    onTestRequested: send({op:"test"})
    Component.onCompleted: {
        if (!adapter) return
        sendPowerUpdates=adapter.sendPowerUpdates; sendFlashSync=adapter.sendFlashSync
        setAdjustmentStep(adapter.adjustmentThirds,false)
        var visible=[];for(var g=0;g<16;g++)if(adapter.visibleGroupMask&(1<<g))visible.push(g)
        visibleGroups=visible
        var states=[]
        for (var i=0;i<16;i++) {
            setGroup(i,adapter["active"+i],adapter["tenthStops"+i],false)
            states.push(adapter["lamp"+i])
        }
        lampStates=states
    }
    Component.onDestruction: send({op:"cancelCurrent"})
}
