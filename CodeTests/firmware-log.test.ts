import test from 'node:test';
import assert from 'node:assert/strict';
import net from 'node:net';
import { once } from 'node:events';
import { AdbChannel, FIRMWARE_BASELINE_HASHES, FIRMWARE_COMMANDS, readFirmwareLogSnapshot, selectFirmwareTransport } from '../app/adb-log';
import { FIRMWARE_LOG_LIMIT, firmwareReplayFixture, parseFirmwareLog } from '../app/firmware-log';
import { DebugService } from '../app/service';
import { DiagnosticError } from '../app/protocol';

const fixtureDevice = 'TEST_PRIVATE_DEVICE device usb:fixture product:eagle2_ec1706_native model:Android_NATIVE_on_Eagle2_EC1706 device:eagle2_ec1706_native transport_id:17\n';
const hashes = Buffer.from(Object.entries(FIRMWARE_BASELINE_HASHES).map(([file, hash]) => `${hash}  ${file}`).join('\n') + '\n');
const deny = (code: string) => (e: unknown) => e instanceof DiagnosticError && e.code === code;
const packet = (id: number, body: Buffer) => { const header = Buffer.alloc(5); header[0] = id; header.writeUInt32LE(body.length, 1); return Buffer.concat([header, body]); };
const response = (text: string) => Buffer.from('OKAY' + Buffer.byteLength(text).toString(16).padStart(4, '0') + text);

interface FixtureOptions { device?: string; features?: string; baseline?: Buffer; logs?: Buffer; reject?: boolean; stderr?: boolean;
  nonzero?: boolean; truncated?: boolean; oversized?: boolean; unknownPacket?: boolean; stall?: boolean; }
async function withAdbFixture(options: FixtureOptions, work: (dial: () => AdbChannel, requests: string[]) => Promise<void>) {
  const requests: string[] = [], sockets = new Set<net.Socket>();
  const server = net.createServer(socket => {
    sockets.add(socket); socket.on('close', () => sockets.delete(socket)); socket.on('error', () => {});
    let pending = Buffer.alloc(0);
    socket.on('data', data => {
      pending = Buffer.concat([pending, data]);
      while (pending.length >= 4) {
        const size = Number.parseInt(pending.subarray(0, 4).toString(), 16);
        if (pending.length < 4 + size) return;
        const command = pending.subarray(4, 4 + size).toString(); pending = pending.subarray(4 + size); requests.push(command);
        let body: Buffer;
        if (command === 'host:devices-l') body = response(options.device ?? fixtureDevice);
        else if (command === 'host-transport-id:17:features') body = response(options.features ?? 'shell_v2,cmd');
        else if (command === 'host:transport-id:17') body = Buffer.from('OKAY');
        else if (command === 'shell,v2,raw:' + FIRMWARE_COMMANDS.verify) body = Buffer.concat([Buffer.from('OKAY'), packet(1, options.baseline ?? hashes), packet(3, Buffer.from([0]))]);
        else if (command === 'shell,v2,raw:' + FIRMWARE_COMMANDS.read) {
          if (options.stall) { socket.write('OKAY'); return; }
          if (options.reject) { body = Buffer.from('FAIL0010TEST_PRIVATE_ERR'); }
          else if (options.oversized) { const header = Buffer.from([1, 1, 0, 1, 0]); body = Buffer.concat([Buffer.from('OKAY'), header]); }
          else if (options.truncated) { socket.end(Buffer.from('OKAY\x01\x10\x00')); return; }
          else body = Buffer.concat([Buffer.from('OKAY'), packet(options.unknownPacket ? 9 : options.stderr ? 2 : 1,
            options.stderr ? Buffer.from('TEST_PRIVATE_ERR') : options.logs ?? firmwareReplayFixture()), packet(3, Buffer.from([options.nonzero ? 1 : 0]))]);
        } else { socket.destroy(); throw new Error('替身收到固定流程以外的请求'); }
        // 将状态、长度及 shell 包边界打散，验证 TCP 分包/粘包。
        socket.write(body.subarray(0, 1));
        setTimeout(() => { if (!socket.destroyed) socket.write(body.subarray(1, 6)); }, 1);
        setTimeout(() => { if (!socket.destroyed) socket.write(body.subarray(6)); }, 3);
      }
    });
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  const port = (server.address() as net.AddressInfo).port;
  try { await work(() => new AdbChannel(port, options.stall ? 150 : 3000), requests); }
  finally { for (const socket of sockets) socket.destroy(); await new Promise<void>(resolve => server.close(() => resolve())); }
}

test('真实固件格式的十类消息被解码，隐去原始头部、任务名和未知数据', () => {
  const raw = firmwareReplayFixture().toString().replaceAll('[fixture]', '[TEST_PRIVATE_TASK]') + 'serial=TEST_PRIVATE_DEVICE\nphoto=TEST_PRIVATE_PHOTO\n';
  const parsed = parseFirmwareLog(Buffer.from(raw));
  assert.equal(parsed.events.length, 10); assert.equal(parsed.ignoredLines, 2);
  assert.equal(parsed.events[5]!.fields[1]!.value, '250000');
  assert.equal(parsed.events[5]!.emissionVa, '0xa3ef4'); assert.equal(parsed.events[5]!.sourceLine, 1028);
  assert.equal(parsed.physicalTimingMeasured, false);
  assert.ok(!JSON.stringify(parsed).includes('TEST_PRIVATE_'));
});

test('错误函数/源码行、陌生数值和附加文本不能伪装为已核实事件', () => {
  const line = '[rcam]: [fixture][Camx_StartExpo:1028]Eshutter, max_shutter_time_us 1000000, Expo->ExpoTimeUs 250000';
  for (const bad of [line.replace(':1028]', ':1029]'), line.replace('Camx_StartExpo', 'Unknown'),
    line.replace('250000', '-1'), line.replace('250000', '3600000001'), line + ' serial=PRIVATE',
    line.replace('250000', '250000.0'), 'I/OTHER(1): ' + line]) assert.equal(parseFirmwareLog(Buffer.from(bad)).events.length, 0);
});

test('日志严格限制编码、控制字符、大小与事件数量', () => {
  assert.throws(() => parseFirmwareLog(Buffer.from([0xff])), deny('FW_LOG_ENCODING'));
  assert.throws(() => parseFirmwareLog(Buffer.from('\x1b[31m')), deny('FW_LOG_ENCODING'));
  assert.throws(() => parseFirmwareLog(Buffer.alloc(FIRMWARE_LOG_LIMIT + 1)), deny('FW_LOG_TOO_LARGE'));
  assert.throws(() => parseFirmwareLog(Buffer.from(firmwareReplayFixture().toString().repeat(31))), deny('FW_LOG_TOO_LARGE'));
});

test('ADB 选择要求唯一且已授权的 Eagle2 目标，并拒绝重复标识字段', () => {
  assert.equal(selectFirmwareTransport(fixtureDevice), '17');
  for (const [list, code] of [['', 'ADB_NOT_PRESENT'], [fixtureDevice + fixtureDevice, 'ADB_AMBIGUOUS'],
    [fixtureDevice.replace(' device ', ' unauthorized '), 'ADB_NOT_AUTHORIZED'],
    [fixtureDevice.replace('model:Android_NATIVE_on_Eagle2_EC1706', 'model:Phone'), 'ADB_TARGET_MISMATCH'],
    [fixtureDevice.trim() + ' transport_id:18', 'ADB_PROTOCOL']]) assert.throws(() => selectFirmwareTransport(list!), deny(code!));
});

test('已有 ADB server 替身端到端：先哈希后日志，详细字段到服务报告且没有任意命令', async () => {
  await withAdbFixture({}, async (dial, requests) => {
    const result = await readFirmwareLogSnapshot(dial);
    assert.equal(result.ok, true); assert.equal(result.baselineMatched, true); assert.equal(result.closed, true);
    assert.equal(result.data!.events.length, 10); assert.equal(result.remoteCommandsSubmitted, 2);
    assert.deepEqual(result.commands.map(x => x.completed), [true, true]);
    assert.deepEqual(requests, ['host:devices-l', 'host-transport-id:17:features', 'host:transport-id:17',
      'shell,v2,raw:' + FIRMWARE_COMMANDS.verify, 'host:transport-id:17', 'shell,v2,raw:' + FIRMWARE_COMMANDS.read]);
    const service = new DebugService(null, async () => result);
    const snapshot = await service.captureFirmware();
    assert.equal(snapshot.rows.length, 0); assert.equal(snapshot.hardwareRequests, 0);
    assert.equal(snapshot.firmware.data!.events.length, 10);
    assert.ok(!JSON.stringify(service.report()).includes('TEST_PRIVATE_'));
    assert.equal(service.replayFirmware().firmware.source, 'offline-replay');
    assert.equal(service.reset().firmware.data, null);
  });
});

test('固件哈希不匹配立即停止，不申请日志数据', async () => {
  await withAdbFixture({ baseline: Buffer.from(hashes.toString().replace(/^f/, 'e')) }, async (dial, requests) => {
    const result = await readFirmwareLogSnapshot(dial);
    assert.equal(result.error, 'FW_BASELINE_MISMATCH'); assert.equal(result.remoteCommandsSubmitted, 1);
    assert.equal(result.data, null); assert.equal(result.closed, true);
    assert.ok(!requests.some(x => x.includes('logcat')));
  });
});

test('未授权设备或缺少 shell v2 时不执行机内命令', async () => {
  for (const options of [{ device: fixtureDevice.replace(' device ', ' unauthorized ') }, { features: 'cmd' }]) {
    await withAdbFixture(options, async (dial, requests) => {
      const result = await readFirmwareLogSnapshot(dial);
      assert.equal(result.ok, false); assert.equal(result.remoteCommandsSubmitted, 0);
      assert.ok(!requests.some(x => x.startsWith('shell')));
    });
  }
});

test('FAIL、stderr、非零退出码均中止，不泄露服务端错误文本', async () => {
  for (const options of [{ reject: true }, { stderr: true }, { nonzero: true }]) {
    await withAdbFixture(options, async dial => {
      const result = await readFirmwareLogSnapshot(dial);
      assert.equal(result.ok, false); assert.equal(result.data, null); assert.equal(result.closed, true);
      assert.equal(result.commands[1]!.completed, false);
      assert.ok(!JSON.stringify(result).includes('TEST_PRIVATE_'));
    });
  }
});

test('损坏包、过大包、截断与超时停止且关闭连接，不自动重试', async () => {
  for (const options of [{ unknownPacket: true }, { oversized: true }, { truncated: true }, { stall: true }]) {
    await withAdbFixture(options, async (dial, requests) => {
      const result = await readFirmwareLogSnapshot(dial);
      assert.equal(result.ok, false); assert.equal(result.data, null); assert.equal(result.closed, true);
      assert.equal(requests.filter(x => x.includes('logcat')).length, 1);
      assert.equal(result.error, options.stall ? 'ADB_TIMEOUT' : options.truncated ? 'ADB_TRUNCATED' : 'ADB_PROTOCOL');
    });
  }
});

test('空的已读缓冲区保留零事件，不补造轨迹', async () => {
  await withAdbFixture({ logs: Buffer.alloc(0) }, async dial => {
    const result = await readFirmwareLogSnapshot(dial);
    assert.equal(result.ok, true); assert.equal(result.data!.events.length, 0);
  });
});

test('本机 server 不可用时停止，不能自动启动服务或提交机内命令', async () => {
  const server = net.createServer(); server.listen(0, '127.0.0.1'); await once(server, 'listening');
  const port = (server.address() as net.AddressInfo).port;
  await new Promise<void>(resolve => server.close(() => resolve()));
  const result = await readFirmwareLogSnapshot(() => new AdbChannel(port, 200));
  assert.equal(result.error, 'ADB_SERVER_UNAVAILABLE'); assert.equal(result.remoteCommandsSubmitted, 0);
  assert.equal(result.closed, true); assert.equal(result.data, null);
});

test('固件读取与原六项快照共享忙状态，离线实例没有实机适配器', async () => {
  const offline = new DebugService();
  await assert.rejects(() => offline.captureFirmware(), deny('HARDWARE_DISABLED'));
  assert.equal(offline.replayFirmware().firmware.source, 'offline-replay');
  let release!: () => void;
  const service = new DebugService(null, async () => {
    await new Promise<void>(resolve => { release = resolve; });
    return { source: 'adb-existing', ok: false, baselineMatched: false, closed: true, stage: 'test', error: 'ADB_IO',
      hostRequests: 0, remoteCommandsSubmitted: 0, elapsedMs: 0, data: null, commands: [] };
  });
  const running = service.captureFirmware();
  assert.throws(() => service.replayFirmware(), deny('BUSY')); assert.throws(() => service.reset(), deny('BUSY'));
  release(); await running;
});
