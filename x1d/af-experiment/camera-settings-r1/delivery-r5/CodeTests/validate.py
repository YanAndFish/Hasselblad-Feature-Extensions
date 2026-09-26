"""r5 离线组合验证与冻结；不访问设备。"""
import contextlib,hashlib,io,json,sys,unittest
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[3]
sys.path[:0]=[str(HERE),str(Path(__file__).parent)]
import delivery_package as package
def main():
    assert Path.cwd().resolve()==ROOT
    package.frozen_inputs()
    assert (HERE/'build/002bacc0/candidate.bin').read_bytes()==(HERE.parent/'build/002bacc0/candidate.bin').read_bytes()
    import test_delivery,test_host,test_composition
    suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromModule(m) for m in (test_delivery,test_host,test_composition))
    out=HERE/'CodeTests/output';out.mkdir(exist_ok=True)
    text=io.StringIO()
    with contextlib.redirect_stdout(text):result=unittest.TextTestRunner(stream=text,verbosity=2).run(suite)
    (out/'tests.txt').write_text(text.getvalue(),encoding='utf-8')
    if not result.wasSuccessful():print(text.getvalue());raise RuntimeError('r5 model tests failed')
    linux=package.read(out/'linux.json');assert linux['passed']
    for n,digest in linux['sources'].items():assert package.sha(ROOT/n)==digest
    paths=list(HERE.glob('*.py'))+list((HERE/'CodeTests').glob('*.py'))
    paths+=[p for p in (HERE/'inputs').rglob('*') if p.is_file()]
    paths += [HERE/'local_check.cpp',HERE/'local-build/local-check-build.json',out/'tests.txt',out/'linux.json',
        HERE/'build/002bacc0/candidate.bin',HERE/'build/002bacc0/capture-manifest.json']
    if (HERE/'README.md').exists():paths.append(HERE/'README.md')
    report={'revision':'af-clean-install-r5','passed':True,'modelTests':result.testsRun,'linuxChecks':len(linux['checks']),
        'hardwareRequests':0,'physicalRoundtripVerified':False,'candidateUnchanged':True,
        'preflightRequests':7905,'preflightWrites':0,'preflightHoldChecks':31,'firstFarmReadAfterHoldTimeoutMs':20000,
        'normalFarmReadTimeoutMs':2000,'automaticRetry':False,'upstreamProofs':package.PROOFS,
        'linuxPackageSha256':package.read(HERE/'inputs/package.json')['packageSha256'],
        'sources':{p.relative_to(ROOT).as_posix():package.sha(p) for p in sorted(set(paths))}}
    (HERE/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    package.verify()
    print(json.dumps({'passed':True,'modelTests':result.testsRun,'linuxChecks':len(linux['checks']),'hardwareRequests':0,'validationSha256':package.sha(HERE/'validation.json')}))
if __name__=='__main__':main()
