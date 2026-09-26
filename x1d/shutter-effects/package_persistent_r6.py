"""用已验收的原声和扬声器链路修正签发 R6；不连接相机。"""
from pathlib import Path
import io
import json
import tarfile
import wave
from package_persistent_r5 import ROOT, HERE, digest, read_members, checked_lists, lic, seal_resources

OUT=HERE/'build/candidate-r6'
BASE=HERE/'build/candidate/x1d-ciallo-persistent-candidate-r5.tgz'
BASE_REPORT=HERE/'build/candidate/result-r5.json'
AUDIO=HERE/'build/audio-candidates/ciallo-callio.wav'
APPROVED_AUDIO='3ec6498ba2b7679daf7d8cdd96afb0ed38eae09992a653a60ce180af8051cace'
TRANSACTION=ROOT/'x1d/patch-distribution/native-camera-transaction/build'

def main():
    archive=OUT/'x1d-ciallo-persistent-candidate-r6.tgz'
    target_report=OUT/'result-r6.json'
    if archive.exists() or target_report.exists():raise FileExistsError('Candidate is immutable')
    baseline=json.loads(BASE_REPORT.read_text(encoding='utf-8'))
    if digest(BASE.read_bytes())!=baseline['packageSha256']:raise ValueError('Installed baseline changed')
    members=read_members(BASE);old_manifest=checked_lists(members)
    report=json.loads((OUT/'result.json').read_text(encoding='utf-8'))
    if not report['nativeCompiled'] or not report['resourceSealed']:raise ValueError('Native build missing')
    if digest((OUT/'hotspot-libhotspot-entry.so').read_bytes())!=report['nativeSha256']:raise ValueError('Native build changed')
    # 本版没有修改任何 QML；继续使用已经装入的原资源封包。
    if report['outputRccSha256']!=baseline['outputRccSha256']:raise ValueError('Unexpected UI change')
    if digest(seal_resources.unseal(members['files/af-ui.rcc'][1],seal_resources.host_library(report['resourceSealId'])))!=report['outputRccSha256']:
        raise ValueError('Installed resource differs')
    audio=AUDIO.read_bytes()
    if digest(audio)!=APPROVED_AUDIO:raise ValueError('User-approved audio changed')
    with wave.open(io.BytesIO(audio),'rb') as w:
        if (w.getframerate(),w.getnchannels(),w.getsampwidth(),w.getnframes())!=(48000,2,2,59392):raise ValueError('Unexpected audio format')
    validation=json.loads((TRANSACTION/'core-validation.json').read_text())
    model=json.loads((TRANSACTION/'model-validation.json').read_text())
    if not validation['passed'] or not model['retainedPayloadRepeatAndNextBoot']:raise ValueError('Transaction checks missing')
    for name,expected in validation['sources'].items():
        if digest((ROOT/name).read_bytes())!=expected:raise ValueError('Transaction source changed: '+name)
    tx=(TRANSACTION/'camera-transaction').read_bytes()
    if digest(tx)!=validation['binarySha256']:raise ValueError('Transaction build changed')
    replacements={'files/hotspot-libhotspot-entry.so':(OUT/'hotspot-libhotspot-entry.so').read_bytes(),
                  'files/ciallo.wav':audio,'camera-transaction':tx}
    for name,data in replacements.items():members[name]=(members[name][0],data)
    names=sorted(old_manifest)
    manifest=''.join(digest(members['files/'+name][1])+'  '+name+'\n' for name in names).encode('ascii')
    key=lic.PRIVATE/'signing-key.pem';public=lic.openssl('pkey','-in',key,'-pubout','-outform','DER')
    previous=members['files/authorization.bin'][1];old=members['files/manifest.sha256'][1]
    authorized=[s for s in lic.parse_whitelist(lic.PRIVATE/'WHITELIST.md') if lic.verify(previous,public,s,old)]
    if not authorized or len(authorized)!=int.from_bytes(previous[40:44],'little'):raise ValueError('Authorization set changed')
    signature,_=lic.issue(key,authorized,manifest)
    if not all(lic.verify(signature,public,s,manifest) for s in authorized):raise ValueError('Signature verification failed')
    members['files/manifest.sha256']=(members['files/manifest.sha256'][0],manifest)
    members['files/authorization.bin']=(members['files/authorization.bin'][0],signature)
    checks=''.join(digest(members[n][1])+'  '+n+'\n' for n in sorted(members) if n!='package.sha256').encode('ascii')
    members['package.sha256']=(members['package.sha256'][0],checks)
    with tarfile.open(archive,'w:gz') as tar:
        for name,(template,data) in sorted(members.items()):
            info=tarfile.TarInfo(name);info.size=len(data);info.mode=template.mode;info.uid=info.gid=0
            tar.addfile(info,io.BytesIO(data))
    new=checked_lists(read_members(archive))
    changed=sorted(name for name in new if new[name]!=old_manifest[name])
    if changed!=['ciallo.wav','hotspot-libhotspot-entry.so']:raise ValueError('Unexpected payload difference')
    report.update(packagePath=str(archive),packageSha256=digest(archive.read_bytes()),baseline='ciallo-r5',
        installed=False,cameraValidated=False,offlineInstallReady=True,preservesCurrentLoader=True,
        changedPayloadFiles=changed,audioDurationSec=59392/48000,audioSha256=APPROVED_AUDIO,
        audioUserApproved=True,audioSource='https://github.com/soyobat/callio/blob/main/cialloMp3.mp3',
        audioPath=str(AUDIO.relative_to(ROOT)),transactionSha256=validation['binarySha256'],
        retainPreviousUntilNextBoot=True,signedDevices=len(authorized),
        pending=['新版实际拍摄音效及原厂声音共存','正常开机后的音频加载','实机更新收尾恢复只读'])
    target_report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Signed R6 ready; only audio, native sound controller, and install finalization changed')

if __name__=='__main__':main()
