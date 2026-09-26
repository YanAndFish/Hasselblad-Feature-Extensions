"""会话 ELF 的固定依赖/版本/旧链接器布局及原资源接入点审计。"""
from collections import defaultdict
from pathlib import Path
import hashlib
import json
import sys
HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[2]
sys.path.insert(0,str(HERE/'tools'))
from audit_load_preparation import symbols
from binary import ArmElf,BASELINE

def sha(b):return hashlib.sha256(b).hexdigest()
def run():
    session=json.loads((HERE/'artifacts/session/manifest.json').read_text(encoding='utf-8'))
    assert session['adapterManifestSha256']==sha((HERE/'artifacts/adapter/manifest.json').read_bytes())
    for path,wanted in session['sourceHashes'].items():assert sha((ROOT/path).read_bytes())==wanted,path
    frozen=ROOT/'x1d/candidates/replay-next/artifacts/load-preparation'
    inputs=json.loads((frozen/'inputs.json').read_text(encoding='utf-8'))
    data={}
    for p,item in inputs['files'].items():
        data[p]=(frozen/'inputs'/p).read_bytes();assert sha(data[p])==item['sha256']
    parsed={}
    def get(p):
        if p not in parsed:parsed[p]=symbols(data[p])
        return parsed[p]
    results={}
    native=json.loads((HERE/'artifacts/adapter/manifest.json').read_text(encoding='utf-8'))
    for name,item in {**session['products'],**native['outputs']}.items():
        folder='adapter' if name in native['outputs'] else 'session'
        b=(HERE/'artifacts'/folder/name).read_bytes();assert sha(b)==item['sha256']
        if not b.startswith(b'\x7fELF'):continue
        data[name]=b;e=ArmElf(b).elf
        assert e['e_flags']&0x400
        rel,plt=e.get_section_by_name('.rel.dyn'),e.get_section_by_name('.rel.plt')
        assert rel['sh_addr']+rel['sh_size']==plt['sh_addr']
        assert not any(t.entry.d_tag=='DT_TEXTREL' for t in e.get_section_by_name('.dynamic').iter_tags())
        queue=[name];closure=[]
        while queue:
            p=queue.pop(0)
            if p in closure:continue
            closure.append(p);info=get(p);assert not info['searchPaths']
            queue += [inputs['libraryPaths'][n] for n in info['needed']+info['interpreter']]
        exports=defaultdict(list)
        for p in closure:
            for s in get(p)['exports']:exports[s['name']].append(s)
        matched=0;weak=[]
        for p in closure:
            for requirement in get(p)['versionNeeds']:
                lib=inputs['libraryPaths'][requirement['library']]
                assert lib in closure and requirement['version'] in get(lib)['versionDefinitions']
            for imported in get(p)['imports']:
                found=any((s['version']==imported['version'] if imported['version'] else s['default']) for s in exports[imported['name']])
                if found:matched+=1
                elif imported['weak']:weak.append(imported['name'])
                else:raise AssertionError((name,p,imported))
        results[name]={'relocationsContiguous':True,'armHardFloat':True,'textRelocations':False,
                       'closure':closure,'matchedReferences':matched,'unresolvedStrong':0,'unresolvedWeak':sorted(set(weak))}
    gui=ArmElf.load('usr/bin/victory-gui')
    resource='_Z21qRegisterResourceDataiPKhS0_S0_';load='_ZN21QQmlApplicationEngine4loadERK4QUrl'
    calls=[]
    # 从实际映射的可执行 section 遍历，不把 ELF 文件大小当成虚拟地址长度。
    for section in gui.sections:
        if section['sh_flags']&4 and section['sh_type']=='SHT_PROGBITS':
            calls+=list(gui.direct_calls(section['sh_addr'],section['sh_size']))
    assert any(c[2]==resource for c in calls) and any(c[2]==load for c in calls)
    quick=ArmElf.load('usr/lib/libQt5Quick.so.5.5.1')
    entry=next(s['st_value'] for s in quick.symbols if s.name=='_ZN15QQuickImageBase4loadEv' and s['st_value'])
    assert entry==0x4be61224
    assert any(c[0]+4==entry+0x1a8 and 'QQuickPixmap4load' in c[2] for c in quick.direct_calls(entry,0x1ac))
    source=(HERE/'native/ready_refresh.cpp').read_text(encoding='utf-8')
    assert 'caller != loadEntry + 0x1a8' in source
    report={'passed':True,'kind':'static-session-load-contract','cameraAccess':False,'targetLoaderExecuted':False,
            'products':results,'guiResourceHookCalls':[hex(c[0]) for c in calls if c[2]==resource],
            'guiEngineLoadCalls':[hex(c[0]) for c in calls if c[2]==load],
            'qtQuickRefreshReturnOffset':'0x1a8','fixedStatAbi':'ARM glibc 2.22 __lxstat64/__fxstat64 version 3',
            'sessionManifestSha256':sha((HERE/'artifacts/session/manifest.json').read_bytes()),
            'adapterManifestSha256':sha((HERE/'artifacts/adapter/manifest.json').read_bytes()),
            'fixedInputsManifestSha256':sha((frozen/'inputs.json').read_bytes()),
            'sourceHashes':{p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in [Path(__file__),HERE/'tools/audit_load_preparation.py',HERE/'native/ready_refresh.cpp']}}
    out=HERE/'artifacts/session-tests';out.mkdir(parents=True,exist_ok=True)
    (out/'abi.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'sessionAbi':'passed','modules':list(results),'cameraAccess':False}))

if __name__=='__main__':run()
