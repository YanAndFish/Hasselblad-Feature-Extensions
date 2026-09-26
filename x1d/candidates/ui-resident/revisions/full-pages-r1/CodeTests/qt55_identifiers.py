"""运行已审阅 Qt 5.5.1 原始关键词分类器；不冒充完整目标 QML 编译。"""
from fixtures import HERE,ROOT,CANDIDATE,sha,save,patch
from pathlib import Path
import json,os,re,subprocess
def main():
    old=CANDIDATE/'build/qt55-keywords';out=HERE/'build/qt55-keywords';out.mkdir(parents=True,exist_ok=True)
    proof=json.loads((CANDIDATE/'build/qt55-identifiers-validation.json').read_text(encoding='utf-8'))
    parser=ROOT/'.research-cache/x1d-1.25.0/qt-public/qtdeclarative-opensource-src-5.5.1/src/qml/parser'
    for name,value in proof['parserSourceHashes'].items():assert sha(parser/name)==value
    # 原分类函数在旧夹具中的文本必须逐字包含当前官方 5.5.1 输入。
    cpp=(old/'classify.cpp').read_text(encoding='utf-8')
    assert (parser/'qqmljskeywords_p.h').read_text(encoding='utf-8').replace('#include "qqmljslexer_p.h"','') in cpp
    (out/'classify.cpp').write_text(cpp,encoding='utf-8')
    zig=ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    env=dict(os.environ,ZIG_GLOBAL_CACHE_DIR=str(out/'global-cache'),ZIG_LOCAL_CACHE_DIR=str(out/'local-cache'))
    subprocess.run([str(zig),'c++','-O2',str(out/'classify.cpp'),'-o',str(out/'classify.exe')],env=env,capture_output=True,text=True,check=True,timeout=60)
    values=patch.resources()[0];ids={k:sorted(set(re.findall(r'\bid\s*:\s*([A-Za-z_$][\w$]*)',v))) for k,v in values.items() if k.endswith('.qml')}
    names=sorted(set(['transient','lazyPageLoader']+[n for group in ids.values() for n in group]))
    result=subprocess.run([str(out/'classify.exe'),*names],capture_output=True,text=True,check=True)
    tokens={n:int(v) for n,v in (line.split() for line in result.stdout.splitlines())}
    expected=tokens['lazyPageLoader'];assert tokens['transient']!=expected
    assert all(tokens[n]==expected for group in ids.values() for n in group)
    save(HERE/'build/qt55-identifiers.json',{'passed':True,'ids':ids,'identifierCount':sum(map(len,ids.values())),'method':'Qt5.5.1 original Lexer::classify with ASCII QChar adapter','targetQmlCompilePassed':False,
        'resources':{k:patch.digest(v) for k,v in values.items()},'sources':{p.relative_to(ROOT).as_posix():sha(p) for p in [Path(__file__),out/'classify.cpp',*(parser/n for n in proof['parserSourceHashes'])]},'hardwareRequests':0})
    print(json.dumps({'passed':True,'ids':sum(map(len,ids.values())),'targetQmlCompilePassed':False}))
if __name__=='__main__':main()
