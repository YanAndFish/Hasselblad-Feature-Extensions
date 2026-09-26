"""固定原厂 QRC 的离线内存评估输入；不生成装载包、不连接设备。"""
from pathlib import Path
import hashlib,json,os,re,struct,sys,zlib
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;CANDIDATE=HERE.parents[1];ROOT=CANDIDATE.parents[2]
OUT=HERE/'build';HOST=CANDIDATE/'fixes/card-format-r1/build/python-qt515'
sys.path.insert(0,str(HOST));sys.path.insert(0,str(ROOT/'x1d/tools'))
from binary import ArmElf,qml_files
from PyQt5.QtCore import QCoreApplication
from PyQt5.QtQml import QJSEngine
GUI_SHA='d29c62402091c3ad40f6f247c03ce55f248ca79e92531889b1670edeb014ed9b'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def extract_assets(gui):
    result={}
    for tree,names,data in ((0x10C75C,0x10C5E8,0x94E20),(0x1EC7F0,0x1E7E44,0x10C7F8)):
        pending=[(0,'')];seen=set()
        while pending:
            index,parent=pending.pop()
            if index in seen or len(seen)>=10000:raise ValueError('resource index')
            seen.add(index);entry=gui.read(tree+14*index,14);nameoff,flags=struct.unpack_from('>IH',entry)
            length=struct.unpack('>H',gui.read(names+nameoff,2))[0]
            if length>=1024:raise ValueError('name length')
            name=gui.read(names+nameoff+6,length*2).decode('utf-16be') if index else ''
            path=parent+'/'+name if name else parent
            if flags&2:
                count,child=struct.unpack_from('>II',entry,6)
                if count>=10000:raise ValueError('children')
                pending.extend((n,path) for n in range(child,child+count))
            elif path.lower().endswith(('.png','.svg','.ttf','.otf')):
                offset=struct.unpack_from('>I',entry,10)[0];size=struct.unpack('>I',gui.read(data+offset,4))[0]
                if size>16000000:raise ValueError('asset size')
                raw=gui.read(data+offset+4,size)
                if flags&1:
                    expanded=struct.unpack_from('>I',raw)[0]
                    if expanded>32000000:raise ValueError('expanded size')
                    raw=zlib.decompress(raw[4:]);assert len(raw)==expanded
                result[path]=raw
    return result
def catalog(spec):
    app=QCoreApplication.instance() or QCoreApplication([]);js=QJSEngine()
    prefix='''function qsTranslate(c,s){return s} function QT_TRANSLATE_NOOP(c,s){return s}
var configstore={},camera={},system={},suc={},prodinfo={},guiconfig={},farm={};'''
    value=js.evaluate(prefix+spec)
    if value.isError():raise ValueError(value.toString())
    value=js.evaluate('''JSON.stringify({menus:[cameraMenuItems,settingsMenuItems,videoMenuItems],pages:cameraMenuItems.concat(settingsMenuItems,videoMenuItems).filter(function(e){return !e.demo && e.itemFile.indexOf("SettingsGeneric.qml")>=0}).map(function(e){return {name:e.settingsList,rows:getSettingsList(e.settingsList).filter(function(r){return !r.demo})}})},function(k,v){if(k==="proxy")return v===configstore?"configstore":v===camera?"camera":v===system?"system":v===suc?"suc":v===prodinfo?"prodinfo":v===guiconfig?"guiconfig":v===farm?"farm":"unknown";return v})''')
    if value.isError():raise ValueError(value.toString())
    result=json.loads(value.toString());result['sourceSha256']=hashlib.sha256(spec.encode()).hexdigest()
    result['counts']={'categories':len(result['menus']),'menuEntries':sum(map(len,result['menus'])),'ordinaryPages':len(result['pages']),
        'potentialRows':sum(len(p['rows']) for p in result['pages']),'sectionDeclarations':sum(r['editType']==9 for p in result['pages'] for r in p['rows']),
        'functionalRows':sum(r['editType']!=9 for p in result['pages'] for r in p['rows'])}
    return result
def prepare():
    if Path.cwd().resolve()!=ROOT:raise ValueError('workspace mismatch')
    gui=ArmElf.load('usr/bin/victory-gui');assert hashlib.sha256(gui.data).hexdigest()==GUI_SHA
    source=qml_files(gui);spec=source['/settings/scripts/MenuItemSpecificationsWedge.js'];inventory=catalog(spec)
    save(OUT/'catalog.json',inventory)
    assets=extract_assets(gui)
    adaptations=[]
    for variant in ('factory','a8'):
        dest=OUT/'qml'/variant;dest.mkdir(parents=True,exist_ok=True);values=dict(source)
        if variant=='a8':
            frozen=CANDIDATE/'build/fixed/ui-resident-0456d37bc5ddbc57/overlay'
            for p in frozen.rglob('*.qml'):values['/'+p.relative_to(frozen).as_posix()]=p.read_text(encoding='utf-8')
        for key,value in values.items():
            value=re.sub(r'^import com\.hasselblad\..*\n','',value,flags=re.M)
            value=value.replace('qrc:///',dest.as_uri()+'/').replace('qrc:/',dest.as_uri()+'/')
            # 只在评估副本中计数行/分组；不改变控件行为。
            if key=='/settings/SettingsGeneric.qml':
                value=value.replace('section.delegate:\n            Item {','section.delegate:\n            Item {\n            objectName: "EvaluationSection"')
                value=value.replace('    id: root','    id: root\n    property alias evaluationList: list',1)
            if key=='/mainmenu/Menu.qml':value=value.replace('    id: root','    id: root\n    property alias evaluationList: list',1)
            p=dest/key.lstrip('/');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(value,encoding='utf-8')
        for key,raw in assets.items():
            p=dest/key.lstrip('/');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        # 保留真实 Wedge 数组和筛选表达式，只移除原生 JS 插件 import/Qt.include。
        (dest/'settings/scripts/MenuItemImporter.js').write_text(spec.replace('qrc:///',dest.as_uri()+'/').replace('qrc:/',dest.as_uri()+'/'),encoding='utf-8')
    report={'guiSha256':GUI_SHA,'catalogCounts':inventory['counts'],'nativeImportsRemoved':True,'graphicalEffectsOriginal':True,
        'assets':{p:{'sha256':hashlib.sha256(v).hexdigest(),'bytes':len(v)} for p,v in assets.items()},
        'sourceSha256':sha(Path(__file__)),'hardwareRequests':0,'productionChanged':False}
    save(OUT/'input-manifest.json',report)
    print(json.dumps({'counts':inventory['counts'],'assets':len(assets),'assetBytes':sum(map(len,assets.values()))}))
if __name__=='__main__':prepare()
