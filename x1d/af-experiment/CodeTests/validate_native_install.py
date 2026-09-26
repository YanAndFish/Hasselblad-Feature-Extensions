"""运行并核对当前 AF 装载离线检查；此入口不创建 USB 客户端。"""
import concurrent.futures,hashlib,json,subprocess,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
from native_loader import NativeContract,REQUIRED_FILES,BUILD,ROOT,BASELINE_SHA

CASES=(
    ('test_native_memory.py',(), 'build/native-memory-study/tests.json',5,None),
    ('test_native_reserve.py',(), 'build/native-memory-study/reserve-tests.json',6,'reserve'),
    ('test_native_bootstrap.py',(), 'build/native-bootstrap-r1/tests.json',5,'bootstrap'),
    ('test_native_task_wake.py',(), 'build/native-bootstrap-r1/task-wake-tests.json',5,'bootstrap'),
    ('test_native_af.py',('--capture',), 'build/native-capture-r1/00800000/tests.json',35,'capture'),
    ('test_native_capture.py',(), 'build/native-capture-r1/00800000/capture-tests.json',10,'capture'),
    ('test_native_capture_concurrency.py',(), 'build/native-capture-r1/00800000/concurrency-tests.json',5,'capture'),
    ('test_native_loader.py',(), 'build/native-capture-r1/loader-tests.json',11,'relocated'),
    ('test_native_sgi.py',(), 'build/native-capture-r1/sgi-tests.json',5,'relocated'),
    ('test_native_capture_reader.py',(), 'build/native-capture-r1/reader-tests.json',11,'relocated'),
    ('test_native_detach.py',(), 'build/native-capture-r1/detach-tests.json',6,'relocated'),
    ('test_native_hold.py',(), 'build/native-capture-r1/hold-tests.json',15,'relocated'),
)

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def snapshot(names):return {name:sha(HERE/name) for name in sorted(names)}
def run(case):
    name,args,report,count,payload=case
    completed=subprocess.run([sys.executable,'-X','utf8','-B',str(HERE/'CodeTests'/name),*args],
        cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=120)
    if completed.returncode:raise RuntimeError(name+' failed\n'+completed.stdout[-2000:]+completed.stderr[-4000:])
    return case,json.loads((HERE/report).read_text(encoding='utf-8'))

def main():
    start=time.perf_counter();c=NativeContract()
    relocated=json.loads((BUILD/'002bacc0/capture-manifest.json').read_text(encoding='utf-8'))
    reserve=json.loads((HERE/'build/native-memory-study/reserve-manifest.json').read_text(encoding='utf-8'))
    manifests={'capture':c.offline,'bootstrap':c.bootstrap,'relocated':relocated,'reserve':reserve}
    artifacts={
        'capture':('build/native-capture-r1/00800000/capture-manifest.json','build/native-capture-r1/00800000/candidate.bin'),
        'relocated':('build/native-capture-r1/002bacc0/capture-manifest.json','build/native-capture-r1/002bacc0/candidate.bin'),
        'bootstrap':('build/native-bootstrap-r1/bootstrap-manifest.json','build/native-bootstrap-r1/bootstrap.bin'),
        'reserve':('build/native-memory-study/reserve-manifest.json','build/native-memory-study/reserve.bin'),
    }
    names=set(REQUIRED_FILES)|set(c.hold['sourceHashes']);payload_hashes={}
    for key,m in manifests.items():
        sources=m.get('sourceSha256',m.get('source_sha256',{}));names.update(sources)
        if snapshot(sources)!=sources:raise ValueError('source identity '+key)
        payload_hashes[key]=m.get('payloadSha256',m.get('payload_sha256'))
        if sha(HERE/artifacts[key][1])!=payload_hashes[key]:raise ValueError('payload identity '+key)
    names.update(name for pair in artifacts.values() for name in pair)
    before=snapshot(names)
    # 保存未完成状态，旧 PASS 不能在本次验证中途继续授权装载。
    output=BUILD/'loader-validation.json'
    pending={'passed':False,'observationInstallReady':False,'enhancedAfReady':False,'hardwareRequests':0}
    output.write_text(json.dumps(pending,indent=2)+'\n',encoding='utf-8')
    subprocess.run([sys.executable,'-X','utf8','-B',str(HERE/'CodeTests/inspect_native_task_ownership.py')],
        cwd=ROOT,capture_output=True,check=True,timeout=30)
    ownership_path='build/native-task-study/evidence.json'
    ownership=json.loads((HERE/ownership_path).read_text(encoding='utf-8'))
    if ownership['sourceSha256']!=before['CodeTests/inspect_native_task_ownership.py'] or ownership['baselineSha256']!=BASELINE_SHA:
        raise ValueError('task ownership evidence identity')
    for region in ownership['regions']:
        a,b=region['start'],region['endExclusive']
        if hashlib.sha256(c.farm.read(a,b-a)).hexdigest()!=region['sha256'] or any(c.expected.get(p)!=c.farm.word(p) for p in range(a,b,4)):
            raise ValueError('task ownership region not bound in preflight')
    reports={};total=0
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for case,r in pool.map(run,CASES):
            name,args,path,count,payload=case
            if r.get('passed') is not True or r.get('tests')!=count or r.get('failures') or r.get('errors') or r.get('hardwareRequests')!=0:
                raise ValueError('test result '+name)
            if r.get('testSha256',r.get('test_sha256'))!=before['CodeTests/'+name]:raise ValueError('test source '+name)
            if name in ('test_native_loader.py','test_native_detach.py','test_native_hold.py'):
                if r.get('contractSha256')!=c.identity:raise ValueError('loader contract')
            elif r.get('baselineSha256',r.get('baseline_sha256'))!=BASELINE_SHA:raise ValueError('factory baseline '+name)
            if payload and r.get('payloadSha256',r.get('payload_sha256',r.get('relocatedPayloadSha256')))!=payload_hashes[payload]:
                raise ValueError('tested payload '+name)
            reports[path]={'sha256':sha(HERE/path),'tests':count,'scope':r['scope']};total+=count
    if before!=snapshot(names):raise ValueError('sources/artifacts changed during validation')
    result={'passed':True,'observationInstallReady':bool(c.hold.get('targetExecutableSha256')),'enhancedAfReady':False,'hardwareRequests':0,
        'contractSha256':c.identity,'baselineSha256':BASELINE_SHA,'payloadSha256':payload_hashes,
        'files':before,'reports':reports,'tests':total,'seconds':time.perf_counter()-start,
        'taskOwnershipEvidence':{'path':ownership_path,'sha256':sha(HERE/ownership_path)},
        'observerDetachOfflineVerified':True,'captureAbi':2,
        'holdContract':c.hold,'targetHeldWorkflowMeasuredByThisTask':False,
        'nativeFinePreserved':True,'predictionActuation':False,'speedOverrides':False,
        'scope':'当前源码及构建的离线装载、记录和原厂 AF 集成验证；允许准备观察装载，不代表增强 AF 已实机可用',
        'requires':['来源任务释放本轮独占窗口','实时原厂代码与堆归属核对','实时缓存探针/取指回执','用户手动 AF 样本与物理帧关联/延迟标定']}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('passed','observationInstallReady','enhancedAfReady','hardwareRequests','tests','contractSha256','seconds')},ensure_ascii=False))

if __name__=='__main__':main()
