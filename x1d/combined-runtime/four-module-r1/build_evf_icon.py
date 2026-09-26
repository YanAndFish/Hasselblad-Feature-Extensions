"""扩展中央提示留白、字号并复用原厂信息图标。"""
from pathlib import Path
import hashlib,sys
sys.dont_write_bytecode=True
import build_evf_increment as builder
HERE=Path(__file__).resolve().parent;WORK=HERE/'evf-hint-r4'
def main():
    builder.WORK=WORK;builder.build()
    old=hashlib.sha256((HERE/'evf-hint-r2/update/manifest.sha256').read_bytes()).hexdigest()
    new=hashlib.sha256((HERE/'evf-hint-r3/update/manifest.sha256').read_bytes()).hexdigest()
    for name in ('apply.sh','increment.py'):
        text=(HERE/'evf-hint-r3'/name).read_text(encoding='utf-8')
        text=text.replace('/tmp/hbl-evf-hint-r3','/tmp/hbl-evf-hint-r4').replace(old,new)
        text=text.replace("PARENT/'evf-hint-r2/update/manifest.sha256'","PARENT/'evf-hint-r3/update/manifest.sha256'")
        text=text.replace("session.Session('evf-hint-orange')","session.Session('evf-hint-icon')")
        (WORK/name).write_text(text,encoding='utf-8',newline='\n')
if __name__=='__main__':main()
