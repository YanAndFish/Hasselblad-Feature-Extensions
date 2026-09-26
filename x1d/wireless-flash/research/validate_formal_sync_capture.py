"""用固定官方 FARM 指令验证正式双模式采集的两种链接地址。"""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]

def run(farm):
    assert Path.cwd().resolve()==ROOT
    path=HERE/'CodeTests/test_formal_sync_capture.py'
    spec=importlib.util.spec_from_file_location('formal_capture_tests',path)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    assert hashlib.sha256(farm).hexdigest()==module.FARM_SHA
    module.FARM=farm
    output=HERE/'build/formal-sync-capture'
    report={'hardware_requests':0,'installed':False,'physical_timing_measured':False,
            'farm_sha256':module.FARM_SHA,'passed':True}
    for variant in ('simulation','target'):
        module.ELF_PATH=output/(variant+'.elf')
        log=io.StringIO()
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(module))
        report[variant]={'tests':result.testsRun,'passed':result.wasSuccessful(),'log':log.getvalue(),
                         'elf_sha256':hashlib.sha256(module.ELF_PATH.read_bytes()).hexdigest()}
        report['passed'] &= result.wasSuccessful() and result.testsRun==12
        if not result.wasSuccessful(): print(log.getvalue())
    names=('CodeTests/test_formal_sync_capture.py','native/formal_sync_capture.c','native/formal_sync_hooks.S',
           'native/mechanical_sync_wire.h','native/farm_sync_wire.h',
           'research/build_formal_sync_capture.py','research/validate_formal_sync_capture.py')
    report['source_hashes']={name:hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in names}
    report['payload_sha256']=hashlib.sha256((output/'target.bin').read_bytes()).hexdigest()
    (output/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if not report['passed']: raise RuntimeError('formal capture validation failed')
    return {k:report[k] for k in ('passed','hardware_requests','payload_sha256')}

if __name__=='__main__':
    assert Path.cwd().resolve()==ROOT
    sys.path.insert(0,str(ROOT/'x1d/tools'))
    from farm_diagnostic_binary import FarmApplication
    print(json.dumps(run(FarmApplication().data)))
