"""生成与当前 r4 安装匹配的标定成对更新包。"""
from pathlib import Path
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
def main():
    source=(HERE.parent/'evf-hint-r4/increment.py').read_text(encoding='utf-8')
    source=source.replace('/tmp/hbl-evf-hint-r4','/tmp/hbl-calibration-r1').replace("session.Session('evf-hint-icon')","session.Session('mechanical-calibration-increment')")
    source=source.replace("PARENT/'evf-hint-r3/update/manifest.sha256'","PARENT/'evf-hint-r4/update/manifest.sha256'")
    source=source.replace('33694e7ba01f7c2acc8e887a44b68b8a2d166816a1fa9e0388f7dc8b66a3beff','e52e3304080bee4e6767137d18498e9c289d6317bfa962e7fc1e44d2766b00ab')
    anchor="    rows['formal-ui.rcc']=sha(rcc);rows['libhbl-formal.so']=sha(lib)"
    replacement=anchor+"\n    observer=(HERE/'build/formal-flash-program/libhbl-formal-observer.so').read_bytes()\n    clients=json.loads((HERE/'build/formal-flash-program/client-build.json').read_text())\n    assert sha(observer)==clients['outputs']['libhbl-formal-observer.so']['sha256']\n    rows['libhbl-formal-observer.so']=sha(observer)"
    assert source.count(anchor)==1;source=source.replace(anchor,replacement)
    source=source.replace("'formal-ui.rcc':rcc,'libhbl-formal.so':lib,","'formal-ui.rcc':rcc,'libhbl-formal.so':lib,'libhbl-formal-observer.so':observer,")
    source=source.replace('evf-hint-increment-ready','calibration-increment-ready')
    source=source.replace("'librarySha256':sha(lib),","'librarySha256':sha(lib),'observerSha256':sha(observer),")
    (HERE/'increment.py').write_text(source,encoding='utf-8',newline='\n')
if __name__=='__main__': main()
