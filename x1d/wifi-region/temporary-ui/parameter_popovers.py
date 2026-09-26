"""X1D 1.25 adapters retain option tables and value writes, replace rendering."""
from pathlib import Path

def apply_parameter_popovers(resources, root):
    original=root.parents[1]/'candidates/replay-page-resident/build/original-page'
    prefix=original.as_uri()+'/'
    for name in ['ParameterPopover','ParameterChoiceTile','ParameterWhiteTemperature','ParameterExposureAdjust']:
        resources['/components/popups/'+name+'.qml']=(root/(name+'.qml')).read_text(encoding='utf-8')
    control=resources['/controlscreen/ControlScreen.qml']
    for name in ['ExposureMode','WhiteBalance','FocusMode','MeterMethod','DriveMode']:
        old='Popover'+name
        source=(original/('components/popups/'+old+'.qml')).read_text(encoding='utf-8')
        source=source.replace(prefix,'qrc:///')
        source='import com.hasselblad.camera 1.0\nimport com.hasselblad.config 1.0\n'+source
        # Keep the firmware option/validity adapters, but use our own frame,
        # input layer and tile renderer. Reuse the original icon assets.
        source=source.replace('Popover {','ParameterPopover {',1).replace('FramedImage {','ParameterChoiceTile {')
        source=source.replace('PopoverManualWhiteBalance {','ParameterWhiteTemperature {')
        source=source.replace('qsTr(', 'qsTranslate("'+old+'",')
        new='Own'+old
        resources['/components/popups/'+new+'.qml']=source
        old_url='qrc:/components/popups/'+old+'.qml'
        new_url='qrc:///components/popups/'+new+'.qml'
        if control.count(old_url)==1:control=control.replace(old_url,new_url)
        elif control.count(new_url)!=1:raise ValueError('Unexpected popup route '+old)
    old_url='qrc:/components/popups/PopupExposureAdjust.qml'
    new_url='qrc:///components/popups/ParameterExposureAdjust.qml'
    if control.count(old_url)==1:control=control.replace(old_url,new_url)
    elif control.count(new_url)!=1:raise ValueError('Unexpected compensation route')
    resources['/controlscreen/ControlScreen.qml']=control
