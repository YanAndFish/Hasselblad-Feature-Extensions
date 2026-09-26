"""仅将中央两行提示边框改为原厂 hblOrange。"""
from pathlib import Path
import hashlib,sys
sys.dont_write_bytecode=True
import build_evf_increment as builder
HERE=Path(__file__).resolve().parent;WORK=HERE/'evf-hint-r3'
def main():
    builder.WORK=WORK;builder.build()
    old='2fecd16e4fda183463fdd92c74404c9a2aedb26ea291adef444bab033395ccff'
    new=hashlib.sha256((HERE/'evf-hint-r2/update/manifest.sha256').read_bytes()).hexdigest()
    for name in ('apply.sh','increment.py'):
        text=(HERE/'evf-hint-r2'/name).read_text(encoding='utf-8')
        text=text.replace('/tmp/hbl-evf-hint-r2','/tmp/hbl-evf-hint-r3').replace(old,new)
        text=text.replace("PARENT/'evf-hint-r1/update/manifest.sha256'","PARENT/'evf-hint-r2/update/manifest.sha256'")
        text=text.replace("session.Session('evf-hint-framed')","session.Session('evf-hint-orange')")
        (WORK/name).write_text(text,encoding='utf-8',newline='\n')
if __name__=='__main__':main()
