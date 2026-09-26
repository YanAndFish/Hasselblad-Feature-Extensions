"""只读核验固定包内引导器和内核的候选加载能力；不生成或安装启动补丁。"""
from pathlib import Path
import gzip,hashlib,importlib.util,json,re,sys,zlib
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
assert Path.cwd().resolve()==ROOT
sys.path.insert(0,str(ROOT/'x1d/tools'))
from recovery_binary import Uboot,fdt_nodes
u=Uboot();commands={c['name']:c for c in u.commands()}
wanted=('ext4load','ext4ls','bootz','source','env','run')
assert all(n in commands for n in wanted)
base=ROOT/'.research-cache/x1d-1.25.0/baseline'
script=(base/'hbl-upgrade').read_text(encoding='utf-8');post=(base/'usr/bin/hbl-post-upgrade').read_text(encoding='utf-8')
environment_writes=re.findall(r'^\s*fw_setenv\s+(\w+)',script+'\n'+post,re.MULTILINE)
assert set(environment_writes)=={'bootargs','emmcboot','upgrade','current_bootpart'}
spec=importlib.util.spec_from_file_location('boot_route_inputs',ROOT/'x1d/recovery-review/20260910-usb-sd/inspect_payloads.py')
reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
kernelname='boot/zImage-3.14.28-1.0.0_ga+yocto+gf7d0ab5';reader.WANTED={kernelname}
kernel=reader.inputs()[kernelname]
markers={'gzip':b'\x1f\x8b\x08','xz':b'\xfd7zXZ\0','lzo':b'\x89LZO\0\r\n\x1a\n','bzip2':b'BZh','lz4':b'\x02\x21\x4c\x18'}
compression_markers={name:[m.start() for m in re.finditer(re.escape(value),kernel)] for name,value in markers.items()}
expanded=[]
for m in re.finditer(b'\x1f\x8b\x08',kernel):
    try:
        d=zlib.decompress(kernel[m.start():],16+zlib.MAX_WBITS)
        if len(d)>len(kernel):expanded.append((m.start(),d))
    except zlib.error:pass
configuration={};found=False
for offset,data in [(0,kernel)]+expanded:
    start=data.find(b'IKCFG_ST')
    if start<0:continue
    end=data.find(b'IKCFG_ED',start+8)
    if end<0:continue
    try:config=gzip.decompress(data[start+8:end]).decode('ascii')
    except (OSError,EOFError,UnicodeError):continue
    found=True
    keys=('CONFIG_BLK_DEV_INITRD','CONFIG_RD_GZIP','CONFIG_INITRAMFS_SOURCE','CONFIG_DEVTMPFS','CONFIG_DEVTMPFS_MOUNT','CONFIG_EXT4_FS','CONFIG_TMPFS','CONFIG_PROC_FS','CONFIG_SYSFS','CONFIG_CMDLINE','CONFIG_CMDLINE_FORCE','CONFIG_CMDLINE_EXTEND')
    for key in keys:
        rows=[line for line in config.splitlines() if line.startswith(key+'=') or line=='# '+key+' is not set']
        configuration[key]=rows[0] if rows else 'not present in embedded config'
    break
report={'firmware':'X1D-50c 1.25.0','cimSha256':reader.SHA256,'ubootSha256':hashlib.sha256(u.data).hexdigest(),
        'kernelSha256':hashlib.sha256(kernel).hexdigest(),'kernelBytes':len(kernel),
        'commands':{n:{'entry':commands[n]['entry'],'handler':commands[n]['handler']} for n in wanted},
        'upgradeEnvironmentWrites':environment_writes,'bootcmdOrPrebootExplicitlyOverwritten':False,
        'compressionMarkers':compression_markers,'expandedKernelCandidates':[{'offset':o,'bytes':len(d),'sha256':hashlib.sha256(d).hexdigest()} for o,d in expanded],
        'embeddedKernelConfigFound':found,'kernelConfig':configuration,
        'hardwareRequests':0,'firmwareExecuted':False,'installedBootloaderVerified':False,'bootRouteImplemented':False,
        'crossUpgradePersistenceVerified':False}
(HERE/'CodeTests/boot-route-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
