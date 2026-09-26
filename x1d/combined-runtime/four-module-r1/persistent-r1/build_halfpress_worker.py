"""构建半按功率、全按排队候选；不访问相机。"""
from pathlib import Path
import hashlib,json,os,subprocess,sys
sys.dont_write_bytecode=True
P=Path(__file__).resolve().parent;ROOT=P.parents[3]
assert Path.cwd().resolve()==ROOT
O=P/'build/halfpress-ui/worker';O.mkdir(parents=True,exist_ok=True)
# 保留已使用的内存时间线探针，用于手动验收提前同步被丢弃的情况。
probe=(P/'build_flash_timeline_probe.py').read_text(encoding='utf-8').split('reference = json.loads',1)[0]
probe=probe.replace("P / 'build/flash-timeline-probe'","P / 'build/halfpress-ui/worker'")
probe=probe.replace("replace('            case FORMAL_FLUSH: {', '            case FORMAL_FLUSH: { probe(1,p.values[FV_TOKEN],0);')", "replace('            case FORMAL_PREPARE:case FORMAL_FLUSH: {', '            case FORMAL_PREPARE:case FORMAL_FLUSH: { probe(1,p.values[FV_TOKEN],0);')")
scope={'__file__':str(P/'build_flash_timeline_probe.py')};exec(compile(probe,str(P/'build_flash_timeline_probe.py'),'exec'),scope)
proof=json.loads((P/'CodeTests/formal_policy_output/validation.json').read_text())
assert proof['passed']
for name,digest in proof['sourceHashes'].items():
    assert hashlib.sha256((P/name).read_bytes()).hexdigest()==digest,name
reference=json.loads((P/'build/combined-hub/runtime-build.json').read_text())
for name,digest in reference['sources'].items():
    if name.replace('\\','/')!='native/formal_worker.cpp':
        assert hashlib.sha256((P/name).read_bytes()).hexdigest()==digest,name
zig=ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
env=dict(os.environ)
for key,name in [('ZIG_GLOBAL_CACHE_DIR','global-cache'),('ZIG_LOCAL_CACHE_DIR','local-cache'),('TEMP','tmp'),('TMP','tmp')]:
    d=O/name;d.mkdir(exist_ok=True);env[key]=str(d)
commands=[]
for command in reference['commands']:
    args=[str(O/Path(v).name) if v.endswith(('.o','.so')) and 'combined-hub' in v else v for v in command['arguments']]
    args=[str(O/'formal_worker.cpp') if Path(v).name=='formal_worker.cpp' else v for v in args]
    if '-c' in args:args[1:1]=['-I'+str(P/'native')]
    r=subprocess.run([str(zig)]+args,cwd=ROOT,env=env,capture_output=True,text=True)
    commands.append(dict(arguments=args,exit=r.returncode,stderr=r.stderr))
    if r.returncode:raise RuntimeError(r.stderr)
binary=O/'libhbl-combined-loader.so'
report=dict(passed=True,installed=False,commands=commands,sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),bytes=binary.stat().st_size)
(O/'build.json').write_text(json.dumps(report,indent=2),encoding='utf-8',newline='\n')
print(json.dumps(dict(built=True,installed=False,bytes=report['bytes'])))
