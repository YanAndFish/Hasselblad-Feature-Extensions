"""签发 X1D 1.25.0 持久候选包；仅离线构建，不执行安装脚本。"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import wave

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
SOURCE=ROOT/'x1d/patch-distribution/build/confirmed-ui-20260922-203447/stage'
UI=ROOT/'x1d/wifi-region/temporary-ui'
OUT=HERE/'build/candidate'
sys.path.insert(0,str(ROOT/'x1d/patch-distribution'))
sys.path.insert(0,str(UI))
import licensing as license_api
import seal_resources

def digest(data):return hashlib.sha256(data).hexdigest()

def checked_manifest(folder,manifest):
    listed={}
    for line in manifest.decode('ascii').splitlines():
        expected,name=line.split('  ',1)
        if Path(name).name!=name or name in listed or not (folder/name).is_file():
            raise ValueError('Invalid package manifest path')
        if digest((folder/name).read_bytes())!=expected:raise ValueError('Old payload mismatch: '+name)
        listed[name]=expected
    names={p.name for p in folder.iterdir() if p.is_file()}
    if names-set(listed)!={'manifest.sha256','authorization.bin'}:
        raise ValueError('Unexpected payload file set')

def main():
    report=json.loads((OUT/'result.json').read_text(encoding='utf-8'))
    if not report.get('nativeCompiled') or not report.get('resourceSealed'):
        raise ValueError('Run prepare.py and build_native.py first')
    audio=HERE/'audio/ciallo-yaoyao.wav'
    with wave.open(str(audio),'rb') as sound:
        duration=sound.getnframes()/sound.getframerate()
        if not (1.0<duration<2.0 and sound.getsampwidth()==2):raise ValueError('Long audio is missing')
    old_manifest=(SOURCE/'files/manifest.sha256').read_bytes()
    checked_manifest(SOURCE/'files',old_manifest)
    key=license_api.PRIVATE/'signing-key.pem'
    whitelist=license_api.PRIVATE/'WHITELIST.md'
    if not key.is_file() or not whitelist.is_file():raise FileNotFoundError('Existing X1D signing materials')
    serials=license_api.parse_whitelist(whitelist)
    public=license_api.openssl('pkey','-in',key,'-pubout','-outform','DER')
    old_signature=(SOURCE/'files/authorization.bin').read_bytes()
    old_count=int.from_bytes(old_signature[40:44],'little')
    authorized=[serial for serial in serials if license_api.verify(old_signature,public,serial,old_manifest)]
    if not serials or old_count<1 or len(authorized)!=old_count:
        raise ValueError('Existing signed package provenance failed')
    seal_id=report['resourceSealId']
    host=seal_resources.host_library(seal_id)
    if digest(seal_resources.unseal((SOURCE/'files/af-ui.rcc').read_bytes(),host))!=report['sourceRccSha256']:
        raise ValueError('RCC source does not match signed X1D package')
    out=OUT/'persistent-stage-r4'
    if out.exists():raise FileExistsError('Keep prior candidate immutable: '+str(out))
    files=out/'files'
    shutil.copytree(SOURCE, out)
    files=out/'files'
    (files/'af-ui.rcc').write_bytes((OUT/'af-ui.rcc').read_bytes())
    (files/'hotspot-libhotspot-entry.so').write_bytes((OUT/'hotspot-libhotspot-entry.so').read_bytes())
    (files/'ciallo.wav').write_bytes(audio.read_bytes())
    (files/'manifest.sha256').unlink()
    (files/'authorization.bin').unlink()
    manifest=''.join(digest(p.read_bytes())+'  '+p.name+'\n' for p in sorted(files.iterdir()) if p.is_file()).encode()
    (files/'manifest.sha256').write_bytes(manifest)
    # 保留来源包的设备授权集合；不因本地白名单后续增加而扩大新包范围。
    signature,_=license_api.issue(key,authorized,manifest)
    (files/'authorization.bin').write_bytes(signature)
    if not all(license_api.verify(signature,public,serial,manifest) for serial in authorized):
        raise ValueError('Candidate authorization failed')
    checked_manifest(files,manifest)
    shell='C:/Program Files/Git/bin/sh.exe'
    if (out/'install.sh').is_file() and (out/'remove.sh').is_file():
        for name in ['install.sh','remove.sh']:
            subprocess.run([shell,'-n',str(out/name).replace('\\','/')],check=True)
    elif not ((out/'camera-transaction').is_file() and
              (out/'transaction-profile').read_bytes()==b'native-v1\n'):
        raise ValueError('Unrecognized installer profile')
    (out/'package.sha256').write_text(''.join(digest(p.read_bytes())+'  '+p.relative_to(out).as_posix()+'\n'
        for p in sorted(out.rglob('*')) if p.is_file() and p.name!='package.sha256'),encoding='ascii',newline='\n')
    archive=OUT/'x1d-ciallo-persistent-candidate-r4.tgz'
    with tarfile.open(archive,'w:gz') as tar:
        for p in sorted(out.rglob('*')):
            if not p.is_file():continue
            info=tar.gettarinfo(str(p),p.relative_to(out).as_posix())
            info.uid=info.gid=0;info.uname=info.gname=''
            executable=p.name.endswith('.sh') or p.name in [
                'authorization-guard','configstore-full','jpeg-daemon-full','camera-launch','camera-bootstrap']
            info.mode=0o700 if executable else 0o600
            with p.open('rb') as stream:tar.addfile(info,stream)
    report.update({'persistentPackageBuilt':True,'signedDevices':len(authorized),
        'audioDurationSec':round(duration,6),'audioSha256':digest(audio.read_bytes()),
        'packageSha256':digest(archive.read_bytes()),'packagePath':str(archive),
        'installed':False,'cameraValidated':False,'installable':True,
        'offlineInstallReady':True,
        'pending':['实机曝光/黑屏时序','播放器与原厂提示音共存','LCD/EVF层级和冷启动验收']})
    (OUT/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Signed X1D persistent package built: '+str(archive))

if __name__=='__main__':main()
