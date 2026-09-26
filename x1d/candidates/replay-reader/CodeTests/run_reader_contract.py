"""JPEG 读取端专有契约；执行候选 ARM 与原 codec，文件和 GL 为显式替身。"""
from pathlib import Path
import json
from run_stable_provider import StableMachine,image
from run_provider import jpeg,FALLBACK,TEXTURE_DELETE,sha
from arm_machine import HERE,X1D

def run():
    m=StableMachine();cases=[]
    for label,data in [('standard-jpeg-without-exif-or-unique-id',jpeg((640,480),(50,100,150))),
                       ('factory-sized-jpeg-with-exif',image())]:
        m.select_files(data);texture,size=m.request()
        assert texture not in (0,FALLBACK) and size==(640,480)
        m.call(TEXTURE_DELETE,[texture]);cases.append(label)
    data=image()
    for padding in (1,511):
        m.select_files(data+b'\0'*padding);texture,size=m.request();assert texture not in (0,FALLBACK)
        m.call(TEXTURE_DELETE,[texture])
    for tail in (b'\0'*512,b'\1'):
        m.select_files(data+tail);assert m.request()[0]==0
    cases.append('bounded-zero-padding-after-eoi-accepted-other-tail-rejected')
    m.select_files(data[:-2]);assert m.request()[0]==0
    m.select_files(data);texture,size=m.request();assert texture not in (0,FALLBACK)
    m.call(TEXTURE_DELETE,[texture]);cases.append('same-source-incomplete-then-complete-retry-needs-no-publisher')
    before=len(m.fallback_calls);m.select_files(b'not-jpeg');assert m.request()[0]==0
    assert len(m.fallback_calls)==before;cases.append('invalid-existing-jpeg-does-not-trigger-additional-raw-read')
    assert not m.writes and not m.failed_watchers
    assert all(p.lower().endswith('.jpg') for p,_,_ in m.reads)
    module=HERE/'artifacts/adapter/libx1d-replay-provider.so'
    binary=module.read_bytes()
    for forbidden in (b'QSaveFile',b'loadRecord',b'saveRecord',b'invalidateRecord',b'x1d-replay-pending',
                      b'tjInitCompress',b'tjCompress2',b'StorageProxy9writeFile',b'StorageProxy10freeBuffer',b'StorageProxy5image'):
        assert forbidden not in binary,forbidden
    cases.append('linked-provider-has-no-writer-publisher-or-encoder-entry')
    source=(HERE/'native/ready_refresh.cpp').read_text(encoding='utf-8')
    assert 'loadRecord' not in source and 'QFileSystemWatcher' not in source
    assert 'live.readRetries<4' in source and 'property("status").toInt()==3' in source
    assert 'item->isVisible()' in source and 'check(++ticks%10==0)' in source
    cases.append('bounded-error-refresh-source-audit-only')
    report={'passed':True,'cases':cases,'cameraAccess':False,'realArm':['provider','Qt QImage','TurboJPEG'],
      'replaced':['Storage File replies','GL and synchronization'],
      'refreshEventLoopExecuted':False,'writeCount':len(m.writes),'rawReadCount':0,
      'moduleSha256':sha(binary),'sourceHashes':{p.relative_to(X1D.parent).as_posix():sha(p.read_bytes()) for p in
      [Path(__file__),HERE/'CodeTests/run_stable_provider.py',HERE/'CodeTests/run_provider.py',HERE/'CodeTests/arm_machine.py',*sorted((HERE/'native').glob('*'))] if p.is_file()}}
    out=HERE/'artifacts/reader-tests';out.mkdir(parents=True,exist_ok=True)
    (out/'contract.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'cases':len(cases),'rawReads':0,'writes':0}))

if __name__=='__main__':run()
