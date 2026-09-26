"""按白名单打包已核对的独立离线界面；没有镜头/相机安装入口。"""
import hashlib,json,sys,zipfile
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
assert Path.cwd().resolve()==ROOT.resolve()
BUILD=HERE/'build/native-af-r1';UI=HERE/'ui'
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
arm=read(BUILD/'tests.json');ui=read(BUILD/'ui-tests.json');compiled=read(BUILD/'offline-manifest.json')
assert arm['passed'] and arm['failures']==arm['errors']==0 and ui['passed']==len(ui['checks'])
assert arm['payload_sha256']==compiled['payload_sha256']==ui['payloadSha256']==digest(BUILD/'offline.bin')
assert arm['test_sha256']==digest(HERE/'CodeTests/test_native_af.py')
for mapping in (compiled['source_sha256'],ui['sourceSha256']):
    for p,h in mapping.items():assert digest(HERE/p)==h,p
text=(UI/'model-bundle.js').read_text(encoding='utf-8');prefix='globalThis.AF_TEST_DATA = '
assert text.startswith(prefix) and text.endswith(';\n');data=json.loads(text[len(prefix):-2])
assert data['wasmSha256']==ui['wasmSha256']==digest(BUILD/'ui-core.wasm')
assert data['images']==read(HERE/'CodeTests/Fixtures/NativeUserImageModels.json')
for p,h in data['sourceSha256'].items():assert digest(HERE/p)==h,p
figures=read(BUILD/'image-report-manifest.json')
assert figures['generatorSha256']==digest(HERE/'CodeTests/render_native_image_report.py')
for p,h in figures['inputSha256'].items():assert digest(BUILD/p)==h,p
for p,h in figures['outputSha256'].items():assert digest(HERE/p)==h,p
files=('index.html','engine.js','controller.js','model-bundle.js','validation.html','使用说明.md',
       'evidence/contrast-curves.png','evidence/direction-outcomes.png')
manifest={'kind':'XCD75P独立离线AF测试界面','schemaVersion':1,'installable':False,'hardwareRequests':0,
          'armPayloadSha256':arm['payload_sha256'],'wasmSha256':ui['wasmSha256'],
          'verifiedArmChecks':arm['tests'],'verifiedUiCoreChecks':ui['passed'],
          'browserEntryVerified':'本机127.0.0.1静态服务；file URL打开方式未验证',
          'files':{p:digest(UI/p) for p in files}}
destination=BUILD/'XCD75P-AF-offline-test.zip'
with zipfile.ZipFile(destination,'w',compression=zipfile.ZIP_DEFLATED) as z:
    for p in files:z.write(UI/p,p)
    z.writestr('package-manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
with zipfile.ZipFile(destination) as z:
    assert z.testzip() is None
    for p,h in manifest['files'].items():assert hashlib.sha256(z.read(p)).hexdigest()==h
report={**manifest,'archive':destination.name,'archiveBytes':destination.stat().st_size,'archiveSha256':digest(destination),
        'packageBuilderSha256':digest(Path(__file__))}
(BUILD/'ui-package.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:report[k] for k in ('archive','archiveBytes','archiveSha256','installable')},ensure_ascii=False))
