"""以真实 Qt 宿主对象验证公开 Loader.item 收集与固定类别诊断。"""
from pathlib import Path
import collections,hashlib,json,sys
sys.dont_write_bytecode=True
REV=Path(__file__).resolve().parents[1];R1=REV.parent/'full-pages-r1';ROOT=REV.parents[4]
sys.path.insert(0,str(R1/'CodeTests'))
from fixtures import *
import fixtures as fixture_module

MENUS={'camera','general','video'}
PAGES={v['settingsList'] for group in memory_fixture.data()['menus'] for v in group if not v.get('demo') and v['itemFile']=='qrc:///settings/SettingsGeneric.qml'}
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def collect(f):
    objects=walk(f.root);result={'screen':len(named(f.root,'MainScreen_root')),'top':len(named(f.root,'menu_Loader')),
        'child':len(named(f.root,'entry_loader')),'native':0,'null':0,'loading':0,'ready':0,'error':0,
        'menus':0,'pages':0,'prepared':0,'lists':0,'model':0,'delegates':0,'rowloaders':0,'rowready':0,'rowerrors':0,'pools':[]}
    menu_keys=set();page_keys=set()
    for loader in (o for o in objects if o.objectName()=='residentNativeLoader'):
        result['native']+=1;state=loader.property('status');result[{0:'null',1:'ready',2:'loading',3:'error'}[state]]+=1
        raw=str(loader.property('slotKey'));kind='menu' if raw in MENUS else 'page' if raw in PAGES else 'other'
        pool={'key':raw if kind!='other' else 'other','kind':kind,'loader':state,'item':0,'prepared':0,'lists':0,'model':0,'delegates':0,'rowloaders':0,'rowready':0,'rowerrors':0}
        page=loader.property('item')
        if page is not None:
            pool['item']=1;pool['prepared']=int(bool(page.property('residentPrepared')));result['prepared']+=pool['prepared']
            menu=page.objectName()=='Menu_root';(menu_keys if menu else page_keys).add(raw)
            lists=named(page,'Menu_list' if menu else 'SettingsGeneric_list');pool['lists']=len(lists);result['lists']+=len(lists)
            for li in lists:
                count=li.property('count');rows=named(li,'listDelegate' if menu else 'baseItem');loaders=[] if menu else named(li,'specialItem')
                pool['model']+=count;pool['delegates']+=len(rows);pool['rowloaders']+=len(loaders)
                pool['rowready']+=sum(v.property('status')==1 for v in loaders);pool['rowerrors']+=sum(v.property('status')==3 for v in loaders)
                for key in ('model','delegates','rowloaders','rowready','rowerrors'):result[key]+=pool[key] if len(lists)==1 else 0
        result['pools'].append(pool)
    result['menus']=len(menu_keys);result['pages']=len(page_keys);return result
def complete(value):
    if [value[k] for k in ('screen','top','child')]!=[1,1,3] or value['menus']!=3 or value['pages']!=23:return False
    if value['native']!=26 or value['ready']!=26 or value['prepared']!=26 or value['lists']!=26:return False
    return all(p['item']==1 and p['prepared']==1 and p['lists']==1 and p['model']>0 and p['delegates']==p['model'] and
        (p['kind']=='menu' or p['rowloaders']==p['model']==p['rowready']) for p in value['pools'])
def main():
    fixture_module.HERE=REV
    app=QGuiApplication([]);f=Fixture('r2-diagnostic');f.root.setObjectName('MainScreen_root');checks=[]
    def check(name,value):assert value,name;checks.append(name)
    cold=collect(f);check('cold fixed counters show incomplete without error',not complete(cold) and cold['error']==0)
    f.start_warm();ready=collect(f);check('public Loader.item sees exact 3 menu 23 page pool',complete(ready))
    check('public item equals visual child in host but collector does not rely on it',all(o.property('item') is not None and len(o.childItems())==1 and int(sip.unwrapinstance(o.property('item')))==int(sip.unwrapinstance(o.childItems()[0])) for o in named(f.root,'residentNativeLoader')))
    check('diagnostic uses fixed keys only',all(p['key'] in MENUS|PAGES|{'other'} for p in ready['pools']))
    slot=named(f.root,'residentNativeLoader')[-1];slot.setProperty('source',QUrl.fromLocalFile(str(f.work/'missing-r2.qml')));QTest.qWait(100)
    failed=collect(f);check('real Loader error identifies one failed fixed pool',failed['error']==1 and failed['ready']==25)
    source=(REV/'native/readiness.h').read_text(encoding='utf-8')
    loader_header=ROOT/'.research-cache/x1d-1.25.0/qt-public/qtdeclarative-opensource-src-5.5.1/src/quick/items/qquickloader_p.h'
    header=loader_header.read_text(encoding='utf-8')
    check('production reads public item property','QObject *page = o->property("item").value<QObject *>();' in source and 'QList<QQuickItem *> roots = loader->childItems();' not in source)
    check('fixed Qt5.5 header defines Loader item property','Q_PROPERTY(QObject *item READ item NOTIFY itemChanged)' in header)
    check('diagnostic excludes native values and free text',all(v not in source for v in ('SuSerial','lensVersion','menuLabel','text1','text2','error.toString')))
    f.close();report={'passed':True,'checks':checks,'count':len(checks),'cold':cold,'ready':ready,'failed':failed,
        'hardwareRequests':0,'targetValidated':False,'scope':'Qt5.15.2 host actual QML object tree; production collector separately ARM Qt5.5 compiled',
        'sources':{p.relative_to(ROOT).as_posix():sha(p) for p in [Path(__file__),REV/'native/readiness.h',loader_header,R1/'CodeTests/fixtures.py',R1/'build/readiness-validation.json']}}
    out=REV/'build/diagnostic-validation.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'checks':len(checks),'ready':{k:ready[k] for k in ('native','menus','pages','model','delegates','rowloaders','rowready')},'hardwareRequests':0}))
if __name__=='__main__':main()
