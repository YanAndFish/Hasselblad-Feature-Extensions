"""执行 ARM 目录快照判断和 provider 回退；GUI 模型采集另有固定二进制静态证据。"""
import json
from pathlib import Path
from run_stable_provider import StableMachine,image
from run_provider import sha,FALLBACK,TEXTURE_DELETE
from arm_machine import HERE,X1D

REPLACE='_ZN3X1D14replaceCatalogERK7QStringRK11QStringListS5_b'
ABSENT='_ZN3X1D15knownJpegAbsentERK7QString'

def snapshot(m,raw,jpeg,complete=True,directory='/card0/folder'):
    allocated=[];strings=[]
    def listing(items):
        values=[m.qstring(p) for p in items];strings.extend(values)
        data=m.allocate(16+len(values)*4,True);obj=m.allocate(4);allocated.extend([data,obj]);m.put(obj,data)
        for off,value in [(0,1),(4,len(values)),(8,0),(12,len(values))]:m.put(data+off,value)
        for i,p in enumerate(values):m.put(data+16+4*i,m.word(p))
        return obj
    d=m.qstring(directory);a=listing(raw);b=listing(jpeg)
    m.call(REPLACE,[d,a,b,int(complete)])
    m.drop_string(d)
    for p in strings:m.drop_string(p)
    for p in allocated:m.free(p)

def run():
    m=StableMachine();cases=[];raw='/card0/folder/a.3FR';jpeg='/card0/folder/a.jpg'
    def absent(path=raw):
        p=m.qstring(path);result=m.call(ABSENT,[p]);m.drop_string(p);return bool(result)
    def done(name):cases.append(name);print(name,flush=True)
    snapshot(m,[raw],[]);assert absent() and not absent('/card1/folder/a.3FR')
    m.files={raw:b'not-read-by-our-provider'};m.file_failure=lambda *a:True
    before=len(m.fallback_calls);assert m.request()[0]==FALLBACK and len(m.fallback_calls)==before+1
    done('fresh-complete-same-folder-raw-only-snapshot-allows-single-original-fallback')
    m.file_failure=None;m.select_files(image());before=len(m.fallback_calls)
    texture,_=m.request();assert texture not in (0,FALLBACK) and len(m.fallback_calls)==before
    m.call(TEXTURE_DELETE,[texture]);done('present-jpeg-wins-even-over-earlier-absence-snapshot')
    for rawlist,jpglist,complete in [([raw],[],False),([raw],[jpeg],True),([raw],['/card1/folder/a.jpg'],True),([],[],True),([raw],['/card0/folder/../a.jpg'],True)]:
        snapshot(m,rawlist,jpglist,complete);assert not absent()
        m.file_failure=lambda *a:True;before=len(m.fallback_calls);assert m.request()[0]==0 and len(m.fallback_calls)==before
    m.file_failure=None;done('incomplete-other-card-malformed-present-and-no-raw-row-forbid-fallback')
    snapshot(m,[raw],[]);m.clock_seconds+=2;assert not absent()
    snapshot(m,[raw],[]);m.call('_ZN3X1D17invalidateCatalogEv',[]);assert not absent()
    done('expired-or-invalidated-snapshot-is-not-absence')
    snapshot(m,[raw],['/card0/folder/a.JPG']);m.files={'/card0/folder/a.JPG':image()}
    texture,_=m.request();assert texture not in (0,FALLBACK);m.call(TEXTURE_DELETE,[texture])
    snapshot(m,[raw],[jpeg,'/card0/folder/a.JPG']);reads=len(m.reads);assert m.request()[0]==0 and len(m.reads)==reads
    done('exact-cached-jpeg-extension-resolved-and-ambiguous-pair-rejected')
    m.call('_ZN3X1D17invalidateCatalogEv',[]);m.files={jpeg:b''};before=len(m.fallback_calls)
    assert m.request()[0]==0 and len(m.fallback_calls)==before;done('empty-existing-jpeg-is-not-missing')
    assert all(not p.lower().endswith('.3fr') for p,_,_ in m.reads)
    report={'passed':True,'cases':cases,'cameraAccess':False,'originalProviderExecuted':False,
      'guiModelObserverExecuted':False,'moduleHashes':m.module_hashes,'sourceHashes':{p.relative_to(X1D.parent).as_posix():sha(p.read_bytes()) for p in [Path(__file__),HERE/'CodeTests/run_stable_provider.py',HERE/'CodeTests/run_provider.py',HERE/'CodeTests/arm_machine.py',HERE/'native/replay_catalog.cpp',HERE/'native/replay_provider.cpp']}}
    out=HERE/'artifacts/stable-tests';out.mkdir(parents=True,exist_ok=True);(out/'catalog.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':run()
