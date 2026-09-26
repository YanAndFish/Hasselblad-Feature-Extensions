"""已授权的后屏拖动试用；仅写 /run，重启恢复持久包。"""
from pathlib import Path
import sys, hashlib, io, tarfile, time
P=Path(__file__).resolve().parent
sys.path[:0]=[str(P.parents[1]/'patch-distribution'),str(P.parents[1]/'tools')]
from build_viewfinder_modes import read_rcc
from usb_transport import Channel
from installer import upload

baseline=P.parents[1]/'patch-distribution/build/confirmed-ui-20260922-151234/stage/files'
data=(P/'build/flash-ui.rcc').read_bytes()
old=read_rcc((baseline/'af-ui.rcc').read_bytes()); new=read_rcc(data)
changed={k for k in old.keys()|new.keys() if old.get(k)!=new.get(k)}
assert changed=={'/common/FocusDelivery.qml','/liveview/LiveViewImage.qml','/liveview/Touchpad.qml','/liveview/AFIndicator.qml'},changed
digest=hashlib.sha256(data).hexdigest()
remote='/run/hbl-focus-trial-'+str(int(time.time()))
launch='''#!/bin/sh
set -eu
p=/opt/hbl-af-only-v1
h=/run/hbl-hotspot-ui
"$p/authorization-guard" "$p" >/dev/null 2>&1
(cd "@TRIAL@" && sha256sum -c manifest.sha256 >/dev/null)
cp "@TRIAL@/flash-ui.rcc" "$h/flash-ui.rcc"
printf '%s\n' "$$" > /run/hbl-four-module/gui.pid
exec env HBL_FORMAL_ENABLE_PLUGIN=1 HBL_FORMAL_INSTALL_HOLD=1 HBL_PERSISTENT_SETTINGS=1 HBL_BOOT_LOAD_GUI=1 LD_PRELOAD="$h/libhotspot-entry.so:$p/libhbl-af-ui.so" /usr/bin/victory-gui -platform wayland
'''.replace('@TRIAL@',remote).encode()
files={'flash-ui.rcc':data,'launch.sh':launch}
files['manifest.sha256']=''.join(hashlib.sha256(b).hexdigest()+'  '+n+'\n' for n,b in files.items()).encode()
files['99-focus-drag-memory.conf']=('[Service]\nExecStart=\nExecStart=/bin/sh '+remote+'/launch.sh\n').encode()
buf=io.BytesIO()
with tarfile.open(fileobj=buf,mode='w:gz') as tar:
    for n,b in files.items():
        item=tarfile.TarInfo(n);item.size=len(b);item.mode=0o600
        tar.addfile(item,io.BytesIO(b))
c=Channel()
with c.session():
    answer=c.command('sha256sum /opt/hbl-af-only-v1/manifest.sha256;true')
    assert answer.split()[0]==hashlib.sha256((baseline/'manifest.sha256').read_bytes()).hexdigest()
upload(c,remote,buf.getvalue(),'trial.tgz')
with c.session():
    answer=c.command('cd '+remote+' && tar xzf trial.tgz && sha256sum -c manifest.sha256 >/dev/null && sh -n launch.sh && echo verified')
    assert 'verified' in answer,answer
    c.command('cp /run/hbl-hotspot-ui/flash-ui.rcc '+remote+'/previous.rcc')
    c.command('mkdir -p /run/systemd/system/victory-gui.service.d')
    c.command('cp '+remote+'/99-focus-drag-memory.conf /run/systemd/system/victory-gui.service.d/')
    c.command('systemctl daemon-reload && systemctl restart victory-gui;true')
(P/'build/latest-focus-trial.txt').write_text(remote,encoding='ascii')
print('RAM-only focus drag trial loaded; post-start check required')
