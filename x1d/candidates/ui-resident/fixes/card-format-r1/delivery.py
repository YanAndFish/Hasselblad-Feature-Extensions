"""独立新目录交付；默认离线。旧 a8/默认入口/记录不改。"""
from pathlib import Path
import hashlib,importlib.util,sys
sys.dont_write_bytecode=True
FIX=Path(__file__).resolve().parent;CANDIDATE=FIX.parents[1]
def load(n,p):
    s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
BASE=CANDIDATE/'session/delivery.py'
if hashlib.sha256(BASE.read_bytes()).hexdigest()!='69a1045dcfdf328ae455ab05f3833292cd0e5b3eb7ea8c0da62b68d8586c78f4':raise ValueError('reviewed a8 transfer changed')
package=load('card_format_fixed_package',FIX/'package.py')
transport=load('card_format_reviewed_transfer',BASE)
transport.package=package;transport.HERE=FIX;transport.OUT=package.OUT;transport.REMOTE=package.build.REMOTE
if __name__=='__main__':transport.main(sys.argv[1:])
