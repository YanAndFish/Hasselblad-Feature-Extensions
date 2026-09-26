"""仅将已验收样式的提示停留时间改为两秒。"""
from pathlib import Path
import hashlib,sys
sys.dont_write_bytecode=True
import build_evf_increment as builder
HERE=Path(__file__).resolve().parent;WORK=HERE/'evf-hint-r5'
def main():
    builder.WORK=WORK;builder.build()
    old=hashlib.sha256((HERE/'evf-hint-r3/update/manifest.sha256').read_bytes()).hexdigest()
    new=hashlib.sha256((HERE/'evf-hint-r4/update/manifest.sha256').read_bytes()).hexdigest()
    for name in ('apply.sh','increment.py'):
        text=(HERE/'evf-hint-r4'/name).read_text(encoding='utf-8')
        text=text.replace('/tmp/hbl-evf-hint-r4','/tmp/hbl-evf-hint-r5').replace(old,new)
        text=text.replace("PARENT/'evf-hint-r3/update/manifest.sha256'","PARENT/'evf-hint-r4/update/manifest.sha256'")
        text=text.replace("session.Session('evf-hint-icon')","session.Session('evf-hint-duration')")
        (WORK/name).write_text(text,encoding='utf-8',newline='\n')
if __name__=='__main__':main()
