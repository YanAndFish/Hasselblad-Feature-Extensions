"""Photo live-view presentation and focus-drag patch for firmware 1.25.0 RCC.

The native video transport and camera focus-delivery service remain untouched.
"""

from pathlib import Path
import re


def apply_viewfinder_ui(resources: dict[str, str], root: Path) -> None:
    overlay_key = '/liveview/LiveViewOverlay.qml'
    image_key = '/liveview/LiveViewImage.qml'
    overlay = resources[overlay_key]
    image = resources[image_key]

    old_indicator = re.compile(
        r'    AFIndicator \{\s+anchors\.fill: liveViewVideoArea\s+'
        r'visible: guiconfig\.isWedge &&[\s\S]*?'
        r'sizeFactor: root\.sizeFactor\s+\}',
    )
    assert len(old_indicator.findall(overlay)) == 1
    overlay = old_indicator.sub(
        lambda match: match.group(0).replace('AFIndicator {',
            'AFIndicator {\n        opacity: 0', 1) + '''
    OwnFocusFrame {
        id: focusFrame
        anchors.fill: liveViewVideoArea
        visible: guiconfig.isWedge &&
                 !GlobalStateInfo.afSelectionActive &&
                 (VideoControl.videoMode === VideoControl.View ||
                  VideoControl.videoMode === VideoControl.AF) &&
                 ((Lens.lens_family === Lens.HCCLens) || (Lens.lens_family === Lens.XCLens))
        sizeFactor: root.sizeFactor
    }''', overlay, count=1)

    first = overlay.index('    function pickFocusPoint(px, py) {')
    last = overlay.index('    // Representing the area where live view will be seen.', first)
    overlay = overlay[:first] + '''    property real focusDragOffsetX: 0
    property real focusDragOffsetY: 0

    function focusTouchAllowed() {
        return root.inActiveWindow && !GlobalStateInfo.evfActive && !root.isInHDMI &&
               !GlobalStateInfo.afSelectionActive && !Camera.findOngoing &&
               (VideoControl.videoMode === VideoControl.View || VideoControl.videoMode === VideoControl.AF)
    }

    function focusPointAt(px, py, clampToCrop) {
        var x = px - liveViewVideoArea.x
        var y = py - liveViewVideoArea.y
        var cropLeft = crop.cropWidth
        var cropTop = crop.cropHeight
        var cropRight = liveViewVideoArea.width - cropLeft
        var cropBottom = liveViewVideoArea.height - cropTop
        if (cropRight <= cropLeft || cropBottom <= cropTop) return null
        if (!clampToCrop && (x < cropLeft || x > cropRight || y < cropTop || y > cropBottom)) return null
        var g = directFocusGrid
        if (g.afItemWidth <= 0 || g.afItemHeight <= 0 || g.xCount < 1 || g.yCount < 1) return null
        var minX = Math.max(cropLeft, g.gridXMargin + g.afItemWidth / 2)
        var maxX = Math.min(cropRight, g.gridXMargin + (g.xCount - 0.5) * g.afItemWidth)
        var minY = Math.max(cropTop, g.gridYMargin + g.afItemHeight / 2)
        var maxY = Math.min(cropBottom, g.gridYMargin + (g.yCount - 0.5) * g.afItemHeight)
        if (maxX < minX || maxY < minY) return null
        return Qt.point(Math.max(minX, Math.min(maxX, x)) / liveViewVideoArea.width,
                        Math.max(minY, Math.min(maxY, y)) / liveViewVideoArea.height)
    }

    function pickFocusPoint(px, py) {
        if (!focusTouchAllowed()) return
        var point = focusPointAt(px, py, false)
        if (point === null) return
        focusFrame.preview(point.x, point.y)
        focusFrame.releasePreview()
        GlobalStateInfo.afSselectedIndex = -1
        GlobalStateInfo.focusDelivery.select(Camera.combine(point.x, point.y))
    }

    function beginFocusDrag(px, py) {
        if (!focusTouchAllowed() || !focusFrame.visible) return false
        var centerX = liveViewVideoArea.x + focusFrame.focusX * liveViewVideoArea.width
        var centerY = liveViewVideoArea.y + focusFrame.focusY * liveViewVideoArea.height
        if (Math.abs(px - centerX) > Math.max(42, focusFrame.boxWidth / 2 + 16) ||
                Math.abs(py - centerY) > Math.max(42, focusFrame.boxHeight / 2 + 16)) return false
        focusDragOffsetX = px - centerX
        focusDragOffsetY = py - centerY
        focusFrame.preview(focusFrame.focusX, focusFrame.focusY)
        return true
    }

    function moveFocusDrag(px, py) {
        if (!focusFrame.dragging) return
        var point = focusPointAt(px - focusDragOffsetX, py - focusDragOffsetY, true)
        if (point !== null) focusFrame.preview(point.x, point.y)
    }

    function endFocusDrag(px, py, moved) {
        if (!focusFrame.dragging) return
        if (!moved || !focusTouchAllowed()) { focusFrame.cancelPreview(); return }
        var point = focusPointAt(px - focusDragOffsetX, py - focusDragOffsetY, true)
        if (point === null) { focusFrame.cancelPreview(); return }
        focusFrame.preview(point.x, point.y)
        focusFrame.releasePreview()
        GlobalStateInfo.afSselectedIndex = -1
        GlobalStateInfo.focusDelivery.select(Camera.combine(point.x, point.y))
    }

    function cancelFocusDrag() { focusFrame.cancelPreview() }

''' + overlay[last:]
    # Keep factory data/control objects alive, but draw the ordinary photo HUD
    # once with our own lightweight component. Specialist screens (ISO/WB,
    # focus grid, timer, no-live-view notice) remain in front when invoked.
    hide_markers = [
        '        id: iso\n',
        '        id: battery\n',
        '        id: manualFocusIndicator\n',
        '        id: autoFocusIndicatorDividedScan\n',
        '        id: nearFarIndicator\n',
        '        id: balanceScale\n',
        '        id: aeLock\n',
        '        id: aperture\n',
        '        id: evadjIcon\n',
        '        id: eShutterIcon\n',
        '        id: shutterspeed\n',
        '        id: imageLeftIndicator\n',
    ]
    for marker in hide_markers:
        assert overlay.count(marker) == 1, marker
        overlay = overlay.replace(marker, marker + '        opacity: 0\n', 1)
    for item_id in [
        'iso', 'manualFocusIndicator', 'autoFocusIndicatorDividedScan',
        'nearFarIndicator', 'balanceScale', 'aeLock', 'aperture',
        'evadjIcon', 'eShutterIcon', 'shutterspeed', 'imageLeftIndicator',
    ]:
        start = overlay.index('id: ' + item_id + '\n')
        visible_at = overlay.index('visible:', start)
        assert visible_at - start < 800, item_id
        overlay = overlay[:visible_at] + 'visible: false && ' + overlay[visible_at + len('visible: '):]
    overlay = overlay.replace('canShowBattery: root.infoVisible', 'canShowBattery: false', 1)
    # Two factory widgets already bind opacity, so use their existing bindings.
    existing = '        opacity: autoFocusIndicatorDividedScan.opacity'
    assert overlay.count(existing) == 2
    overlay = overlay.replace(existing,
        '        // Original opacity binding is superseded by OwnViewfinderHud.', 2)
    connectivity = '    Row {\n        anchors.left: parent.left\n        anchors.top: parent.top\n'
    assert overlay.count(connectivity) == 1
    overlay = overlay.replace(connectivity, connectivity + '        opacity: 0\n', 1)
    auto_iso = '    RoundedTextIndicator {\n        visible: root.infoVisible && guiconfig.fromIsoVal(Camera.iso) === "Auto"'
    assert overlay.count(auto_iso) == 1
    overlay = overlay.replace(auto_iso,
        '    RoundedTextIndicator {\n        opacity: 0\n        visible: root.infoVisible && guiconfig.fromIsoVal(Camera.iso) === "Auto"', 1)
    hud = '''    OwnViewfinderHud {
        id: ownHud
        anchors.fill: parent
        visible: root.infoVisible && !root.overlayOff && !isoWbState.isoWbActive()
        textFont: constants.cameraControlTextFontName
        whiteBalanceText: Camera.WBMode === 1 ? "AWB" : "WB"
        focusText: Camera.FocusMode === Config.Focus_MAN ? "MF" : "AF"
        wifiActive: configstore.WIFI_power
        gpsActive: gpsImage.visible
        flashReady: flashStatus.visible
        chargeActive: battery.showCharge
        batteryVisible: battery.showBattery
        aeLocked: cambody.AEL
        electronicShutter: configstore.eshutter
        batteryLevel: System.batteryLevel
        isoText: "ISO " + (guiconfig.fromIsoVal(Camera.iso) === "Auto" ? cambody.autoIso : guiconfig.fromIsoVal(Camera.iso))
        apertureText: (cambody.capabilities & Cambody.CapabilityGetAV) ?
            (cambody.AV_out_of_range ? "f/--" : "f/" + cambody.aperture) : ""
        shutterText: (cambody.capabilities & Cambody.CapabilityGetTV) ? getShutterSpeed() : ""
        remainingText: availCounter.text
        remainingOpacity: availCounter.opacity
        exposureScaleValid: guiconfig.isWedge && balanceScale.validScale && !cambody.current_stop_down
        exposureValue: cambody.balanceScaleReal
    }

'''
    loader_marker = '    Loader {\n        source: "qrc:///liveview/AFPointSelection.qml"'
    assert overlay.count(loader_marker) == 1
    overlay = overlay.replace(loader_marker, hud + loader_marker, 1)
    resources[overlay_key] = overlay

    image = image.replace('onPressed: {info.reportFocusTouchState();info.startZoomTimer()}',
                          'onPressed: info.startZoomTimer()', 1)
    old_drag = '''        onPressAndHold: if(!exposureButton.isDragging) info.pickFocusPoint(mouse.x, mouse.y)
        onClicked: info.pickFocusPoint(mouse.x, mouse.y)
        onPositionChanged: if(pressed && !exposureButton.isDragging) info.pickFocusPoint(mouse.x, mouse.y)
        preventStealing: true
        onDoubleClicked: liveViewSwitch(mouse)
        anchors.fill: parent
        onPressed: info.startZoomTimer()
        onReleased: info.startZoomTimer()
'''
    assert image.count(old_drag) == 1
    new_drag = '''        property bool focusDragging: false
        property bool movedFocus: false
        property real pressX: 0
        property real pressY: 0
        onPressAndHold: if (!focusDragging && !exposureButton.isDragging) info.pickFocusPoint(mouse.x, mouse.y)
        onClicked: if (!movedFocus && !focusDragging) info.pickFocusPoint(mouse.x, mouse.y)
        onPositionChanged: {
            if (!pressed || !focusDragging || exposureButton.isDragging) return
            if (Math.abs(mouse.x - pressX) + Math.abs(mouse.y - pressY) > 3) movedFocus = true
            if (movedFocus) info.moveFocusDrag(mouse.x, mouse.y)
        }
        preventStealing: focusDragging
        onDoubleClicked: { info.cancelFocusDrag(); liveViewSwitch(mouse) }
        anchors.fill: parent
        onPressed: {
            pressX = mouse.x; pressY = mouse.y; movedFocus = false
            info.reportFocusTouchState()
            focusDragging = info.beginFocusDrag(mouse.x, mouse.y)
            info.startZoomTimer()
        }
        onReleased: {
            if (focusDragging) info.endFocusDrag(mouse.x, mouse.y, movedFocus)
            focusDragging = false
            info.startZoomTimer()
        }
        onCanceled: { info.cancelFocusDrag(); focusDragging = false; movedFocus = false }
'''
    image = image.replace(old_drag, new_drag, 1)
    marker = '    property alias enableDrag: dragArea.enabled\n'
    assert image.count(marker) == 1
    image = image.replace(marker, marker + '    property alias focusDragging: dragArea.focusDragging\n', 1)
    resources[image_key] = image

    # The factory parent swipe filters child touches. During a reticle drag it
    # must not seize the pointer; elsewhere its navigation gesture is retained.
    live_key = '/liveview/LiveView.qml'
    live = (root.parents[1] / 'candidates/ui-resident/build/baseline/liveview/LiveView.qml').read_text(encoding='utf-8')
    assert 'import com.hasselblad.video 1.0' in live
    assert 'import com.hasselblad.systemmanager 1.0' in live
    assert 'drag.filterChildren' not in live
    assert live.count('filterChildren: true') == 1
    live = live.replace('filterChildren: true', 'filterChildren: !liveViewImage.focusDragging', 1)
    resources[live_key] = live
    resources['/liveview/OwnFocusFrame.qml'] = (root / 'OwnFocusFrame.qml').read_text(encoding='utf-8')
    resources['/liveview/OwnViewfinderHud.qml'] = (root / 'OwnViewfinderHud.qml').read_text(encoding='utf-8')
