"""安装编排的阶段顺序与失败停止检查。设备、FARM 与时间等待均用替身。"""
from pathlib import Path
import contextlib
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE/'research'))
import formal_install_session as candidate


SEQUENCE=['formal-fresh-preflight','transfer','linux-ui-start','linux-ui-result','formal-ui-held','prepare',
          'formal-before-observer','linux-observer-start','linux-observer-result','formal-before-capture',
          'probe','formal-before-hooks','install-disarmed','formal-before-arm','arm','verify-armed',
          'formal-final-health','formal-final-status','formal-release-install-gate','formal-enable-confirmation',
          'formal-before-hold-release','formal-release-hold']
HEALTH_LABELS={x for x in SEQUENCE if x.startswith('formal-before-')}|{'formal-ui-held','formal-final-health'}

class Checks(unittest.TestCase):
    def exercise(self, failure=None, retain_hold=False, staged=False):
        trace, records = [], []
        def operation(name):
            trace.append(name)
            if name == failure:
                raise RuntimeError('synthetic failure: ' + name)
        class Session:
            failed = False
            def __init__(self, name):
                self.output = HERE/'CodeTests'/name
                self.entries = []
            def command(self, label, command, timeout_ms=30000):
                assert 0 < len(command.encode('ascii')) <= 231
                self.entries.append({'submitted':1,'closed':True})
                operation(label)
                if label=='formal-staged-preflight':
                    return {'output':'system=4 suc=0 farm=0 pwr=0 ui-power=1 hold=0'}
                if label in HEALTH_LABELS:
                    return {'output':'system=2 suc=0 farm=0 pwr=0 ui-power=0 hold=1'}
                if label == 'formal-release-install-gate':
                    return {'output':'gate-requested'}
                if label == 'formal-enable-confirmation':
                    return {'output':'ready\nactive\nactive'}
                return {'output': 'formal-ui-loaded-default-off\nformal-worker-ready-default-off\nmaster=0 radio-held=0 radio-busy=0 same-process=1 pid=123\nstage=ready meta=1 observe=1\nactive\nactive'}
        class Loader:
            def __init__(self):
                self.io = types.SimpleNamespace(requests=0, writes=0, closed=True)
            def prepare(self, farm, path):
                operation('prepare')
            def probe(self):
                operation('probe')
            def install_disarmed(self):
                operation('install-disarmed')
            def arm(self):
                operation('arm')
            def verify(self, value):
                assert value == 1
                operation('verify-armed')
        package = {'packageSha256':'p','firmwareSha256':'f','files':{}}
        binary = types.SimpleNamespace(FarmApplication=lambda: types.SimpleNamespace(data=b'fixed-farm-model'))
        with tempfile.TemporaryDirectory(prefix='formal-session-',dir=HERE/'CodeTests') as directory:
            staged_path=Path(directory)/'staged-model.json' if staged else None
            if staged:staged_path.write_text(json.dumps({'staged':True,'allHandlesClosed':True,'packageSha256':'p'}),encoding='utf-8')
            with patch.object(candidate,'OUT',Path(directory)), patch.object(candidate,'check_host',return_value=package), \
                 patch.object(candidate.transfer,'Session',Session), patch.object(candidate.capture,'Loader',Loader), \
                 patch.object(candidate.transfer,'stage',side_effect=lambda s: operation('transfer')), \
                 patch.object(candidate.transfer,'start_linux',side_effect=lambda s,p: operation('linux-'+p+'-start')), \
                 patch.object(candidate.transfer,'linux_result',side_effect=lambda s,p: (operation('linux-'+p+'-result') or ('0\nformal-ui-hold-ready-default-off' if p=='ui' else '0\nformal-linux-ready-default-off'))), \
                 patch.object(candidate.time,'sleep',return_value=None), patch.dict(sys.modules,{'farm_diagnostic_binary':binary}), \
                 contextlib.redirect_stdout(io.StringIO()):
                if failure:
                    with self.assertRaises(RuntimeError):
                        candidate.install(True)
                else:
                    result = candidate.install(True,retain_hold=retain_hold,staged_record=staged_path)
                    self.assertTrue(result['installed'])
                    self.assertTrue(result['targetSelfChecksRun'])
                    self.assertEqual(result['cameraShotsTriggered'],0)
                    self.assertEqual(result['agentFlashTrials'],0)
                    self.assertFalse(result['physicalTimingVerified'])
                paths = list(Path(directory).glob('installation-*.json'))
                self.assertEqual(len(paths),1)
                record = json.loads(paths[0].read_text(encoding='utf-8'))
                if retain_hold and not failure:
                    self.assertTrue(record['installationHoldRetained'])
                    self.assertFalse(record['installationGateReleased'])
                if failure:
                    self.assertFalse(record['installed'])
                    self.assertFalse(record['automaticRetryPerformed'])
                    self.assertEqual(record['stage'],'stopped-review-current-record-before-recovery')
                    if failure == 'verify-armed':
                        self.assertIs(record['farmArmed'],True)
                        self.assertEqual(record['lastCompletedStage'],'farm-arm-written-awaiting-verification')
                    if failure == 'arm':
                        self.assertIsNone(record['farmArmed'])
                    if failure == 'formal-enable-confirmation':
                        self.assertIsNone(record['installationGateReleased'])
        return trace

    def test_success_order(self):
        self.assertEqual(self.exercise(), SEQUENCE)

    def test_every_stage_failure_stops_following_stages(self):
        for index, name in enumerate(SEQUENCE):
            with self.subTest(name=name):
                self.assertEqual(self.exercise(name), SEQUENCE[:index+1])

    def test_joint_af_keeps_hold_and_controls_locked(self):
        self.assertEqual(self.exercise(retain_hold=True), SEQUENCE[:SEQUENCE.index('formal-final-status')+1])

    def test_staged_standby_restarts_gui_before_any_farm(self):
        self.assertEqual(self.exercise(staged=True), ['formal-staged-preflight']+SEQUENCE[2:])

    def test_no_standby_confirmation_has_no_host_or_device_operation(self):
        with patch.object(candidate,'check_host') as host:
            with self.assertRaises(RuntimeError):
                candidate.install()
            host.assert_not_called()

    def test_restore_stops_radio_before_unhook_and_keeps_observer_until_after(self):
        trace = []
        class Session:
            def __init__(self,name):
                self.output=HERE/'CodeTests'/name
            def command(self,label,command,timeout_ms):
                trace.append(label)
                return {'output': 'formal-linux-stopped-observer-retained' if label=='formal-stop-before-unhook'
                        else 'original-linux-services-and-radio-restored'}
        class Loader:
            def __init__(self):
                self.io=types.SimpleNamespace(read=lambda a: (trace.append('read-enable') or 1))
            def verify(self,armed):
                self.asserted=armed
                assert armed==1
                trace.append('verify-current-hooks')
            def unhook(self):
                trace.append('unhook')
        with tempfile.TemporaryDirectory(prefix='formal-restore-',dir=HERE/'CodeTests') as directory:
            with tempfile.NamedTemporaryFile(prefix='formal-capture-recovery-model-',suffix='.json',dir=HERE/'build',delete=False) as output:
                recovery=Path(output.name)
            try:
                saved={'installed':True,'payload_sha256':candidate.capture.PAYLOAD_SHA,
                       'payload_base':candidate.capture.PAYLOAD_START,'payload_bytes':candidate.capture.PAYLOAD_BYTES,
                       'record_address':candidate.capture.RECORD,'original_hooks':candidate.capture.ORIGINAL_HOOKS,
                       'new_hooks':candidate.capture.NEW_HOOKS}
                recovery.write_text(json.dumps(saved),encoding='utf-8')
                record=Path(directory)/'installation-model.json'
                original={'packageSha256':'p','recoveryRecord':str(recovery.relative_to(HERE)),'installed':True}
                record.write_text(json.dumps(original),encoding='utf-8')
                with patch.object(candidate,'OUT',Path(directory)), patch.object(candidate,'check_host',return_value={'packageSha256':'p'}), \
                     patch.object(candidate.transfer,'Session',Session), patch.object(candidate.capture,'Loader',Loader):
                    self.assertFalse(candidate.restore(record,True)['installed'])
                self.assertEqual(trace,['formal-stop-before-unhook','read-enable','verify-current-hooks','unhook','formal-restore-original-linux'])
            finally:
                recovery.unlink()


if __name__ == '__main__':
    output = HERE/'CodeTests/formal_session_output'
    output.mkdir(exist_ok=True)
    log = io.StringIO()
    result = unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks))
    names = ('research/formal_install_session.py','research/formal_transfer.py','CodeTests/formal_install_session.test.py')
    report = {'passed':result.wasSuccessful() and result.testsRun==6, 'tests':result.testsRun,
              'failureStages':len(SEQUENCE),'log':log.getvalue(),'hardwareRequests':0,
              'sourceHashes':{name:hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in names}}
    (output/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(log.getvalue())
    if not report['passed']:
        raise SystemExit(1)
