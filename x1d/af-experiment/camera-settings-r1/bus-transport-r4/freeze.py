"""只冻结离线已核对的条件式 bus 包；不接触设备。"""
import hashlib,json,sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
assert Path.cwd().resolve()==ROOT
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for name in ('roundtrip-tests.json','shell-tests.json','entry-tests.json','gates-tests.json'):
    assert read(HERE/name)['passed']
build=read(HERE/'linux-build/client-build.json')
assert build['compiled'] and build['hardwareRequests']==0
for name,digest in build['sourceHashes'].items():assert sha(HERE/name)==digest
for name,item in build['outputs'].items():assert sha(HERE/'linux-build'/name)==item['sha256']
for name,digest in read(HERE/'roundtrip-tests.json')['files'].items():assert sha(HERE/name)==digest
for name,digest in read(HERE/'shell-tests.json')['files'].items():assert sha(HERE/name)==digest
paths=[p for p in HERE.iterdir() if p.is_file() and p.name!='validation.json']
paths += [p for p in (HERE/'CodeTests').iterdir() if p.is_file()]
paths += [HERE/'linux-build'/n for n in ('libhbl-af-bus.so','bus-local-check','client-build.json')]
paths += [HERE/'build/package'/n for n in ('af-bus-r4.tar.gz','package.json')]
paths += [ROOT/'x1d/tools'/n for n in ('read_usb_link_once.py','usb_diagnostic_contract.py','sutest_ram_contract.py')]
result={'passed':True,'revision':'bus-transport-r4','hardwareRequests':0,'physicalRoundtripVerified':False,
        'requiresInstalledDeliveryR5':True,'cameraResetOrAfRamWritesIncluded':False,
        'sources':{p.relative_to(ROOT).as_posix():sha(p) for p in sorted(set(paths))}}
(HERE/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'offlineFrozen':True,'validationSha256':sha(HERE/'validation.json'),'physicalRoundtripVerified':False}))
