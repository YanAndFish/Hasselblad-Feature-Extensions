"""构建独立离线测试界面的共享计算模块与脱敏输入；不含网络/相机接口。"""
import base64,hashlib,json,os,struct,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
assert Path.cwd().resolve()==ROOT.resolve()
BUILD=HERE/'build/native-af-r1';UI=HERE/'ui';CACHE=ROOT/'.research-cache/x1d-1.25.0'

def main():
    UI.mkdir(exist_ok=True);env=dict(os.environ)
    for k,v in {'TEMP':'tmp','TMP':'tmp','ZIG_GLOBAL_CACHE_DIR':'cache/global','ZIG_LOCAL_CACHE_DIR':'cache/local'}.items():
        p=BUILD/v;p.mkdir(parents=True,exist_ok=True);env[k]=str(p)
    source=ROOT/'x1d/wireless-flash/research/lens-speed-reference'
    reference=json.loads((source/'source.json').read_text(encoding='utf-8'))
    for name,key in [('artifact.hex','artifact_hex_sha256'),('LensSpecifics_XCD75P.hex','specifics_hex_sha256')]:
        assert hashlib.sha256((source/name).read_bytes()).hexdigest()==reference[key]
    memory={};upper=0
    for line in (source/'LensSpecifics_XCD75P.hex').read_text().splitlines():
        line=line.strip()
        if not line:continue
        row=bytes.fromhex(line[1:]);assert line[0]==':' and sum(row)%256==0 and len(row)==row[0]+5
        kind=row[3];address=int.from_bytes(row[1:3],'big')
        if kind==4:upper=int.from_bytes(row[4:6],'big')<<16
        elif kind==0:
            for i,b in enumerate(row[4:-1]):assert upper+address+i not in memory;memory[upper+address+i]=b
        elif kind in (1,5):pass
        else:raise ValueError('未核对的Intel HEX记录类型')
    keys=sorted(memory);assert len(keys)==keys[-1]-keys[0]+1
    decoded=bytes(memory[k] for k in keys)
    assert len(decoded)==reference['specifics_decoded_bytes']
    assert hashlib.sha256(decoded).hexdigest()==reference['specifics_decoded_sha256']
    coefficient=reference['first_channel_zero_additional_correction_coefficient']
    assert decoded.find(struct.pack('<f',coefficient))>=0
    catalog={'lens':'Hasselblad XCD 75P','kind':'实验协议档位，非定版或实测速率',
             'options':[{'value':0,'label':'跟随原厂'},{'value':1000,'label':'1 000'},{'value':2000,'label':'2 000'},{'value':3000,'label':'3 000'},
                        {'value':5000,'label':'5 000'},{'value':8000,'label':'8 000'},{'value':12000,'label':'12 000'}],
             'default':{'probe':0,'fast':0,'fine':0,'newDirection':False},
             'encoding':'原厂0xCD报文有符号16位命令；界面选择幅值，方向由AF确定；0表示保留原厂值',
             'selectionBasis':'3000/5000/8000/12000来自本项目已有实验命令值；1000/2000是为低速采样对照增加的编码候选。均不是实测最佳或安全速度',
             'referencePackage':reference['source_package'],'referenceUrl':reference['source_url'],
             'referencePackageSha256':reference['source_sha256'],
             'specificsName':'LensSpecifics_XCD75P.hex','specificsSha256':reference['specifics_hex_sha256'],
             'sharedFirmwareCaveat':'75P专用参数来自共享55V分发包；未把55V专用参数当作75P参数',
             'zeroAdditionalCorrectionExample':{'command':12000,'factor':4,'coefficient':coefficient,'roundedDriverInput':9969,'softwareLimit':16000},
             'currentLensFirmwareVerified':False,'physicalVelocityMeasured':False,
             'modelFactoryCommands':[5000,5000,3000],
             'modelFactoryCommandsCaveat':'仅离线演示基准，不是当前镜头原厂速度读回值'}
    sources=['native_af.c','native_config.c','native_ui_api.c']
    cmd=[str(CACHE/'toolchain/zig-windows-x86_64-0.13.0/zig.exe'),'cc','-target','wasm32-freestanding',
         '-Oz','-ffreestanding','-fno-builtin','-nostdlib','-Wl,--no-entry','-Wl,--export-memory',
         '-o',str(BUILD/'ui-core.wasm'),*[str(HERE/s) for s in sources]]
    subprocess.run(cmd,cwd=HERE,env=env,check=True,timeout=60)
    wasm=(BUILD/'ui-core.wasm').read_bytes();assert wasm[:4]==b'\0asm'
    inputs=json.loads((BUILD/'user-image-inputs.json').read_text(encoding='utf-8'))
    core={'catalog':catalog,'images':inputs,'wasmBase64':base64.b64encode(wasm).decode('ascii'),
          'wasmSha256':hashlib.sha256(wasm).hexdigest(),'hardwareRequests':0,
          'sourceSha256':{p:hashlib.sha256((HERE/p).read_bytes()).hexdigest() for p in sources+['native_af.h','native_config.h']}}
    (BUILD/'speed-catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (UI/'model-bundle.js').write_text('globalThis.AF_TEST_DATA = '+json.dumps(core,ensure_ascii=False,separators=(',',':'))+';\n',encoding='utf-8')
    (BUILD/'ui-manifest.json').write_text(json.dumps({k:v for k,v in core.items() if k not in ('images','wasmBase64','catalog')},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'wasmBytes':len(wasm),'wasmSha256':core['wasmSha256'],'specificsVerified':'XCD75P','hardwareRequests':0}))

if __name__=='__main__':main()
