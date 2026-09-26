"""只读核对修复安装及旧载荷清理；不重启、不触发拍摄或对焦。"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import sys
import tarfile

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'x1d/patch-distribution'),str(ROOT/'x1d/tools')]
from usb_transport import Channel

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build')
    args=parser.parse_args()
    out=Path(args.build).resolve()
    assert out.parent==ROOT/'x1d/patch-distribution/build' and out.name.startswith(('installer-repair-','startup-repair-'))
    build_report=json.loads((out/'build-report.json').read_text(encoding='utf-8'))
    meta=json.loads((out/'native-client-package.json').read_text(encoding='utf-8'))
    result=json.loads((Path(meta['directory'])/'last-result.json').read_text(encoding='utf-8'))
    assert result['completed'] and result['action']=='install'
    with tarfile.open(out/'x1d-authorized-candidate.tgz','r:gz') as archive:
        manifest=archive.extractfile('files/manifest.sha256').read()
        launcher=archive.extractfile('files/camera-launch').read()
    c=Channel()
    with c.session():
        manifest_hash=c.command('sha256sum /opt/hbl-af-only-v1/manifest.sha256').split()[0]
        assert manifest_hash==hashlib.sha256(manifest).hexdigest()
        assert c.command('cd /opt/hbl-af-only-v1 && sha256sum -c manifest.sha256 >/dev/null 2>&1;echo $?')=='0'
        assert c.command('sha256sum /opt/hbl-patch-launch').split()[0]==hashlib.sha256(launcher).hexdigest()
        assert c.command('cat /opt/hbl-af-only-v1/enabled')=='af-only-v1'
        backup=c.command('if test -d /opt/hbl-authorized-backup;then ls -A /opt/hbl-authorized-backup;else echo absent;fi')
        assert backup in ('boot-id','absent'),backup
        root=c.command("awk '$2==\"/\"{v=$4}END{print v}' /proc/mounts")
        assert 'ro' in root.split(',')
        directories=c.command('ls -d /tmp/hbl-pkg-* 2>/dev/null;true').splitlines()
        assert 1<=len(directories)<=4
        for remote in directories:
            assert re.fullmatch(r'/tmp/hbl-pkg-\d{1,12}',remote)
            residue=c.command('r='+remote+';for n in files p.tgz b camera-transaction install.sh remove.sh;do if test -e "$r/$n" || test -L "$r/$n";then echo "$n";fi;done;echo checked')
            assert residue=='checked',residue
        services={name:c.command('systemctl is-active '+name+';true') for name in
                  ('victory-gui','msg2dbus-farm','configstore','jpeg-daemon','bodystate-daemon')}
        assert all(value=='active' for value in services.values())
    report=dict(passed=True,installerCompleted=True,payloadManifestVerified=True,enabled=True,
                previousPatchFilesAbsent=True,backupReceiptOnly=backup=='boot-id',
                uploadPayloadAbsent=True,rootReadOnly=True,services=services,
                featurePayloadUnchanged=build_report.get('cameraFeaturePayloadUnchanged',False),
                coldBootVerified=False,focusTested=False)
    (out/'installation-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__':main()
