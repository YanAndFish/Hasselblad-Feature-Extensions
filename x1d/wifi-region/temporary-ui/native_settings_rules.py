"""只在构建副本中替换设置规则；源码 QML 基线保持不动。"""
import re


def block_span(source, pattern):
    match = re.search(pattern, source)
    if not match:
        raise ValueError('Missing settings block: ' + pattern)
    depth, offset, quote, comment = 1, match.end(), None, None
    while depth and offset < len(source):
        char, pair = source[offset], source[offset:offset + 2]
        if comment == 'line':
            if char == '\n':
                comment = None
        elif comment == 'block':
            if pair == '*/':
                comment = None
                offset += 1
        elif quote:
            if char == '\\':
                offset += 1
            elif char == quote:
                quote = None
        elif pair == '//':
            comment = 'line'
            offset += 1
        elif pair == '/*':
            comment = 'block'
            offset += 1
        elif char in ('"', "'"):
            quote = char
        elif char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
        offset += 1
    if depth:
        raise ValueError('Unterminated settings block: ' + pattern)
    return match.start(), offset, match


def replace_block(source, pattern, replacement):
    begin, end, _ = block_span(source, pattern)
    return source[:begin] + replacement + source[end:]


def apply_native_settings_adapter(source):
    if 'function nativeSettings(' in source:
        raise ValueError('Settings adapter already converted')
    source = replace_block(source, r'    function rebuild\(\)\s*\{',
                           '    function rebuild(){nativeSettings(1,[Date.now()])}')
    source = replace_block(source, r'    function refreshSpecification\(\)\s*\{',
                           '    function refreshSpecification(){nativeSettings(2,[Date.now()])}')
    source = replace_block(source, r'    onLanguageIndexChanged:if\(ready\)\s*\{',
                           '    onLanguageIndexChanged:if(ready)nativeSettings(6,[Date.now()])')
    for name, operation, args in [('Toggle', 3, 'rowIndex,value,Date.now()'),
                                  ('Edit', 4, 'rowIndex'), ('Value', 5, 'rowIndex,value,Date.now()')]:
        source = replace_block(source, r'        on' + name + r'Requested:\s*\{',
                               '        on' + name + 'Requested:root.nativeSettings(' + str(operation) + ',[' + args + '])')
    anchor = '    id:root\n'
    if source.count(anchor) != 1:
        raise ValueError('Settings adapter root anchor changed')
    return source.replace(anchor, anchor + '''    property alias nativePage:page
    property alias nativeChooser:chooser
    property alias nativeRadioChooser:radioChooser
    property alias nativeActions:actions
    property var nativeRadio:typeof hblNative!=="undefined"?hblNative:undefined
    property var nativeSettingsApi:Settings
    property bool nativeHideDemoItems:guiconfig.hideDemoItems
    function nativeSettings(operation,args){
        _hblSettingsRulesCore.request=[root,operation,args]
        return _hblSettingsRulesCore.result
    }
    // Original firmware APIs and their lexical condition scope only.
    function nativeSpecification(name){return MenuItems.getSettingsList(name)}
    function nativeRefreshTranslations(){if(typeof MenuItems.refreshResidentTranslations==="function")MenuItems.refreshResidentTranslations()}
    function nativeTranslate(text){return qsTranslate("MENUS",text)}
''', 1)


def apply_native_settings_page(source):
    if 'function nativeSettings(' in source:
        raise ValueError('Settings presentation already converted')
    source = replace_block(source, r'    function syncRows\(\)\s*\{',
                           '    function syncRows(){nativeSettings(20,[])}')
    source = replace_block(source, r'                        function updateValue\(px\)\s*\{',
                           '                        function updateValue(px){page.nativeSettings(21,[sliderTouch,row.entry,index,px,Date.now()])}')
    old = 'onTriggered:if(Math.abs(row.entry.numberValue-sliderTouch.previewValue)<0.00001 || Date.now()>sliderTouch.readbackDeadline)sliderTouch.awaitingValue=false'
    if source.count(old) != 1:
        raise ValueError('Settings slider readback anchor changed')
    source = source.replace(old, 'onTriggered:page.nativeSettings(22,[sliderTouch,row.entry,Date.now()])', 1)
    anchor = '    id: page\n'
    if source.count(anchor) != 1:
        raise ValueError('Settings presentation root anchor changed')
    return source.replace(anchor, anchor + '''    property alias nativeRowModel:rowModel
    function nativeSettings(operation,args){
        _hblSettingsRulesCore.request=[page,operation,args]
        return _hblSettingsRulesCore.result
    }
''', 1)
