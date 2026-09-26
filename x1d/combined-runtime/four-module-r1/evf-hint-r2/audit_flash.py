"""界面增量完成后只读核对引闪 RAM，不允许写入。"""
from pathlib import Path
import sys,json
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
import session
class ReadOnly(session.capture.FixedIO):
    def exchange(self,kind,a=None,v=None):
        if kind!='read':raise RuntimeError('read-only audit')
        return super().exchange(kind,a,v)
if __name__=='__main__':
    loader=session.capture.Loader(ReadOnly())
    loader.verify(1)
    assert loader.io.writes==0 and loader.io.closed
    result={'passed':True,'requests':loader.io.requests,'writes':loader.io.writes,'allHandlesClosed':loader.io.closed}
    (HERE/'update/flash-audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
