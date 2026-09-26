"""全普通页真实状态机/真实控件回归。设备入口不存在；危险方法仅内存计数。"""
from fixtures import *
from PyQt5.QtCore import QTranslator,qVersion
checks=[]
def check(label,condition):
    if not condition:raise AssertionError(label)
    checks.append(label)
def row_map(page):return {r.property('testRowKey'):int(sip.unwrapinstance(r)) for r in named(page,'baseItem')}
def row(page,key):return next(v for v in named(page,'baseItem') if v.property('testRowKey')==key)
def select(f,page,key,mouse=False):
    rows=json.loads(page.testRows());index=next(i for i,r in enumerate(rows) if r['name']==key)
    li=named(page,'SettingsGeneric_list')[0];li.positionViewAtIndex(index,0);QTest.qWait(70)
    item=row(page,key)
    if mouse:
        button=named(item,'buttonDelegate_menuButton')[0]
        p=button.mapToScene(QPointF(button.width()/2,button.height()/2)).toPoint()
        QTest.mouseClick(f.view,Qt.LeftButton,Qt.NoModifier,p)
    else:
        content=next(v for v in walk(item) if v.objectName() in ('buttonDelegate','checkBoxDelegate','dropDownItem'))
        content.gotSelected()
    QTest.qWait(150)
def transient(f,page,name):
    wait_for(lambda:len(named(page,name))==1,name+' ready')
    return named(page,name)[0]
def cancel(f,page):
    QTest.keyClick(f.view,Qt.Key_F2);QTest.qWait(150)
    check('cancel closes transient '+str(len(checks)),not named(page,'subDialogLoader')[0].property('active'))
def main():
    app=QGuiApplication([]);f=Fixture('suite')
    check('no preconstruction before System.StateUp',not f.pages() and not named(f.root,'Menu_root'))
    check('cold QML clean',not f.errors())
    f.start_warm();pages=f.pages()
    identities={p.property('itemValues'):int(sip.unwrapinstance(p)) for p in pages}
    rows={p.property('itemValues'):row_map(p) for p in pages}
    check('three distinct menu instances',len(named(f.root,'Menu_root'))==3)
    check('23 distinct normal page instances',len(identities)==23)
    check('99 ready functional rows',sum(len(v) for v in rows.values())==99)
    check('27 section and 26 menu delegates',len(named(f.root,'testSection'))==27 and len(named(f.root,'listDelegate'))==26)
    check('preconstruction never writes proxy',not any(v.fixtureWrites for v in f.keep.values()))
    check('preconstruction never calls native action/read',not any(v.actions for v in f.keep.values()))
    check('all warm pages hidden and inactive',all(not p.property('visible') and not p.property('residentPresented') for p in pages))
    check('no eager special or confirm instance',not named(f.root,'TransientRouteFixture') and not named(f.root,'GenericConfirm_root') and not named(f.root,'CardFormat_root'))
    catalog=memory_fixture.data()
    for cycle in range(2):
        for index,items in enumerate(catalog['menus']):
            f.open_menu(index)
            for entry in items:
                if entry.get('demo') or not entry['itemFile'].endswith('SettingsGeneric.qml'):continue
                name=entry['settingsList'];page=f.open_page(name)
                check('single visible page '+str((cycle,name)),sum(bool(p.property('visible')) for p in f.pages())==1)
                check('same page and rows '+str((cycle,name)),int(sip.unwrapinstance(page))==identities[name] and row_map(page)==rows[name])
                QTest.keyClick(f.view,Qt.Key_Escape);QTest.qWait(70)
                check('escape closes page but retains rows '+str((cycle,name)),not page.property('residentPresented') and row_map(page)==rows[name])
            f.root.closeMenu();QTest.qWait(70)
        print(json.dumps({'navigationCycle':cycle,'checks':len(checks)}),flush=True)
    check('About reads only on two actual entries',f.keep['suc'].actions==[('readLensVersion',)]*2)
    check('all navigation still zero settings write',not f.config.fixtureWrites)
    # 连续切换 key/source，旧的异步完成不能复活被关闭的页。
    f.root.openMenu(0);f.root.openMenu(1);f.root.closeMenu();QTest.qWait(350)
    check('rapid supersession leaves no page presented',all(not p.property('residentPresented') for p in f.pages()) and not f.root.canOpen())
    f.open_menu(0);f.root.loadCameraMenuItem('Configuration','CustomOption_QuickAdjustOn')
    wait_for(lambda:f.page('cameraSettingsConfiguration').property('residentPresented'),'favorite direct page')
    check('actual camera shortcut reuses correct page',int(sip.unwrapinstance(f.page('cameraSettingsConfiguration')))==identities['cameraSettingsConfiguration'])
    f.root.closeMenu();QTest.qWait(150)
    # 三个特殊入口与 Profiles 快捷入口只测试真实路由，控件为显式特殊页壳。
    for index,key,file in [(0,'cameraSettingsGreyBalanceTool','components/GreyBalanceTool.qml'),(1,'generalSettingsDateTime','settings/DateTime.qml'),(1,'generalSettingsSpiritLevel','settings/SpiritLevelView.qml')]:
        f.open_menu(index);f.root.openSpecial(key,file);wait_for(lambda:len(named(f.root,'TransientRouteFixture'))==1,'special route')
        instance=named(f.root,'TransientRouteFixture')[0]
        check('special uses transient route '+key,not any(p.property('residentPresented') for p in f.pages()))
        f.root.closePage();QTest.qWait(150);check('special destroyed '+key,sip.isdeleted(instance))
        f.root.closeMenu();QTest.qWait(70)
    f.root.loadProfilesMenu();wait_for(lambda:len(named(f.root,'TransientRouteFixture'))==1,'profiles shortcut')
    f.root.closeMenu();QTest.qWait(150)
    check('profiles shortcut transient destroyed',not named(f.root,'TransientRouteFixture'))
    # 可见行集改变只插入/移除相应行，未变的功能控件保留身份。
    f.native_update('guiconfig','showSecretMenuItems',False);QTest.qWait(80)
    check('hidden capability refresh deferred',len(row_map(f.page('generalSettingsService')))==8)
    f.open_menu(1);service=f.open_page('generalSettingsService');service_rows=row_map(service)
    check('secret rows removed on entry',len(service_rows)==5 and not {'ram_only_mode','fwUpdateRetry','thumbwheel_mode'} & set(service_rows))
    check('unaffected service row identities preserved',all(rows['generalSettingsService'][k]==v for k,v in service_rows.items()))
    f.root.closeMenu();QTest.qWait(100);f.native_update('guiconfig','showSecretMenuItems',True)
    f.open_menu(1);service=f.open_page('generalSettingsService')
    check('secret rows return with unaffected identities',len(row_map(service))==8 and all(row_map(service)[k]==v for k,v in service_rows.items()))
    f.root.closeMenu();QTest.qWait(100)
    f.native_update('suc','lensVersion','');f.open_menu(1);about=f.open_page('generalSettingsAbout')
    check('empty lens version excludes text row','lensVersion' not in row_map(about))
    f.native_update('suc','lensVersion','fixture');QTest.qWait(200)
    check('visible lens version refresh restores row','lensVersion' in row_map(about))
    f.root.closeMenu();QTest.qWait(150)
    # 翻译数组在语言索引变化后刷新，仍保留原委托身份。
    class MarkerTranslator(QTranslator):
        def translate(self,context,source,disambiguation=None,n=-1):
            return 'TEST '+source if context=='MENUS' else ''
    translator=MarkerTranslator();app.installTranslator(translator)
    f.native_update('configstore','languageIndex',1)
    f.open_menu(0);page=f.open_page('cameraSettingsImage')
    check('language index refreshes included specification',json.loads(page.testRows())[1]['text1']=='TEST Mask Opacity')
    check('language refresh retains delegate identities',row_map(page)==rows['cameraSettingsImage'])
    app.removeTranslator(translator);f.native_update('configstore','languageIndex',0);QTest.qWait(200)
    check('visible language change refreshes back',json.loads(page.testRows())[1]['text1']=='Mask Opacity')
    f.root.closeMenu();QTest.qWait(100)
    # Slider 的实际键盘/鼠标路径及绑定恢复。
    for index,pname,key in [(0,'cameraSettingsImage','crop_mode_opacity'),(1,'generalSettingsDisplay','BACKLIGHT_brightness')]:
        f.native_update('configstore',key,50);f.open_menu(index);page=f.open_page(pname)
        slider=named(row(page,key),'settingsSlider')[0];li=named(page,'SettingsGeneric_list')[0]
        li.positionViewAtIndex(next(i for i,r in enumerate(json.loads(page.testRows())) if r['name']==key),0);QTest.qWait(100)
        f.config.fixtureWrites.clear();slider.forceActiveFocus();QTest.keyClick(f.view,Qt.Key_Left);QTest.qWait(50)
        check('slider keyboard once '+key,f.config.fixtureWrites==[key] and f.config.fixtureValues[key]==49)
        f.config.fixtureWrites.clear();f.native_update('configstore',key,70);QTest.qWait(50)
        check('slider backend update after key remains bound '+key,slider.property('value')==70 and not f.config.fixtureWrites)
        marker=next(v for v in walk(slider) if hasattr(v,'width') and v.width()==36 and v.height()==36)
        start=marker.mapToScene(QPointF(18,18)).toPoint();end=start+QPointF(-45,0).toPoint()
        QTest.mousePress(f.view,Qt.LeftButton,Qt.NoModifier,start);QTest.mouseMove(f.view,start+QPointF(-20,0).toPoint(),60)
        QTest.mouseMove(f.view,end,60);QTest.mouseRelease(f.view,Qt.LeftButton,Qt.NoModifier,end);QTest.qWait(100)
        check('slider mouse commit once '+key,f.config.fixtureWrites==[key] and f.config.fixtureValues[key]<70)
        f.config.fixtureWrites.clear();f.root.closeMenu();QTest.qWait(100)
        f.native_update('configstore',key,30);QTest.qWait(50);slider.commitUserValue(31)
        check('hidden slider refresh and input rejection '+key,slider.property('value')==30 and not f.config.fixtureWrites)
    # 双卡格式化的真实按钮/真实弹窗仅进入与取消；永远不按确认格式化。
    for present in ('both','card0','card1'):
        f.native_update('ContentModel','card0Status',0 if present=='card1' else 1)
        f.native_update('ContentModel','card1Status',0 if present=='card0' else 1)
        f.open_menu(1);f.open_page('generalSettingsLanguage');f.root.closePage();QTest.qWait(80)
        page=f.open_page('generalSettingsStorage')
        for card in ([0,1] if present=='both' else [0] if present=='card0' else [1]):
            select(f,page,'cardFormatCard'+str(card),True);dialog=transient(f,page,'CardFormat_root')
            check('format warning and exact card '+str((present,card)),dialog.property('actualCardToFormat')==card and dialog.property('subText')=='All content will be erased!')
            cancel(f,page)
        f.root.closeMenu();QTest.qWait(120)
    check('format native mock never invoked',not f.keep['ContentModel'].actions)
    # 取消 c1 后确认 c2，不得保存仍常驻的 c1/c3 委托。
    f.open_menu(1);page=f.open_page('generalSettingsProfiles')
    select(f,page,'saveCustomMode1',True);transient(f,page,'GenericConfirm_root');cancel(f,page)
    select(f,page,'saveCustomMode2',True);transient(f,page,'GenericConfirm_root');QTest.keyClick(f.view,Qt.Key_F4);QTest.qWait(150)
    check('confirm only current profile owner',f.config.actions==[('saveProfile','c2')])
    f.root.closeMenu();QTest.qWait(150)
    f.open_menu(1);page=f.open_page('generalSettingsService')
    select(f,page,'fwUpdateRetry',True);transient(f,page,'GenericConfirm_root');cancel(f,page)
    f.config.fixtureWrites.clear();f.keep['farm'].fixtureWrites.clear()
    select(f,page,'ram_only_mode');transient(f,page,'GenericConfirm_root');QTest.keyClick(f.view,Qt.Key_F4);QTest.qWait(150)
    check('cancelled firmware retry cannot hear later confirm',not f.keep['Upgrader'].actions)
    check('only RAM checkbox owns confirmation',f.keep['farm'].fixtureWrites==['ram_only_mode'] and not f.config.fixtureWrites)
    f.root.closeMenu();QTest.qWait(150)
    # 所有隐藏页的原生业务 Connections 断开。
    f.keep['Camera'].fixtureWrites.clear();f.keep['GlobalStateInfo'].fixtureWrites.clear()
    f.config.focusSizeChanged.emit();f.keep['farm'].resetGlobalImageSequenceCounterSucceeded.emit('');QTest.qWait(100)
    check('hidden native events do not write AF state',not f.keep['Camera'].fixtureWrites and not f.keep['GlobalStateInfo'].fixtureWrites)
    check('hidden native events do not display inform',all(not v.property('visible') for v in named(f.root,'informDialog')))
    check('all 23 pages survive interactions',len(f.pages())==23 and all(int(sip.unwrapinstance(p))==identities[p.property('itemValues')] for p in f.pages()))
    check('final QML warnings empty',not f.errors())
    report={'passed':True,'checks':checks,'count':len(checks),'qt':qVersion(),'targetValidated':False,'hardwareRequests':0,'formatCalls':0,'resources':{k:patch.digest(v) for k,v in patch.resources()[0].items()},'sources':{str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),Path(__file__).with_name('fixtures.py'),HERE/'patch.py',HERE/'qml/mainmenu/ResidentLoader.qml']},'specialToolsAreRouteStubs':True,'mainScreenUsesActualLoaderAndStatesFragment':True,'actions':{k:v.actions for k,v in f.keep.items() if v.actions}}
    save(HERE/'build/qml-validation.json',report);print(json.dumps({'passed':True,'count':len(checks),'hardwareRequests':0,'targetValidated':False},ensure_ascii=False));f.close()
if __name__=='__main__':main()
