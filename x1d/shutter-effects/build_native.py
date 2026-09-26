"""编译 X1D 1.25.0 的 GUI 扩展候选；只写本模块 build。"""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
CACHE=ROOT/'.research-cache/x1d-1.25.0'
BASE=CACHE/'baseline'
UI=ROOT/'x1d/wifi-region/temporary-ui'
PERSIST=ROOT/'x1d/combined-runtime/four-module-r1/persistent-r1/native'
OUT=HERE/'build/candidate'
ZIG=CACHE/'toolchain/zig-windows-x86_64-0.13.0/zig.exe'
sys.path.insert(0,str(UI))
import seal_resources

def run(*args,env):
    result=subprocess.run([str(ZIG),*map(str,args)],env=env,text=True,capture_output=True,timeout=180)
    if result.returncode:raise RuntimeError(result.stderr[-6000:])

def main():
    if not (OUT/'entry.cpp').is_file() or not (OUT/'flash-ui.rcc').is_file():
        raise ValueError('Run prepare.py first')
    report=json.loads((OUT/'result.json').read_text(encoding='utf-8'))
    original=json.loads((UI/'build/build.json').read_text(encoding='utf-8'))
    if original['resourceSealId']!=seal_resources.current_key_id():
        raise ValueError('Resource seal revision changed')
    if hashlib.sha256((UI/'build/flash-ui.rcc').read_bytes()).hexdigest()!=report['sourceRccSha256']:
        raise ValueError('Source GUI changed after preparation')
    seal_lib=UI/'build/resource-seal'/original['resourceSealId']/'arm/resource-seal.a'
    for f in [ZIG,seal_lib,UI/'build/component-guard.a',UI/'build/relocations.ld',UI/'build/entry-exports.map']:
        if not f.is_file():raise FileNotFoundError(f)
    env=dict(os.environ)
    env['ZIG_GLOBAL_CACHE_DIR']=str(CACHE/'zig-global-cache')
    env['ZIG_LOCAL_CACHE_DIR']=str(CACHE/'zig-local-cache')
    env['TEMP']=str(UI/'build/tmp');env['TMP']=env['TEMP']
    qt=CACHE/'qt-public';base=qt/'qtbase-opensource-src-5.5.1'
    target=['-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9']
    flags=target+['-I',str(base/'src/3rdparty/angle/include'),'-marm','-O2','-fPIC',
        '-fno-stack-protector','-DHBL_SEALED_UI=1','-I',str(HERE),'-I',str(UI),'-I',str(PERSIST),
        '-I',str(UI/'build/include'),'-isystem',str(base/'include'),
        '-isystem',str(qt/'qtdeclarative-opensource-src-5.5.1/include'),
        '-I',str(base/'mkspecs/linux-arm-gnueabi-g++'),'-Wno-deprecated-declarations',
        '-Wno-enum-constexpr-conversion']
    obj=OUT/'entry.o'
    run('c++','-std=c++11',*flags,'-c',OUT/'entry.cpp','-o',obj,env=env)
    stock_exports=(UI/'build/entry-exports.map').read_text(encoding='utf-8')
    extra='_ZN8QProcess5startERK7QString6QFlagsIN9QIODevice12OpenModeFlagEE'
    if stock_exports.count(' local: *;')!=1:raise ValueError('Native export map changed')
    export_map=OUT/'entry-exports.map'
    export_map.write_text(stock_exports.replace(' local: *;',f' {extra};\n local: *;'),encoding='utf-8')
    libs=[BASE/('usr/lib/libQt5'+n+'.so.5.5.1') for n in
        ['Quick','Qml','Gui','Network','Core']]+[BASE/n for n in
        ['usr/lib/libstdc++.so.6.0.21','lib/libgcc_s.so.1','lib/libdl-2.22.so',
         'lib/libc-2.22.so','lib/libpthread-2.22.so']]
    target_so=OUT/'hotspot-libhotspot-entry.so'
    run('cc',*target,'-shared','-Wl,--no-undefined','-Wl,-s',
        '-Wl,-T,'+str(UI/'build/relocations.ld'),
        '-Wl,--version-script='+str(export_map),obj,
        UI/'build/component-guard.a',BASE/'usr/lib/libQt5DBus.so.5.5.1',
        BASE/'usr/lib/libappscommon.so.1.0.0',seal_lib,*libs,'-o',target_so,env=env)
    plain=(OUT/'flash-ui.rcc').read_bytes()
    host_seal=seal_resources.host_library(original['resourceSealId'])
    sealed=seal_resources.seal(plain,host_seal)
    if seal_resources.unseal(sealed,host_seal)!=plain:
        raise ValueError('Resource round trip failed')
    (OUT/'af-ui.rcc').write_bytes(sealed)
    sys.path.insert(0,str(CACHE/'python'))
    from elftools.elf.elffile import ELFFile
    with target_so.open('rb') as handle:
        elf=ELFFile(handle)
        symbols=[s.name for s in elf.get_section_by_name('.dynsym').iter_symbols() if s.name and
                 s['st_shndx']!='SHN_UNDEF' and s['st_info']['bind'] in ('STB_GLOBAL','STB_WEAK') and
                 s['st_other']['visibility']=='STV_DEFAULT']
        if elf['e_machine']!='EM_ARM':raise ValueError('Expected ARM32 GUI extension')
    expected=['_ZN9QResource16registerResourceERK7QStringS2_',
        '_ZN8QProcess5startERK7QStringRK11QStringList6QFlagsIN9QIODevice12OpenModeFlagEE',
        '_ZN21QQmlApplicationEngine4loadERK4QUrl',extra]
    if sorted(symbols)!=sorted(expected):raise ValueError('Unexpected exported symbols: '+repr(symbols))
    report.update({'nativeCompiled':True,'target':'arm-linux-gnueabihf.2.22',
        'resourceSealed':True,'resourceSealId':original['resourceSealId'],
        'nativeSha256':hashlib.sha256(target_so.read_bytes()).hexdigest(),
        'sealedRccSha256':hashlib.sha256(sealed).hexdigest(),
        'exports':symbols})
    (OUT/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('X1D ARM32 native extension and sealed RCC built; hardware requests: 0')

if __name__=='__main__':main()
