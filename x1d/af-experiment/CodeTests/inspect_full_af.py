"""仅在电脑内存检查固定FARM；JSON行输入，null退出，无硬件模块。"""
import sys,json,traceback,struct,hashlib,re
from pathlib import Path
from collections import defaultdict
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'x1d/tools'),str(ROOT/'.research-cache/x1d-1.25.0/python')]
from farm_diagnostic_binary import FarmApplication
farm=FarmApplication()
assert farm.sha256=='317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca'

def fd(a,n=128):
    for item in farm.instructions(a,n):print('%08x %s %-8s %s'%(item.address,item.bytes.hex(),item.mnemonic,item.op_str))

if __name__=='__main__':
    print('READY',farm.sha256,flush=True)
    for line in sys.stdin:
        try:
            code=json.loads(line)
            if code is None:break
            exec(code,globals())
        except Exception:traceback.print_exc()
        print('FULL_AF_DONE',flush=True)
