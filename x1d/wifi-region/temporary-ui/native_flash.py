"""将自研引闪业务函数替换为原生入口；布局与原有信号接口保留。"""
import re

OPERATIONS = {
 'setGroup':2, 'setDeliveryOptions':3, 'requestPowerUpdate':4,
 'requestFlashSync':5, 'requestTest':6, 'setAdjustmentStep':7,
 'steppedPower':8, 'adjustPower':9, 'quickAdjust':10, 'swipePower':11,
 'toggleGroup':14, 'toggleLamp':15, 'canAdjustVisiblePower':16,
 'adjustVisiblePower':17, 'toggleVisibleGroup':20,
 'openWireless':22, 'wirelessKey':23, 'confirmWireless':24,
}

def function_span(source, name):
    match=re.search(r'    function '+re.escape(name)+r'\(([^)]*)\)\s*\{',source)
    if not match:raise ValueError('Missing flash function: '+name)
    depth=1;i=match.end();quote=None;comment=None
    while depth:
        c=source[i];n=source[i:i+2]
        if comment=='line':
            if c=='\n':comment=None
        elif comment=='block':
            if n=='*/':comment=None;i+=1
        elif quote:
            if c=='\\':i+=1
            elif c==quote:quote=None
        elif n=='//':comment='line';i+=1
        elif n=='/*':comment='block';i+=1
        elif c in ('"',"'"):quote=c
        elif c=='{':depth+=1
        elif c=='}':depth-=1
        i+=1
    return match.start(),i,match.group(1)

def apply_native_flash(source):
    if 'property alias nativeGroups' in source:raise ValueError('Flash source already converted')
    for name,op in OPERATIONS.items():
        begin,end,parameters=function_span(source,name)
        args=','.join(x.strip() for x in parameters.split(',') if x.strip())
        dependencies=''
        if name=='steppedPower':
            dependencies='var d=[thirdStopSteps,minimumPower,maximumPower];'
        elif name=='canAdjustVisiblePower':
            dependencies='var d=[visibleGroups,thirdStopSteps,minimumPower,maximumPower];for(var n=0;n<visibleGroups.length;++n)d.push(groups.get(visibleGroups[n]).tenthStops);'
        source=source[:begin]+'    function '+name+'('+parameters+') {'+dependencies+'return nativeFlash('+str(op)+',['+args+'])}'+source[end:]
    anchor='    id: page\n'
    if source.count(anchor)!=1:raise ValueError('Flash root anchor changed')
    source=source.replace(anchor,anchor+'''    property alias nativeGroups: groups
    property alias nativeList: groupList
    function nativeFlash(operation,args) {
        _hblFlashCore.request=[page,operation,args]
        return _hblFlashCore.result
    }
''',1)
    return source
