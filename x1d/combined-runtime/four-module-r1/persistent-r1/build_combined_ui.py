"""正式组合 GUI 候选：安装期绑定资源，运行期不重复静态检查和诊断输出。"""
from pathlib import Path
import importlib.util,json
P=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('combined_gui_builder',P.parent/'build_native.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
b.HERE=P;b.FLASH=P;b.OUT=P/'build/combined-hub/gui'
original=b.generate
def generate():
 r=original()
 f=b.OUT/'runtime.cpp';s=f.read_text(encoding='utf-8')
 start=s.index('bool hash(const char *path,');end=s.index('\n}',start)
 # helper namespace closes after combinedResources; preserve its closing brace.
 end=s.index('\n}\n#include "readiness.h"',start)
 s=s[:start]+s[end:]
 start=s.index(' &&\n       hash("/proc/self/exe"');end=s.index('))',start)+1
 s=s[:start]+s[end:]
 s=s.replace('        if(!combinedResources()){status("combined-resource-hash-failed");return;}\n','')
 start=s.index('        for(const Entry &entry:combinedEntries) {');end=s.index('        gate->start();',start)
 s=s[:start]+s[end:]
 f.write_text(s,encoding='utf-8',newline='\n')
 f=b.OUT/'readiness.h';s=f.read_text(encoding='utf-8')
 start=s.index('void saveDiagnostic(');end=s.index('struct BootGate',start)
 s=s[:start]+s[end:]
 s=s.replace('    QByteArray lastDiagnostic;\n','').replace('    long long nextDiagnostic = 0;\n','')
 start=s.index('            QByteArray structure =');end=s.index('            ResidentGate::Result',start)
 s=s[:start]+s[end:]
 s=s.replace('timer.stop(); saveDiagnostic(snapshot.text(now, warningCount));','timer.stop();')
 s=s.replace('saveDiagnostic("schema=1 t=0 state=starting\\n"); ','')
 f.write_text(s,encoding='utf-8',newline='\n')
 return r
b.generate=generate
if __name__=='__main__':print(json.dumps(b.build()))
