"""在已安装中央提示基础上生成两行大字、原厂边框底色增量。"""
from pathlib import Path
import sys
sys.dont_write_bytecode=True
import build_evf_increment as builder
HERE=Path(__file__).resolve().parent
WORK=HERE/'evf-hint-r2'
def main():
    builder.WORK=WORK;builder.build()
    old='61ffd1f1ba51acee1209aa0d5d10cd25a700e4a2189114f0dded5462d0547869'
    new='2fecd16e4fda183463fdd92c74404c9a2aedb26ea291adef444bab033395ccff'
    text=(HERE/'evf-hint-r1/apply.sh').read_text(encoding='utf-8').replace('/tmp/hbl-evf-hint-r1','/tmp/hbl-evf-hint-r2').replace(old,new)
    (WORK/'apply.sh').write_text(text,encoding='utf-8',newline='\n')
    code=(HERE/'evf-hint-r1/increment.py').read_text(encoding='utf-8').replace('/tmp/hbl-evf-hint-r1','/tmp/hbl-evf-hint-r2').replace("session.Session('evf-hint-increment')","session.Session('evf-hint-framed')")
    start=code.index('    previous=json.loads(')
    end=code.index('    rcc=',start)
    code=code[:start]+"    old=(PARENT/'evf-hint-r1/update/manifest.sha256').read_bytes()\n    assert sha(old)=='"+new+"'\n"+code[end:]
    (WORK/'increment.py').write_text(code,encoding='utf-8',newline='\n')
if __name__=='__main__': main()
