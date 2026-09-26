"""构建唯一 GUI 注册器；复用正式引闪桥与 UI、回放就绪检查。"""
from pathlib import Path
import hashlib
import io
import json
import os
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CACHE = ROOT/'.research-cache/x1d-1.25.0'
BASELINE = CACHE/'baseline'
FLASH = ROOT/'x1d/wireless-flash'
UI = ROOT/'x1d/candidates/ui-resident/revisions/full-pages-r2'
REPLAY = ROOT/'x1d/candidates/replay-page-resident'
OUT = HERE/'build/native'
REMOTE = '/run/hbl-four-module'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace(text, before, after):
    if text.count(before) != 1:
        raise ValueError('native integration anchor drift: '+before[:60])
    return text.replace(before, after, 1)


def generate():
    report = json.loads((HERE/'build/resources.json').read_text(encoding='utf-8'))
    if sha(HERE/'build/combined-ui.rcc') != report['rccSha256']:
        raise ValueError('RCC identity')
    OUT.mkdir(parents=True, exist_ok=True)
    src = (FLASH/'native/formal_runtime.cpp').read_text(encoding='utf-8')
    src = '#define HBL_FORMAL_RUNTIME_STATUS_PATH "/tmp/hbl-wireless-flash/formal-runtime.status"\n#define HBL_FORMAL_RUNTIME_RCC_PATH "'+REMOTE+'/combined-ui.rcc"\n'+src
    helper = '''
#include <QtCore/qcryptographichash.h>
#include <QtCore/qsavefile.h>
#include <QtQml/qqmlerror.h>
namespace {
const char *root="@ROOT@";
void status(const char *state) {
    QSaveFile f(QString::fromLatin1(root)+QStringLiteral("/ui.status"));
    if(f.open(QIODevice::WriteOnly)) {f.write(QByteArray(state)+" pid="+QByteArray::number(getpid())+"\\n");f.commit();}
}
void replayStatus(const char *state) {
    QSaveFile f(QString::fromLatin1(root)+QStringLiteral("/replay.status"));
    if(f.open(QIODevice::WriteOnly)) {f.write(QByteArray(state)+" pid="+QByteArray::number(getpid())+"\\n");f.commit();}
}
bool hash(const char *path,const char *expected) {
    QFile f(QString::fromLatin1(path));return f.open(QIODevice::ReadOnly) && QCryptographicHash::hash(f.readAll(),QCryptographicHash::Sha256).toHex()==expected;
}
struct Entry {const char *path;const char *sha;};
const Entry combinedEntries[]={@ENTRIES@};
bool combinedResources(){for(const Entry &entry:combinedEntries)if(!hash(entry.path,entry.sha))return false;return true;}
}
#include "readiness.h"
'''.replace('@ROOT@',REMOTE).replace('@ENTRIES@',',\n'.join('{"'+':'+name+'","'+value['sha256']+'"}' for name,value in report['resources'].items()))
    replay = (REPLAY/'session/native/runtime.cpp').read_text(encoding='utf-8')
    start = replay.index('bool pages(')
    end = replay.index('\n}\n}', start)+2
    helper += '\nnamespace {\n'+replay[start:end]+'\n}\n'
    src = replace(src,'extern "C" bool hbl_formal_register(int,const',helper+'\nextern "C" bool hbl_formal_register(int,const')
    src = replace(src,'if(requested() && version==1 && reinterpret_cast<quintptr>(tree)==0x1ec7f0 && !overlay)',
                  'if(requested() && version==1 && reinterpret_cast<quintptr>(tree)==0x1ec7f0 && !overlay &&\n'
                  '       hash("/proc/self/exe","'+report['guiSha256']+'") &&\n'
                  '       hash("'+REMOTE+'/combined-ui.rcc","'+report['rccSha256']+'"))')
    src = replace(src,'    if(requested() && overlay && !runtime) {',
                  '    static bool combinedLoaded=false;\n    BootGate *gate=nullptr;\n'
                  '    if(requested() && overlay && !combinedLoaded) {\n'
                  '        if(!combinedResources()){status("combined-resource-hash-failed");return;}\n'
                  '        gate=new BootGate(engine);combinedLoaded=true;\n    }\n'
                  '    if(requested() && overlay && !runtime) {')
    src = replace(src,'    original(engine,url);\n    if(requested()) {',
                  '''    original(engine,url);
    if(gate && runtime && !engine->rootObjects().isEmpty()) {
        for(const Entry &entry:combinedEntries) {
            if(!QString::fromLatin1(entry.path).endsWith(QStringLiteral(".qml")))continue;
            QQmlComponent component(engine,QUrl(QStringLiteral("qrc")+QString::fromLatin1(entry.path)));
            if(component.isError() || !component.isReady()){status("combined-component-failed");return;}
        }
        gate->start();
        replayStatus("replay-page-awaiting-pages");
        auto timer=new QTimer(engine);timer->setInterval(250);timer->setProperty("attempts",0);
        QObject::connect(timer,&QTimer::timeout,engine,[timer,engine](){
            if(pages(engine)){replayStatus("replay-page-ready-resources7-components7-pages2");timer->stop();timer->deleteLater();return;}
            int n=timer->property("attempts").toInt()+1;timer->setProperty("attempts",n);
            if(n>=40){replayStatus("replay-page-prewarm-failed");timer->stop();timer->deleteLater();}
        });
        timer->start();
    }
    if(requested()) {''')
    (OUT/'runtime.cpp').write_text(src,encoding='utf-8',newline='\n')
    for name in ('readiness.h','gate_policy.h'):
        text=(UI/'native'/name).read_text(encoding='utf-8').replace('/tmp/hbl-ui-full-r2',REMOTE)
        if name=='gate_policy.h':
            text=replace(text,'elapsed >= 30000','elapsed >= 90000')
            text=text.replace('// 与 r1 相同的就绪策略；r2 只增强对象收集和诊断。','// 四模块启动预算 90 秒；错误拒绝、完整结构和三次连续就绪条件不变。')
        (OUT/name).write_text(text,encoding='utf-8',newline='\n')
    (OUT/'catalog.h').write_bytes((UI/'session/native/catalog.h').read_bytes())
    return report


def build():
    if Path.cwd().resolve()!=ROOT:
        raise RuntimeError('workspace mismatch')
    resources=generate()
    compiler=CACHE/'toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    qt=CACHE/'qt-public';base=qt/'qtbase-opensource-src-5.5.1'
    env=dict(os.environ)
    for key,name in [('ZIG_GLOBAL_CACHE_DIR','global-cache'),('ZIG_LOCAL_CACHE_DIR','local-cache'),('TEMP','tmp'),('TMP','tmp')]:
        p=OUT/name;p.mkdir(exist_ok=True);env[key]=str(p)
    inc=OUT/'include/QtCore';inc.mkdir(parents=True,exist_ok=True)
    (inc/'qconfig.h').write_text('#define QT_SHARED\n#define QT_NO_DEBUG\n#define QT_POINTER_SIZE 4\n#define QT_OPENGL_ES_2\n',encoding='ascii')
    (inc/'qfeatures.h').write_text('/* Qt5.5 public ABI */\n',encoding='ascii')
    layout=OUT/'relocations.ld'
    layout.write_text('SECTIONS { .rel.dyn : { *(.rel.dyn) } .rel.plt : { *(.rel.plt) } } INSERT BEFORE .ARM.exidx;\n',encoding='ascii')
    target=['-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9']
    obj=OUT/'runtime.o';lib=OUT/'libhbl-four-module.so'
    flags=['-marm','-O2','-fPIC','-fno-stack-protector','-I',str(OUT/'include'),'-I',str(FLASH/'native'),
           '-isystem',str(base/'include'),'-isystem',str(base/'include/QtANGLE'),
           '-isystem',str(qt/'qtdeclarative-opensource-src-5.5.1/include'),'-I',str(base/'mkspecs/linux-arm-gnueabi-g++'),
           '-Wno-deprecated-declarations','-Wno-enum-constexpr-conversion','-Wall','-Wextra','-Werror']
    libs=[BASELINE/('usr/lib/libQt5'+name+'.so.5.5.1') for name in ('Quick','Qml','Gui','Core')]
    libs += [BASELINE/p for p in ('usr/lib/libstdc++.so.6.0.21','lib/libgcc_s.so.1','lib/libdl-2.22.so','lib/libc-2.22.so','lib/libpthread-2.22.so')]
    commands=[['c++','-std=c++11']+target+flags+['-c',str(OUT/'runtime.cpp'),'-o',str(obj)],
              ['cc']+target+['-shared','-Wl,--no-undefined','-Wl,-s','-Wl,-T,'+str(layout),'-Wl,-soname,'+lib.name,str(obj)]+list(map(str,libs))+['-o',str(lib)]]
    for command in commands:
        result=subprocess.run([str(compiler)]+command,env=env,capture_output=True,text=True,timeout=60)
        if result.returncode:raise RuntimeError(result.stderr)
    sys.path.insert(0,str(CACHE/'python'))
    from elftools.elf.elffile import ELFFile
    elf=ELFFile(io.BytesIO(lib.read_bytes()));rel=elf.get_section_by_name('.rel.dyn');plt=elf.get_section_by_name('.rel.plt')
    if elf.elfclass!=32 or elf['e_machine']!='EM_ARM' or not rel or not plt or rel['sh_addr']+rel['sh_size']!=plt['sh_addr']:
        raise ValueError('ARM/old-loader ABI')
    paths=[Path(__file__),HERE/'build/resources.json',FLASH/'native/formal_runtime.cpp',FLASH/'native/formal_bridge.h',
           FLASH/'native/rf_local_socket.h',FLASH/'native/formal_install_hold.h',REPLAY/'session/native/runtime.cpp',
           UI/'native/readiness.h',UI/'native/gate_policy.h',UI/'session/native/catalog.h']
    report={'compiled':True,'soleResourceRegistrar':True,'rccSha256':resources['rccSha256'],'librarySha256':sha(lib),
            'libraryBytes':lib.stat().st_size,'arm32':True,'relocationsContiguous':True,
            'sources':{p.relative_to(ROOT).as_posix():sha(p) for p in paths},'hardwareRequests':0,'targetValidated':False}
    (OUT/'build.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return {k:report[k] for k in ('compiled','libraryBytes','soleResourceRegistrar','hardwareRequests','targetValidated')}

if __name__=='__main__':
    print(json.dumps(build()))
