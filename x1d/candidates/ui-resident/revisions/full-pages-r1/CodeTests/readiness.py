"""真实宿主对象树观测 + 与生产共用的 C++ 就绪策略；不冒充目标机执行。"""
from fixtures import *
from PyQt5.QtTest import QTest
import subprocess

def snapshot(f):
    objects=walk(f.root);complete=True;error=False;menus=set();pages=set();row_counts=[]
    for o in objects:
        if o.objectName()!='residentNativeLoader':continue
        state=o.property('status')
        if state==3:error=True
        if state!=1:complete=False;continue
        children=o.childItems()
        if len(children)!=1:complete=False;continue
        page=children[0];menu=page.objectName()=='Menu_root'
        if not menu and page.objectName()!='SettingsGeneric_root':error=True;continue
        key=o.property('slotKey');keys=menus if menu else pages
        if key in keys:error=True
        keys.add(key)
        if not menu and page.property('itemValues')!=key:error=True
        if not page.property('residentPrepared'):complete=False
        lists=named(page,'Menu_list' if menu else 'SettingsGeneric_list')
        if len(lists)!=1:complete=False;error=error or len(lists)>1
        for li in lists:
            rows=named(li,'listDelegate' if menu else 'baseItem');count=li.property('count')
            loaders=[] if menu else named(li,'specialItem')
            if count<1 or len(rows)!=count or (not menu and len(loaders)!=count):complete=False
            for loader in loaders:
                if loader.property('status')==3:error=True
                if loader.property('status')!=1:complete=False
            row_counts.append((key,count,len(rows),len(loaders)))
    expected={v['settingsList'] for group in memory_fixture.data()['menus'] for v in group if not v.get('demo') and v['itemFile']=='qrc:///settings/SettingsGeneric.qml'}
    # Harness 使用真实 MainScreen Loader/States，根 objectName 在本测试设为原厂名。
    counts=[len(named(f.root,n)) for n in ('MainScreen_root','menu_Loader','entry_loader')]
    if counts!=[1,1,3]:complete=False
    if any(v>n for v,n in zip(counts,[1,1,3])):error=True
    if menus!={'camera','general','video'} or pages!=expected:complete=False
    if menus-{'camera','general','video'} or pages-expected:error=True
    return {'complete':complete,'error':error,'menus':len(menus),'pages':len(pages),'rows':row_counts}

def main():
    app=QGuiApplication([]);f=Fixture('readiness');f.root.setObjectName('MainScreen_root');checks=[]
    def check(name,value):assert value,name;checks.append(name)
    cold=snapshot(f);check('System0 stays pending',not cold['complete'] and not cold['error'])
    f.start_warm();ready=snapshot(f)
    check('actual 3 menus 23 pages and all row loaders ready',ready['complete'] and not ready['error'])
    check('native loader has exactly one visual page child',all(len(o.childItems())==1 for o in named(f.root,'residentNativeLoader')))
    check('warming issues zero native actions and writes',all(not o.actions and not o.fixtureWrites for o in f.keep.values()))
    # 一个真实异步 Loader 错误；保留其他已就绪页，禁止误报整个池已完成。
    slot=named(f.root,'residentNativeLoader')[-1]
    slot.setProperty('source',QUrl.fromLocalFile(str(f.work/'missing-gate.qml')));QTest.qWait(100)
    failed=snapshot(f);check('one real pool Loader error is terminal failure',failed['error'] and not failed['complete'])
    f.close()
    out=HERE/'build/readiness';out.mkdir(parents=True,exist_ok=True)
    cpp='''#include <cassert>
#include "gate_policy.h"
using namespace ResidentGate;
int main() {
 Policy delayed; assert(delayed.sample(false,false,0)==Pending);
 assert(delayed.sample(false,false,20000)==Pending);
 assert(delayed.sample(true,false,20200)==Pending);
 assert(delayed.sample(true,false,20400)==Pending);
 assert(delayed.sample(true,false,20600)==Ready);
 Policy error; assert(error.sample(true,false,0)==Pending);
 assert(error.sample(false,true,200)==Failed);
 assert(error.sample(true,false,400)==Failed);
 Policy never; for(int t=0;t<30000;t+=200) assert(never.sample(false,false,t)==Pending);
 assert(never.sample(false,false,30000)==TimedOut);
 Policy unstable; unstable.sample(true,false,0);unstable.sample(true,false,200);
 assert(unstable.sample(false,false,400)==Pending);
 assert(unstable.sample(true,false,600)==Pending);
 assert(unstable.sample(true,false,800)==Pending);
 assert(unstable.sample(true,false,1000)==Ready);
 Policy deadline;deadline.sample(true,false,29600);deadline.sample(true,false,29800);
 assert(deadline.sample(true,false,30000)==TimedOut);
}
'''
    path=out/'policy.cpp';path.write_text(cpp,encoding='utf-8')
    zig=ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    env=dict(os.environ,ZIG_GLOBAL_CACHE_DIR=str(out/'global-cache'),ZIG_LOCAL_CACHE_DIR=str(out/'local-cache'))
    subprocess.run([str(zig),'c++','-std=c++11','-I',str(HERE/'native'),str(path),'-o',str(out/'policy.exe')],env=env,check=True,capture_output=True,text=True,timeout=60)
    subprocess.run([str(out/'policy.exe')],check=True,timeout=10)
    checks+=['shared C++ policy delayed completion','shared C++ policy loader failure','shared C++ policy never completes timeout','shared C++ policy resets unstable streak','shared C++ policy deadline wins']
    save(HERE/'build/readiness-validation.json',{'passed':True,'checks':checks,'cold':cold,'ready':ready,'failed':failed,'hardwareRequests':0,'targetValidated':False,'collectorValidation':'Python equivalent observes real host Qt5.15 objects; ARM Qt5.5 collector compile verified separately','sources':{p.relative_to(ROOT).as_posix():sha(p) for p in [Path(__file__),Path(__file__).with_name('fixtures.py'),HERE/'native/readiness.h',HERE/'native/gate_policy.h',path]}})
    print(json.dumps({'passed':True,'count':len(checks),'ready':ready,'hardwareRequests':0}))
if __name__=='__main__':main()
