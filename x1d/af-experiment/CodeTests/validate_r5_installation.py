"""运行固定R4装载和诊断测试后生成源文件绑定；完全离线。"""
import sys,json,hashlib,unittest,time,importlib
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import full_loader_r5 as L

def main():
    names=('test_r5_install_barrier','test_r5_task_wake','test_r5_install_plan',
           'test_full_loader_r5','test_r5_sgi_native','test_r5_diagnostics')
    suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromModule(importlib.import_module(n)) for n in names)
    started=time.monotonic();result=unittest.TextTestRunner(verbosity=2).run(suite)
    contract=L.FixedContract(L.FarmApplication())
    candidate=json.loads((L.BUILD/'peak-regression.json').read_text(encoding='utf-8'))
    assert candidate['passed'] and candidate['tests']==37 and candidate['hardwareRequests']==0
    assert candidate['artifactSha256']==L.ARTIFACT
    required=('full_loader_r5.py','r3_install_journal.py','CodeTests/test_full_loader_r5.py',
        'CodeTests/test_r5_task_wake.py','CodeTests/test_r5_install_barrier.py','CodeTests/r5_install_plan.py',
        'CodeTests/test_r5_sgi_native.py','CodeTests/test_r5_install_plan.py',
        'CodeTests/validate_r5_installation.py','CodeTests/check_r5_peak.py',
        'read_full_diagnostic_r5.py','read_r5_transition_timing.py','CodeTests/test_r5_diagnostics.py')
    record={'passed':result.wasSuccessful(),'artifactSha256':L.ARTIFACT,'contractSha256':contract.digest,
        'tests':result.testsRun,'seconds':time.monotonic()-started,'hardwareRequests':0,
        'candidateTests':candidate['tests'],
        'files':{n:hashlib.sha256((L.HERE/n).read_bytes()).hexdigest() for n in required},
        'releaseReady':False,'physicalAfVerified':False,'physical160TransitionMeasured':False}
    (L.BUILD/'loader-validation.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(record,ensure_ascii=False,indent=2))
    raise SystemExit(not result.wasSuccessful())

if __name__=='__main__':main()
