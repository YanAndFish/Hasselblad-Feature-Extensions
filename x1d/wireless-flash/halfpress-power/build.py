"""离线生成 GUI 与 worker；不签发、不安装、不连接相机。"""
from pathlib import Path
import sys,json,hashlib,importlib.util,subprocess,os
from integrate import resources,native,policy,worker
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
P=ROOT/'x1d/combined-runtime/four-module-r1/persistent-r1'
S=ROOT/'x1d/shutter-effects';BASE=S/'build/candidate-r6';OUT=HERE/'build'
sys.path.insert(0,str(ROOT/'x1d/patch-distribution'))
from build_viewfinder_modes import read_rcc,rcc

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    gui=OUT/'gui';radio=OUT/'native'
    gui.mkdir(parents=True,exist_ok=True);radio.mkdir(parents=True,exist_ok=True)
    baseline=json.loads((BASE/'result-r6.json').read_text(encoding='utf8'))
    assert sha(BASE/'flash-ui.rcc')==baseline['outputRccSha256']
    values=resources(read_rcc((BASE/'flash-ui.rcc').read_bytes()))
    blob=rcc(values);assert read_rcc(blob)==values
    (gui/'flash-ui.rcc').write_bytes(blob)
    (gui/'entry.cpp').write_text(native((BASE/'entry.cpp').read_text(encoding='utf8')),encoding='utf8')
    (gui/'halfpress_settings.h').write_bytes((HERE/'halfpress_settings.h').read_bytes())
    report=dict(baseline);report['outputRccSha256']=hashlib.sha256(blob).hexdigest()
    (gui/'result.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    b=load('halfpress_native_build',S/'build_native.py');b.OUT=gui;b.main()
    (radio/'formal_policy.h').write_text(policy((P/'native/formal_policy.h').read_text(encoding='utf8')),encoding='utf8')
    (radio/'formal_worker.cpp').write_text(worker((P/'build/radio-three-state/formal_worker.cpp').read_text(encoding='utf8')),encoding='utf8')
    old=json.loads((P/'build/uart-source-repair/build.json').read_text(encoding='utf8'))['commands']
    args=list(old[0]['arguments']);assert args[args.index('-c')+1].endswith('formal_worker.cpp')
    args[args.index('-c')+1]=str(radio/'formal_worker.cpp');args[args.index('-o')+1]=str(radio/'formal_worker.o')
    boot=ROOT/'x1d/patch-distribution/build/boot-hold-repair'
    prior=json.loads((boot/'build.json').read_text(encoding='utf8'))
    assert sha(boot/'libhbl-af-loader.so')==prior['sha256']=='459e730437892ddfeef11ddd35d3855789d9782187b515493de7175f3a4ebf47'
    link=list(prior['commands'][-1]);found=[i for i,x in enumerate(link) if x.endswith('formal_worker.o')];assert len(found)==1
    link[found[0]]=str(radio/'formal_worker.o');link[link.index('-o')+1]=str(radio/'libhbl-af-loader.so')
    zig=ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    env=dict(os.environ)
    for k,sub in [('ZIG_GLOBAL_CACHE_DIR','zig-global'),('ZIG_LOCAL_CACHE_DIR','zig-local'),('TEMP','tmp'),('TMP','tmp')]:
        path=OUT/sub;path.mkdir(exist_ok=True);env[k]=str(path)
    for command in [args,link]:
        result=subprocess.run([str(zig),*command],env=env,capture_output=True,text=True,timeout=180)
        if result.returncode:raise RuntimeError(result.stderr[-5000:])
    proof=dict(compiled=True,installed=False,hardwareRequests=0,base='ciallo-r6',
        guiSha256=sha(gui/'hotspot-libhotspot-entry.so'),rccSha256=sha(gui/'af-ui.rcc'),
        loaderSha256=sha(radio/'libhbl-af-loader.so'),defaultEnabled=False,
        modes=['mechanical','electronic'],commands=[args,link])
    (OUT/'build.json').write_text(json.dumps(proof,indent=2),encoding='utf8')
    print('Halfpress GUI and worker ARM candidates built; not installed')
if __name__=='__main__':main()
