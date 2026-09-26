"""在固定原厂拍摄参数页加入右滑第二页；只改本模块的 QML 覆盖。"""
from pathlib import Path
from prepare_mechanical_candidate import once

SWIPE = '''
    // 两页共用原参数页作用域；左右手势由父 MouseArea 过滤子控件。
    MouseArea {
        id: hblRfSwipe
        objectName: "MechanicalFlashSwipe"
        anchors.fill: parent
        drag.filterChildren: !scope.popupOpen
        drag.target: !scope.popupOpen ? hblRfTrack : null
        drag.axis: Drag.XAxis
        drag.minimumX: 0
        drag.maximumX: width
        drag.threshold: constants.dragThreshold
        property bool secondPage: false
        property real turnDistance: Math.min(width / 5, 80)
        function openFlashPage() { secondPage=true; hblRfTrack.x=width }
        function closeFlashPage() { secondPage=false; hblRfTrack.x=0 }
        Component.onCompleted: console.log("HBL flash page gate", scope.popupOpen, Camera.inSession)
        drag.onActiveChanged: {
            console.log("HBL flash swipe", drag.active, hblRfTrack.x, width)
            if (!drag.active) {
                secondPage = secondPage ? hblRfTrack.x >= width - turnDistance : hblRfTrack.x > turnDistance
                hblRfTrack.x = secondPage ? width : 0
            }
        }
        Item {
            id: hblRfTrack
            objectName: "MechanicalFlashTrack"
            width: scope.width; height: scope.height
            Behavior on x {
                enabled: !hblRfSwipe.drag.active
                NumberAnimation { duration: 180; easing.type: Easing.InOutQuad }
            }
            MechanicalFlashPage {
                id: hblRfHomePage
                x: -width; width: scope.width; height: scope.height
                pageActive: scope.visible && hblRfSwipe.secondPage
                onBackRequested: hblRfSwipe.closeFlashPage()
            }
            Rectangle {
                objectName: "MechanicalFlashEntry"
                parent: root
                x: exposureAdjustSetting.x + flashAdjustRow.x
                y: exposureAdjustSetting.y + flashAdjustRow.y
                width: flashAdjustRow.width; height: flashAdjustRow.height
                color: "#805829"; radius: 4; z: 2
                visible: !scope.popupOpen
                Text {
                    anchors.centerIn: parent
                    text: "无线引闪  ›"; color: "white"; font.pixelSize: 22 * scope.width / 640
                }
                MouseArea { anchors.fill: parent; onClicked: hblRfSwipe.openFlashPage() }
            }
        }
    }
'''

def extend(common, qml):
    out=common['OUT']; here=common['HERE']
    original=(common['BASELINE']/'usr/bin/victory-gui').read_bytes()
    if common['sha'](original)!=common['GUI_SHA']: raise RuntimeError('GUI baseline changed')
    files=dict(common['qml_files'](common['ArmElf'](original)))
    control=files['/controlscreen/ControlScreen.qml']
    control=once(control,'    id: scope','    id: scope\n    clip: true')
    control=once(control,'property bool preventSwipe: popupOpen || Camera.inSession',
                 'property bool preventSwipe: popupOpen || Camera.inSession || hblRfSwipe.secondPage || hblRfSwipe.drag.active')
    control=once(control,'        objectName: "ControlScreen_root"',
                 '        objectName: "ControlScreen_root"\n        parent: hblRfTrack')
    control=once(control,'                visible: ((Camera.FLASH_EVADJ !== 0) || (Camera.canShow & Camera.PropEVADJ != Camera.PropEVADJ)) &&\n                         (Camera.canShow & Camera.PropEVADJ)',
                 '                visible: false // 本临时界面以无线引闪入口替代原闪光补偿按钮，数值不变。')
    control=control[:control.rfind('}')]+SWIPE+'\n}\n'
    edited={p:(out/'qml'/p.lstrip('/')).read_text(encoding='utf-8') for p in qml}
    edited['/controlscreen/ControlScreen.qml']=control
    edited['/controlscreen/MechanicalFlashPage.qml']=(here/'ui/MechanicalFlashPage.qml').read_text(encoding='utf-8')
    for p,text in edited.items():
        target=out/'qml'/p.lstrip('/'); target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(text,encoding='utf-8')
    (out/'ui.rcc').write_bytes(common['rcc'](edited))
    return {p:common['sha'](text.encode('utf-8')) for p,text in edited.items()}
