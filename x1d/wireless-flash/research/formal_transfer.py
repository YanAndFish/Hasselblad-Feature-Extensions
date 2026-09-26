"""正式完整包的有限顺序传输。导入或直接运行仅离线核验，不连接相机。"""
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
import time
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import package_formal_flash as candidate
from mechanical_hw_ready_transfer import DECODER
from mechanical_sync_session import Session as OriginalSession

HERE, OUT, REMOTE = candidate.HERE, candidate.OUT, '/tmp/hbl-wireless-flash'


class Session(OriginalSession):
    """沿用已核实 USB 帧；证据只写新的正式包目录。"""
    def __init__(self, evidence_name):
        super().__init__(evidence_name)
        self.output = OUT / evidence_name
        if not OUT.is_dir() or self.output.exists():
            raise RuntimeError('Formal session output missing or already exists')


def stage(session, pause=time.sleep):
    if session.failed:
        raise RuntimeError('Session stopped')
    report, data = candidate.verify_package()
    result = session.command('formal-services', 'systemctl is-active victory-gui msg2dbus-farm')
    if result['output'].split() != ['active', 'active']:
        raise RuntimeError('Camera services not ready')
    session.command('formal-create-stage', 'test ! -e ' + REMOTE + ' && test ! -L ' + REMOTE + ' && mkdir -m 700 ' + REMOTE)
    for index, start in enumerate(range(0, len(DECODER), 90)):
        session.command('formal-decoder-' + str(index), 'printf %s ' + shlex.quote(DECODER[start:start+90]) +
                        (' >' if index == 0 else ' >>') + REMOTE + '/d.awk')
    encoded = base64.b64encode(data).decode('ascii')
    parts = [encoded[start:start+176] for start in range(0, len(encoded), 176)]
    for index, part in enumerate(parts):
        session.command('formal-package-' + str(index), 'printf %s ' + shlex.quote(part) +
                        (' >' if index == 0 else ' >>') + REMOTE + '/p64')
        if (index+1) % 100 == 0:
            print('formal-package-chunks', index+1, '/', len(parts), flush=True)
    session.command('formal-decode-once', 'd=' + REMOTE + ';(printf \'%b\' "$(awk -f "$d/d.awk" "$d/p64")" >"$d/session.tar.gz";sha256sum "$d/session.tar.gz" >"$d/decode.sha") </dev/null >/dev/null 2>&1 &')
    for attempt in range(120):
        pause(1)
        result = session.command('formal-archive-check-' + str(attempt), 'd=' + REMOTE + ';if test -f "$d/decode.sha";then cat "$d/decode.sha";else printf pending;fi')
        if result['output'] != 'pending':
            break
    else:
        raise RuntimeError('Decode pending; never dispatch decode again')
    if result['output'].split()[0] != report['packageSha256']:
        raise RuntimeError('Archive mismatch; extraction refused')
    result = session.command('formal-extract-verified', 'cd ' + REMOTE + ' && tar xzf session.tar.gz && sha256sum -c manifest.sha256 >/dev/null && sh -n formal-install.sh && printf formal-package-verified')
    if result['output'] != 'formal-package-verified':
        raise RuntimeError('Extracted package failed verification')
    return {'packageVerified': True, 'chunks': len(parts), 'bytes': len(data), 'packageSha256': report['packageSha256']}


def start_linux(session, phase):
    """只派发一次安装脚本；后续通过固定结果文件观察，不重试执行。"""
    if phase not in ('ui','observer'):
        raise RuntimeError('Explicit UI-first installation phase required')
    option = '--stage-ui' if phase == 'ui' else '--start-observer'
    session.command('formal-'+phase+'-dispatch', 'd=' + REMOTE + ';p='+phase+';test ! -e "$d/$p.sent" && touch "$d/$p.sent" && (sh "$d/formal-install.sh" '+option+' >"$d/$p.log" 2>&1;echo $? >"$d/$p.exit") </dev/null >/dev/null 2>&1 &')


def linux_result(session, phase):
    """单次有界查询；调用者维持进度沟通，不隐含长等待或重发。"""
    if phase not in ('ui','observer'):
        raise RuntimeError('Explicit installation phase required')
    result = session.command('formal-'+phase+'-result', 'd=' + REMOTE + ';p='+phase+';if test -f "$d/$p.exit";then cat "$d/$p.exit";cat "$d/formal-install.status" 2>/dev/null;else printf pending;fi')
    return result['output'].strip()


def validate():
    report, _, = candidate.verify_package()
    class ModelSession:
        failed = False
        def __init__(self, bad_hash=False, fail_chunk=False):
            self.commands, self.bad_hash, self.fail_chunk = [], bad_hash, fail_chunk
        def command(self, label, command, timeout_ms=30000):
            assert not self.failed
            assert 0 < len(command.encode('ascii')) <= 231 and '\n' not in command
            self.commands.append((label, command))
            if self.fail_chunk and label == 'formal-package-3':
                self.failed = True
                raise RuntimeError('synthetic ambiguous transfer')
            if label == 'formal-services':
                output = 'active\nactive'
            elif label.startswith('formal-archive-check-'):
                output = ('0'*64 if self.bad_hash else report['packageSha256']) + ' session.tar.gz'
            elif label == 'formal-extract-verified':
                output = 'formal-package-verified'
            else:
                output = ''
            return {'output': output}
    normal = ModelSession()
    result = stage(normal, lambda _: None)
    for phase in ('ui','observer'):
        start_linux(normal,phase)
        linux_result(normal,phase)
    for refused in (ModelSession(bad_hash=True), ModelSession(fail_chunk=True)):
        try:
            stage(refused, lambda _: None)
        except RuntimeError:
            pass
        else:
            raise AssertionError('Failed transfer was accepted')
        assert not any(label == 'formal-extract-verified' for label, _ in refused.commands)
    assert sum(label == 'formal-decode-once' for label, _ in normal.commands) == 1
    assert sum(label == 'formal-ui-dispatch' for label, _ in normal.commands) == 1
    assert sum(label == 'formal-observer-dispatch' for label, _ in normal.commands) == 1
    proof = {'passed': True, 'hardwareRequests': 0, 'commands': len(normal.commands),
             'maxCommandBytes': max(len(cmd.encode('ascii')) for _, cmd in normal.commands),
             'decodeDispatches': 1, 'installDispatches': 2,
             'wrongHashStopsBeforeExtraction': True, 'ambiguousChunkStopsWithoutRetry': True,
             'packageSha256': result['packageSha256'],
             'sourceHashes': {str(p.relative_to(HERE)).replace('\\','/'): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in (Path(__file__), HERE/'research/mechanical_sync_session.py',
                                        HERE/'research/mechanical_hw_ready_transfer.py', HERE/'research/package_formal_flash.py')}}
    (OUT/'transfer-validation.json').write_text(json.dumps(proof, indent=2)+'\n', encoding='utf-8')
    return proof


if __name__ == '__main__':
    print(json.dumps(validate()))
