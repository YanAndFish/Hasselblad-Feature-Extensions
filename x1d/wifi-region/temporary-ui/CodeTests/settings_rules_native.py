"""设置规则独立差分材料与 Qt5.5.1 ARM 构建；默认仅运行主机旧 QML oracle。

只读基线、仅向 build/settings-rules-native 写证据；不连接设备或网络。
目标程序运行由父任务统一安排。主机 oracle 通过不代表 C++ 候选通过。
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import tarfile

P = Path(__file__).resolve().parents[1]
ROOT = P.parents[2]
OUT = P / 'build/settings-rules-native'
HASHES = {'NativeSettingsPage.qml': '5190a0e78110e103cf8da14f140ab657790003544d83cf8086593eac2880f187',
          'SettingsPage.qml': 'aacd0f930816dbd9151fa534f64533b4c47002382f6b5e23698413d8ebb97bca'}
sys.path.insert(0, str(P))
from native_settings_rules import (apply_native_settings_adapter, apply_native_settings_page,
                                   block_span)


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def function(source, name):
    begin, end, _ = block_span(source, r'(?m)^\s*function ' + name + r'\([^)]*\)\s*\{')
    return source[begin:end]


def handler(source, name):
    match = re.search(r'(?m)^\s*on' + name + r'Requested:', source)
    if source[match.end():].lstrip().startswith('{'):
        begin, end, _ = block_span(source, r'(?m)^\s*on' + name + r'Requested:\s*\{')
        return source[begin:end]
    return source[match.start():source.index('\n', match.end())]


MOCKS = r'''
    property double testNow:1000
    property int testSliderIndex:5
    property int translationRefreshes:0
    property var commands:[]
    property alias testPage:page
    property alias testTouch:sliderTouch
    QtObject {
        id:settings
        function getDisplayValue(name,value){return "L"+configstore.languageIndex+":"+String(value)}
        function getUntranslatedDisplayValue(name,value){return value===0?"Off":String(value)}
        function getMinValue(name){return name==="fine"?-1:0}
        function getMaxValue(name){return name==="fine"?1:10}
        function getStepsForValue(name){return name==="fine"?0.25:name==="zeroStep"?0:1}
    }
    QtObject {
        id:menuItems
        function getSettingsList(name){return root.fixture(name)}
        function refreshResidentTranslations(){root.translationRefreshes++}
    }
    function fixture(name){
        if(name==="cameraSettingsAutofocus")return [{editType:1,name:"testValue",text1:"AF",proxy:configstore}]
        if(name==="cameraSettingsManualFocus")return [{editType:2,name:"testFlag",text1:"MF",text2:"Manual focus detail",proxy:configstore}]
        if(name==="empty")return []
        var l="L"+configstore.languageIndex+":"
        return [
            {editType:9,text1:l+"Heading"},
            {editType:2,name:"testFlag",text1:l+"Flag",text2:"Flag detail",proxy:configstore,enableCond:"configstore.allow",validCheck:"configstore.valid"},
            {editType:4,name:"toggleFour",text1:l+"Four",proxy:configstore,enableCond:"configstore.allow"},
            {editType:1,name:"testValue",text1:l+"Choice",text2:"units",suppressUnitOn:"Off",proxy:configstore},
            {editType:7,name:"readOnly",text1:l+"Text",proxy:configstore,enableCond:"configstore.allow"},
            {editType:5,name:"brightness",text1:l+"Brightness",proxy:configstore,enableCond:"configstore.allow",validCheck:"configstore.valid"},
            {editType:3,name:"defaultSettings",text1:l+"Action"},
            {editType:8,name:"raw",text1:l+"Raw",proxy:configstore},
            {editType:4,name:"WIFI_power",text1:l+"Radio",proxy:configstore,enableCond:"configstore.allow"},
            {editType:2,name:"CustomOption_LiveViewEVFOnly",text1:l+"EVF",proxy:configstore},
            {editType:1,name:"image_format",text1:l+"Format",proxy:configstore},
            {editType:1,name:"demo",text1:l+"Demo",demo:true,proxy:configstore},
            {editType:1,name:"invalid",text1:l+"Invalid",validCheck:"false",proxy:configstore},
            {editType:2,name:"ram_only_mode",text1:l+"RAM",proxy:configstore},
            {editType:5,name:"fine",text1:l+"Fine",proxy:configstore},
            {editType:5,name:"zeroStep",text1:l+"Zero step",proxy:configstore}
        ]
    }
    function testIndex(name){for(var i=0;i<entries.length;i++)if(entries[i].name===name)return i;return -1}
    function testEdit(name){page.editRequested(testIndex(name))}
    function testToggle(name,value){page.toggleRequested(testIndex(name),value)}
    function testValue(name,value){page.valueRequested(testIndex(name),value)}
    function testChoose(value){configstore.testValue=value;chooser.close()}
    function testStart(name,px){testSliderIndex=testIndex(name);sliderTouch.pressed=true;page.adjusting=true;sliderTouch.updateValue(px)}
    function testMove(px){if(sliderTouch.pressed)sliderTouch.updateValue(px)}
    function testRelease(){sliderTouch.pressed=false;page.adjusting=false}
    function testCancel(){sliderTouch.pressed=false;page.adjusting=false}
    function testPoll(){sliderTouch.poll()}
    function testTick(){rebuild();sliderTouch.poll()}
    function testScroll(value){page.contentY=value}
    function testDirectRows(value){page.rows=value}
    function testSnapshot(){
        var model=[],names=[],spec=[]
        for(var i=0;i<rowModel.count;i++)model.push(rowModel.get(i))
        for(var j=0;j<entries.length;j++)names.push(entries[j].name===undefined?null:entries[j].name)
        for(var k=0;k<specification.length;k++)spec.push(specification[k].name===undefined?null:specification[k].name)
        return JSON.stringify({rows:page.rows,model:model,entries:names,specification:spec,lastRows:lastRows,
            pending:pendingSliderValues,rowChanges:page.rowChanges,scroll:page.contentY,
            adjusting:page.adjusting,preview:sliderTouch.previewValue,awaiting:sliderTouch.awaitingValue,
            deadline:sliderTouch.readbackDeadline,pressed:sliderTouch.pressed,
            chooser:chooser.visible,radioChooser:radioChooser.visible,actionsBusy:actions.busy,
            translations:translationRefreshes,presented:presented,commands:commands})
    }
    Item {
        id:chooser;visible:false
        function close(){visible=false}
        function open(p,o,n){root.commands.push(["choice",n]);visible=true}
        function openViewfinder(p,n){root.commands.push(["viewfinder",n]);visible=true}
        onVisibleChanged:if(root.ready && !visible)root.rebuild()
    }
    Item {
        id:radioChooser;visible:false
        function close(){visible=false}
        function openRadio(p,n){root.commands.push(["radio",n]);visible=true}
        onVisibleChanged:if(root.ready && !visible)root.rebuild()
    }
    Item {
        id:actions
        property bool busy:false
        function close(){busy=false}
        function run(e){root.commands.push(["action",e.name]);busy=true}
    }
'''


def headless(adapter, presentation):
    begin = adapter.index('Item {\n') + len('Item {\n')
    end = adapter.index('    Timer {interval:250;')
    top = adapter[begin:end]
    if 'function nativeSettings(' in presentation:
        page_native = 'property alias nativeRowModel:rowModel\n' + function(presentation, 'nativeSettings')
    else:
        page_native = ''
    poll = re.search(r'onTriggered:(.*)', presentation).group(1)
    result = '''import QtQuick 2.5
Item {
''' + top + MOCKS + '''
    Item {
        id:page
        property bool adjusting:false
        property real dragOffset:0
        property bool returning:false
        property real contentY:0
        property var rows:[]
        property int rowChanges:0
        onRowsChanged:{rowChanges++;syncRows()}
        signal toggleRequested(int rowIndex,bool value)
        signal editRequested(int rowIndex)
        signal valueRequested(int rowIndex,real value)
        ListModel {id:rowModel;dynamicRoles:true}
''' + page_native + function(presentation, 'syncRows') + '\n' + '\n'.join(handler(adapter, n) for n in ['Toggle', 'Edit', 'Value']) + '''
        Item {
            id:row
            property int index:root.testSliderIndex
            property var entry:page.rows.length>index && index>=0?page.rows[index]:({numberValue:0,minimum:0,maximum:10,step:1})
            Item {
                id:sliderTouch
                width:592
                property int index:root.testSliderIndex
                property real previewValue:0
                property bool awaitingValue:false
                property double readbackDeadline:0
                property bool pressed:false
''' + function(presentation, 'updateValue') + '\nfunction poll(){' + poll + '}\n}\n}\n}\n}\n'
    return result.replace('MenuItems.', 'menuItems.').replace('Settings.', 'settings.').replace('nativeSettingsApi:Settings', 'nativeSettingsApi:settings').replace('Date.now()', 'root.testNow')


STORE = {'languageIndex': 0, 'allow': True, 'valid': True, 'testFlag': False, 'toggleFour': True,
         'testValue': 0, 'readOnly': 4, 'brightness': 2, 'raw': 'raw text', 'WIFI_power': False,
         'CustomOption_LiveViewEVFOnly': False, 'image_format': 1, 'demo': 6, 'invalid': 9,
         'ram_only_mode': False, 'fine': -1, 'zeroStep': 2, 'deferWrites': False}
RADIO = {'radioMode': 1, 'radioModeVerified': True, 'radioModeBusy': False, 'radioModeError': '', 'viewfinderMode': -1}


def call(method, *args, expect=None):
    out = {'op': 'call', 'method': method, 'args': list(args)}
    if expect is not None:
        out['expect'] = expect
    return out


def put(target, name, value):
    return {'op': 'set', 'target': target, 'name': name, 'value': value}


def cases():
    result = [
        {'name': '行规则、选择和滚动保持', 'events': [
            call('rebuild', expect={'rowChanges': 2, 'rows.1.description': 'Flag detail', 'rows.3.valueText': 'L0:0'}),
            call('testScroll', 620), call('testEdit', 'testValue', expect={'commands': [['choice', 'testValue']], 'chooser': True}),
            call('testChoose', 3, expect={'rows.3.valueText': 'L0:3 units', 'scroll': 620, 'chooser': False}),
            call('rebuild', expect={'rowChanges': 3, 'scroll': 620}),
            call('testToggle', 'testFlag', True, expect={'rows.1.value': True, 'rows.1.description': 'Flag detail'}),
            call('testToggle', 'ram_only_mode', True, expect={'commands': [['action', 'ram_only_mode']], 'actionsBusy': True}),
            call('testEdit', 'defaultSettings', expect={'commands': [['action', 'defaultSettings']]}),
            call('testEdit', 'raw', expect={'commands': [['action', 'raw']]}),
            put('root', 'formatLocked', True), call('rebuild', expect={'rows.10.kind': 'text', 'rows.10.enabled': False, 'rows.10.valueText': 'L0:1'}),
            call('testEdit', 'image_format', expect={'commands': []}),
            put('root', 'formatLocked', False), call('rebuild'), call('testEdit', 'image_format', expect={'commands': [['choice', 'image_format']]}),
        ]},
        {'name': '条件二次校验、demo和隐藏文本', 'events': [
            put('store', 'allow', False), call('testToggle', 'testFlag', True, expect={'commands': []}),
            call('testValue', 'brightness', 8), call('testEdit', 'testValue'),
            call('rebuild', expect={'rows.1.enabled': False, 'rows.4.kind': 'slider'}),
            put('store', 'valid', False), call('rebuild'),
            put('config', 'hideDemoItems', False), call('rebuild'),
            put('store', 'allow', True), put('store', 'valid', True), call('rebuild'),
            call('testToggle', 'toggleFour', False), call('testToggle', 'testFlag', True),
        ]},
        {'name': '无线与EVF特殊行', 'events': [
            call('testEdit', 'WIFI_power', expect={'commands': [['radio', 1]]}),
            call('testEdit', 'CustomOption_LiveViewEVFOnly', expect={'commands': [['viewfinder', 0]]}),
            put('store', 'CustomOption_LiveViewEVFOnly', True), call('rebuild', expect={'rows.9.valueText': '电子取景器'}),
            put('radio', 'viewfinderMode', 2), call('rebuild', expect={'rows.9.valueText': '屏幕取景'}),
            call('testEdit', 'CustomOption_LiveViewEVFOnly', expect={'commands': [['viewfinder', 2]]}),
            put('radio', 'radioModeBusy', True), call('rebuild', expect={'rows.8.enabled': False, 'rows.8.description': '切换中'}),
            call('testEdit', 'WIFI_power', expect={'commands': []}),
            put('radio', 'radioModeBusy', False), put('radio', 'radioModeVerified', False),
            put('radio', 'radioModeError', 'fixture failure'), call('rebuild', expect={'rows.8.description': 'fixture failure'}),
            call('testEdit', 'WIFI_power', expect={'commands': []}),
            put('radio', 'radioModeVerified', True), put('radio', 'radioMode', 2), call('rebuild', expect={'rows.8.valueText': '引闪'}),
        ]},
        {'name': '缺少原生无线接口', 'withoutNative': True, 'events': [
            call('rebuild', expect={'rows.8.valueText': '未就绪', 'rows.8.enabled': False}),
            call('testEdit', 'WIFI_power', expect={'commands': []}),
            call('testEdit', 'CustomOption_LiveViewEVFOnly', expect={'commands': [['viewfinder', 0]]}),
        ]},
        {'name': '语言更新、AF-MF拼接和空列表', 'events': [
            call('testScroll', 250), put('store', 'languageIndex', 1),
            call('rebuild', expect={'translations': 1, 'rows.1.label': 'L1:Flag', 'rows.3.valueText': 'L1:0', 'scroll': 250}),
            put('root', 'itemValues', 'cameraSettingsAutofocus'), call('rebuild', expect={'entries': [None, 'testValue', None, 'testFlag']}),
            put('store', 'languageIndex', 2), call('rebuild', expect={'translations': 2, 'rows.3.description': 'Manual focus detail'}),
            put('root', 'itemValues', 'empty'), call('rebuild', expect={'rows': [], 'model': []}),
            put('root', 'itemValues', 'main'), call('residentActivate', expect={'presented': True}),
            call('testEdit', 'testValue'), call('residentDeactivate', expect={'presented': False, 'chooser': False}),
        ]},
        {'name': '拖动、旧回执、精确超时和异步确认', 'events': [
            put('store', 'deferWrites', True), call('testStart', 'brightness', 580, expect={'adjusting': True, 'preview': 10, 'awaiting': True, 'rows.5.numberValue': 2}),
            put('store', 'brightness', 3), call('rebuild', expect={'rows.5.numberValue': 2}),
            call('testMove', 296, expect={'preview': 5}), call('testRelease'), call('testTick', expect={'rows.5.numberValue': 5, 'pending.brightness.value': 5, 'awaiting': False}),
            put('root', 'testNow', 3000), call('testTick', expect={'rows.5.numberValue': 5}),
            put('root', 'testNow', 3001), call('testTick', expect={'rows.5.numberValue': 3, 'pending': {}}),
            put('root', 'testNow', 4000), call('testValue', 'brightness', 7.6, expect={'rows.5.numberValue': 8}),
            put('store', 'brightness', 6), call('rebuild', expect={'rows.5.numberValue': 8}),
            put('store', 'brightness', 8), call('rebuild', expect={'pending': {}, 'rows.5.numberValue': 8}),
            call('testStart', 'brightness', -100, expect={'preview': 0}), call('testCancel'), call('testTick'),
        ]},
        {'name': '量化范围、零step和连续写入', 'events': [
            call('testValue', 'fine', -0.875, expect={'rows.12.numberValue': -0.75}),
            call('testValue', 'fine', 100, expect={'rows.12.numberValue': 1}),
            call('testValue', 'fine', -100, expect={'rows.12.numberValue': -1}),
            call('testValue', 'zeroStep', 4.5, expect={'rows.13.numberValue': 5}),
            call('testStart', 'fine', 225), call('testMove', 12), call('testMove', 900), call('testRelease'), call('testTick'),
        ]},
        {'name': '滑条视图独立等待与ListModel原位覆盖', 'events': [
            call('testDirectRows', [{'kind': 'slider', 'numberValue': 1, 'minimum': 0, 'maximum': 10, 'step': 1}]),
            call('testStart', '', 580), call('testRelease'), call('testPoll', expect={'awaiting': True}),
            put('root', 'testNow', 3000), call('testPoll', expect={'awaiting': True}),
            put('root', 'testNow', 3001), call('testPoll', expect={'awaiting': False}),
            call('testScroll', 300),
            call('testDirectRows', [{'kind': 'toggle', 'description': 'detail', 'value': True}, {'kind': 'slider', 'numberValue': 9, 'minimum': 0, 'maximum': 10, 'step': 1}]),
            call('testDirectRows', [{'label': 'plain'}], expect={'model.0.description': '', 'model.0.numberValue': 0, 'scroll': 300}),
        ]},
    ]
    rng = random.Random(20260922)
    for run in range(3):
        events = []
        now = 1000
        for _ in range(300):
            choice = rng.randrange(12)
            if choice == 0:
                events.append(put('store', 'allow', bool(rng.randrange(2))))
            elif choice == 1:
                events.append(put('store', rng.choice(['brightness', 'testValue', 'fine']), rng.randrange(11)))
            elif choice == 2:
                events.append(call('testValue', rng.choice(['brightness', 'fine', 'zeroStep']), rng.randrange(-10, 30) / 2))
            elif choice == 3:
                events.append(call('testToggle', rng.choice(['testFlag', 'toggleFour', 'ram_only_mode']), bool(rng.randrange(2))))
            elif choice == 4:
                events.append(call('testEdit', rng.choice(['testValue', 'image_format', 'WIFI_power', 'raw', 'CustomOption_LiveViewEVFOnly'])))
            elif choice == 5:
                now += rng.randrange(0, 2400)
                events.extend([put('root', 'testNow', now), call('testTick')])
            elif choice == 6:
                events.extend([call('testStart', 'brightness', rng.randrange(-20, 620)), call('testMove', rng.randrange(-20, 620)), call('testRelease')])
            elif choice == 7:
                events.append(put('store', 'languageIndex', rng.randrange(4)))
            elif choice == 8:
                events.append(put('store', 'deferWrites', bool(rng.randrange(2))))
            elif choice == 9:
                events.append(put('radio', rng.choice(['radioModeBusy', 'radioModeVerified']), bool(rng.randrange(2))))
            elif choice == 10:
                events.append(call('residentDeactivate'))
            else:
                events.append(call('rebuild'))
        result.append({'name': '固定种子交错轨迹' + str(run + 1), 'events': events})
    return result


def extract_inputs():
    OUT.mkdir(parents=True, exist_ok=True)
    sources = {}
    for name, expected in HASHES.items():
        raw = (P / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('QML baseline changed: ' + name)
        sources[name] = raw.decode('utf-8').replace('\r\n', '\n')
    adapter, page = sources['NativeSettingsPage.qml'], sources['SettingsPage.qml']
    converted_adapter, converted_page = apply_native_settings_adapter(adapter), apply_native_settings_page(page)
    for name, source in [('NativeSettingsPage.qml', converted_adapter), ('SettingsPage.qml', converted_page),
                         ('baseline.qml', headless(adapter, page)), ('candidate.qml', headless(converted_adapter, converted_page))]:
        (OUT / name).write_text(source, encoding='utf-8')
    events = {'schema': 1, 'store': STORE, 'radio': RADIO, 'cases': cases()}
    start, end, _ = block_span(MOCKS, r'    QtObject \{')
    settings_api = MOCKS[start:end].replace('id:settings', 'id:settings\n        property var apiCalls:[]')
    for method, args in [('getDisplayValue', 'name,value'), ('getUntranslatedDisplayValue', 'name,value'),
                         ('getMinValue', 'name'), ('getMaxValue', 'name'), ('getStepsForValue', 'name')]:
        original = 'function ' + method + '(' + args + '){'
        settings_api = settings_api.replace(original, original + 'apiCalls.push(["' + method + '",' + args + ']);', 1)
    (OUT / 'settings-api.qml').write_text('import QtQuick 2.5\n' + settings_api, encoding='utf-8')
    save('events.json', events)
    save('manifest.json', {'baselineSha256': HASHES, 'cameraRequests': 0,
                          'scope': '原始函数/handler提取的无窗口QML；QObject代理、ListModel、模拟时钟；不验证视觉布局或实机侧作用。',
                          'retainedQml': ['原厂条件eval词法桥', '原厂Settings与MenuItems API桥', '布局/动画/信号接线', '原厂focus_size网格兼容Connections（本候选未迁移）'],
                          'contextProperty': '_hblSettingsRulesCore', 'class': 'NativeSettingsRules'})
    return events


def at(value, path):
    for part in path.split('.'):
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def run_baseline(events):
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    os.environ['QML_DISABLE_DISK_CACHE'] = '1'
    os.environ['QML_DISK_CACHE_PATH'] = str(OUT / 'qml-cache')
    sys.path.insert(0, str(ROOT / 'x1d/wireless-flash/build/ui-test-python'))
    from PySide6.QtCore import QCoreApplication, QUrl, qVersion
    from PySide6.QtQml import QQmlEngine, QQmlComponent, QQmlPropertyMap
    app = QCoreApplication.instance() or QCoreApplication([])

    class Proxy(QQmlPropertyMap):
        def __init__(self):
            super().__init__()
            self.writes = []

        def updateValue(self, key, value):
            value = value.toVariant() if hasattr(value, 'toVariant') else value
            self.writes.append([key, value])
            return self.value(key) if self.value('deferWrites') and key in ('brightness', 'fine', 'zeroStep') else value

    records, assertions = [], 0
    for case in events['cases']:
        engine = QQmlEngine()
        warnings = []
        engine.warnings.connect(lambda errors: warnings.extend(e.toString() for e in errors))
        store, radio, config = Proxy(), QQmlPropertyMap(), QQmlPropertyMap()
        for name, value in events['store'].items():
            store.insert(name, value)
        for name, value in events['radio'].items():
            radio.insert(name, value)
        config.insert('hideDemoItems', True)
        engine.rootContext().setContextProperty('configstore', store)
        engine.rootContext().setContextProperty('guiconfig', config)
        if not case.get('withoutNative'):
            engine.rootContext().setContextProperty('hblNative', radio)
        component = QQmlComponent(engine, QUrl.fromLocalFile(str(OUT / 'baseline.qml')))
        obj = component.create()
        if not obj:
            raise AssertionError([e.toString() for e in component.errors()])
        wrapper = engine.newQObject(obj)
        maps = {'store': store, 'radio': radio, 'config': config, 'root': obj}
        for index, event in enumerate([{'op': 'reset'}] + case['events']):
            obj.setProperty('commands', engine.newArray())
            store.writes.clear()
            if event['op'] == 'set':
                target = maps[event['target']]
                if event['target'] == 'root':
                    target.setProperty(event['name'], event['value'])
                else:
                    target.insert(event['name'], event['value'])
            elif event['op'] == 'call':
                method = wrapper.property(event['method'])
                value = method.callWithInstance(wrapper, [engine.toScriptValue(v) for v in event['args']])
                if value.isError():
                    raise AssertionError(value.toString() + ' ' + value.property('stack').toString())
            app.processEvents()
            observed = wrapper.property('testSnapshot').callWithInstance(wrapper)
            if observed.isError():
                raise AssertionError(observed.toString())
            observed = json.loads(observed.toString())
            observed['writes'] = store.writes[:]
            if warnings:
                raise AssertionError(warnings)
            for path, value in event.get('expect', {}).items():
                if at(observed, path) != value:
                    save('baseline-failure.json', {'case': case['name'], 'index': index - 1, 'event': event, 'observed': observed})
                    raise AssertionError((case['name'], index - 1, path, at(observed, path), value))
                assertions += 1
            records.append({'case': case['name'], 'index': index - 1, 'observed': observed})
        obj.deleteLater()
        app.processEvents()
        del wrapper, obj, component, engine
    with (OUT / 'baseline-trace.jsonl').open('w', encoding='utf-8') as output:
        for record in records:
            output.write(json.dumps(record, ensure_ascii=False) + '\n')
    (OUT / 'baseline-failure.json').unlink(missing_ok=True)
    report = {'baseline': 'passed', 'candidate': 'not_run', 'qtVersion': qVersion(), 'records': len(records),
              'assertions': assertions, 'cases': len(events['cases']), 'cameraRequests': 0, 'armRuntimeVerified': False}
    save('host-result.json', report)
    return report


def build_arm(diagnostic_trace=False):
    base = ROOT / '.research-cache/x1d-1.25.0'
    qt = base / 'qt-public'
    qtbase = qt / 'qtbase-opensource-src-5.5.1'
    env = dict(os.environ)
    for key, folder in [('ZIG_GLOBAL_CACHE_DIR', 'global'), ('ZIG_LOCAL_CACHE_DIR', 'local'), ('TEMP', 'tmp'), ('TMP', 'tmp')]:
        path = OUT / folder
        path.mkdir(exist_ok=True)
        env[key] = str(path)
    include = OUT / 'include/QtCore'
    include.mkdir(parents=True, exist_ok=True)
    (include / 'qconfig.h').write_text('#define QT_SHARED\n#define QT_NO_DEBUG\n#define QT_POINTER_SIZE 4\n#define QT_OPENGL_ES_2\n')
    (include / 'qfeatures.h').write_text('/* Qt5.5 */\n')
    layout = OUT / 'relocations.ld'
    layout.write_text('SECTIONS { .rel.dyn : { *(.rel.dyn) } .rel.plt : { *(.rel.plt) } } INSERT BEFORE .ARM.exidx;\n')
    zig = base / 'toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    target = ['-target', 'arm-linux-gnueabihf.2.22', '-mcpu=cortex_a9']
    flags = target + ['-marm', '-O2', '-fPIC', '-fno-stack-protector', '-I', str(OUT / 'include'),
                      '-isystem', str(qtbase / 'include'), '-isystem', str(qt / 'qtdeclarative-opensource-src-5.5.1/include'),
                      '-I', str(qtbase / 'mkspecs/linux-arm-gnueabi-g++'), '-Wno-deprecated-declarations', '-Wno-enum-constexpr-conversion']
    if diagnostic_trace:
        flags.append('-DHBL_SETTINGS_RULES_TRACE=1')
    libs = [base / ('baseline/usr/lib/libQt5' + name + '.so.5.5.1') for name in ['Quick', 'Qml', 'Gui', 'Network', 'Core']]
    libs += [base / ('baseline/' + name) for name in ['usr/lib/libstdc++.so.6.0.21', 'lib/libgcc_s.so.1', 'lib/libdl-2.22.so', 'lib/libc-2.22.so', 'lib/libpthread-2.22.so']]
    obj, runner = OUT / 'runner.o', OUT / 'runner'
    commands = [['c++', '-std=c++11'] + flags + ['-c', str(Path(__file__).with_suffix('.cpp')), '-o', str(obj)],
                ['cc'] + target + ['-no-pie', '-Wl,--no-undefined', '-Wl,-s', '-Wl,-T,' + str(layout), str(obj)] + [str(p) for p in libs] + ['-o', str(runner)]]
    for command in commands:
        completed = subprocess.run([str(zig)] + command, env=env, capture_output=True, text=True, timeout=120)
        if completed.returncode:
            raise RuntimeError(completed.stderr)
    names = ['runner', 'baseline.qml', 'candidate.qml', 'events.json', 'settings-api.qml']
    with tarfile.open(OUT / 'test.tgz', 'w:gz', compresslevel=9) as tar:
        for name in names:
            tar.add(OUT / name, arcname=name)
    sources = [P / 'settings_rules_core.h', P / 'native_settings_rules.py', Path(__file__), Path(__file__).with_suffix('.cpp')]
    sources += [P / name for name in HASHES]
    sources += [OUT / name for name in ['baseline.qml', 'candidate.qml', 'events.json', 'settings-api.qml']]
    save('build.json', {'built': True, 'executed': False, 'qtVersion': '5.5.1', 'cameraRequests': 0, 'diagnosticTrace': diagnostic_trace,
                        'files': {name: hashlib.sha256((OUT / name).read_bytes()).hexdigest() for name in names + ['test.tgz']},
                        'sources': {str(p.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}})
    return {'built': True, 'executed': False, 'archiveBytes': (OUT / 'test.tgz').stat().st_size}


def main():
    assert Path.cwd().resolve() == ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-arm', action='store_true')
    parser.add_argument('--export-only', action='store_true')
    parser.add_argument('--diagnostic-trace', action='store_true')
    args = parser.parse_args()
    events = extract_inputs()
    report = {'exported': True}
    if not args.export_only:
        report.update(run_baseline(events))
    if args.build_arm:
        report.update(build_arm(args.diagnostic_trace))
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
