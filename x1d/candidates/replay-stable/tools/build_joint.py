"""把组合守护库绑定到协调方最终 main.qml；只编译/审计，不注册资源或访问设备。"""
from __future__ import annotations
import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'x1d/tools'))
from binary import ArmElf,BASELINE,CACHE
from audit_load_preparation import symbols
from compose_joint_resources import MARKER

def sha(data):return hashlib.sha256(data).hexdigest()
def build(main_path,expected):
    source_paths=[Path(__file__),HERE/'joint/joint_runtime.cpp',HERE/'joint/joint_policy.h',HERE/'joint/joint_check.cpp',HERE/'tools/compose_joint_resources.py',HERE/'tools/audit_load_preparation.py']
    source_paths.extend(ROOT/p for p in ('x1d/combined-runtime/native/install_window.h','x1d/wireless-flash/native/formal_install_hold.h','x1d/wireless-flash/native/rf_local_socket.h','x1d/wireless-flash/native/rf_bridge.h'))
    before_sources={p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in source_paths}
    main_path=Path(main_path).resolve();main_path.relative_to(ROOT.resolve())
    main=main_path.read_bytes()
    assert sha(main)==expected,'输入主资源已改变'
    assert main.count(MARKER.encode())==1 and b'x1dReplaySession' in main
    out=HERE/'artifacts/joint'/expected[:12];out.mkdir(parents=True,exist_ok=True)
    core=json.loads((HERE/'artifacts/adapter/manifest.json').read_text(encoding='utf-8'))
    for path,wanted in core['inputHashes'].items():assert sha((ROOT/path).read_bytes())==wanted,path
    include=HERE/'artifacts/build'
    (out/'bindings.h').write_bytes((include/'bindings.h').read_bytes()+('\n#define X1D_JOINT_MAIN_SHA256 "'+expected+'"\n').encode())
    exports=['_ZN21QQmlApplicationEngine4loadERK4QUrl','x1d_replay_session_admit']
    (out/'exports.map').write_text('{ global: '+'; '.join(exports)+'; local: *; };\n',encoding='ascii')
    layout=out/'relocations.ld'
    layout.write_text('SECTIONS { .rel.dyn : { *(.rel.dyn) } .rel.plt : { *(.rel.plt) } } INSERT BEFORE .ARM.exidx;\n',encoding='ascii')
    compiler=CACHE/'toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    qt=CACHE/'qt-public';base=qt/'qtbase-opensource-src-5.5.1';declarative=qt/'qtdeclarative-opensource-src-5.5.1'
    env=dict(os.environ,ZIG_GLOBAL_CACHE_DIR=str(out/'zig-global-cache'),ZIG_LOCAL_CACHE_DIR=str(out/'zig-local-cache'))
    flags=['-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9','-marm','-O2','-std=c++11','-fPIC','-fno-stack-protector',
           '-I',str(include/'include'),'-isystem',str(base/'include'),'-isystem',str(declarative/'include'),
           '-I',str(base/'mkspecs/linux-arm-gnueabi-g++'),'-isystem',str(base/'src/3rdparty/angle/include'),'-include',str(out/'bindings.h'),
           '-Wno-deprecated-declarations','-Wno-enum-constexpr-conversion','-Wall','-Wextra']
    obj=out/'joint.o';module=out/'libx1d-replay-joint.so'
    subprocess.run([str(compiler),'c++',*flags,'-c',str(HERE/'joint/joint_runtime.cpp'),'-o',str(obj)],cwd=ROOT,env=env,check=True)
    libraries=[BASELINE/'usr/lib'/('libQt5'+m+'.so.5.5.1') for m in ('Quick','Qml','Gui','Network','Core')]+[
        HERE/'artifacts/load-preparation/inputs/usr/lib/libGLESv2.so.2.0.0',BASELINE/'usr/lib/libstdc++.so.6.0.21',
        BASELINE/'lib/libgcc_s.so.1',BASELINE/'lib/libdl-2.22.so',BASELINE/'lib/librt-2.22.so',BASELINE/'lib/libc-2.22.so']
    subprocess.run([str(compiler),'cc','-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9','-shared','-nostdlib',
                    '-Wl,-soname,'+module.name,'-Wl,--no-undefined','-Wl,-T,'+str(layout),
                    '-Wl,--version-script,'+str(out/'exports.map'),str(obj),*[str(p) for p in libraries],'-o',str(module)],cwd=ROOT,env=env,check=True)
    check=out/'replay-joint-check';check_obj=out/'check.o'
    subprocess.run([str(compiler),'c++',*flags,'-c',str(HERE/'joint/joint_check.cpp'),'-o',str(check_obj)],cwd=ROOT,env=env,check=True)
    checklibs=[BASELINE/'usr/lib/libstdc++.so.6.0.21',BASELINE/'lib/libgcc_s.so.1',BASELINE/'lib/libc-2.22.so',BASELINE/'lib/librt-2.22.so']
    subprocess.run([str(compiler),'cc','-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9','-Wl,--no-undefined',
                    '-Wl,-T,'+str(layout),str(check_obj),*[str(p) for p in checklibs],'-o',str(check)],cwd=ROOT,env=env,check=True)
    data=module.read_bytes();elf=ArmElf(data).elf
    dyn=elf.get_section_by_name('.dynsym')
    actual=sorted(s.name for s in dyn.iter_symbols() if s.name and s['st_shndx']!='SHN_UNDEF')
    assert actual==sorted(exports),actual
    assert not any('qRegisterResourceData' in s.name or 'QResource' in s.name for s in dyn.iter_symbols())
    assert b'/tmp/hbl-wireless-flash' not in data
    assert not {'sendto','recvfrom','socket','bind','connect'}.intersection(s.name for s in dyn.iter_symbols())
    rel,plt=elf.get_section_by_name('.rel.dyn'),elf.get_section_by_name('.rel.plt')
    assert rel['sh_addr']+rel['sh_size']==plt['sh_addr']
    assert elf['e_flags']&0x400
    inputs=json.loads((HERE/'artifacts/load-preparation/inputs.json').read_text(encoding='utf-8'))
    checked_elf=ArmElf(check.read_bytes()).elf
    rel2,plt2=checked_elf.get_section_by_name('.rel.dyn'),checked_elf.get_section_by_name('.rel.plt')
    assert rel2['sh_addr']+rel2['sh_size']==plt2['sh_addr']
    parsed={'candidate':symbols(data),'gpu-check':symbols(check.read_bytes())};queue=['candidate','gpu-check'];closure=[]
    while queue:
        name=queue.pop(0)
        if name in closure:continue
        closure.append(name)
        if name not in parsed:
            b=(HERE/'artifacts/load-preparation/inputs'/name).read_bytes()
            assert sha(b)==inputs['files'][name]['sha256'];parsed[name]=symbols(b)
        assert not parsed[name]['searchPaths']
        queue.extend(inputs['libraryPaths'][n] for n in parsed[name]['needed']+parsed[name]['interpreter'])
    available=defaultdict(list)
    for info in parsed.values():
        for s in info['exports']:available[s['name']].append(s)
    matched=0;weak=[]
    for name,info in parsed.items():
        for requirement in info['versionNeeds']:
            assert requirement['version'] in parsed[inputs['libraryPaths'][requirement['library']]]['versionDefinitions']
        for imported in info['imports']:
            found=any(s['version']==imported['version'] if imported['version'] else s['default'] for s in available[imported['name']])
            if found:matched+=1
            elif imported['weak']:weak.append(imported['name'])
            else:raise AssertionError((name,imported))
    assert main_path.read_bytes()==main,'构建期间输入资源改变'
    assert before_sources=={p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in source_paths},'构建期间共享源码改变'
    report={'jointModuleBuilt':True,'cameraAccess':False,'targetValidated':False,'standaloneInstallable':False,
            'mainQmlPath':main_path.relative_to(ROOT).as_posix(),'mainQmlSha256':expected,
            'module':module.relative_to(ROOT).as_posix(),'moduleSha256':sha(data),'bytes':len(data),
            'exports':exports,'registersResource':False,'relocationsContiguous':True,'matchedReferences':matched,
            'unresolvedStrong':0,'unresolvedWeak':sorted(set(weak)),'closure':closure,
            'sessionState':'/tmp/hbl-x1d-combined/replay-state','coordinatorStateReadOnly':'/tmp/hbl-x1d-combined/install-state',
            'gpuChecker':check.relative_to(ROOT).as_posix(),'gpuCheckerSha256':sha(check.read_bytes()),
            'requires':'unique coordinator RCC and new one-shot state; no old standalone session library',
            'inputHashes':core['inputHashes'],
            'sourceHashes':before_sources}
    (out/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'jointModule':report['module'],'mainSha256':expected,'moduleSha256':report['moduleSha256'],'cameraAccess':False}))
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main-qml',required=True,type=Path)
    parser.add_argument('--main-sha256',required=True)
    args=parser.parse_args();build(args.main_qml,args.main_sha256)
