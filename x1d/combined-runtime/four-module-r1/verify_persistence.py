"""固定官方归档的只读启动链审计及升级/降级文件模型；不连接相机。"""
from pathlib import Path
import hashlib,importlib.util,json,posixpath,re,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
assert Path.cwd().resolve()==ROOT
spec=importlib.util.spec_from_file_location('persistence_inputs',ROOT/'x1d/recovery-review/20260910-usb-sd/inspect_payloads.py')
reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
reader.WANTED=set()
original=reader.tarfile.open
links=[];references=[];count=0;scanned=0
class Scan:
    def __init__(self,*args,**kwargs):self.archive=original(*args,**kwargs)
    def __enter__(self):self.archive.__enter__();return self
    def __exit__(self,*args):return self.archive.__exit__(*args)
    def extractfile(self,m):return self.archive.extractfile(m)
    def __iter__(self):
        global count,scanned
        for m in self.archive:
            count+=1;n=m.name.removeprefix('./')
            if m.issym() or m.islnk():links.append({'path':n,'target':m.linkname})
            if m.isfile() and 0<m.size<200000 and n.startswith(('etc/','lib/systemd/','usr/bin/','usr/sbin/','lib/udev/')):
                data=self.archive.extractfile(m).read()
                if b'\0' not in data:
                    scanned+=1
                    hits=[{'line':i,'text':line} for i,line in enumerate(data.decode('utf-8',errors='replace').splitlines(),1)
                          if '/media/data' in line or 'rc.local' in line]
                    if hits:references.append({'path':n,'sha256':hashlib.sha256(data).hexdigest(),'references':hits})
            yield m
reader.tarfile.open=Scan
try:reader.inputs()
finally:reader.tarfile.open=original
def link_target(x):
    return posixpath.normpath(x['target'] if x['target'].startswith('/') else '/'+posixpath.join(posixpath.dirname(x['path']),x['target']))
data_links=[dict(x,resolved=link_target(x)) for x in links if link_target(x)=='/media/data' or link_target(x).startswith('/media/data/')]
startup_links=[x for x in links if x['path'].startswith(('etc/systemd/','sbin/init','etc/init.d/','etc/rc'))]
# 根据已核验脚本抽取分区切换规则，模型不执行固件脚本。
base=ROOT/'.research-cache/x1d-1.25.0/baseline'
upgrade=(base/'hbl-upgrade').read_text();post=(base/'usr/bin/hbl-post-upgrade').read_text()
assert all(s in upgrade for s in ('BOOT_A_DEV=/dev/mmcblk3p1','ROOT_A_DEV=/dev/mmcblk3p2','BOOT_B_DEV=/dev/mmcblk3p3','ROOT_B_DEV=/dev/mmcblk3p4','do_mkfs','bzcat ${ROOTFS} | tar xf - -C $2'))
assert 'STAGING_UPGRADE=/media/data/upgrade' in post and 'rm -rf ${STAGING_UPGRADE}' in post
slots={1:{'factory','loader'},3:{'factory'}};active=1;data={'patch','settings'}
checks=[]
def update():
    global active
    target=3 if active==1 else 1
    slots[target]={'factory'};active=target
assert 'loader' in slots[active];checks.append('initial-installed-root-entry')
update();assert 'patch' in data and 'loader' not in slots[active];checks.append('upgrade-retains-modeled-data-but-loses-entry')
assert 'loader' in slots[1];checks.append('old-slot-temporarily-still-has-entry')
update();assert 'patch' in data and all('loader' not in slot for slot in slots.values());checks.append('stock-downgrade-reformats-old-slot-and-loses-entry')
report={'firmware':'X1D-50c 1.25.0','cimSha256':reader.SHA256,'archiveMembers':count,'textFilesScanned':scanned,
        'localSourceHashes':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),base/'hbl-upgrade',base/'usr/bin/hbl-post-upgrade',base/'lib/systemd/system/media-data.mount',base/'lib/systemd/system/victory-gui.service')},
        'dataLinks':data_links,'startupLinks':startup_links,'textReferences':references,'modelChecks':checks,
        'modelScope':'Model applies verified 1.25.0 slot replacement behavior in both directions; unknown future installer behavior not verified.',
        'hardwareRequests':0,'firmwareExecuted':False,'crossUpdateAutoRestoreVerified':False}
out=HERE/'CodeTests/persistence-audit.json';out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'members':count,'textFilesScanned':scanned,'dataLinks':data_links,'referenceFiles':[r['path'] for r in references],'modelChecks':checks,'hardwareRequests':0}))
