"""构建目标 Qt5.5.1 纯业务差分测试；不连接硬件。"""
from pathlib import Path
import hashlib,json,os,re,subprocess,sys,tarfile

P=Path(__file__).resolve().parents[1]
ROOT=P.parents[2]
OUT=P/'build/flash-native-arm-regression'
BASE=ROOT/'.research-cache/x1d-1.25.0'

def headless(source):
    # No window is created. Remove the font probe only, equally from both test variants.
    assert source.count('Rectangle {')==1
    source=source.replace('    Text {id:menuFontReference;visible:false}\n','')
    source=source.replace('property string fontName: menuFontReference.font.family','property string fontName: ""')
    assert 'Text {' not in source
    return source

def main():
    assert Path.cwd().resolve()==ROOT
    OUT.mkdir(parents=True,exist_ok=True)
    inputs=P/'build/flash-native-regression'
    for variant in ['baseline','candidate']:
        (OUT/(variant+'.qml')).write_text(headless((inputs/(variant+'-business.qml')).read_text(encoding='utf-8')),encoding='utf-8')
    for name in ['events.json','interface.json']:(OUT/name).write_bytes((inputs/name).read_bytes())
    env=dict(os.environ)
    for name,sub in [('ZIG_GLOBAL_CACHE_DIR','global'),('ZIG_LOCAL_CACHE_DIR','local'),('TEMP','tmp'),('TMP','tmp')]:
        folder=OUT/sub;folder.mkdir(exist_ok=True);env[name]=str(folder)
    qt=BASE/'qt-public';base=qt/'qtbase-opensource-src-5.5.1'
    target=['-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9']
    flags=target+['-marm','-O2','-fPIC','-fno-stack-protector','-I',str(P/'build/include'),'-isystem',str(base/'include'),'-isystem',str(qt/'qtdeclarative-opensource-src-5.5.1/include'),'-I',str(base/'mkspecs/linux-arm-gnueabi-g++'),'-Wno-deprecated-declarations','-Wno-enum-constexpr-conversion']
    zig=BASE/'toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    libs=[BASE/('baseline/usr/lib/libQt5'+n+'.so.5.5.1') for n in ['Quick','Qml','Gui','Network','Core']]+[BASE/('baseline/'+n) for n in ['usr/lib/libstdc++.so.6.0.21','lib/libgcc_s.so.1','lib/libdl-2.22.so','lib/libc-2.22.so','lib/libpthread-2.22.so']]
    obj=OUT/'runner.o';binary=OUT/'runner'
    for command in [['c++','-std=c++11']+flags+['-c',str(Path(__file__).with_suffix('.cpp').with_name('flash_arm_regression.cpp')),'-o',str(obj)],['cc']+target+['-no-pie','-Wl,--no-undefined','-Wl,-s','-Wl,-T,'+str(P/'build/relocations.ld'),str(obj)]+[str(x) for x in libs]+['-o',str(binary)]]:
        r=subprocess.run([str(zig)]+command,env=env,capture_output=True,text=True,timeout=120)
        if r.returncode:raise RuntimeError(r.stderr)
    with tarfile.open(OUT/'test.tgz','w:gz',compresslevel=9) as tar:
        for name in ['runner','baseline.qml','candidate.qml','events.json','interface.json']:tar.add(OUT/name,arcname=name)
    names=['runner','baseline.qml','candidate.qml','events.json','interface.json','test.tgz']
    sources=[P/'flash_logic.h',P/'native_flash.py',Path(__file__).with_name('flash_arm_regression.cpp')]
    report={'built':True,'executed':False,'qt':'5.5.1','scope':'pure UI business; no camera interfaces or windows; font probe removed identically','files':{n:hashlib.sha256((OUT/n).read_bytes()).hexdigest() for n in names},'sources':{str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}
    (OUT/'build.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'built':True,'bytes':(OUT/'test.tgz').stat().st_size,'executed':False}))

if __name__=='__main__':main()
