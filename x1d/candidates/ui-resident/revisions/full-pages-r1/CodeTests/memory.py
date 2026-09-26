"""相同原厂资产和原生替身下比较新候选与 card-format-r1；仅宿主内存。"""
from fixtures import *
import collections,importlib.util,statistics,subprocess

def run(variant,tag):
    actual_resources=patch.resources
    baseline=CANDIDATE/'fixes/card-format-r1/patch.py'
    if variant=='baseline':
        spec=importlib.util.spec_from_file_location('memory_baseline',baseline);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
        factory=actual_resources()[1];patch.resources=lambda:(old.resources(),factory)
    app=QGuiApplication([]);f=Fixture('memory-'+variant+'-'+tag,instrument=False)
    cold=memory_fixture.settled()
    f.native_update('System','system_state',2)
    if variant=='full':f.start_warm()
    for index,menu in enumerate(memory_fixture.data()['menus']):
        f.open_menu(index)
        for entry in menu:
            if entry.get('demo') or not entry['itemFile'].endswith('SettingsGeneric.qml'):continue
            name=entry['settingsList'];f.root.openPage(name)
            wait_for(lambda:any(p.property('itemValues')==name and p.property('residentPresented') for p in f.pages()),'memory page '+name)
            QTest.qWait(180);f.root.closePage();QTest.qWait(40)
        f.root.closeMenu();QTest.qWait(100)
    hidden=memory_fixture.settled();objects=walk(f.root)
    names=dict(collections.Counter(o.objectName() for o in objects if o.objectName()))
    if variant=='full':assert names.get('SettingsGeneric_root')==23 and names.get('baseItem')==99
    else:assert names.get('SettingsGeneric_root')==1 and names.get('Menu_root')==1
    report={'variant':variant,'tag':tag,'cold':cold,'hidden':hidden,'namedObjects':names,'objects':len(objects),'warnings':f.errors(),'hardwareRequests':0,'targetMeasured':False,
        'resources':{k:patch.digest(v) for k,v in patch.resources()[0].items()},'sources':{p.relative_to(ROOT).as_posix():sha(p) for p in [Path(__file__),Path(__file__).with_name('fixtures.py'),HERE/'patch.py',HERE/'qml/mainmenu/ResidentLoader.qml',baseline]}}
    save(HERE/'build/memory'/(variant+'-'+tag+'.json'),report)
    print(json.dumps({'variant':variant,'tag':tag,'privateMiB':hidden['median']['privateCommit']/1048576,'objects':len(objects),'warnings':len(f.errors())}),flush=True);f.close()

def suite():
    reports=[]
    for i in range(1,6):
        for variant in ('baseline','full'):
            subprocess.run([sys.executable,str(Path(__file__)),variant,'r'+str(i)],check=True,timeout=100)
            reports.append(json.loads((HERE/'build/memory'/(variant+'-r'+str(i)+'.json')).read_text(encoding='utf-8')))
    paired=[]
    for i in range(5):
        a,b=reports[i*2:i*2+2]
        paired.append({key:b['hidden']['median'][key]-a['hidden']['median'][key] for key in ('privateCommit','workingSet')})
    summary={'passed':True,'pairs':5,'pairedDeltaBytes':paired,'medianDeltaBytes':{k:statistics.median(v[k] for v in paired) for k in paired[0]},'targetMeasured':False,'hardwareRequests':0,
        'scope':'Qt5.15.2 Windows64 software/offscreen; same 23-page traversal; route stubs; no native gate library loaded',
        'sources':{p.relative_to(ROOT).as_posix():sha(p) for p in [Path(__file__),Path(__file__).with_name('fixtures.py'),*(HERE/'build/memory'/(variant+'-r'+str(i)+'.json') for i in range(1,6) for variant in ('baseline','full'))]}}
    save(HERE/'build/memory-summary.json',summary);print(json.dumps(summary),flush=True)
if __name__=='__main__':suite() if len(sys.argv)==1 else run(*sys.argv[1:])
