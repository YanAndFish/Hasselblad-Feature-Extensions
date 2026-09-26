"""联合安装收尾的真实日志链与顺序替身；零设备请求。"""
from pathlib import Path
import hashlib
import io
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[1]
assert Path.cwd().resolve()==ROOT
sys.path.insert(0,str(HERE/'research'));sys.path.insert(0,str(ROOT/'x1d/af-experiment'))
import formal_joint_finish as candidate
from r3_install_journal import canonical
SEQUENCE=['joint-before-controls','joint-default-off','joint-enable-once','joint-enable-confirmation',
          'joint-before-hold-release','joint-release-hold-once','joint-final-health']

class Checks(unittest.TestCase):
    def exercise(self,failure=None,inflight=False):
        trace=[]
        with tempfile.TemporaryDirectory(prefix='joint-',dir=HERE/'CodeTests') as folder:
            root=Path(folder);afdir=root/'af';afdir.mkdir();out=root/'flash';out.mkdir()
            path=out/'installation-model.json'
            path.write_text(json.dumps({'packageSha256':'p','installed':True,'allHandlesClosed':True,'farmArmed':True,
                'installationGateReleased':False,'installationHoldRetained':True,'stage':'installed-default-off-locked-for-joint-af'}),encoding='utf-8')
            afpath=afdir/'native-observe-model.json';identity='a'*64
            anchor={'artifactSha256':identity,'schema':2,'format':'append-only-sha256-chain','eventsFile':afpath.with_suffix('.events.jsonl').name}
            afpath.write_text(canonical(anchor)+'\n',encoding='utf-8')
            record={'artifactSha256':identity,'phase':'installed_observation_until_restart','installed':True,'backend':'fixed_usb',
                    'mode':'native_af_observation','ownedCodeExecuted':True,'predictionActuation':False,'speedOverrides':False,
                    'nativeFinePreserved':True,'flashCodePreserved':True,'allHandlesClosed':True,
                    'inFlight':{'kind':'write'} if inflight else None,'cacheInFlight':None}
            record['preservedFlash']={'sourceInstallation':path.relative_to(ROOT).as_posix(),'installationSha256':hashlib.sha256(path.read_bytes()).hexdigest(),'packageSha256':'p'}
            event={'index':1,'previous':'0'*64,'change':record,'remove':[]}
            event['sha256']=hashlib.sha256(canonical(event).encode()).hexdigest()
            afpath.with_suffix('.events.jsonl').write_text(canonical(event)+'\n',encoding='utf-8')
            before=path.read_bytes()
            class Session:
                def __init__(self,name):self.output=out/name;self.entries=[]
                def command(self,label,command):
                    assert 0<len(command.encode('ascii'))<=231 and '\n' not in command
                    trace.append(label);self.entries.append({'submitted':1,'closed':True})
                    if label==failure:raise RuntimeError('injected unknown result')
                    if label=='joint-default-off':return {'output':'formal-worker-ready-default-off\nmaster=0 radio-held=0 radio-busy=0 same-process=1 pid=1\n'}
                    if label=='joint-enable-once':return {'output':'requested'}
                    if label=='joint-enable-confirmation':return {'output':'ready'}
                    return {'output':candidate.HEALTH[:-1]+'0' if label=='joint-final-health' else candidate.HEALTH}
            with patch.object(candidate,'OUT',out),patch.object(candidate,'AF_RECOVERY',afdir), \
                 patch.object(candidate.flash,'check_host',return_value={'packageSha256':'p'}), \
                 patch.object(candidate.flash.transfer,'Session',Session),patch.object(candidate.time,'sleep',return_value=None):
                if failure or inflight:
                    with self.assertRaises(RuntimeError):candidate.finish(path,afpath)
                else:
                    state=candidate.finish(path,afpath)
                    self.assertTrue(state['completed']);self.assertTrue(state['holdReleased'])
                    self.assertTrue(state['allHandlesClosed']);self.assertTrue(state['userControlsReleased'])
            self.assertEqual(path.read_bytes(),before)
            if failure:
                state=json.loads(next(out.glob('joint-completion-*.json')).read_text(encoding='utf-8'))
                self.assertFalse(state['completed']);self.assertFalse(state['automaticRetry'])
                if failure=='joint-enable-once':self.assertIsNone(state['userControlsReleased'])
                if failure=='joint-release-hold-once':self.assertIsNone(state['holdReleased'])
        return trace
    def test_complete_sequence_preserves_flash_source(self):self.assertEqual(self.exercise(),SEQUENCE)
    def test_any_failure_stops_without_repeating(self):
        for index,label in enumerate(SEQUENCE):
            with self.subTest(label=label):self.assertEqual(self.exercise(label),SEQUENCE[:index+1])
    def test_pending_af_operation_prevents_all_device_requests(self):self.assertEqual(self.exercise(inflight=True),[])

if __name__=='__main__':
    stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks))
    sources=[Path(__file__),HERE/'research/formal_joint_finish.py',ROOT/'x1d/af-experiment/r3_install_journal.py']
    out=HERE/'CodeTests/formal_joint_output';out.mkdir(exist_ok=True)
    report={'passed':result.wasSuccessful() and result.testsRun==3,'tests':result.testsRun,'failureStages':len(SEQUENCE),
            'hardwareRequests':0,'sourceHashes':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},'log':stream.getvalue()}
    (out/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(stream.getvalue())
    if not report['passed']:raise SystemExit(1)
