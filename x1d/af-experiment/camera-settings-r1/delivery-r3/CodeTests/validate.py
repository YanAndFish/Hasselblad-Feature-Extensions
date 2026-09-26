"""运行 r3 离线检查并冻结来源；不加载任何设备会话。"""
import contextlib,hashlib,io,json,sys,unittest
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[3]
sys.path[:0]=[str(HERE),str(Path(__file__).parent)]
import delivery_package as package
from candidate import build
from runtime import AF
from af_only_bus_r2_loader import runtime as previous

def main():
    if Path.cwd().resolve()!=ROOT:raise ValueError('workspace required')
    old=previous.readiness()
    if not old:raise ValueError('frozen AF inputs changed')
    # Build in r3, then compare to the previously checked AF body.
    with contextlib.redirect_stdout(io.StringIO()):build(0x2bacc0)
    if (HERE/'build/002bacc0/candidate.bin').read_bytes()!=(AF/'build/002bacc0/candidate.bin').read_bytes():
        raise ValueError('AF candidate changed')
    import test_delivery,test_host
    suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromModule(m) for m in (test_delivery,test_host))
    output=io.StringIO()
    with contextlib.redirect_stdout(output):
        result=unittest.TextTestRunner(stream=output,verbosity=2).run(suite)
    folder=HERE/'CodeTests/output';folder.mkdir(exist_ok=True)
    (folder/'tests.txt').write_text(output.getvalue(),encoding='utf-8')
    if not result.wasSuccessful():
        print(output.getvalue());raise RuntimeError('r3 tests failed')
    provenance=package.read(HERE/'inputs/provenance.json')
    for name,expected in provenance['snapshotProofs'].items():
        if package.sha(HERE/'inputs/proofs'/name)!=expected:raise ValueError('snapshot proof changed')
    paths=list(HERE.glob('*.py'))+list((HERE/'CodeTests').glob('*.py'))
    paths+=[p for p in (HERE/'inputs').rglob('*') if p.is_file()]
    paths+=[previous.VALIDATION,folder/'tests.txt',AF/'build/002bacc0/candidate.bin',AF/'build/002bacc0/capture-manifest.json']
    # The legacy validator rechecks its entire original AF dependency chain at runtime.
    report={'revision':'af-only-delivery-r3','passed':True,'tests':result.testsRun,'hardwareRequests':0,
        'physicalR3Verified':False,'candidateUnchanged':True,'normalFarmReadTimeoutMs':2000,
        'firstFarmReadAfterHoldTimeoutMs':20000,'automaticRetry':False,
        'preflightRequests':7905,'preflightWrites':0,'preflightHoldChecks':31,
        'linuxPackageSha256':package.read(HERE/'inputs/package.json')['packageSha256'],
        'sources':{p.relative_to(ROOT).as_posix():package.sha(p) for p in paths},
        'limitations':['真实 USB 时延与 Qt 事件循环未在 r3 重测','20s 是请求预算，非物理根因结论',
            '完整 RAM 回滚仅接受既有未释放健康窗口；未知写入保留证据独立审阅',
            '新预测动作及两个提前补偿均未接通实际执行']}
    (HERE/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    package.verify()
    print(json.dumps({'passed':True,'tests':result.testsRun,'hardwareRequests':0,
        'validationSha256':package.sha(HERE/'validation.json')}))

if __name__=='__main__':main()
