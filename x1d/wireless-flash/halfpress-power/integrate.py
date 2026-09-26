"""在已装 R6 上构造半按功率候选；纯字符串变换，不连接设备。"""
from pathlib import Path
HERE=Path(__file__).resolve().parent

def once(text, old, new):
    if text.count(old)!=1:raise ValueError('Integration anchor changed: '+old[:100])
    return text.replace(old,new,1)

def resources(source):
    values=dict(source)
    values['/FormalExposureGate.qml']=(HERE/'HalfPressExposureGate.qml').read_text(encoding='utf8')
    main=values['/main.qml']
    main=once(main,'            console.log("Got half press")','            formalExposureGate.prepareHalfPress()\n            console.log("Got half press")')
    main=once(main,'                console.log("Got half release")','                formalExposureGate.halfReleased()\n                console.log("Got half release")')
    main=once(main,'        id: formalExposureGate','        id: formalExposureGate\n        halfPowerEnabled: typeof _hblHalfPress!=="undefined" && _hblHalfPress.enabled')
    values['/main.qml']=main
    values['/common/ElectronicFlashHint.qml']=(HERE/'ElectronicFlashHint.qml').read_text(encoding='utf8')
    touch=values['/common/TouchWindow.qml']
    hint='''
    ElectronicFlashHint {
        anchors.horizontalCenter: parent.horizontalCenter
        y: 70; z: 99999
        flashEnabled: typeof hblNative!=="undefined" && hblNative.masterEnabled && hblNative.sendFlashSync
        electronic: configstore.eshutter
        manualExposure: configstore.ExpMode===Config.ExpMode_Manual
        exposureValid: !cambody.TV_out_of_range && !cambody.isBMode && !cambody.isTMode && isFinite(cambody.TV)
        exposureUs: Math.round(1000000*Math.pow(2,-cambody.TV/12))
        displayAllowed: root.isReady && !root.sleeping && !root.isBrowsing &&
                        ErrorControl.code===Errors.ErrorNone &&
                        !(typeof hblNative!=="undefined" && hblNative.bootLoading)
    }
'''
    values['/common/TouchWindow.qml']=once(touch,'    title: "main"','    title: "main"\n'+hint)
    page=values['/controlscreen/FlashPage.qml']
    page=once(page,'Rectangle {width:608;height:604;color:"black"}','Rectangle {width:608;height:738;color:"black"}')
    page=once(page,'contentHeight:604; contentWidth:width','contentHeight:738; contentWidth:width')
    row='''
            Item {
                objectName:"HalfPressPowerSetting";x:8;y:616;width:592;height:106
                readonly property bool checked: typeof _hblHalfPress!=="undefined" && _hblHalfPress.enabled
                enabled:typeof _hblHalfPress!=="undefined"
                FlashText {x:0;y:0;height:80;text:"半按快门发送功率更新";font.pixelSize:32;font.family:page.fontName}
                SettingsToggle {x:506;y:22;checked:parent.checked}
                FlashText {x:0;y:66;height:27;font.pixelSize:18;opacity:0.6;font.family:page.fontName
                    text:typeof _hblHalfPress!=="undefined" && _hblHalfPress.error ? _hblHalfPress.error : "电子、机械快门均支持；每次半按发送一次"}
                MouseArea {anchors.fill:parent;onClicked:_hblHalfPress.enabled=!parent.checked}
            }
'''
    page=once(page,'            Repeater {model:[224,328,512];',row+'            Repeater {model:[224,328,512];')
    values['/controlscreen/FlashPage.qml']=page
    return values

def native(source):
    source=once(source,'#include "shutter_effects.h"','#include "shutter_effects.h"\n#include "halfpress_settings.h"')
    return once(source,' next(e,u);',' if(componentAuthorized() && !e->rootContext()->contextProperty("_hblHalfPress").isValid())\n  e->rootContext()->setContextProperty("_hblHalfPress",new HblHalfPressSettings(e));\n next(e,u);')

def policy(source):
    # 公开源码已经实化半按策略；旧输入仍走严格的一次变换。
    if 'bool halfPressPower=false;' in source:
        if ('if(prepareOnly && !shutterPower && !halfPressPower)' not in source or
                'frozenPower=master && powerUpdates && (shutterPower || (prepareOnly && halfPressPower));' not in source):
            raise ValueError('Incomplete half-press policy integration')
        return source
    source=once(source,'    bool shutterPower=true;','    bool shutterPower=true;\n    bool halfPressPower=false;')
    source=once(source,'if(prepareOnly && !shutterPower)','if(prepareOnly && !shutterPower && !halfPressPower)')
    return once(source,'frozenPower=master && powerUpdates && shutterPower;','frozenPower=master && powerUpdates && (shutterPower || (prepareOnly && halfPressPower));')

def worker(source):
    if 'policy.halfPressPower=true;' in source:
        if 'policy.shutterPower=false;' not in source:
            raise ValueError('Incomplete half-press worker integration')
        return source
    return once(source,'        policy.shutterPower=false;','        policy.shutterPower=false;\n        policy.halfPressPower=true;')
