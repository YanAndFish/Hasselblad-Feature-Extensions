"""机械候选装入、缓存、恢复及逐写入故障模型，替身不访问相机。"""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parents[1]

def run(farm):
    assert Path.cwd().resolve()==HERE.parents[1]
    path=HERE/'CodeTests/test_mechanical_sync_loader.py'
    spec=importlib.util.spec_from_file_location('mechanical_loader_tests',path)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    assert hashlib.sha256(farm).hexdigest()==module.m.pre.FARM_SHA
    module.FARM=farm
    log=io.StringIO()
    result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(module))
    names=('research/mechanical_sync_loader.py','research/prepare_mechanical_loader.py','research/validate_mechanical_sync_loader.py',
           'research/farm_probe_loader.py','research/farm_probe_preflight.py','CodeTests/test_mechanical_sync_loader.py')
    report={'passed':result.wasSuccessful() and result.testsRun==7,'tests':result.testsRun,'log':log.getvalue(),
            'payload_sha256':module.m.PAYLOAD_SHA,'hardware_requests':0,
            'source_hashes':{name:hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in names}}
    (HERE/'build/mechanical-sync-capture/loader-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if not report['passed']: raise RuntimeError(report['log'])
    return {'passed':True,'tests':result.testsRun,'hardware_requests':0}

if __name__=='__main__': raise SystemExit('Pass fixed official FARM bytes; no device import.')
