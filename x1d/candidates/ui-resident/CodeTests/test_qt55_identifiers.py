"""运行 Qt 5.5.1 原关键词分类函数，检查候选 QML id；不是完整目标 QML 编译测试。"""
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
PARSER = ROOT/'.research-cache/x1d-1.25.0/qt-public/qtdeclarative-opensource-src-5.5.1/src/qml/parser'
COMPILER = ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
sys.path.insert(0,str(HERE/'tools'))
from build import build, PATHS

def run():
    build()
    work = HERE/'build/qt55-keywords'
    work.mkdir(parents=True,exist_ok=True)
    grammar = (PARSER/'qqmljsgrammar_p.h').read_text(encoding='utf-8')
    lexer = (PARSER/'qqmljslexer_p.h').read_text(encoding='utf-8')
    keywords = (PARSER/'qqmljskeywords_p.h').read_text(encoding='utf-8')
    tokens = dict(re.findall(r'\b(T_\w+)\s*=\s*(\d+)\b',grammar))
    tokens.update(dict(re.findall(r'\b(T_\w+)\s*=\s*(T_\w+)\b',lexer)))
    assert tokens['T_TRANSIENT']=='T_RESERVED_WORD'
    used = set(re.findall(r'Lexer::(T_\w+)',keywords))
    def value(name):
        v=tokens[name]
        return value(v) if v.startswith('T_') else v
    declarations=',\n'.join(name+'='+value(name) for name in sorted(used|{'T_RESERVED_WORD'}))
    # 用最小 ASCII QChar 替身调用原 classify 函数；函数体保持逐字不变。
    classifier=keywords.replace('#include "qqmljslexer_p.h"','')
    cpp='''#include <stdio.h>
#define QT_QML_BEGIN_NAMESPACE
#define QT_QML_END_NAMESPACE
struct QChar { unsigned short code; unsigned short unicode() const { return code; } };
namespace QQmlJS { struct Lexer { enum { @TOKENS@ }; static int classify(const QChar*, int, bool); }; }
'''.replace('@TOKENS@',declarations)+classifier+'''
int main(int argc, char **argv) {
 for(int i=1;i<argc;i++) {
  QChar word[512]; int n=0;
  while(argv[i][n] && n<511) { word[n].code=(unsigned char)argv[i][n]; n++; }
  printf("%s %d\\n",argv[i], QQmlJS::Lexer::classify(word,n,true));
 }
 return 0;
}
'''
    (work/'classify.cpp').write_text(cpp,encoding='utf-8')
    env=dict(os.environ, ZIG_GLOBAL_CACHE_DIR=str(work/'global-cache'),ZIG_LOCAL_CACHE_DIR=str(work/'local-cache'))
    compiled=subprocess.run([str(COMPILER),'c++','-O2',str(work/'classify.cpp'),'-o',str(work/'classify.exe')],env=env,capture_output=True,text=True)
    assert compiled.returncode==0,compiled.stderr
    files={path:(HERE/'build/overlay'/path.lstrip('/')).read_text(encoding='utf-8')
           for path in (*PATHS,'/mainmenu/ResidentLoader.qml')}
    ids={path:sorted(set(re.findall(r'\bid\s*:\s*([A-Za-z_$][\w$]*)',text))) for path,text in files.items()}
    names=sorted(set(['transient','lazyPageLoader']+[name for values in ids.values() for name in values]))
    result=subprocess.run([str(work/'classify.exe'),*names],capture_output=True,text=True,check=True)
    classified={name:int(token) for name,token in (line.split() for line in result.stdout.splitlines())}
    identifier=int(value('T_IDENTIFIER'));reserved=int(value('T_RESERVED_WORD'))
    assert classified['transient']==reserved
    assert classified['lazyPageLoader']==identifier
    bad={path:[name for name in names if classified[name]!=identifier] for path,names in ids.items()}
    assert not any(bad.values()),bad
    old=(HERE/'build/fixed/ui-resident-589913e798229625/overlay/mainmenu/ResidentLoader.qml').read_text(encoding='utf-8')
    current=files['/mainmenu/ResidentLoader.qml']
    assert re.sub(r'\btransient\b','lazyPageLoader',old)==current
    old_manifest=json.loads((HERE/'build/fixed/ui-resident-589913e798229625/manifest.json').read_text(encoding='utf-8'))
    for path in PATHS:
        assert hashlib.sha256(files[path].encode()).hexdigest()==old_manifest['resources'][path]['outputSha256']
    report={'passed':True,'targetQmlCompilePassed':False,'method':'Qt5.5.1 original Lexer::classify, ASCII QChar adapter, host native execution',
            'oldIdentifier':{'name':'transient','token':reserved},'newIdentifier':{'name':'lazyPageLoader','token':identifier},
            'checkedIds':ids,'identifierCount':sum(map(len,ids.values())),'onlyIdentifierRename':True,'otherThreeResourcesUnchanged':True,
            'parserSourceHashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [PARSER/'qqmljsgrammar_p.h',PARSER/'qqmljslexer_p.h',PARSER/'qqmljskeywords_p.h']},
            'sourceSha256':hashlib.sha256(current.encode()).hexdigest()}
    (HERE/'build/qt55-identifiers-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['passed','targetQmlCompilePassed','identifierCount','onlyIdentifierRename']},ensure_ascii=False))

if __name__=='__main__':run()
