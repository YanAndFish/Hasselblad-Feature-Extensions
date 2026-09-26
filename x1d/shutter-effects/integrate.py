"""X1D 1.25.0 离线资源适配；不修改已有构建、不连接相机。"""
from pathlib import Path

HERE = Path(__file__).resolve().parent


def once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('X1D integration anchor changed: ' + before[:90])
    return text.replace(before, after, 1)


def add_item(text, block):
    at = text.rfind('}')
    if at < 0:
        raise ValueError('Missing QML root')
    return text[:at] + block + '\n' + text[at:]


def resources(original):
    values = dict(original)
    if '/common/X1dShutterAnimation.qml' in values:
        raise ValueError('Already integrated')
    values['/common/X1dShutterAnimation.qml'] = (HERE/'X1dShutterAnimation.qml').read_text(encoding='utf-8')
    for key in ['/common/TouchWindow.qml', '/liveview/EVFWindow.qml']:
        text = values[key]
        if key.startswith('/liveview/'):
            text = 'import "qrc:///common"\n' + text
        values[key] = add_item(text, '''
    X1dShutterAnimation {
        anchors.fill: parent
        exposing: Camera.exposing
        activeSurface: root.visible && root.showContent
        effectMode: typeof _hblShutterEffects !== "undefined" ? _hblShutterEffects.mode : 0
    }
''')
    # 唯一音频触发点；LCD/EVF 两个实例只负责各自绘制，避免重复声音。
    values['/main.qml'] = add_item(values['/main.qml'], '''
    Connections {
        target: Camera
        onExposingChanged: if (typeof _hblShutterEffects !== "undefined") _hblShutterEffects.exposing=Camera.exposing
    }
''')
    key='/settings/NativeSettingsPage.qml'
    text=values[key]
    if 'function nativeSettings(' in text:
        text=once(text,'        return _hblSettingsRulesCore.result', '''        if(operation===1 || operation===2 || operation===6)syncShutterRow()
        return _hblSettingsRulesCore.result''')
        text=once(text,'    function nativeSettings(operation,args){', '''    function syncShutterRow() {
        if(itemValues!=="cameraSettingsExposure")return
        var rows=page.rows.slice(0), bindings=entries.slice(0)
        if(bindings.length && bindings[bindings.length-1].name==="hblShutterEffects")bindings.pop()
        if(rows.length && rows[rows.length-1].label==="曝光动画与声音")rows.pop()
        rows.push({kind:"choice",label:"曝光动画与声音",enabled:typeof _hblShutterEffects!=="undefined",
            value:false,valueText:typeof _hblShutterEffects!=="undefined"?["关","动画","动画与声音"][_hblShutterEffects.mode]:"未就绪",
            description:typeof _hblShutterEffects!=="undefined"?_hblShutterEffects.error:""})
        bindings.push({name:"hblShutterEffects"});entries=bindings
        if(JSON.stringify(rows)!==JSON.stringify(page.rows))page.rows=rows
    }
    function nativeSettings(operation,args){''')
        text=once(text,'        onEditRequested:root.nativeSettings(4,[rowIndex])', '''        onEditRequested: {
            if(root.entries[rowIndex] && root.entries[rowIndex].name==="hblShutterEffects")
                chooser.openShutterEffects(page,_hblShutterEffects.mode)
            else root.nativeSettings(4,[rowIndex])
        }''')
    else:
        text=once(text,'        entries=bindings', '''        if (itemValues === "cameraSettingsExposure") {
            out.push({kind:"choice",label:"曝光动画与声音",enabled:typeof _hblShutterEffects!=="undefined",
                value:false,valueText:typeof _hblShutterEffects!=="undefined"?["关","动画","动画与声音"][_hblShutterEffects.mode]:"未就绪",
                description:typeof _hblShutterEffects!=="undefined"?_hblShutterEffects.error:""})
            bindings.push({name:"hblShutterEffects"})
        }
        entries=bindings''')
        text=once(text,'            if(!e || (e.name===', '''            if(e && e.name==="hblShutterEffects") {
                chooser.openShutterEffects(page,_hblShutterEffects.mode);return
            }
            if(!e || (e.name===''')
    values[key]=text
    # 最新构建将两个原厂选择器映射为同一套组件，均保持其它选择逻辑。
    changed=0
    for key,text in list(values.items()):
        if not key.endswith('.qml') or 'function openViewfinder(returnItem, currentMode)' not in text or 'property string mode:"setting"' not in text:
            continue
        text=once(text,'    function openViewfinder(', '''    function openShutterEffects(returnItem, currentMode) {
        mode="shutterEffects";theProxy=undefined;thePropertyName=""
        var labels=["关","动画","动画与声音"]
        present(returnItem,labels,labels[currentMode])
    }
    function openViewfinder(''')
        text=once(text,'        if(mode==="parameter")', '''        if(mode==="shutterEffects") {
            var index=["关","动画","动画与声音"].indexOf(value)
            if(index>=0 && typeof _hblShutterEffects!=="undefined")_hblShutterEffects.mode=index
        } else if(mode==="parameter")''')
        values[key]=text
        changed+=1
    if not changed:
        raise ValueError('Expected X1D resident settings chooser is missing')
    return values


def native(text):
    text=once(text,'#include "settings_rules_core.h"','#include "settings_rules_core.h"\n#include "shutter_effects.h"')
    text=once(text,' QStringList actual=args;', ''' if(program==QStringLiteral("aplay") || program.endsWith(QStringLiteral("/aplay")))
  X1dShutterEffects::factorySoundStarting();
 QStringList actual=args;''')
    hook='''
extern "C" void previewStartCommand(QProcess *,const QString &,QIODevice::OpenMode)
    __asm__("_ZN8QProcess5startERK7QString6QFlagsIN9QIODevice12OpenModeFlagEE");
extern "C" void previewStartCommand(QProcess *p,const QString &command,QIODevice::OpenMode mode){
 using F=void(*)(QProcess*,const QString&,QIODevice::OpenMode);
 static F next=reinterpret_cast<F>(dlsym(RTLD_NEXT,"_ZN8QProcess5startERK7QString6QFlagsIN9QIODevice12OpenModeFlagEE"));
 if(!next)return;
 if(command.startsWith(QStringLiteral("aplay ")) || command.startsWith(QStringLiteral("/usr/bin/aplay ")))
  X1dShutterEffects::factorySoundStarting();
 next(p,command,mode);
}
'''
    text=once(text,'#ifdef HBL_EXPERIMENTAL_NETWORK\nstatic void note',hook+'\n#ifdef HBL_EXPERIMENTAL_NETWORK\nstatic void note')
    text=once(text,' next(e,u);',''' if(componentAuthorized() && !e->rootContext()->contextProperty("_hblShutterEffects").isValid())
  e->rootContext()->setContextProperty("_hblShutterEffects",new X1dShutterEffects(e));
 next(e,u);''')
    return text
