"""绑定 X2D 4.2.0 内部日志发射点及获取通路；只读离线 ELF。"""
from pathlib import Path
import hashlib
import json
import sys

from inspect_phocus import Binary, HASHES

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.research-cache/python'))
from dissect.extfs import ExtFS

# 定义的是已存在的日志发射点，不增加固件日志或运行固件。
EVENTS = [
    ('exposure_requested', '曝光时间参数', 'Camx_PreStartExpo', 0xa2238, 0x1d8c5f, 0xa2550, 630, 3,
     'Using ExpTime: %f us, TV: %d',
     '本轮曝光准备阶段使用的时间参数；不是传感器实际开始或结束时刻。',
     [('exposureUs', '曝光时间参数', 'us', 'decimal', 0, 3600000000), ('tv', 'TV 代码', '原始代码', 'int', -32768, 32767)]),
    ('lens_capabilities_failed', '镜头能力读取失败', 'Camx_PreStartExpo', 0xa2238, 0x1d8e02, 0xa296c, 716, 1,
     'Cannot get lens version capabilities --> lens disconnected', '固件进入镜头版本能力读取失败分支；不是实时连接检测结果。', []),
    ('lens_not_hbl', '镜头类型识别分支', 'Camx_PreStartExpo', 0xa2238, 0x1d8e7e, 0xa2ce0, 733, 1,
     'Lens version info --> Not HBL-lens, lens disconnected', '固件进入非 HBL 镜头识别分支并清除曝光对象 +0x60 标志。', []),
    ('true_exposure_eshutter', '电子快门与 True exposure 冲突', 'Camx_PreStartExpo', 0xa2238, 0x1d8ff5, 0xa3218, 792, 2,
     'Invalid user setting (True exposure enabled in e-shutter)', '固件报告设置组合冲突；不能据此证明实际完成曝光。', []),
    ('flash_sync_failed', 'FlashSync 设置失败', 'Camx_PreStartExpo', 0xa2238, 0x1d9111, 0xa3520, 862, 1,
     'Failed to set FlashSync', '曝光准备阶段报告 FlashSync 配置失败；没有对应成功日志也不能推断成功。', []),
    ('eshutter_parameters', '电子快门曝光分支', 'Camx_StartExpo', 0xa3b90, 0x1d9430, 0xa3ef4, 1028, 3,
     'Eshutter, max_shutter_time_us %ld, Expo->ExpoTimeUs %ld',
     '执行到了电子快门参数日志点。两个值是固件计算参数，不是物理曝光窗口测量。',
     [('maximumUs', '最大时间参数', 'us', 'int', 0, 3600000000), ('exposureUs', '曝光时间参数', 'us', 'int', 0, 3600000000)]),
    ('set_exposure_failed', '设置曝光失败', 'Camx_StartExpo', 0xa3b90, 0x1d947b, 0xa3f8c, 1035, 1,
     'Failed to setExposure', '固件设置曝光调用报告失败；不能解读为已曝光。', []),
    ('sensor_flush_failed', '传感器 flush 失败', 'Camx_StartExpo', 0xa3b90, 0x1d94d9, 0xa408c, 1057, 1,
     'Failed to flush, type: %d', '固件 flush 调用报告失败；type 保持原始代码，不猜其枚举。',
     [('type', 'flush 类型', '原始代码', 'int', -2147483648, 2147483647)]),
    ('long_exposure_branch', '长曝光分支', 'Camx_StartExpo', 0xa3b90, 0x1d9624, 0xa4498, 1124, 3,
     'Long exposure (tv=%d). Time %ld us', '执行到了长曝光分支日志点；此日志在分支中的同步调用之前，不证明同步脉冲已发出。',
     [('tv', 'TV 代码', '原始代码', 'int', -32768, 32767), ('exposureUs', '曝光时间参数', 'us', 'int', 0, 3600000000)]),
    ('fsync_setup_failed', 'FSYNC 配置失败', 'Camx_FlashEnable', 0xa63d8, 0x1d9d43, 0xa64a4, 1226, 1,
     'Cannot setup FSYNC, %d', 'FsyncCtrl_SetupAndEnable 返回错误；保留错误整数，不猜设备状态。',
     [('error', '返回代码', '原始代码', 'int', -2147483648, 2147483647)]),
]


def main():
    b = Binary('librcam.so')
    checks, events = [], []
    for identifier, label, name, address, fmt, call, line, level, body, meaning, fields in EVENTS:
        raw = b.read(fmt, 300).split(b'\0')[0].decode('ascii')
        assert raw == '[rcam]: [%s][%s:%d]' + body, identifier
        instruction = next(b.cs.disasm(b.read(call, 4), call))
        assert instruction.mnemonic == 'bl' and b.names[instruction.operands[0].imm] == 'duss_log_print@plt'
        moves = {x.op_str.split(',')[0]: x.operands[1].imm for x in b.cs.disasm(b.read(call-32, 32), call-32)
                 if x.mnemonic == 'mov' and len(x.operands) == 2 and x.operands[1].type == 2}
        assert moves.get('w0') == 0x51 and moves.get('w1') == level and moves.get('w6') == line, identifier
        assert any(s.name == name and s['st_value'] == address for s in b.symbols), identifier
        checks.append({'id': identifier, 'checks': ['literal', 'symbol', 'printCall', 'module', 'level', 'sourceLine'], 'ok': True})
        events.append({'id': identifier, 'label': label, 'function': name, 'symbolVa': hex(address), 'formatVa': hex(fmt),
                       'emissionVa': hex(call), 'sourceLine': line, 'level': level, 'bodyFormat': body, 'meaning': meaning,
                       'fields': [dict(zip(['key', 'label', 'unit', 'type', 'min', 'max'], row)) for row in fields]})

    chains = [
        ('camera-service', 0x1c80d8, 'bl', 'dcam_dbg_cmd@plt'),
        ('camera-service', 0x26c9f4, 'bl', 'duss_event_create_client@plt'),
        ('libdcam_base.so', 0x14ad4, 'b', 'looper_message_send_and_wait@plt'),
        ('libdcam_base.so', 0x15498, 'bl', 'socket@plt'),
        ('libdcam_base.so', 0x155b8, 'bl', 'bind@plt'),
        ('libdcam_base.so', 0x17a7c, 'bl', '__vsnprintf_chk@plt'),
        ('dji_sys', 0x288e4, 'bl', 'sys_route_control_ttygs_channel'),
        ('dji_sys', 0x288f0, 'bl', 'sys_route_control_ttygs_channel'),
        ('dji_sys', 0x34360, 'bl', 'duss_event_control_rt_byname@plt'),
        ('libduml_util.so', 0x1b8c8, 'bl', '__android_log_write@plt'),
        ('libduml_util.so', 0x1b97c, 'bl', '__android_log_buf_write@plt'),
        ('libduml_util.so', 0x1bd34, 'bl', 'sendto@plt'),
    ]
    binaries = {'librcam.so': b}
    for name, address, mnemonic, target in chains:
        if name not in binaries:
            binaries[name] = Binary(name)
        obj = binaries[name]
        ins = next(obj.cs.disasm(obj.read(address, 4), address))
        assert ins.mnemonic == mnemonic and obj.names[ins.operands[0].imm] == target
        checks.append({'binary': name, 'va': hex(address), 'target': target, 'ok': True})

    with (ROOT / '.research-cache/system.img').open('rb') as fh:
        fs = ExtFS(fh)
        configs = {}
        for name, digest in {
            '/etc/dji.json': '15a1fde3489b230249e4b2bbe87d409f8e7ea0315f44b0d854d261d0e945e892',
            '/bin/setup_usb.sh': '1a2d593ae6d7c777deef1b205e91d7f08e185fc61070c021d0317d8fad8304cd',
            '/bin/collect_logs.sh': 'c3d918f3ced2d2eced41c2fb441ee8eecb5a5d37c28d2a5a1caaf2a0e7c2a0cc',
            '/bin/cam_log_dump.sh': '652b7f80ca5d7bc49a674a38b21953f6f8c481e5f9ed5a386d7930a08329e0d1'
        }.items():
            data = fs.get(name).open().read()
            assert hashlib.sha256(data).hexdigest() == digest
            configs[name] = digest
        config = json.loads(fs.get('/etc/dji.json').open().read())
        assert config['system_service']['mb_route_table']['system']['a0']['status'] == 0
        assert config['system_service']['mb_route_table']['system']['a0']['uart']['interface'] == '/dev/ttyGS0'
        assert config['log']['default_channel'] == 'android_log'
        assert 'sha256sum' in fs.get('/bin').listdir() and 'logcat' in fs.get('/bin').listdir()
    catalog = {'schemaVersion': 1, 'model': 'X2D 100C', 'firmware': '4.2.0', 'binary': 'librcam.so',
               'sha256': HASHES['librcam.so'], 'targetProcess': 'camera-service', 'module': 'DUSS51',
               'scope': '仅固定日志发射点；不是完整执行轨迹或物理时序', 'events': events}
    report = {'schemaVersion': 1, 'firmware': '4.2.0', 'hardwareRequests': 0,
              'binaries': {n: HASHES[n] for n in binaries}, 'configs': configs,
              'eventChecks': 60, 'chainChecks': len(chains), 'checks': checks,
              'limitations': ['默认路由值不是实机运行状态', '静态发射点不证明实机日志存在', 'ADB 合法开启入口和实机读取未验证']}
    (ROOT / 'research/firmware-observer-events.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (ROOT / 'research/firmware-observer-checks.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'events': len(events), 'eventChecks': 60, 'chainChecks': len(chains), 'configHashes': len(configs), 'hardwareRequests': 0}))


if __name__ == '__main__':
    main()
