"""Run the bounded offline suite and write the gate consumed by temporary_install.py."""
import hashlib,json,sys,unittest
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;DELIVERY=HERE.parent
sys.path.insert(0,str(HERE))
NAMES=['test_advance_window','test_advance_boundary','test_identity','test_profiles','test_r6_candidate',
       'test_r6_flow','test_start','test_delivery','test_profile_contract','test_temporary_standby','test_lens_max_reference']
suite=unittest.defaultTestLoader.loadTestsFromNames(NAMES)
result=unittest.TextTestRunner(verbosity=1).run(suite)
manifest=DELIVERY/'build/release/00800000/capture-manifest.json'
sources=[DELIVERY/'range_contract.py',DELIVERY/'runtime.py',DELIVERY/'temporary_install.py',
         DELIVERY/'reviewed-profile-sources.json',HERE/'lens_reference_inspect.py',
         HERE/'output/lens-max-reference/parameters.json',*[HERE/(name+'.py') for name in NAMES]]
report={'schema':'af-r7-temporary-release-validation-v1','passed':result.wasSuccessful(),
        'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'hardwareRequests':0,
        'releaseManifestSha256':hashlib.sha256(manifest.read_bytes()).hexdigest(),
        'releasePayloadSha256':json.loads(manifest.read_text(encoding='utf-8'))['payload_sha256'],
        'sources':{str(p.relative_to(DELIVERY)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}
(HERE/'output/r7-temporary-release-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='sources'}))
raise SystemExit(not result.wasSuccessful())
