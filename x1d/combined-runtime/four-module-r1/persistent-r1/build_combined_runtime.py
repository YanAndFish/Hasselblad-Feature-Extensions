"""从通过模型检查的候选构建独立 AF Linux 装载器，不访问相机。"""
from pathlib import Path
import sys,os,json,hashlib,subprocess
sys.dont_write_bytecode=True
P=Path(__file__).resolve().parent;ROOT=P.parents[3];assert Path.cwd().resolve()==ROOT
out=P/'build/combined-hub'
model=json.loads((out/'lifecycle-validation.json').read_text(encoding='utf-8'))
assert model['passed']
for name,digest in model['sources'].items():assert hashlib.sha256((P/name).read_bytes()).hexdigest()==digest,name
arm=json.loads((P/'build/combined-hub/arm-validation.json').read_text(encoding='utf-8'))
assert arm['passed'] and arm['initializerSha256']==hashlib.sha256((P/'build/combined-hub/initializer.bin').read_bytes()).hexdigest()
assert arm['testSha256']==hashlib.sha256((P/'CodeTests/combined_hub_init_arm_check.py').read_bytes()).hexdigest()
transport=json.loads((P/'build/block-write/transport-arm-validation.json').read_text(encoding='utf-8'))
assert transport['passed'] and transport['testSha256']==hashlib.sha256((P/'CodeTests/block_transport_arm_check.py').read_bytes()).hexdigest()
seed=json.loads((P/'build/combined-hub/handoff-arm-validation.json').read_text(encoding='utf-8'))
assert seed['passed'] and seed['seedSha256']==hashlib.sha256((P/'build/combined-hub/seed.bin').read_bytes()).hexdigest()
assert seed['testSha256']==hashlib.sha256((P/'CodeTests/combined_hub_handoff_arm_check.py').read_bytes()).hexdigest()
reference=json.loads((P/'build/formal-flash-program/client-build.json').read_text(encoding='utf-8'))['commands']
compile_args=reference[0]['arguments'];compile_args=compile_args[:compile_args.index('-c')]
link_args=next(c['arguments'] for c in reference if '-Wl,-soname,libhbl-formal.so' in c['arguments'])
zig=ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
env=dict(os.environ)
for key,name in [('ZIG_GLOBAL_CACHE_DIR','global-cache'),('ZIG_LOCAL_CACHE_DIR','local-cache'),('TEMP','tmp'),('TMP','tmp')]:
 d=P/'build/formal-flash-program'/name;d.mkdir(exist_ok=True);env[key]=str(d)
sources=[P/'native/formal_worker.cpp',P/'native/formal_sync_observer.cpp',P/'native/boot_transport.cpp',out/'combined_loader.cpp',out/'combined_session.cpp']
commands=[];objects=[]
def run(args):
 r=subprocess.run([str(zig)]+args,cwd=ROOT,env=env,text=True,capture_output=True)
 commands.append(dict(arguments=args,exit=r.returncode,stderr=r.stderr))
 if r.returncode:print(r.stderr);r.check_returncode()
for source in sources:
 obj=out/(source.stem+'.o');run(compile_args+['-c',str(source),'-o',str(obj)]);objects.append(str(obj))
args=[]
for v in link_args:
 if v.endswith('formal_runtime.o'):args+=objects
 elif v=='-Wl,-soname,libhbl-formal.so':args.append('-Wl,-soname,libhbl-combined-loader.so')
 else:args.append(v)
output=out/'libhbl-combined-loader.so';args[-1]=str(output);run(args)
report=dict(passed=True,commands=commands,sha256=hashlib.sha256(output.read_bytes()).hexdigest(),bytes=output.stat().st_size,
 sources={str(s.relative_to(P)):hashlib.sha256(s.read_bytes()).hexdigest() for s in sources},installed=False)
(out/'runtime-build.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ('commands','sources')}))
