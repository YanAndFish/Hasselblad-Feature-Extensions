"""真实 Qt Loader 延迟孵化、失效代次及临时路由失败回归。"""
from fixtures import *
from PyQt5.QtQml import QQmlIncubationController
from PyQt5.QtCore import qVersion
def main():
    app=QGuiApplication([]);f=Fixture('races');checks=[]
    def check(name,condition):
        assert condition,name
        checks.append(name)
    original=f.view.engine().incubationController();controller=QQmlIncubationController()
    f.view.engine().setIncubationController(controller)
    f.root.openMenu(0);QTest.qWait(100)
    check('actual incubation pending before close',controller.incubatingObjectCount()>0)
    f.root.closeMenu()
    for i in range(200):
        controller.incubateFor(10);QTest.qWait(10)
        if controller.incubatingObjectCount()==0 and named(f.root,'Menu_root'):break
    check('late completion stays hidden',not f.root.canOpen() and all(not p.property('residentPresented') and not p.property('visible') for p in named(f.root,'Menu_root')))
    check('no About or settings action during cancelled load',not any(v.actions for v in f.keep.values()) and not f.config.fixtureWrites)
    f.view.engine().setIncubationController(original)
    f.start_warm();f.open_menu(0);f.open_page('cameraSettingsImage');f.root.closeMenu();QTest.qWait(100)
    check('normal route recovers after cancelled incubation',len(f.pages())==23 and len(named(f.root,'baseItem'))==99)
    f.root.setProperty('state','add_favorite');wait_for(lambda:len(named(f.root,'TransientRouteFixture'))==1,'add favorite route')
    instance=named(f.root,'TransientRouteFixture')[0];f.root.closeMenu();QTest.qWait(150)
    check('actual add-favorite state remains transient',sip.isdeleted(instance) and not f.root.canOpen())
    check('all normal pages survive favorite transient',len(f.pages())==23)
    host=named(f.root,'menu_Loader')[0];emissions=[];host.loaded.connect(lambda:emissions.append(1))
    previous=len(f.warnings)
    host.setSource((f.work/'missing-fixture.qml').as_uri(),{});host.setProperty('active',True)
    wait_for(lambda:host.property('status')==3,'missing source error')
    check('missing source does not emit loaded',not emissions)
    host.setProperty('active',False);QTest.qWait(100)
    check('missing source close resets status',host.property('status')==0 and host.property('item') is None)
    expected=f.warnings[previous:];check('only expected missing source diagnostic',len(expected)==1 and 'missing-fixture.qml' in expected[0])
    del f.warnings[previous:]
    f.open_menu(2);p=f.open_page('videoSettingsVideoQuality')
    check('resident route works after lazy failure',p.property('residentPresented') and len(emissions)==1)
    f.root.closeMenu();QTest.qWait(100)
    check('no unexpected warnings '+str(f.errors()),not f.errors())
    save(HERE/'build/race-validation.json',{'passed':True,'checks':checks,'count':len(checks),'qt':qVersion(),'hardwareRequests':0,'targetValidated':False,'resources':{k:patch.digest(v) for k,v in patch.resources()[0].items()},'sources':{p.relative_to(ROOT).as_posix():sha(p) for p in [Path(__file__),Path(__file__).with_name('fixtures.py'),HERE/'patch.py',HERE/'qml/mainmenu/ResidentLoader.qml']}})
    print(json.dumps({'passed':True,'checks':len(checks),'hardwareRequests':0}));f.close()
if __name__=='__main__':main()
