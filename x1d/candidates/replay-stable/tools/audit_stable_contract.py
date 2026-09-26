"""固定 1.25.0 的目录缓存、File 失败与显示回退静态依据；不执行目标进程。"""
from pathlib import Path
import hashlib,json,sys,tarfile
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'x1d/tools'))
from binary import ArmElf,BASELINE,qml_files,CACHE

def sha(b):return hashlib.sha256(b).hexdigest()
def run():
    gui=ArmElf.load('usr/bin/victory-gui');storage=ArmElf.load('usr/bin/storage-daemon')
    assert sha(gui.data)=='d29c62402091c3ad40f6f247c03ce55f248ca79e92531889b1670edeb014ed9b'
    meta=gui.meta_object('_ZN12ContentModel16staticMetaObjectE')
    enums={e['name']:{v['name']:v['value'] for v in e['values']} for e in meta['enums']}
    assert enums['Roles']['DisplayRole']==0 and enums['Roles']['TypeRole']==259
    assert enums['FileType']['Image']==1 and enums['FileType']['ImageJpeg']==8
    checks={
      'fixed-model-data-vtable':gui.word(0x21856c+8+0x48)==0x3bb3c,
      'model-data-reads-cached-row-list':gui.word(0x3bb9c)==0xe5973008,
      'display-role-uses-cached-name':any(n=='_ZN8CStorage7tagNameEv' for _,_,n in gui.direct_calls(0x3c268,4)),
      'data-name-lookup-is-qmap':any('findNode' in n for _,_,n in gui.direct_calls(0x3c274,4)),
      'browse-loop-appends-all-reply-maps':any(n=='_ZN5QListI4QMapI7QString8QVariantEE6appendERKS3_' for _,_,n in gui.direct_calls(0x4010c,4)),
      'browse-request-count-is-10000':gui.word(0x3fcec)==0xe3023710,
      'model-does-not-override-canFetchMore':gui.name(gui.word(0x21856c+8+0x94))=='_ZNK18QAbstractItemModel12canFetchMoreERK11QModelIndex',
      'file-open-errors-rewritten-as-generic-failed':storage.word(0x38888)==0xe3a03002,
    }
    assert all(checks.values()),checks
    blocks={
      'ContentModel-data-head':gui.disassembly(0x3bb3c,0x90),
      'ContentModel-display-role':gui.disassembly(0x3c268,0x40),
      'ContentModel-type-role':gui.disassembly(0x3be88,0x64),
      'ContentModel-browse-count':gui.disassembly(0x3fcd4,0x28),
      'ContentModel-browse-append':gui.disassembly(0x400d0,0x88),
      'Storage-File-open-error':storage.disassembly(0x38860,0x44),
    }
    quick=CACHE/'qt-public/qtdeclarative-opensource-src-5.5.1.tar.xz'
    with tarfile.open(quick) as archive:
        quickSource=archive.extractfile('qtdeclarative-opensource-src-5.5.1/src/quick/items/qquickimage.cpp').read()
    text=quickSource.decode('utf-8');assert 'textureForFactory' in text
    at=text.index('textureForFactory');blocks['Qt55-null-texture-node']=text[at-250:at+550]
    qml=qml_files(gui);source=(HERE/'native/replay_catalog.cpp').read_text(encoding='utf-8')
    assert 'model->data(index,0)' in source and 'count>4096' in source and 'model->data(index,257)' not in source
    # 原模型请求至多 10000 项；本候选只接受 <=4096 的已结束列表，且不发补充 Browse/File。
    assert 'readFile(' not in source and 'Bus::' not in source and 'StorageProxy' not in source
    out=HERE/'artifacts/stable-tests';out.mkdir(parents=True,exist_ok=True)
    evidence='\n\n'.join('['+n+']\n'+v for n,v in blocks.items())+'\n'
    (out/'static-excerpts.txt').write_text(evidence,encoding='utf-8')
    report={'passed':True,'checks':checks,'cameraAccess':False,'firmware':'X1D-50c 1.25.0',
      'classification':'static control-flow and cached-model inference, not a live directory or atomic storage snapshot',
      'originalGuiSha256':sha(gui.data),'originalStorageSha256':sha(storage.data),
      'qtSourceArchiveSha256':sha(quick.read_bytes()),'qtImageSourceSha256':sha(quickSource),'excerptsSha256':sha(evidence.encode()),
      'sourceHashes':{p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in [Path(__file__),HERE/'native/replay_catalog.cpp',HERE/'native/replay_provider.cpp',HERE/'tools/build_session.py']}}
    (out/'static.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'staticChecks':len(checks)}))

if __name__=='__main__':run()
