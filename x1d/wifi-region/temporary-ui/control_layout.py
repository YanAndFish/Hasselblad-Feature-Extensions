"""X1D 1.25 参数页：保留原厂按压底块尺寸，边界贴合底块。"""
def replace_once(source, before, after):
    if source.count(before) != 1:
        raise ValueError('参数页基线不匹配：' + before[:90])
    return source.replace(before, after, 1)


def apply_control_layout(source):
    source = replace_once(source,
        'function openFlashPage() { secondPage=true; formalFlashTrack.x=-width }\n        function closeFlashPage() { secondPage=false; formalFlashTrack.x=0 }\n        drag.onActiveChanged: if (!drag.active) {\n            secondPage=secondPage ? formalFlashTrack.x<=-width+turnDistance : formalFlashTrack.x < -turnDistance\n            formalFlashTrack.x=secondPage ? -width : 0\n        }',
        '''function settlePage(showFlash) {
            pageSettle.stop()
            pageSettle.destinationFlash=showFlash
            pageSettle.from=formalFlashTrack.x
            pageSettle.to=showFlash ? -width : 0
            pageSettle.restart()
        }
        function openFlashPage() { settlePage(true) }
        function closeFlashPage() { settlePage(false) }
        drag.onActiveChanged: {
            if(drag.active)pageSettle.stop()
            else settlePage(secondPage ? formalFlashTrack.x<=-width+turnDistance : formalFlashTrack.x < -turnDistance)
        }
        NumberAnimation {
            id:pageSettle;target:formalFlashTrack;property:"x"
            property bool destinationFlash:false
            duration:200;easing.type:Easing.OutCubic
            onStopped:if(Math.abs(formalFlashTrack.x-to)<1)formalFlashSwipe.secondPage=destinationFlash
        }''')
    source = replace_once(source,
        'Behavior on x { enabled: !formalFlashSwipe.drag.active; NumberAnimation { duration: 180; easing.type: Easing.InOutQuad } }',
        '// Position is owned by drag or pageSettle, never two competing animations.')
    for handler in ('isoWbHandler', 'isoHandler', 'wbHandler'):
        source = replace_once(source, 'function '+handler+'()\n    {',
            'function '+handler+'()\n    {\n        formalFlashSwipe.closeFlashPage()')
    # Visible cell boundaries must include neither a hidden leading gutter nor
    # symbol-dependent widths. Keep the original 100 x 82 pressed rectangles.
    for control_id in ('whitebalance_control', 'af_control', 'exposureControl', 'meterControl', 'driveControl'):
        source = replace_once(source, 'id: '+control_id+'\n',
            'id: '+control_id+'\n                    width: constants.minWidthBrackets\n')
    start = source.index('id: bottom_controls')
    end = source.index('// Row from left', start)
    band = source[start:end].replace('leftMargin: constants.cameraViewMargin', 'leftMargin: 0').replace('rightMargin: constants.cameraViewMargin', 'rightMargin: 5')
    source = source[:start]+band+source[end:]
    start = source.index('topMargin: constants.cameraViewMargin\n                bottom: first_line.top')
    end = source.index('id: whitebalance_control', start)
    band = source[start:end].replace('leftMargin: constants.cameraViewMargin', 'leftMargin: 0')
    source = source[:start]+band+source[end:]
    # BracketedCameraControl.height is the native bracket image height; the
    # pressed rectangle fills it. Never resize that component or its hit box.
    source = replace_once(source,
        'topMargin: constants.cameraViewMargin\n                bottom: first_line.top',
        'topMargin: 0\n                bottom: first_line.top')
    source = replace_once(source,
        'anchors.topMargin: constants.cameraViewLineTopBottomMargin',
        'anchors.topMargin: whitebalance_control.height')
    source = replace_once(source,
        'bottomMargin: first_line.anchors.topMargin',
        'bottomMargin: meterControl.height')
    source = replace_once(source,
        'bottomMargin: constants.cameraViewMargin\n                top: second_line.top',
        'bottomMargin: 0\n                top: second_line.bottom')
    # Adjacent cells abut: the native orange rectangles retain their widths.
    start = source.index('id: whitebalance_control')
    row = source.rfind('spacing: constants.cameraViewMargin', 0, start)
    assert row >= 0
    source = source[:row] + source[row:].replace('spacing: constants.cameraViewMargin', 'spacing: 0', 1)
    start = source.index('id: bottom_row')
    source = source[:start] + source[start:].replace('spacing: constants.cameraViewMargin', 'spacing: 0', 1)
    # Same actual line thickness as the accepted combined settings list.
    start = source.index('id: first_line')
    end = source.index('TextCameraControl {', start)
    source = source[:start] + source[start:end].replace('height: 2', 'height: 1') + source[end:]
    source = replace_once(source,'id: availCounter\n',
        'id: availCounter\n                        font.pixelSize: showCounter ? 64 : 78\n                        anchors.topMargin: 0\n                        anchors.verticalCenterOffset: showCounter ? 4 : 0\n                        verticalAlignment: Text.AlignVCenter\n')
    source = replace_once(source,
        'anchors.top: left_bracket.top\n                        height: left_bracket.height',
        'anchors.verticalCenter: parent.verticalCenter\n                        height: parent.height')
    source = replace_once(source,
        'id: bottom_row_right\n                anchors.bottom: parent.bottom',
        'id: bottom_row_right\n                height: meterControl.height\n                anchors.bottom: parent.bottom')
    source = replace_once(source,
        'anchors.top: bottom_row_right.top\n                    anchors.bottom: bottom_row_right.bottom',
        'anchors.verticalCenter: bottom_row_right.verticalCenter')
    source = replace_once(source,'id: cardStatus\n',
        'id: cardStatus\n                    scale: 0.94\n                    transformOrigin: Item.Center\n')
    source = replace_once(source,'rowSpacing: 20','rowSpacing: 6')
    # Native CardStatusOK is a blank 31px image. Keep a nonzero grid cell
    # (zero width is skipped by Grid), but reclaim its blank width normally.
    start = source.index('id: cardStatus')
    end = source.index('DemoModeIndicator {', start)
    cards = source[start:end]
    cards = cards.replace('CardStatusImage {', '''CardStatusImage {
                        property bool showStatusGlyph: status === ContentModel.STORAGE_ERROR || status === ContentModel.STORAGE_FULL || status === ContentModel.STORAGE_LOCKED
                        width: showStatusGlyph ? constants.cardStatusIconSize : 1
                        height: constants.cardStatusIconSize
                        fillMode: Image.PreserveAspectFit''')
    source = source[:start]+cards+source[end:]
    source = replace_once(source,
        '? 100 : 153 + 10',
        '? 100 : Math.min(163, Math.max(100, bottom_controls.width-bottom_row.width-100-cardStatus.width-7-left_bracket.width-right_bracket.width-9))')
    source = replace_once(source,'// Row from right\n            Row {',
        '// Reserve the empty cell left of storage information.\n            Rectangle {\n                anchors.right: bottom_row_right.left\n                anchors.rightMargin: 8\n                anchors.bottom: parent.bottom\n                width: 1; height: meterControl.height; color: "#555"\n            }\n            // Row from right\n            Row {')
    source = replace_once(source,'Row {\n                    Image {\n                        id: left_bracket',
        'Row {\n                    height: bottom_row_right.height\n                    Image {\n                        id: left_bracket')
    for bracket in ('left_bracket','right_bracket'):
        source = replace_once(source,'id: '+bracket+'\n                        anchors.top: parent.top',
            'id: '+bracket+'\n                        anchors.verticalCenter: parent.verticalCenter\n                        height: Math.max(1, bottom_row_right.height-24)\n                        width: sourceSize.width * height / sourceSize.height\n                        fillMode: Image.PreserveAspectFit')
    marker='        TextCameraControl {\n            id: evSetting'
    if source.count(marker)!=1:raise ValueError('EV ruler anchor baseline mismatch')
    source=source.replace(marker,'''        ExposureRuler {
            id:parameterExposureRuler;objectName:"ParameterExposureRuler"
            anchors.left:second_line.left;anchors.leftMargin:13
            anchors.bottom:second_line.top;anchors.bottomMargin:6
            value:cambody.balanceScaleReal
            valid:cambody.BalanceScale!==cambody.invalidBalanceScaleCode && !cambody.current_stop_down
            visible:guiconfig.isWedge && configstore.ExpMode!==Config.ExpMode_ManualQuick
        }
'''+marker,1)
    start=source.index('id: evSetting');end=source.index('id: exposureAdjustSetting',start)
    source=source[:start]+source[start:end].replace('leftMargin: constants.cameraViewMargin','leftMargin: parameterExposureRuler.visible?225:constants.cameraViewMargin')+source[end:]
    return source
