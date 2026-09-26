"""宿主 C++ 生命周期和并发用例；不代表 Qt/ARM 线程调度或相机性能。"""
from pathlib import Path
import hashlib,json,os,subprocess
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
def sha(b):return hashlib.sha256(b).hexdigest()
def run():
    assert Path.cwd().resolve()==ROOT
    out=HERE/'artifacts/cache-tests';out.mkdir(parents=True,exist_ok=True)
    zig=ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    source=HERE/'CodeTests/latest_cache_test.cpp';exe=out/'latest-cache-test.exe'
    env=dict(os.environ,ZIG_GLOBAL_CACHE_DIR=str(out/'global'),ZIG_LOCAL_CACHE_DIR=str(out/'local'))
    subprocess.run([str(zig),'c++','-std=c++11','-O1','-UNDEBUG','-g','-Wall','-Wextra',str(source),'-o',str(exe)],env=env,check=True)
    subprocess.run([str(exe)],check=True,timeout=30)
    role=HERE/'CodeTests/role_cache_test.cpp';role_exe=out/'role-cache-test.exe'
    subprocess.run([str(zig),'c++','-std=c++11','-O1','-UNDEBUG','-g','-Wall','-Wextra',str(role),'-o',str(role_exe)],env=env,check=True)
    subprocess.run([str(role_exe)],check=True,timeout=30)
    budget=HERE/'CodeTests/byte_budget_test.cpp';budget_exe=out/'byte-budget-test.exe'
    subprocess.run([str(zig),'c++','-std=c++11','-O1','-UNDEBUG','-g','-Wall','-Wextra',str(budget),'-o',str(budget_exe)],env=env,check=True)
    subprocess.run([str(budget_exe)],check=True,timeout=30)
    report={'passed':True,'cameraAccess':False,'realTargetThreads':False,'productionHookImplemented':False,
      'cases':['latest-only-publication','in-use-old-generation-safe','two-slot-and-byte-cap',
               'last-reader-releases-old-allocation','delayed-old-publish-rejected',
               'borrowed-oversize-empty-duplicate-rejected','move-lease-single-release',
               '10000-host-replacements-with-concurrent-reader','latest-current-prev-next-role-sharing',
               'prefetch-completion-does-not-change-current','move-into-prefetched-frame-without-new-copy',
               'four-identity-cap-includes-retired-leases','late-prefetch-after-exit-rejected',
               'exit-releases-browse-keeps-latest','new-capture-does-not-switch-manual-selection',
               'global-and-category-byte-reservations','zero-copy-category-transfer-keeps-total',
               'failed-transfer-keeps-original-charge','full-pixels-exceed-default-budget'],
      'sourceHashes':{p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in [source,role,budget,Path(__file__),HERE/'native/latest_cache.h',HERE/'native/role_cache.h',HERE/'native/byte_budget.h']}}
    (out/'validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'cacheCases':len(report['cases']),'cameraAccess':False}))
if __name__=='__main__':run()
