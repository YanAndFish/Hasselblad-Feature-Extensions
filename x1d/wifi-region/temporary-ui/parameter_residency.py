"""Share one resident wheel for the three numeric parameter controls."""
def apply_parameter_residency(resources, root):
    key='/controlscreen/ControlScreen.qml'
    source=resources[key]
    resources['/components/controls/ResidentParameterSelector.qml']=(root/'ResidentParameterSelector.qml').read_text(encoding='utf-8')
    resources['/components/controls/ResidentPopupHost.qml']=(root/'ResidentPopupHost.qml').read_text(encoding='utf-8')
    for state,component in [('iso','popupISO'),('aperture','popupApertureSettings'),('shutterspeed','popupShutterSpeedSettings')]:
        old='PropertyChanges { target: popup; sourceComponent: '+component+'; active: true; }'
        assert source.count(old)==1,state
        source=source.replace(old,'StateChangeScript { script: residentParameterSelector.openParameter("'+state+'",root) }')
    source=source.replace('property bool popupOpen: popup.status !== Loader.Null','property bool popupOpen: residentParameterSelector.visible || popup.status !== Loader.Null')
    # Hardware ISO/WB acceptance must address the active resident wheel.
    source=source.replace('popup.item.setSelected()','(residentParameterSelector.visible ? residentParameterSelector : popup.item).setSelected()')
    source=source.replace('from: "iso,aperture,shutterspeed,whitebalance"','from: "whitebalance"')
    marker='        Loader {\n            id: popup\n'
    assert source.count(marker)==1
    source=source.replace(marker,'''        ResidentParameterSelector {
            id:residentParameterSelector
            z:100
            onClosed:{states.state="";root.forceActiveFocus()}
        }
'''+marker)
    source=source.replace(marker,'        ResidentPopupHost {\n            id: popup\n')
    source=source.replace('            asynchronous: false\n            anchors.fill: parent\n            onLoaded: popup.item.forceActiveFocus()', '''            preloadSources:["qrc:///components/popups/OwnPopoverExposureMode.qml","qrc:///components/popups/OwnPopoverWhiteBalance.qml","qrc:///components/popups/OwnPopoverFocusMode.qml","qrc:///components/popups/OwnPopoverMeterMethod.qml","qrc:///components/popups/OwnPopoverDriveMode.qml","qrc:///components/popups/ParameterExposureAdjust.qml"]
            anchors.fill: parent
            onLoaded: popup.item.forceActiveFocus()''')
    resources[key]=source
