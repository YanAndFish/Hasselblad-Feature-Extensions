"""X1D 1.25.0 AF 独立装载资源；不改原厂曝光、回放和常驻页面。"""
from pathlib import Path
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
PARENT=HERE.parent
ROOT=HERE.parents[2]
AF=ROOT/'x1d/af-experiment/camera-settings-r1'
CACHE=ROOT/'.research-cache/x1d-1.25.0'
OUT=HERE/'build/resources'
AF_MENU='/settings/scripts/MenuItemSpecificationsWedge.js'
AF_ENTRY='cameraSettingsAdvancedAF'
AF_ANCHOR='        {settingsList: "cameraSettingsAutofocus",       itemText:QT_TRANSLATE_NOOP("MENUS", "Autofocus"),           itemFile:"qrc:///settings/SettingsGeneric.qml", demo: false, largeIcon: "LargeIconAutofocus"},'
def digest(data):return hashlib.sha256(data).hexdigest()
def sha(path):return digest(path.read_bytes())
def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def build():
    if Path.cwd().resolve()!=ROOT:raise RuntimeError('workspace mismatch')
    flash=ROOT/'x1d/wireless-flash'
    sys.path.insert(0,str(flash))
    spec=importlib.util.spec_from_file_location('af_only_resource_common',flash/'build.py')
    common=importlib.util.module_from_spec(spec);spec.loader.exec_module(common)
    raw=(common.BASELINE/'usr/bin/victory-gui').read_bytes()
    if digest(raw)!=common.GUI_SHA:raise ValueError('factory GUI version')
    original=common.qml_files(common.ArmElf(raw))
    main=original['/main.qml']
    if digest(main.encode())!='9793c2eb01018e1f17610d99934425638884338167fc055237211f70f757e0e3':raise ValueError('factory main')
    hold='''    // 一次性安装保持，只在当前原厂界面健康且空闲时发送活动通知。
    Timer {
        id: afOnlyInstallHoldTimer
        interval: 500; repeat: true; triggeredOnStart: true
        running: typeof hblAfInstall!=="undefined" && hblAfInstall.installationHold
        onTriggered: {
            var healthy = System.system_state===System.StateUp && ErrorControl.code===Errors.ErrorNone &&
                          mainWindow.status===Loader.Ready && mainWindow.item && !mainWindow.item.sleeping &&
                          control.state!=="sleeping" && !Camera.inSession && !Camera.exposing
            if (healthy) mainWindow.item.idleWakeupOrForceOff(true)
            hblAfInstall.installPulse = !!healthy
        }
    }
'''
    end=main.rfind('}')
    edited=main[:end]+hold+main[end:]
    if edited.replace(hold,'',1)!=main:raise ValueError('factory body changed')
    menu=original[AF_MENU]
    if menu.count(AF_ANCHOR)!=1 or AF_ENTRY in menu:raise ValueError('menu anchor')
    # 用户指定入口放入原厂自动对焦页，使用原厂 BUTTON 和子页面导航。
    anchor='            /* AF debug options */'
    if menu.count(anchor)!=1:raise ValueError('AF settings list anchor')
    entry='            {editType: SettingType.BUTTON, name: "'+AF_ENTRY+'", text1: "AF 设置", demo: false },\n\n'
    menu=menu.replace(anchor,entry+anchor,1)
    generic=original['/settings/SettingsGeneric.qml']
    branch='                            case "liveViewStart":'
    addition='''                            case "cameraSettingsAdvancedAF":
                                activateSettingsSubMenu("cameraSettingsAdvancedAF", "qrc:///af-settings/AfSettingsHost.qml", "AF 设置")
                                subDialogMA.allowSubDialogSwipe = true
                                break;
'''
    if generic.count(branch)!=1:raise ValueError('factory button dispatch')
    generic=generic.replace(branch,addition+branch,1)
    anchor='''                if(item.hasOwnProperty("menuLabel"))
                    item.menuLabel = menuLabel;'''
    close='''
                if(item.hasOwnProperty("afCloseRequested"))
                    item.afCloseRequested.connect(subDialog.closeSubDialog);'''
    if generic.count(anchor)!=1:raise ValueError('factory subdialog completion')
    generic=generic.replace(anchor,anchor+close,1)
    if generic.replace(addition,'',1).replace(close,'',1)!=original['/settings/SettingsGeneric.qml']:raise ValueError('factory settings body changed')
    control=original['/controlscreen/ControlScreen.qml']
    imports='import QtQuick 2.5'
    guard='    property bool preventSwipe: popupOpen || Camera.inSession'
    if control.count(imports)!=1 or control.count(guard)!=1:raise ValueError('factory control anchors')
    control=control.replace(imports,imports+'\nimport "qrc:/af-settings"',1)
    control=control.replace(guard,guard+' || afQuickEntry.pageOpen',1)
    quick='''    AfQuickEntry {
        id: afQuickEntry
        parent: root
        anchors.fill: root
        z: 20
        available: guiconfig.isWedge && !scope.popupOpen && !Camera.inSession && !Camera.exposing && !viewModel.videoMode
        onPageOpenChanged: if (!pageOpen) root.forceActiveFocus()
    }
'''
    end=control.rfind('}');control=control[:end]+quick+control[end:]
    recovered=control.replace(quick,'',1).replace(' || afQuickEntry.pageOpen','',1).replace('\nimport "qrc:/af-settings"','',1)
    if recovered!=original['/controlscreen/ControlScreen.qml']:raise ValueError('factory controls body changed')
    files={'/main.qml':edited,AF_MENU:menu,'/settings/SettingsGeneric.qml':generic,
           '/controlscreen/ControlScreen.qml':control,
           '/af-settings/AfQuickEntry.qml':(HERE/'qml/AfQuickEntry.qml').read_text(encoding='utf-8'),
           '/af-settings/AfSettingsHost.qml':(HERE/'qml/AfSettingsHost.qml').read_text(encoding='utf-8'),
           '/af-settings/SettingsPage.qml':(AF/'SettingsPage.qml').read_text(encoding='utf-8')}
    for key,value in files.items():
        path=OUT/'qml'/key.lstrip('/');path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(value,encoding='utf-8',newline='\n')
    data=common.rcc(files);(OUT/'af-only-ui.rcc').write_bytes(data)
    # 测试器沿用组合 RCC 文件名，仅为本地测试别名，不加入相机包。
    (OUT/'combined-ui.rcc').write_bytes(data)
    sources=[Path(__file__),HERE/'qml/AfSettingsHost.qml',HERE/'qml/AfQuickEntry.qml',AF/'SettingsPage.qml']
    report={'kind':'af-only-resources','sourceVersion':'X1D 1.25.0','qml':{k:digest(v.encode()) for k,v in files.items()},
            'sourceHashes':{p.relative_to(ROOT).as_posix():sha(p) for p in sources},'mainSha256':digest(edited.encode()),
            'factoryMainPreserved':True,'factorySettingsPreserved':True,'factoryControlsPreserved':True,
            'entryLocation':['cameraSettingsAutofocus-child-button','controlscreen-center-button'],'resourceCount':7,'rccSha256':digest(data),'hardwareRequests':0,'installed':False}
    save(OUT/'manifest.json',report)
    return report

def native():
    if Path.cwd().resolve()!=ROOT:raise RuntimeError('workspace mismatch')
    output=HERE/'build/native';output.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ)
    for key,name in [('ZIG_GLOBAL_CACHE_DIR','global-cache'),('ZIG_LOCAL_CACHE_DIR','local-cache'),('TEMP','tmp'),('TMP','tmp')]:
        path=output/name;path.mkdir(exist_ok=True);env[key]=str(path)
    previous=json.loads((PARENT/'build/native/build.json').read_text())
    mappings={str(PARENT/'native/combined_runtime.cpp'):str(HERE/'native/runtime.cpp'),
              str(PARENT/'build/native/libhbl-combined.so.o'):str(output/'runtime.o'),
              str(PARENT/'build/native/libhbl-combined.so'):str(output/'libhbl-af-only.so'),
              '-Wl,-soname,libhbl-combined.so':'-Wl,-soname,libhbl-af-only.so'}
    compiler=CACHE/'toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    commands=[]
    for old in previous['commands'][:2]:
        args=[mappings.get(arg,arg) for arg in old['arguments']]
        result=subprocess.run([str(compiler)]+args,env=env,capture_output=True,text=True,timeout=60)
        commands.append({'arguments':args,'exit':result.returncode,'stderr':result.stderr})
        if result.returncode:raise RuntimeError(result.stderr)
    sys.path.insert(0,str(CACHE/'python'))
    from elftools.elf.elffile import ELFFile
    binary=output/'libhbl-af-only.so';elf=ELFFile(io.BytesIO(binary.read_bytes()))
    rel=elf.get_section_by_name('.rel.dyn');plt=elf.get_section_by_name('.rel.plt')
    assert elf.elfclass==32 and elf['e_machine']=='EM_ARM' and elf.little_endian
    assert rel['sh_addr']+rel['sh_size']==plt['sh_addr']
    imports=[s.name for s in elf.get_section_by_name('.dynsym').iter_symbols() if s['st_shndx']=='SHN_UNDEF']
    assert not set(imports)&{'socket','connect','send','sendto','recv','recvfrom','system','execve'}
    report={'compiled':True,'sha256':sha(binary),'bytes':binary.stat().st_size,'imports':imports,
            'commands':commands,'relocationsContiguous':True,'hardwareRequests':0,
            'sources':{p.relative_to(ROOT).as_posix():sha(p) for p in [Path(__file__),HERE/'native/runtime.cpp',PARENT/'native/install_window.h',ROOT/'x1d/wireless-flash/native/formal_install_hold.h']}}
    save(output/'build.json',report);return report

if __name__=='__main__':
    a=build();b=native();print(json.dumps({'resources':a['resourceCount'],'nativeBytes':b['bytes'],'hardwareRequests':0}))
