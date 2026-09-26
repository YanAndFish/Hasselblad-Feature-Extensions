"""在固定 a8 四资源上生成独立全普通页候选，原输入与评估记录不变。"""
from pathlib import Path
import hashlib,json,re,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;CANDIDATE=HERE.parents[1];ROOT=CANDIDATE.parents[2]
FROZEN=CANDIDATE/'build/fixed/ui-resident-0456d37bc5ddbc57'
GUI_SHA='d29c62402091c3ad40f6f247c03ce55f248ca79e92531889b1670edeb014ed9b'
def digest(s):return hashlib.sha256(s.encode()).hexdigest()
def replace(s,a,b,count=1):
    if s.count(a)!=count:raise ValueError('patch anchor '+a[:90]+' count '+str(s.count(a)))
    return s.replace(a,b)
SYNC='''    function synchronizeRows(model, rows, keyName) {
        for (var i = 0; i < rows.length; i++) {
            var key = rows[i][keyName]
            if (i >= model.count || model.get(i)[keyName] !== key) {
                var found = -1
                for (var j = i + 1; j < model.count; j++)
                    if (model.get(j)[keyName] === key) { found = j; break }
                if (found >= 0) model.move(found, i, 1)
                else model.insert(i, rows[i])
            }
            model.set(i, rows[i])
        }
        if (model.count > rows.length) model.remove(rows.length, model.count - rows.length)
    }
'''
def menu(s):
    s=replace(s,'    property bool residentPresented: true','''    property var residentSeed: []
    property bool residentPrepared: false
    readonly property bool residentWarmEnabled: residentHost !== null && residentHost.warmEnabled
    function residentCatalog() {
        var entries = []
        residentSeed.forEach(function(v) {
            if (!v.demo && v.itemFile === "qrc:///settings/SettingsGeneric.qml")
                entries.push({key: v.settingsList, properties: {itemValues: v.settingsList, menuLabel: v.itemText, upperMenuLabel: root.text}})
        })
        return entries
    }
    function residentPrepare() {
        list.cacheBuffer = 100000
        populateModel(residentSeed)
        residentPrepared = true
        list.currentIndex = -1
        list.lastIndex = -1
    }
    property bool residentPresented: true''')
    s=replace(s,'        menu_model.clear()\n        lastItems = []','')
    s=replace(s,'        if (!residentPresented) return\n','')
    s=replace(s,'        menu_model.clear();','        var nextRows = [];')
    s=replace(s,'                menu_model.append({','                nextRows.push({')
    s=replace(s,'        });\n    }','        });\n        synchronizeRows(menu_model, nextRows, "settingsList")\n    }',1)
    s=replace(s,'    function populateModel(menuItemValues)',SYNC+'\n    function populateModel(menuItemValues)')
    s=replace(s,'            residentSource: "qrc:///settings/SettingsGeneric.qml"','''            residentSource: "qrc:///settings/SettingsGeneric.qml"
            catalog: root.residentCatalog()
            selectionKey: String(itemValues)
            warmEnabled: root.residentWarmEnabled''')
    return s
def generic(s):
    s=replace(s,'    property bool residentPresented: true','''    property bool residentPrepared: false
    property var residentLanguageIndex: configstore.languageIndex
    property var languageAtPopulation
    property bool residentHideDemo: guiconfig.hideDemoItems
    property bool residentSecretItems: guiconfig.showSecretMenuItems
    property string residentLensVersion: suc.lensVersion
    function residentPrepare() {
        list.cacheBuffer = 100000
        populateModel(itemValues)
        residentPrepared = true
        list.currentIndex = -1
        list.lastIndex = -1
    }
    function requestResidentRefresh() {
        if (residentPrepared && residentPresented) residentRefresh.restart()
    }
    onResidentLanguageIndexChanged: requestResidentRefresh()
    onResidentHideDemoChanged: requestResidentRefresh()
    onResidentSecretItemsChanged: requestResidentRefresh()
    onResidentLensVersionChanged: requestResidentRefresh()
    Timer {
        id: residentRefresh
        interval: 0
        onTriggered: if (root.residentPresented) root.populateModel(root.itemValues)
    }
    property bool residentPresented: true''')
    s=replace(s,'        residentPresented = false\n        listTimer.stop()','        residentPresented = false\n        residentRefresh.stop()\n        listTimer.stop()')
    s=replace(s,'        list.section.property = ""\n        listModel.clear()\n        itemValues = ""','        subDialog.ownerKey = ""')
    s=replace(s,'    function populateModel(newItemValues)',SYNC+'\n    function populateModel(newItemValues)')
    s=replace(s,'''        if (!residentPresented) return
        list.section.property = ""
        listModel.clear();''','''        if (languageAtPopulation !== residentLanguageIndex) {
            MenuItems.refreshResidentTranslations()
            languageAtPopulation = residentLanguageIndex
        }
        var nextRows = [];''')
    s=replace(s,'                    listModel.append({ "editType": v.editType, "name": v.name, "text1": v.text1, "text2": v.text2, "suppressUnitOn": v.suppressUnitOn, "enableCond": v.enableCond, "proxy": v.proxy, "demo": v.demo, "sectionName": sectionName, "validCheck": v.validCheck })','''                    nextRows.push({ "editType": v.editType, "name": v.name, "text1": v.text1,
                        "text2": (v.text2 === undefined || v.text2 === null) ? "" : v.text2,
                        "suppressUnitOn": v.suppressUnitOn,
                        "enableCond": (v.enableCond === undefined || v.enableCond === null || v.enableCond === "") ? "true" : v.enableCond,
                        "proxy": v.proxy,
                        "demo": v.demo, "sectionName": sectionName, "validCheck": v.validCheck })''')
    s=replace(s,'listModel.setProperty(listModel.count-1, "text2", "")','nextRows[nextRows.length-1].text2 = ""',3)
    s=replace(s,'''        if(sectionName !== "") {
            list.section.property = "sectionName"
        }''','''        synchronizeRows(listModel, nextRows, "name")
        list.section.property = sectionName !== "" ? "sectionName" : ""''')
    s=replace(s,'                            onValueChanged: proxy[name] = value','                            onUserEdited: if (root.residentPresented) proxy[name] = editedValue')
    s=replace(s,'                            if (!isEnabled)','                            if (!root.residentPresented || !isEnabled)',4)
    # 长期保留的委托必须只监听自己打开的确认框，取消后旧按钮不能收到新确认。
    s=replace(s,'                            switch(name) {\n                            case "ram_only_mode":','                            subDialog.ownerKey = name\n                            switch(name) {\n                            case "ram_only_mode":')
    s=replace(s,'                            // We should find a more generic way to do this','                            subDialog.ownerKey = name\n                            // We should find a more generic way to do this')
    s=replace(s,'target: root.residentPresented ? (subDialog.item) : null','target: root.residentPresented && subDialog.ownerKey === name && name === "ram_only_mode" ? subDialog.item : null')
    s=replace(s,'target: root.residentPresented ? (delegate_item.customProfile.length > 0 ? subDialog.item : null) : null','target: root.residentPresented && subDialog.ownerKey === name && delegate_item.customProfile.length > 0 ? subDialog.item : null')
    s=replace(s,'target: root.residentPresented ? (delegate_item.fwRetryPressed ? subDialog.item : null) : null','target: root.residentPresented && subDialog.ownerKey === name && delegate_item.fwRetryPressed ? subDialog.item : null')
    s=replace(s,'            objectName: "subDialogLoader"','            objectName: "subDialogLoader"\n            property string ownerKey: ""')
    s=replace(s,'                subDialog.active = false\n                subDialog.x = parent.x + parent.width','                subDialog.active = false\n                subDialog.ownerKey = ""\n                subDialog.x = parent.x + parent.width')
    s=replace(s,'            if(guiconfig.showSecretMenuItems)\n            {','            if(guiconfig.showSecretMenuItems)\n            {\n                subDialog.ownerKey = ""')
    return s
def main_screen(s):
    s=replace(s,'    function loadCameraMenuItem(subMenu, menuItem)\n    {','    function loadCameraMenuItem(subMenu, menuItem)\n    {\n        if (root.state !== "") closeMenu()')
    s=replace(s,'            residentSource: "qrc:///mainmenu/Menu.qml"','''            residentSource: "qrc:///mainmenu/Menu.qml"
            warmEnabled: System.system_state === System.StateUp
            catalog: [
                {key: "camera", properties: {text: "CAMERA SETTINGS", residentSeed: MenuItems.cameraMenuItems}},
                {key: "general", properties: {text: "GENERAL SETTINGS", residentSeed: MenuItems.settingsMenuItems}},
                {key: "video", properties: {text: "VIDEO SETTINGS", residentSeed: MenuItems.videoMenuItems}}
            ]''')
    for key,label in [('camera','CAMERA SETTINGS'),('general','GENERAL SETTINGS'),('video','VIDEO SETTINGS')]:
        anchor='                    menu_loader.setSource("qrc:///mainmenu/Menu.qml", { "text": QT_TR_NOOP("'+label+'")'
        s=replace(s,anchor,'                    menu_loader.selectionKey = "'+key+'"\n'+anchor)
    return s
def resources():
    release=json.loads((FROZEN/'release.json').read_text(encoding='utf-8'))
    values={}
    for name,meta in release['manifest']['resources'].items():
        s=(FROZEN/'overlay'/name.lstrip('/')).read_text(encoding='utf-8')
        if digest(s)!=meta['outputSha256']:raise ValueError('fixed input changed '+name)
        values[name]=s
    sys.path.insert(0,str(ROOT/'x1d/tools'));from binary import ArmElf,qml_files
    gui=ArmElf.load('usr/bin/victory-gui');assert hashlib.sha256(gui.data).hexdigest()==GUI_SHA
    factory=qml_files(gui)
    values['/mainmenu/MainScreen.qml']=main_screen(values['/mainmenu/MainScreen.qml'])
    values['/mainmenu/Menu.qml']=menu(values['/mainmenu/Menu.qml'])
    values['/settings/SettingsGeneric.qml']=generic(values['/settings/SettingsGeneric.qml'])
    values['/mainmenu/ResidentLoader.qml']=(HERE/'qml/mainmenu/ResidentLoader.qml').read_text(encoding='utf-8')
    s=factory['/settings/components/SettingSlider.qml']
    s=replace(s,'    property real value: 1','''    property real value: 1
    signal userEdited(real editedValue)
    function commitUserValue(editedValue) {
        if (!visible || !enabled || editedValue === value) return
        userEdited(editedValue)
    }''')
    s=replace(s,'value = newValue','commitUserValue(newValue)',2)
    s=replace(s,'value = realValue','commitUserValue(realValue)')
    values['/settings/components/SettingSlider.qml']=s
    values['/settings/scripts/MenuItemImporter.js']=factory['/settings/scripts/MenuItemImporter.js']+'''\n// 只在语言索引改变时重建本 JS 实例内的翻译数组。
function refreshResidentTranslations() {
    var result = Qt.include(guiconfig.menuItemSpecificationsName)
    if (result.status !== 0) throw new Error("UI settings translation reload failed")
}
'''
    return values,factory
if __name__=='__main__':
    values,factory=resources()
    out=HERE/'build/resources';out.mkdir(parents=True,exist_ok=True)
    for key,value in values.items():
        p=out/key.lstrip('/');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(value,encoding='utf-8')
    print(json.dumps({'resources':len(values),'hardwareRequests':0}))
