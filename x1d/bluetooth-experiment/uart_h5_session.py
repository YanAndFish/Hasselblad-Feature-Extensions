"""用户明确授权的 UART5 假设验证：默认仅检查传输计划，显式入口至多执行一次。"""
from pathlib import Path
from datetime import datetime, timezone
import importlib.util
import json
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('bt_memory_delivery', HERE/'memory_self_test.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)
bridge.REMOTE = '/tmp/x1d-bt-h5-r1'


def prepare():
    binary, commands, expected = bridge.prepare(HERE/'build/uart-h5-r1/validation.json')
    expected['memory-self-test'] = 'uart_h5_self_test=passed;hardware_access=none'
    index = next(i for i, (label, _) in enumerate(commands) if label == 'cleanup')
    command = bridge.REMOTE+'/probe --probe-uart5-h5-sync-once'
    commands.insert(index, ('uart-h5-sync-once', command))
    assert len(command) <= 231
    assert sum(label == 'uart-h5-sync-once' for label, _ in commands) == 1
    return binary, commands, expected


def run(binary, commands, expected):
    if bridge.digest(bridge.TRANSPORT.read_bytes()) != bridge.TRANSPORT_SHA:
        raise ValueError('transport changed')
    spec = importlib.util.spec_from_file_location('uart_usb', bridge.TRANSPORT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    folder = HERE/'build/uart-h5-r1/session'
    # 记录存在即拒绝整轮重跑，包括未知结果和超时。
    folder.mkdir(exist_ok=False)
    name = 'uart-once-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json'
    session = mod.Session(name)
    session.output = folder/'usb.json'
    state = {'hypothesis':'UART5 may be Bluetooth; unverified',
             'temporary_directory':bridge.REMOTE,'binary_sha256':bridge.digest(binary),
             'probe_invocations':0,'probe_kind':'H5_SYNC','scan_commands_sent':0,'camera_self_test':'not-complete',
             'temporary_files_removed':False}
    try:
        for label, command in commands:
            if label == 'uart-h5-sync-once':
                state['probe_invocations'] += 1
                (folder/'result.json').write_text(json.dumps(state,indent=2)+'\n',encoding='utf-8')
            reply = session.command(label,command,5000)
            output = reply['output'].strip()
            if len(reply['output'].encode('ascii')) >= 231:
                raise ValueError('possibly truncated result')
            if label in expected:
                observed = output.split()[0] if label.endswith('-hash') else output
                if observed != expected[label]:
                    raise ValueError('result mismatch: '+label)
            if label == 'memory-self-test': state['camera_self_test'] = 'passed'
            if label == 'uart-h5-sync-once':
                pairs = output.split(';')
                values = dict(p.split('=',1) for p in pairs)
                required = {'result','tx','rx','restored','closed','original_baud_code'}
                if not required.issubset(values) or len(pairs) != len(values):
                    raise ValueError('invalid probe result')
                if not (0<=int(values['tx'])<=8 and 0<=int(values['rx'])<=259):
                    raise ValueError('invalid probe counts')
                state['probe'] = values
                # 不将无回复当作传输失败并重发；有效的阴性结果继续精确清理。
                print(json.dumps({'probe':values}),flush=True)
            if label == 'cleanup-check': state['temporary_files_removed'] = True
            state['last_completed'] = label
    except BaseException as error:
        state['failure'] = type(error).__name__
        state['note'] = '停止；未知结果不重发，不重复启动探测。'
        raise
    finally:
        state['all_usb_handles_closed'] = all(e['closed'] for e in session.entries)
        state['usb_requests'] = sum(e['submitted'] for e in session.entries)
        (folder/'result.json').write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(state,ensure_ascii=False),flush=True)


if __name__ == '__main__':
    binary, commands, expected = prepare()
    if not sys.argv[1:]:
        print(json.dumps({'offline_plan':'passed','commands':len(commands),
                          'probe_invocations':1,'maximum_uart_tx_bytes':8,
                          'baud':115200,'gpio_changes':0,'scans':0}))
    elif sys.argv[1:] == ['--run-once']:
        run(binary,commands,expected)
    else:
        raise SystemExit('explicit --run-once required')
