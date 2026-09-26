"""离线最终验证；记录实际测试输出和精确文件哈希，安装前检查证据未过期。"""
import sys,subprocess,json,hashlib
from pathlib import Path
from datetime import datetime
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[1];BUILD=HERE/"build/full-r2"
assert Path.cwd().resolve()==ROOT.resolve()
manifest=json.loads((BUILD/"manifest.json").read_text(encoding="utf-8"))
assert hashlib.sha256((BUILD/"candidate.bin").read_bytes()).hexdigest()==manifest["payload_sha256"]
assert hashlib.sha256((HERE/"full_candidate_r2.c").read_bytes()).hexdigest()==manifest["source_sha256"]
files=("full_candidate_r2.c","full_candidate.ld","full_loader_r2.py","probe_loader.py","build_full_r2.py",
       "CodeTests/test_full_r2.py","CodeTests/test_full_loader_r2.py","CodeTests/validate_full_r2.py",
       "CodeTests/test_user_images.py","CodeTests/Fixtures/SyntheticAfCurves.json",
       "CodeTests/test_full_candidate.py","CodeTests/test_loader.py")
before={name:hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in files}
results=[]
for name,log in (("test_full_r2.py","native-tests.txt"),("test_full_loader_r2.py","loader-tests.txt"),("test_loader.py","prior-loader-tests.txt")):
    result=subprocess.run([sys.executable,"-B",str(HERE/"CodeTests"/name)],cwd=ROOT,text=True,encoding="utf-8",errors="replace",capture_output=True,timeout=90)
    (BUILD/log).write_text(result.stdout+result.stderr,encoding="utf-8")
    results.append({"test":name,"exitCode":result.returncode,"log":log})
    print(name,"PASS" if result.returncode==0 else "FAIL",flush=True)
    if result.returncode:print(result.stdout+result.stderr,flush=True);raise SystemExit(result.returncode)
assert before=={name:hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in files}
record={"at":datetime.now().astimezone().isoformat(),"passed":True,"payloadSha256":manifest["payload_sha256"],
        "files":before,"results":results,"hardwareRequests":0,"physicalAfVerified":False}
(BUILD/"validation.json").write_text(json.dumps(record,indent=2)+"\n",encoding="utf-8")
print("EXACT_BUILD_READY",manifest["payload_sha256"],flush=True)
