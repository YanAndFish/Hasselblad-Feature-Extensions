"""仅在用户授权的 RAM 试用中调用；保留旧资源，不修改 /opt。"""
from pathlib import Path
import hashlib, io, sys, tarfile, time, json
P=Path(__file__).resolve().parent
sys.path[:0]=[str(P.parents[1]/'patch-distribution'),str(P.parents[1]/'tools')]
from usb_transport import Channel
from installer import upload
data=(P/'build/flash-ui.rcc').read_bytes()
digest=hashlib.sha256(data).hexdigest()
main=(P/'Main.qml').read_bytes()
main_digest=hashlib.sha256(main).hexdigest()
features=json.loads((P/'build/ui-features.json').read_text()) if (P/'build/ui-features.json').exists() else {}
entry=(P/'build/libhotspot-entry.so').read_bytes() if features.get('newReplayEnabled') else None
entry_digest=hashlib.sha256(entry).hexdigest() if entry else None
buffer=io.BytesIO()
with tarfile.open(fileobj=buffer,mode='w:gz') as archive:
    item=tarfile.TarInfo('flash-ui.rcc');item.size=len(data);item.mode=0o644
    archive.addfile(item,io.BytesIO(data))
    item=tarfile.TarInfo('Main.qml');item.size=len(main);item.mode=0o644
    archive.addfile(item,io.BytesIO(main))
    if entry:
        item=tarfile.TarInfo('libhotspot-entry.so');item.size=len(entry);item.mode=0o644
        archive.addfile(item,io.BytesIO(entry))
c=Channel();remote='/run/hbl-menu-trial-'+str(int(time.time()))
with c.session():
    result=c.command('cd /run/hbl-hotspot-ui && sha256sum -c manifest.sha256 >/dev/null && echo verified')
    if 'verified' not in result:raise RuntimeError('Existing RAM manifest did not verify')
upload(c,remote,buffer.getvalue(),'update.tgz')
with c.session():
    result=c.command('tar -xzf '+remote+'/update.tgz -C '+remote+' && sha256sum '+remote+'/flash-ui.rcc')
    if digest not in result:raise RuntimeError('Uploaded resource hash mismatch')
    result=c.command('sha256sum '+remote+'/Main.qml')
    if main_digest not in result:raise RuntimeError('Uploaded hotspot page hash mismatch')
    if entry:
        result=c.command('sha256sum '+remote+'/libhotspot-entry.so')
        if entry_digest not in result:raise RuntimeError('Uploaded JPEG provider library hash mismatch')
    c.command('cp /run/hbl-hotspot-ui/flash-ui.rcc '+remote+'/previous.rcc && cp /run/hbl-hotspot-ui/manifest.sha256 '+remote+'/previous.manifest')
    c.command('mv '+remote+'/flash-ui.rcc /run/hbl-hotspot-ui/flash-ui.rcc')
    c.command('cp /run/hbl-hotspot-ui/Main.qml '+remote+'/previous-Main.qml && mv '+remote+'/Main.qml /run/hbl-hotspot-ui/Main.qml')
    if entry:
        c.command('cp /run/hbl-hotspot-ui/libhotspot-entry.so '+remote+'/previous-entry.so && mv '+remote+'/libhotspot-entry.so /run/hbl-hotspot-ui/libhotspot-entry.so')
        c.command("sed -i '/  libhotspot-entry.so$/c\\"+entry_digest+"  libhotspot-entry.so' /run/hbl-hotspot-ui/manifest.sha256")
    c.command("sed -i '/  flash-ui.rcc$/c\\"+digest+"  flash-ui.rcc' /run/hbl-hotspot-ui/manifest.sha256")
    c.command("sed -i '/  Main.qml$/c\\"+main_digest+"  Main.qml' /run/hbl-hotspot-ui/manifest.sha256")
    result=c.command('cd /run/hbl-hotspot-ui && sha256sum -c manifest.sha256 >/dev/null && echo verified')
    if 'verified' not in result:raise RuntimeError('Updated RAM manifest did not verify; GUI not restarted')
    c.command('rm -f /run/hbl-hotspot-ui/embedded-used && systemctl restart victory-gui;true')
(P/'build/latest-ram-trial.txt').write_text(remote,encoding='ascii')
(P/'build/deployed-features.json').write_text(json.dumps(dict(features,entryDigest=entry_digest)),encoding='utf-8')
print('RAM resource verified and GUI restart requested; health check remains required')
