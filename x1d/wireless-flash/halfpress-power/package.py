"""从已安装音频修正版生成半按开关签名安装包；不连接设备。"""
from pathlib import Path
import sys,json,tarfile,shutil,importlib.util,argparse
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path[:0]=[str(ROOT/'x1d/shutter-effects'),str(ROOT/'x1d/patch-distribution')]
from package_persistent_r5 import digest,read_members,checked_lists,lic,seal_resources
# 旧打包器使用裸 import build；明确绑定发行模块，避免与本功能 build.py 冲突。
spec=importlib.util.spec_from_file_location('release_build',ROOT/'x1d/patch-distribution/build.py')
release_build=importlib.util.module_from_spec(spec);spec.loader.exec_module(release_build)
sys.modules['build']=release_build
import package_native_windows

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--revision',choices=['r1','r2','r3','r4'],default='r1');args=parser.parse_args()
    out=HERE/('build/persistent-'+args.revision)
    if out.exists():raise FileExistsError('Immutable release already exists')
    base=ROOT/'x1d/shutter-effects/build/candidate-r6'
    base_report=json.loads((base/'result-r6.json').read_text(encoding='utf8'))
    archive=base/'x1d-ciallo-persistent-candidate-r6.tgz'
    assert digest(archive.read_bytes())==base_report['packageSha256']
    if args.revision in ('r3','r4'):
        previous_release=HERE/('build/persistent-r2' if args.revision=='r3' else 'build/persistent-r3')
        previous_report=json.loads((previous_release/'build-report.json').read_text(encoding='utf8'))
        archive=previous_release/'x1d-authorized-candidate.tgz'
        assert digest(archive.read_bytes())==previous_report['archiveSha256']
    members=read_members(archive);old_manifest=checked_lists(members)
    build=json.loads((HERE/'build/build.json').read_text(encoding='utf8'))
    names={'hotspot-libhotspot-entry.so':('gui/hotspot-libhotspot-entry.so','guiSha256'),
           'af-ui.rcc':('gui/af-ui.rcc','rccSha256'),
           'libhbl-af-loader.so':('native/libhbl-af-loader.so','loaderSha256')}
    if args.revision=='r3':
        assert digest(members['files/libhbl-af-loader.so'][1])==build['loaderSha256']
        gui_report=json.loads((HERE/'build/gui/result.json').read_text(encoding='utf8'))
        host=seal_resources.host_library(gui_report['resourceSealId'])
        assert seal_resources.unseal(members['files/af-ui.rcc'][1],host)==(HERE/'build/gui/flash-ui.rcc').read_bytes()
        names={'hotspot-libhotspot-entry.so':names['hotspot-libhotspot-entry.so']}
    if args.revision=='r4':
        assert digest(members['files/libhbl-af-loader.so'][1])==build['loaderSha256']
        assert digest(members['files/hotspot-libhotspot-entry.so'][1])==build['guiSha256']
        names={'af-ui.rcc':names['af-ui.rcc']}
    for name,(path,field) in names.items():
        data=(HERE/'build'/path).read_bytes();assert digest(data)==build[field]
        members['files/'+name]=(members['files/'+name][0],data)
    manifest=''.join(digest(members['files/'+n][1])+'  '+n+'\n' for n in sorted(old_manifest)).encode('ascii')
    key=lic.PRIVATE/'signing-key.pem';public=lic.openssl('pkey','-in',key,'-pubout','-outform','DER')
    previous=members['files/authorization.bin'][1];old=members['files/manifest.sha256'][1]
    authorized=[s for s in lic.parse_whitelist(lic.PRIVATE/'WHITELIST.md') if lic.verify(previous,public,s,old)]
    assert authorized and len(authorized)==int.from_bytes(previous[40:44],'little')
    signature,_=lic.issue(key,authorized,manifest)
    assert all(lic.verify(signature,public,s,manifest) for s in authorized)
    members['files/manifest.sha256']=(members['files/manifest.sha256'][0],manifest)
    members['files/authorization.bin']=(members['files/authorization.bin'][0],signature)
    checks=''.join(digest(members[n][1])+'  '+n+'\n' for n in sorted(members) if n!='package.sha256').encode('ascii')
    members['package.sha256']=(members['package.sha256'][0],checks)
    assert digest(members['files/ciallo.wav'][1])==base_report['audioSha256']
    assert digest(members['camera-transaction'][1])==base_report['transactionSha256']
    out.mkdir();target=out/'x1d-authorized-candidate.tgz'
    with tarfile.open(target,'w:gz') as tar:
        for name,(template,data) in sorted(members.items()):
            info=tarfile.TarInfo(name);info.size=len(data);info.mode=template.mode;info.uid=info.gid=0
            tar.addfile(info,__import__('io').BytesIO(data))
    current=checked_lists(read_members(target))
    changed=sorted(k for k in current if current[k]!=old_manifest[k]);assert changed==sorted(names)
    report=json.loads((ROOT/'x1d/shutter-effects/build/native-client-r3/build-report.json').read_text(encoding='utf8'))
    report.update(archiveSha256=digest(target.read_bytes()),installed=False,cameraValidated=False,coldBootValidated=False,
        previousPayloadRemovedAfterCommit=False,repairChanges=['旧映射备份保留至下次启动后的更新清理'],
        changedPayloadFiles=changed,halfPressPowerDefault=False,halfPressPowerModes=['mechanical','electronic'])
    report['features']['halfPressPowerSetting']=True
    if args.revision in ('r3','r4'):
        report['features']['audioVolumeAndRouteRepair']=True
        report['audioRepair']='读取原厂音量，先音量后扬声器；路由值不作为占用锁；结束恢复现场，原厂声音优先。'
    if args.revision=='r4':
        report['features']['electronicFlashConditionsHint']=True
        report['electronicFlashHint']='仅提示：电子快门引闪开启，非 M 档或快门不在 1/4–1/2 秒时显示；不改变曝光或无线策略。'
    report['knownIssues']=['半按功率及设置持久化待实机验收','快速半按接全按不保证参数发送完成；不延迟原厂曝光','不把发送响应解释为灯具接收确认','原声音频拍摄播放待用户验收']
    (out/'build-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    release=package_native_windows.package(out)
    print('Halfpress signed release ready:',release)
if __name__=='__main__':main()
