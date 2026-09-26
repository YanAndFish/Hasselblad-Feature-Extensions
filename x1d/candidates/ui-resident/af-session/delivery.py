"""AF r4 共存包串行入口；默认离线，复用已核验的有界 Linux 传输。"""
from pathlib import Path
import hashlib,importlib.util,json,sys
sys.dont_write_bytecode=True
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
HERE=Path(__file__).resolve().parent
package=load('ui_af_fixed_package',HERE/'package.py')
BASE=HERE.parent/'session/delivery.py'
BASE_SHA='69a1045dcfdf328ae455ab05f3833292cd0e5b3eb7ea8c0da62b68d8586c78f4'
if hashlib.sha256(BASE.read_bytes()).hexdigest()!=BASE_SHA:raise ValueError('reviewed transfer changed')
transport=load('ui_af_reviewed_transfer',BASE)
transport.REMOTE=package.build.REMOTE;transport.OUT=package.OUT;transport.HERE=HERE;transport.package=package
transport.MARKERS={'preflight':'ui-af-preflight-ready','ui':'ui-af-session-ready','status':'ui-af-session-ready','restore':'ui-af-r4-restored'}
def main(args):
    if not args and not (HERE/'r4-binding.json').exists():
        print(json.dumps({'readyForRootStaging':False,'reason':'AF owner r4 fixed delivery pending','hardwareRequests':0}));return
    transport.main(args)
if __name__=='__main__':main(sys.argv[1:])
