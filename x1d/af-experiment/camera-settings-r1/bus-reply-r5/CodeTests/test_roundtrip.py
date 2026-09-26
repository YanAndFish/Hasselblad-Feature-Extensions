"""从真实源码提取 Bus 类执行；另以实际 ARM 库重跑发现/转发 ABI 检查。"""
import hashlib, importlib.util, json, os, subprocess, sys, unittest
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1]
COMMON=HERE.parent
ROOT=COMMON.parents[2]
assert Path.cwd().resolve()==ROOT
OUT=HERE/'test-build'
OUT.mkdir(exist_ok=True)
source=(HERE/'settings_bus.cpp').read_text(encoding='utf-8')
body=source[source.index('class Bus;'):source.index('\nvoid discover(QObject *sender)')]
assert body.count('private:')==1
body=body.replace('private:','public:') # 仅放开断言读取；实际构造/收发/校验代码不改动。
test=(HERE/'CodeTests/mocks.hpp').read_text(encoding='utf-8')+'\n'+body+'\n'+(HERE/'CodeTests/cases.cpp').read_text(encoding='utf-8')
(OUT/'test_bus.cpp').write_text(test,encoding='utf-8')
env=dict(os.environ)
for key,name in [('ZIG_GLOBAL_CACHE_DIR','global'),('ZIG_LOCAL_CACHE_DIR','local'),('TEMP','tmp'),('TMP','tmp')]:
    folder=OUT/name;folder.mkdir(exist_ok=True);env[key]=str(folder)
zig=ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
exe=OUT/'test_bus.exe'
obj=OUT/'native_config.obj'
result=subprocess.run([str(zig),'cc','-std=c11','-I',str(COMMON),'-c',str(COMMON/'native_config.c'),'-o',str(obj)],env=env,capture_output=True,text=True,timeout=120)
if result.returncode: raise RuntimeError(result.stderr)
cmd=[str(zig),'c++','-std=c++11','-O0','-I',str(COMMON),'-I',str(HERE),str(OUT/'test_bus.cpp'),str(obj),'-o',str(exe)]
result=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=120)
if result.returncode: raise RuntimeError(result.stderr)
result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
print(result.stdout)
if result.returncode: raise RuntimeError(result.stderr+' return '+str(result.returncode))
spec=importlib.util.spec_from_file_location('transport_arm_tests',HERE/'CodeTests/test_transport_arm.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
module.LIB=HERE/'linux-build/libhbl-af-bus.so'
suite=module.suite()
result=unittest.TextTestRunner(verbosity=2).run(suite)
paths=[HERE/'settings_bus.cpp',HERE/'transport_counts.h',HERE/'build_bus.py',module.LIB,Path(__file__),HERE/'CodeTests/mocks.hpp',HERE/'CodeTests/cases.cpp',HERE/'CodeTests/test_transport_arm.py']
report={'passed':result.wasSuccessful(),'methodScenarioGroups':11,'armStartupTests':result.testsRun,
    'hardwareRequests':0,'scope':'真实 Bus 类收发方法与原始 ARM interposer ABI；Qt/socket/文件系统为替身',
    'liveSocketOrUartVerified':False,'files':{str(p.relative_to(HERE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
(HERE/'roundtrip-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
raise SystemExit(not result.wasSuccessful())
