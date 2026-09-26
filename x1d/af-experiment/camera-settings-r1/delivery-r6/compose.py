"""生成独立完整包；只在本目录写入，不改任何上游冻结交付。"""
import gzip,hashlib,io,json,os,subprocess,sys,tarfile
from pathlib import Path
sys.dont_write_bytecode=True
import delivery_package as p
HERE,AF,ROOT=p.HERE,p.AF,p.ROOT
def make():
    assert Path.cwd().resolve()==ROOT
    p.frozen_inputs()
    cache=ROOT/'.research-cache/x1d-1.25.0';out=HERE/'local-build';out.mkdir(exist_ok=True)
    env=dict(os.environ)
    for key,name in [('ZIG_GLOBAL_CACHE_DIR','global'),('ZIG_LOCAL_CACHE_DIR','local'),('TEMP','tmp'),('TMP','tmp')]:
        folder=out/name;folder.mkdir(exist_ok=True);env[key]=str(folder)
    compiler=cache/'toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    target=['-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9']
    linker=out/'relocations.ld';linker.write_text('SECTIONS { .rel.dyn : { *(.rel.dyn) } .rel.plt : { *(.rel.plt) } } INSERT BEFORE .ARM.exidx;\n',encoding='ascii')
    obj=out/'local_check.o';binary=HERE/'inputs/bus-local-check';commands=[]
    def run(args):
        r=subprocess.run([str(compiler)]+args,env=env,capture_output=True,text=True,timeout=60)
        commands.append({'arguments':args,'exit':r.returncode,'stderr':r.stderr})
        if r.returncode:raise RuntimeError(r.stderr)
    run(['c++','-std=c++11']+target+['-marm','-O2','-fPIC','-fno-stack-protector','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror',
        '-I',str(AF/'bus-roundtrip-r3'),'-c',str(HERE/'local_check.cpp'),'-o',str(obj)])
    run(['cc']+target+['-Wl,--no-undefined','-Wl,-s','-Wl,-T,'+str(linker),str(obj),
        str(cache/'baseline/lib/libc-2.22.so'),str(cache/'baseline/lib/libgcc_s.so.1'),'-o',str(binary)])
    sys.path.insert(0,str(cache/'python'))
    from elftools.elf.elffile import ELFFile
    elf=ELFFile(io.BytesIO(binary.read_bytes()));rel=elf.get_section_by_name('.rel.dyn');plt=elf.get_section_by_name('.rel.plt')
    assert elf.elfclass==32 and elf.little_endian and elf['e_machine']=='EM_ARM'
    assert rel['sh_addr']+rel['sh_size']==plt['sh_addr']
    imports={s.name for s in elf.get_section_by_name('.dynsym').iter_symbols() if s['st_shndx']=='SHN_UNDEF'}
    assert '__lxstat64' in imports and not imports.intersection({'stat','lstat','fstat','stat64','lstat64','fstat64','__xstat','__lxstat','__fxstat'})
    (out/'local-check-build.json').write_text(json.dumps({'compiled':True,'hardwareRequests':0,'sha256':p.sha(binary),'commands':commands,
        'sourceSha256':p.sha(HERE/'local_check.cpp'),'headerSha256':p.sha(AF/'bus-roundtrip-r3/settings_socket.h'),
        'relocationsContiguous':True,'statInterface':'__lxstat64'},indent=2)+'\n',encoding='utf-8')
    for dest,source in [('af/libhbl-af-ui.so','ui/linux-build/libhbl-af-ui.so'),
                        ('af/libhbl-af-bus.so','bus/linux-build/libhbl-af-bus.so'),
                        ('af-only-ui.rcc','ui/build/resources/af-only-ui.rcc')]:
        (HERE/'inputs'/dest).write_bytes((HERE/source).read_bytes())
    names=('common.sh','install.sh','restore.sh','run.sh','af/libhbl-af-ui.so','af/libhbl-af-bus.so','libhbl-af-only.so',
           'af-only-ui.rcc','system-check','hold-file.check','baseline.sha256','bus-local-check')
    files={n:(HERE/'inputs'/n).read_bytes() for n in names}
    files['manifest.sha256']=''.join(hashlib.sha256(v).hexdigest()+'  '+n+'\n' for n,v in sorted(files.items())).encode()
    (HERE/'inputs/manifest.sha256').write_bytes(files['manifest.sha256'])
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w',format=tarfile.USTAR_FORMAT) as tar:
        for name,data in sorted(files.items()):
            m=tarfile.TarInfo(name);m.size=len(data);m.mtime=0;m.mode=0o700 if name.endswith('.sh') or name in ('system-check','bus-local-check') else 0o600
            tar.addfile(m,io.BytesIO(data))
    blob=gzip.compress(stream.getvalue(),mtime=0);(HERE/'inputs/af-only.tar.gz').write_bytes(blob)
    report={'kind':'af-only-clean-install-r6','packageSha256':hashlib.sha256(blob).hexdigest(),'bytes':len(blob),
        'files':{n:hashlib.sha256(v).hexdigest() for n,v in files.items()},'hardwareRequests':0,
        'directionAlgorithmChanged':False,'afControlChanged':True,'twoStageProbe':True,'configAbi':4,'probeWhitelistAdded':[15000,17000,20000],'farmConfigValidationChanged':True,'guiRevision':'ui-probe-r6','busRevision':'bus-reply-r6',
        'extraAfParameterWrites':False,'automaticQueryOrApply':False,'physicalRoundtripVerified':False,'upstreamProofs':p.PROOFS}
    (HERE/'inputs/package.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return {'composed':True,'packageSha256':report['packageSha256'],'bytes':len(blob),'hardwareRequests':0}
if __name__=='__main__':print(json.dumps(make()))
