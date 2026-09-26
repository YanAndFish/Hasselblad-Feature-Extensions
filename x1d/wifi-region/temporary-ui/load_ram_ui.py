"""Restore the authorized temporary GUI after reboot; never edits /opt."""
from pathlib import Path
import hashlib, io, tarfile, sys, time
P=Path(__file__).resolve().parent
sys.path[:0]=[str(P.parents[1]/'patch-distribution'),str(P.parents[1]/'tools')]
from usb_transport import Channel
from installer import upload

files={n:(P/'build'/n).read_bytes() for n in ['libhotspot-entry.so','Entry.qml','Main.qml','network.sh','dhcp.sh','radio-mode.sh','flash-ui.rcc']}
files['embedded-launch.sh']=(P/'embedded-launch.sh').read_bytes().replace(b'\r\n',b'\n')
files['health']=(P.parents[1]/'candidates/ui-resident/revisions/full-pages-r2/build/session/native/ui-health').read_bytes()
files['manifest.sha256']=''.join(hashlib.sha256(b).hexdigest()+'  '+n+'\n' for n,b in files.items()).encode()
files['99-hotspot-memory.conf']=b'[Service]\nExecStart=\nExecStart=/bin/sh /run/hbl-hotspot-ui/embedded-launch.sh\n'
data=io.BytesIO()
with tarfile.open(fileobj=data,mode='w:gz') as t:
    for n,b in files.items():
        i=tarfile.TarInfo(n);i.size=len(b);i.mode=0o755 if n.endswith('.sh') or n=='health' else 0o644
        t.addfile(i,io.BytesIO(b))
c=Channel();remote='/run/hbl-ui-restore-'+str(int(time.time()))
with c.session():
    r=c.command('test ! -e /run/hbl-hotspot-ui && /opt/hbl-af-only-v1/authorization-guard /opt/hbl-af-only-v1 >/dev/null 2>&1 && echo ready')
    if 'ready' not in r:raise RuntimeError('RAM directory exists or authorization guard failed')
upload(c,remote,data.getvalue(),'ui.tgz')
with c.session():
    c.command('tar -xzf '+remote+'/ui.tgz -C '+remote)
    r=c.command('cd '+remote+' && sha256sum -c manifest.sha256 >/dev/null && ./health --require-ready && echo verified')
    if 'verified' not in r:raise RuntimeError('Payload or camera health not verified: '+r)
    c.command('mkdir /run/hbl-hotspot-ui && cp '+remote+'/* /run/hbl-hotspot-ui/')
    c.command('mkdir -p /run/systemd/system/victory-gui.service.d')
    c.command('cp /run/hbl-hotspot-ui/99-hotspot-memory.conf /run/systemd/system/victory-gui.service.d/')
    c.command('systemctl daemon-reload && systemctl restart victory-gui;true')
print('RAM UI installed; post-load health remains to check')
