"""r2 默认离线验证；任何设备阶段须由主任务重新授权。"""
from pathlib import Path
import hashlib,importlib.util,sys
sys.dont_write_bytecode=True
REV=Path(__file__).resolve().parent;CANDIDATE=REV.parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
BASE=CANDIDATE/'session/delivery.py'
if hashlib.sha256(BASE.read_bytes()).hexdigest()!='69a1045dcfdf328ae455ab05f3833292cd0e5b3eb7ea8c0da62b68d8586c78f4':raise ValueError('reviewed transfer changed')
package=load('full_ui_r2_package',REV/'package.py');transport=load('full_ui_r2_transport',BASE)
transport.package=package;transport.HERE=REV;transport.OUT=package.OUT;transport.REMOTE=package.build.REMOTE
if __name__=='__main__':transport.main(sys.argv[1:])
