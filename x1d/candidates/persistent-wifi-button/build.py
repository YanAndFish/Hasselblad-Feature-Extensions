"""只构建本探针；固定官方 GUI、Qt5.5 ABI 和原厂单资源。"""
from pathlib import Path
import hashlib, importlib.util, io, json, os, subprocess, sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
CACHE=ROOT/'.research-cache/x1d-1.25.0'
BASE=CACHE/'baseline'
OUT=HERE/'build'
GUI_SHA='d29c62402091c3ad40f6f247c03ce55f248ca79e92531889b1670edeb014ed9b'
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v): p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def build():
    assert Path.cwd().resolve()==ROOT
    assert digest(BASE/'usr/bin/victory-gui')==GUI_SHA
    OUT.mkdir(exist_ok=True)
    sys.path.insert(0,str(ROOT/'x1d/tools'))
    from binary import ArmElf, qml_files
    original=qml_files(ArmElf((BASE/'usr/bin/victory-gui').read_bytes()))['/settings/SettingsGeneric.qml']
    # qml_files 返回 UTF-8 文本，补丁只有预留按钮空间和一个空按钮。
    if isinstance(original,bytes): original=original.decode('utf-8')
    anchor='        id: listViewArea\n        anchors {\n            top: header.bottom\n            left: viewEndLine.right\n            right: root.right\n            bottom: root.bottom\n'
    assert original.count(anchor)==1
    modified=original.replace(anchor,anchor+'            bottomMargin: persistentProbeButton.visible ? 82 : 0\n',1)
    suffix='} // Rectangle (root)'
    assert modified.count(suffix)==1
    modified=modified.replace(suffix,(HERE/'button.qml.inc').read_text(encoding='utf-8')+'\n'+suffix)
    (OUT/'SettingsGeneric.original.qml').write_text(original,encoding='utf-8',newline='\n')
    qml=OUT/'SettingsGeneric.qml';qml.write_text(modified,encoding='utf-8',newline='\n')
    writer=module('probe_rcc_writer',ROOT/'x1d/candidates/replay-page-resident/session/resource_writer.py')
    rcc=OUT/'button.rcc';rcc.write_bytes(writer.rcc({'/settings/SettingsGeneric.qml':modified}))
    native=OUT/'native';native.mkdir(exist_ok=True)
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
    for key,name in [('ZIG_GLOBAL_CACHE_DIR','global-cache'),('ZIG_LOCAL_CACHE_DIR','local-cache'),('TEMP','tmp'),('TMP','tmp')]:
        p=native/name;p.mkdir(exist_ok=True);env[key]=str(p)
    inc=native/'include/QtCore';inc.mkdir(parents=True,exist_ok=True)
    (inc/'qconfig.h').write_text('#define QT_SHARED\n#define QT_NO_DEBUG\n#define QT_POINTER_SIZE 4\n#define QT_OPENGL_ES_2\n',encoding='ascii')
    (inc/'qfeatures.h').write_text('/* Qt 5.5.1 ABI */\n',encoding='ascii')
    (native/'hashes.h').write_text(f'#define GUI_SHA "{GUI_SHA}"\n#define RCC_SHA "{digest(rcc)}"\n#define QML_SHA "{digest(qml)}"\n',encoding='ascii')
    qt=CACHE/'qt-public';base=qt/'qtbase-opensource-src-5.5.1'
    zig=CACHE/'toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    target=['-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9']
    flags=target+['-marm','-O2','-fPIC','-fno-stack-protector','-I',str(native),'-I',str(native/'include'),'-isystem',str(base/'include'),'-isystem',str(qt/'qtdeclarative-opensource-src-5.5.1/include'),'-I',str(base/'mkspecs/linux-arm-gnueabi-g++'),'-Wno-deprecated-declarations','-Wno-enum-constexpr-conversion','-Wall','-Wextra','-Werror']
    layout=native/'relocations.ld';layout.write_text('SECTIONS { .rel.dyn : { *(.rel.dyn) } .rel.plt : { *(.rel.plt) } } INSERT BEFORE .ARM.exidx;\n',encoding='ascii')
    libs0=[BASE/p for p in ('usr/lib/libstdc++.so.6.0.21','lib/libgcc_s.so.1','lib/libdl-2.22.so','lib/libc-2.22.so','lib/libpthread-2.22.so')]
    health=ROOT/'x1d/candidates/ui-resident/session/native/health.cpp'
    # 沿用原独立 UI 安装器的健康条件：正常 Active 或稳定 Standby，三条链路均正常。
    # 不主动设置唤醒/保持；GUI 重启仍有原厂初始化的既有副作用。
    text=health.read_text(encoding='utf-8')
    health_check='if(!snapshot(b,s) || !ready(s) || (previous && previous!=s.pid)) return 65;'
    assert text.count(health_check)==1
    text=text.replace(health_check,'if(!snapshot(b,s) || !ready(s) || (previous && previous!=s.pid)) { std::fprintf(stderr,"health-failed sample=%u system=%d power=%d suc=%d farm=%d pwr=%d pid=%u previous=%u\\n",i,s.system,s.power,s.suc,s.farm,s.pwr,s.pid,previous); return 65; }')
    hp=native/'health.cpp';hp.write_text(text,encoding='utf-8')
    commands=[];outputs={};baseline=set(libs0)|{BASE/'usr/bin/victory-gui'}
    sys.path.insert(0,str(CACHE/'python'))
    from elftools.elf.elffile import ELFFile
    for name,src,ql,shared in [('libhbl-wifi-probe.so',HERE/'runtime.cpp',('Qml','Core'),True),('health',hp,('DBus','Core'),False)]:
        dest=OUT/name;obj=native/(name+'.o');libs=[BASE/('usr/lib/libQt5'+n+'.so.5.5.1') for n in ql]+libs0;baseline.update(libs)
        for args in [['c++','-std=c++11']+flags+['-c',str(src),'-o',str(obj)],['cc']+target+['-shared' if shared else '-no-pie','-Wl,--no-undefined','-Wl,-s','-Wl,-T,'+str(layout)]+(['-Wl,-soname,'+name] if shared else [])+[str(obj)]+list(map(str,libs))+['-o',str(dest)]]:
            r=subprocess.run([str(zig)]+args,env=env,capture_output=True,text=True,timeout=60);commands.append({'exit':r.returncode,'stderr':r.stderr})
            if r.returncode: raise RuntimeError(r.stderr)
        e=ELFFile(io.BytesIO(dest.read_bytes()));a=e.get_section_by_name('.rel.dyn');b=e.get_section_by_name('.rel.plt')
        assert e.elfclass==32 and e['e_machine']=='EM_ARM' and a['sh_addr']+a['sh_size']==b['sh_addr']
        outputs[name]={'sha256':digest(dest),'bytes':dest.stat().st_size,'arm32':True,'relocationsContiguous':True}
    (OUT/'baseline.sha256').write_text(''.join(digest(p)+'  /'+p.relative_to(BASE).as_posix()+'\n' for p in sorted(baseline)),encoding='ascii',newline='\n')
    save(OUT/'build.json',{'compiled':True,'targetValidated':False,'hardwareRequests':0,'guiSha256':GUI_SHA,'qmlSha256':digest(qml),'rccSha256':digest(rcc),'outputs':outputs,'commands':commands})
    print(json.dumps({'compiled':True,'outputs':outputs}))
if __name__=='__main__':build()
