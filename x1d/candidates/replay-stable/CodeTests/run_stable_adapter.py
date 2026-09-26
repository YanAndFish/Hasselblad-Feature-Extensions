"""新写入适配层 ARM 路径：原成片逐字节保留，无额外 codec/File 调用。"""
import json
from pathlib import Path
from run_adapter import AdapterMachine
from run_provider import metadata,marker,jpeg,sha
from arm_machine import HERE,X1D,UC_HOOK_CODE

class StableAdapter(AdapterMachine):
    def __init__(self):
        self.records=[];self.codec_calls=[]
        super().__init__(b'RAW-MUST-NOT-BE-READ')
        self.bind('_ZN16QCoreApplication14applicationPidEv',lambda:self.ret(123))
        self.bind('_ZN9QDateTime22currentMSecsSinceEpochEv',lambda:self.ret(987654321))
        self.drop_string(self.raw);self.raw=self.qstring('/artificial/a.3FR')
        self.bind('_ZN3X1D10saveRecordERK7QStringRK11QJsonObject',self.save_record)
        for symbol in ('tjDecompress2','tjCompress2'):
            at=self.symbols[symbol]
            self.uc.hook_add(UC_HOOK_CODE,lambda uc,at,size,ctx:self.codec_calls.append(at),begin=at,end=at)
    def save_record(self):
        self.records.append(self.string(self.arg(0)));self.ret(1)

def run():
    m=StableAdapter();cases=[]
    def done(name):cases.append(name);print(name,flush=True)
    m.submit(b'unrelated',caller=0x12340);assert m.writes[-1][1]==b'unrelated'
    m.associate(1);m.submit(b'other-resolution');assert m.writes[-1][1]==b'other-resolution'
    done('unrelated-callsite-and-resolution-forward-once')
    m.associate();assert m.records==['/artificial/a.3FR','/artificial/a.jpg']
    count=len(m.writes);watcher=m.submit(b'invalid-jpeg');assert len(m.writes)==count and watcher in m.failed_watchers
    done('pending-marked-before-conversion-and-invalid-container-rejected')
    main=jpeg((8176,6128),(65,110,160));source=main[:2]+marker(0xe1,b'Exif\0\0'+metadata(1,b'112233445566778899aabbccddeeff00'))+main[2:]
    m.associate();m.submit(source);assert len(m.writes)==count+1 and m.writes[-1][1]==source
    assert not m.reads and not m.codec_calls
    done('full-jpeg-bitstream-preserved-zero-extra-decode-encode-or-raw-reads')
    assert not [n for n,_ in m.live.values() if n>=len(source)]
    report={'passed':True,'cases':cases,'cameraAccess':False,'rawReadCount':0,'extraCodecCalls':0,
      'recordPublicationAfterCloseExecuted':False,'moduleHashes':m.module_hashes,
      'notValidated':['actual Storage write/close','success watcher publication and QSaveFile','camera latency'],
      'sourceHashes':{p.relative_to(X1D.parent).as_posix():sha(p.read_bytes()) for p in [Path(__file__),HERE/'CodeTests/run_adapter.py',HERE/'CodeTests/run_provider.py',HERE/'CodeTests/arm_machine.py',HERE/'native/jpeg_adapter.cpp']}}
    out=HERE/'artifacts/stable-tests';out.mkdir(parents=True,exist_ok=True);(out/'adapter.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':run()
