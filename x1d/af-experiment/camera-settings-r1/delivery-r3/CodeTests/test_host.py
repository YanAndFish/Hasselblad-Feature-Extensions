"""主机阶段编排、拒绝重复发送及恢复分流；所有 Linux 命令为替身。"""
import hashlib,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
import delivery_package as package
import session,recovery,runtime
from types import SimpleNamespace
from read_usb_link_once import UsbFailure

REPORT=package.read(HERE/'inputs/package.json')
BLOB=(HERE/'inputs/af-only.tar.gz').read_bytes()

class Linux:
    def __init__(self,directory,fault=None):
        self.directory=directory;self.failed=False;self.dispatched=set();self.calls=[];self.fault=fault
    def summary(self):
        return {'directory':self.directory.relative_to(package.ROOT).as_posix(),
            'requests':len(self.calls),'allHandlesClosed':True,'failed':self.failed,'dispatched':sorted(self.dispatched)}
    def command(self,label,command,timeout_ms=15000):
        assert not self.failed
        assert 0<len(command.encode('ascii'))<=231 and '\n' not in command and '\0' not in command
        self.calls.append((label,command))
        if label==self.fault:
            self.failed=True;raise UsbFailure('USB_READ',121)
        if label=='original-services':out='active\nactive'
        elif label=='helper-hash':
            chunks=[c.split('printf %s ',1)[1] for l,c in self.calls if l.startswith('decode.sh-')]
            import shlex
            body=''.join(shlex.split(c)[0] for c in chunks)
            out=hashlib.sha256(body.encode()).hexdigest()+'  decode.sh'
        elif label.startswith('decode-observe'):out='0\n'+REPORT['packageSha256']+'  archive'
        elif label=='extract-once':out='af-only-package-verified'
        elif label=='same-package':out=('0'*64 if self.fault=='different-package' else REPORT['files']['manifest.sha256'])+'  manifest.sha256'
        elif label.endswith('-observe'):
            phase=label[:-len('-observe')]
            out='pending' if self.fault=='pending' else '0\n'+session.MARKERS[phase]
        else:out='ready'
        return {'output':out,'closed':True,'exit_code':0}

class HostTests(unittest.TestCase):
    def setUp(self):
        folder=HERE/'build/sessions';folder.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=folder)
        self.directory=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def test_stage_exact_package_and_no_retry(self):
        for fault in (None,'chunk-3'):
            linux=Linux(self.directory,fault)
            with patch.object(package,'verify',return_value=(REPORT,BLOB)),patch.object(session.transfer,'Session',return_value=linux),patch.object(session.time,'sleep'):
                if fault:
                    with self.assertRaises(UsbFailure):session.stage()
                    self.assertEqual(linux.calls[-1][0],fault)
                    self.assertFalse(any(l=='extract-once' for l,_ in linux.calls))
                else:
                    path=session.stage();self.assertTrue(package.read(path)['staged'])
                    self.assertEqual(linux.calls[-1][0],'extract-once')
    def test_phase_success_duplicate_and_unknown(self):
        with patch.object(session.time,'sleep'):
            for name in session.MARKERS:
                linux=Linux(self.directory);session.phase(linux,name)
                with self.assertRaises(ValueError):session.phase(linux,name)
                self.assertEqual(sum(l.endswith('-once') for l,_ in linux.calls),1)
            linux=Linux(self.directory,'pending')
            with self.assertRaisesRegex(RuntimeError,'unknown'):session.phase(linux,'ui')
            self.assertEqual(sum(l.endswith('-once') for l,_ in linux.calls),1)
    def test_failed_preflight_does_not_create_ram_journal_or_marker(self):
        staged=self.directory/'stage.json'
        staged.write_text(json.dumps(dict(staged=True,failed=False,allHandlesClosed=True,packageSha256=REPORT['packageSha256'])))
        linux=Linux(self.directory)
        class StopLoader:
            def __init__(self,c,io):self.phase='preflight';self.io=io
            def preflight(self):
                raise UsbFailure('USB_READ',121)
        with patch.object(package,'verify',return_value=(REPORT,BLOB)),patch.object(session.transfer,'Session',return_value=linux),patch.object(session.time,'sleep'),patch.object(runtime,'AfOnlyLoader',StopLoader):
            with self.assertRaises(UsbFailure):session.install(staged)
        state=package.read(self.directory/'installation.json')
        self.assertEqual(state['win32'],121);self.assertEqual(state['afWrites'],0)
        self.assertNotIn('afRecovery',state)
        self.assertFalse(any(l=='ram-write-intent' for l,_ in linux.calls))
    def test_inspect_zero_write_failure_and_reject_unfinished_trace(self):
        p=self.directory/'installation.json'
        p.write_text(json.dumps(dict(stage='stopped-review-no-retry',afPhase='preflight',afWrites=0,
            afHandlesClosed=True,allHandlesClosed=True,packageSha256=REPORT['packageSha256'])))
        trace=runtime.Trace(self.directory/'af-trace.jsonl','a'*64)
        trace.append(dict(event='intent',kind='read',writes=0))
        self.assertEqual(recovery.inspect(p)['nextAction'],'stop-and-review')
        trace.append(dict(event='result',kind='read',writes=0,allHandlesClosed=True))
        trace.close()
        self.assertEqual(recovery.inspect(p)['nextAction'],'restore-preflight-linux')
        linux=Linux(self.directory)
        with patch.object(package,'verify',return_value=(REPORT,BLOB)),patch.object(recovery.transfer,'Session',return_value=linux),patch.object(session.time,'sleep'):
            self.assertTrue(recovery.restore_preflight(p)['completed'])
        self.assertTrue(any(l=='no-ram-start' for l,_ in linux.calls))

    def test_rollback_foreign_live_package_stops_before_af(self):
        c=SimpleNamespace(identity='a'*64,source_record=dict(transportPolicySha256='b'*64,
            deliveryValidationSha256='b'*64,journalAudit={'incompleteTail':False}))
        linux=Linux(self.directory,'different-package')
        with patch.object(package,'verify',return_value=(REPORT,BLOB)),patch.object(package,'sha',return_value='b'*64),patch.object(recovery.AfOnlyRollbackContract,'from_journal',return_value=c),patch.object(recovery.transfer,'Session',return_value=linux):
            with self.assertRaisesRegex(ValueError,'package changed'):
                recovery.rollback_held(self.directory/'source.json')
        result=package.read(self.directory/'recovery.json')
        self.assertEqual(result['afRequests'],0);self.assertEqual(result['afWrites'],0)
        self.assertEqual([l for l,_ in linux.calls],['same-package'])

if __name__=='__main__':unittest.main(verbosity=2)
