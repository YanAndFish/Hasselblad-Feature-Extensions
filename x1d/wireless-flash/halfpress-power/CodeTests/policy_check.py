"""策略测试；比较构建使用的头文件，再运行原回归和新增用例。"""
from pathlib import Path
import sys,subprocess,json,hashlib,os
HERE=Path(__file__).resolve().parent.parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(HERE));from integrate import policy
P=ROOT/'x1d/combined-runtime/four-module-r1/persistent-r1'
out=HERE/'build/policy-test';(out/'native').mkdir(parents=True,exist_ok=True);(out/'CodeTests').mkdir(exist_ok=True)
source=policy((P/'native/formal_policy.h').read_text(encoding='utf8'))
assert source==(HERE/'build/native/formal_policy.h').read_text(encoding='utf8')
(out/'native/formal_policy.h').write_text(source,encoding='utf8')
(out/'CodeTests/formal_policy.test.cpp').write_bytes((P/'CodeTests/formal_policy.test.cpp').read_bytes())
zig=ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
env=dict(os.environ)
for key,sub in [('ZIG_GLOBAL_CACHE_DIR','global-cache'),('ZIG_LOCAL_CACHE_DIR','local-cache'),('TEMP','tmp'),('TMP','tmp')]:
    path=out/sub;path.mkdir(exist_ok=True);env[key]=str(path)
results=[]
for src,name in [(HERE/'CodeTests/policy_check.cpp','halfpress-test'),(out/'CodeTests/formal_policy.test.cpp','regression-test')]:
    exe=out/(name+'.exe')
    built=subprocess.run([str(zig),'c++','-std=c++11','-O2','-include','initializer_list','-I',str(out/'native'),'-I',str(P/'native'),str(src),'-o',str(exe)],env=env,capture_output=True,text=True)
    if built.returncode:raise RuntimeError(built.stderr[-3000:])
    ran=subprocess.run([str(exe)],check=True,capture_output=True,text=True)
    print(ran.stdout.strip());results.append(dict(test=name,result=ran.stdout.strip()))
proof=dict(passed=True,hardwareRequests=0,policySha256=hashlib.sha256(source.encode()).hexdigest(),results=results)
(out/'validation.json').write_text(json.dumps(proof,indent=2),encoding='utf8')
