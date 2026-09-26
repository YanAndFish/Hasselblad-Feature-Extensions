"""Qt 5.5 compatibility using mock objects in RAM; no camera imports or photos."""
from pathlib import Path
import sys,io,tarfile,time,hashlib
P=Path(__file__).resolve().parent
sys.path[:0]=[str(P.parents[1]/'tools'),str(P.parents[1]/'patch-distribution')]
from usb_transport import Channel
from installer import upload
folder=P/'build/replay-adapter-test'
files={p.name:p.read_bytes() for p in folder.glob('*.qml')}
files['CaptureIdentity.js']=(folder/'CaptureIdentity.js').read_bytes()
keys=P.parents[1]/'candidates/replay-page-resident/build/original-page/scripts/Keys.js'
files['Keys.js']=keys.read_bytes().replace(b'Qt.include(guiconfig.keyMapsName)',b'var CAMKEYS = {} // isolated mock; physical keys not exercised')
files['NativePhotoPlayback.qml']=files['NativePhotoPlayback.qml'].replace(keys.as_uri().encode(),b'Keys.js')
main=files['Main.qml'].decode().replace('Item {width:640;height:480','Item {width:640;height:480;property bool passed:false')
pos=main.rfind('}')
main=main[:pos]+'''Timer {interval:100;running:true;onTriggered:{
 page.residentEnter(true,false,-1)
 page.prepareCapture("")
 page.residentLeave()
 passed=!page.residentSessionActive
 console.log("Replay adapter isolated lifecycle",passed)
}}
'''+main[pos:]
files['Main.qml']=main.encode();files['probe']=(P/'build/pool-probe/pool-probe').read_bytes()
files['manifest']=(''.join(hashlib.sha256(b).hexdigest()+'  '+n+'\n' for n,b in files.items())).encode()
buffer=io.BytesIO()
with tarfile.open(fileobj=buffer,mode='w:gz') as archive:
 for name,data in files.items():
  item=tarfile.TarInfo(name);item.size=len(data);item.mode=0o755 if name=='probe' else 0o644
  archive.addfile(item,io.BytesIO(data))
remote='/run/hbl-replay-probe-'+str(int(time.time()));c=Channel()
upload(c,remote,buffer.getvalue(),'probe.tgz')
with c.session():
 result=c.command('cd '+remote+' && tar -xzf probe.tgz && sha256sum -c manifest >/dev/null && echo verified')
 if 'verified' not in result:raise RuntimeError('probe transfer verification failed')
 result=c.command('cd '+remote+' && QT_QPA_PLATFORM=offscreen ./probe Main.qml > probe.log 2>&1;echo probe-result:$?;true')
 print(result)
 log=c.command('tail -c 230 '+remote+'/probe.log');print(log)
 errors=c.command('grep -E "ReferenceError|TypeError|is not a type|Cannot assign" '+remote+'/probe.log | tail -c 230;true')
 if errors.strip():raise RuntimeError('Qt 5.5 adapter error: '+errors)
 if 'probe-result:0' not in result:raise RuntimeError('Qt 5.5 adapter probe failed')
print('PASS Qt5 adapter in RAM; camera modules and image provider absent')
