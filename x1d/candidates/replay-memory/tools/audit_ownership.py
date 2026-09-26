"""固定 1.25.0 编码内存接点的只读静态审计；只向本候选写证据。"""
from pathlib import Path
import hashlib,json,sys
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'x1d/tools'))
from binary import ArmElf,BASELINE,CACHE,qml_files
def sha(b):return hashlib.sha256(b).hexdigest()
def run():
    assert Path.cwd().resolve()==ROOT
    x=ArmElf.load('usr/bin/jpeg-daemon')
    expected=json.loads((ROOT/'x1d/candidates/replay-reader/artifacts/diagnosis/factory-lifecycle.json').read_text(encoding='utf-8'))
    assert expected['firmwareSource']=='X1D-50c 1.25.0' and sha(x.data)==expected['sourceSha256']
    # 本证据记录完整输入摘要，地址解释仅限该离线文件。
    slices={'shared-input':(0x18790,96),'vpu-copy':(0x234cc,128),'vpu-wrap-copy':(0x23768,40),
            'output-local':(0x25670,28),'output-header-and-emit':(0x2584c,256),
            'header-writer':(0x2393c,256),'original-completion':(0x1e2b0,112)}
    code={n:x.disassembly(a,z) for n,(a,z) in slices.items()}
    assert x.name(next(t for a,t,n in x.direct_calls(0x23530,8)))=='_ZN10QByteArray6appendEPKci'
    assert [n for a,t,n in x.direct_calls(0x23768,40)].count('_ZN10QByteArray6appendEPKci')==2
    assert x.name(0x26d8c)=='_ZN16ImxEncoderWorker14encodeFinishedERK10QByteArray'
    gui=ArmElf.load('usr/bin/victory-gui');preview=qml_files(gui)['/liveview/Preview.qml']
    header=CACHE/'qt-public/qtbase-opensource-src-5.5.1/src/corelib/tools/qbytearray.h'
    h=header.read_text(encoding='utf-8');assert '{ return d->alloc ? d->alloc - 1 : 0; }' in h
    report={'firmwareSource':'X1D-50c 1.25.0','cameraAccess':False,'currentCameraFirmwareRead':False,
      'inputHashes':{'usr/bin/jpeg-daemon':sha(x.data),'usr/bin/victory-gui':sha(gui.data),
                    'Qt5.5.1/qbytearray.h':sha(header.read_bytes())},
      'staticInferences':['SharedBufferPool 输入 fromRawData 不能直接保留',
          'VPU 普通及环绕路径以 QByteArray::append 复制压缩位流；发送输出是 sp+0x98 的独立数组',
          '保留 QByteArray 共享引用可以延长压缩数据寿命；原生产任务和输入缓冲释放无需因此推迟',
          '原 Preview.qml 只有 ImageAdded 和路径，未提供跨进程拍摄身份 token'],
      'notProven':['所有错误路径输出均可解码','RAW-only 必定生成可缓存 JPEG',
                   '当前现场 JPEG 尺寸/固件/性能','新增 IPC、引用和解码的实际时延及内存峰值'],
      'disassembly':code,'originalPreviewQml':preview,
      'sourceHashes':{str(Path(__file__).relative_to(ROOT)).replace('\\','/'):sha(Path(__file__).read_bytes())}}
    out=HERE/'artifacts/ownership';out.mkdir(parents=True,exist_ok=True)
    (out/'static.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'staticOwnershipAudit':True,'cameraAccess':False}))
if __name__=='__main__':run()
