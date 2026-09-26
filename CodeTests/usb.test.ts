import test from 'node:test';
import assert from 'node:assert/strict';
import { decodeUsbValue, parseUsbHelperResult, USB_READ_IDS, UsbReadResult } from '../app/usb';
import { DebugService } from '../app/service';
import { DiagnosticError } from '../app/protocol';

const fixture = () => ({ Ok: true, Opened: true, Closed: true, Requests: 6, ReplyBytes: 6144, Win32: 0, ElapsedMs: 50,
  Error: '', Stage: 'complete', InterfaceNumber: 3, PipeIn: 0x81, PipeOut: 2,
  Values: USB_READ_IDS.map((id, index) => ({ Id: id, Encoded: Buffer.from(['S5,4.2.0', 'i1', 'i2', 'fbff0000000000000', 'i0', 'i1'][index]!).toString('base64') })),
  Steps: USB_READ_IDS.map((id, index) => ({ Id: id, Sequence: index + 1, WriteCompleted: true, ReplyCompleted: true, ReplyBytes: 1024, ElapsedMs: 2 })) });
const deny = (code: string) => (error: unknown) => error instanceof DiagnosticError && error.code === code;

test('USB 解码核实的字符串长度和运行标志，隐去未经审查内容', () => {
  assert.equal(decodeUsbValue(27, Buffer.from('S5,4.2.0')).value, '4.2.0');
  assert.equal(decodeUsbValue(27, Buffer.from('S6,v4.2.0')).value, '4.2.0');
  assert.equal(decodeUsbValue(28, Buffer.from('i1')).value, '1');
  assert.equal(decodeUsbValue(28, Buffer.from('i0')).value, '0');
  for (const value of ['S6,4.2.0', 'S5,v4.2.0', 'S5,4.2.0\0', 'S8,UNIT-ID!', '4.2.0', 's4.2.0', 'S999,4.2.0', 'S01,4', 'i1']) {
    assert.equal(decodeUsbValue(27, Buffer.from(value)).valueState, 'hidden');
  }
  for (const value of ['i2', 'i01', 'r1', 'f3ff0000000000000', 'i-1', 'i1\n']) assert.equal(decodeUsbValue(28, Buffer.from(value)).value, null);
  assert.equal(decodeUsbValue(27, Uint8Array.of(0xff)).value, null);
  assert.equal(decodeUsbValue(27, Buffer.alloc(0)).valueState, 'unavailable');
  assert.throws(() => decodeUsbValue(22, Buffer.from('S6,SECRET')), deny('USB_REQUEST_DENIED'));
});

test('调试字段区分整数、布尔与 double 位模式，未知/非有限/越界值隐藏', () => {
  for (const [wire, value] of [['f0', '0'], ['f3ff0000000000000', '1'], ['fbff0000000000000', '-1'], ['f3fb5555555555555', '0.083333']])
    assert.equal(decodeUsbValue(87, Buffer.from(wire!)).value, value);
  for (const wire of ['f1.0', 'r3ff0000000000000', 'f03ff0000000000000', 'f7ff0000000000000', 'f7ff8000000000000',
    'f4059400000000000', 'f3fb999999999999a', 'f3ff0000000000000\n', 'F1,3ff0000000000000']) assert.equal(decodeUsbValue(87, Buffer.from(wire)).value, null);
  assert.equal(decodeUsbValue(25, Buffer.from('i2')).value, '2');
  for (const wire of ['i-1', 'i02', 'i3601', 'f4000000000000000', 'i2\0']) assert.equal(decodeUsbValue(25, Buffer.from(wire)).value, null);
  for (const id of [61, 88]) {
    assert.equal(decodeUsbValue(id, Buffer.from('i0')).value, '0');
    assert.equal(decodeUsbValue(id, Buffer.from('i1')).value, '1');
    assert.equal(decodeUsbValue(id, Buffer.from('i2')).value, null);
  }
  assert.throws(() => decodeUsbValue(74, Buffer.from('S5,1.0.0')), deny('USB_REQUEST_DENIED'));
});

test('USB 私有结果不把原文、补齐数据、路径或身份字段带入输出', () => {
  const input = { ...fixture(), UniqueDevicePath: 'PRIVATE-DEVICE-PATH', Serial: 'PRIVATE-SERIAL' };
  const parsed = parseUsbHelperResult(JSON.stringify(input));
  assert.equal(parsed.ok, true); assert.equal(parsed.requests, 6); assert.equal(parsed.closed, true);
  assert.deepEqual(parsed.rows.map(x => x.value), ['4.2.0', '1', '2', '-1', '0', '1']);
  assert.deepEqual(parsed.steps.map(x => x.id), USB_READ_IDS);
  assert.equal(parsed.rows[0]!.cameraCanSet, null);
  const report = JSON.stringify(parsed);
  for (const denied of ['PRIVATE', 'Encoded', 'UzUsNC4yLjA=', 'UniqueDevicePath']) assert.ok(!report.includes(denied));
});

test('USB 辅助结构拒绝越界、乱序、重复 ID、未知错误及伪造成功', () => {
  const mutations: ((x: any) => void)[] = [
    x => x.Requests = 7, x => x.Closed = false, x => x.Opened = false, x => x.ReplyBytes = 65536,
    x => x.Values[0].Id = 22, x => x.Values.reverse(), x => x.Values[1].Id = 27,
    x => x.Values[0].Encoded = 'not base64', x => x.Values[0].Encoded = Buffer.alloc(601).toString('base64'),
    x => x.Ok = false, x => x.Values.pop(), x => x.Error = 'private exception', x => x.Win32 = -1,
    x => x.Steps.pop(), x => x.Steps[0].WriteCompleted = false, x => x.Steps[2].Id = 22,
    x => x.Steps[1].Sequence = 1, x => x.Steps[2].ReplyBytes = 2048, x => x.ReplyBytes = 2048,
    x => x.Values[0].Encoded = Buffer.from('S5,4.3.0').toString('base64'),
    x => x.Values[1].Encoded = Buffer.from('i0').toString('base64'),
    x => x.Values[3].Encoded = Buffer.from('unknown').toString('base64')
  ];
  for (const mutate of mutations) { const input = fixture(); mutate(input); assert.throws(() => parseUsbHelperResult(JSON.stringify(input)), deny('USB_HELPER_INVALID')); }
  const failed = { ...fixture(), Ok: false, Opened: false, Requests: 0, ReplyBytes: 0, Error: 'USB_NOT_PRESENT', Values: [], Steps: [] };
  assert.equal(parseUsbHelperResult(JSON.stringify(failed)).requests, 0);
  assert.throws(() => parseUsbHelperResult('not json'), deny('USB_HELPER_INVALID'));
});

test('停止后的部分快照保留已核实值和逐项通信阶段，不伪报整批成功', () => {
  const input = fixture();
  input.Ok = false; input.Error = 'USB_VALUE_UNREVIEWED'; input.Requests = 4; input.ReplyBytes = 4096;
  input.Values = input.Values.slice(0, 4); input.Steps = input.Steps.slice(0, 4);
  input.Values[3]!.Encoded = Buffer.from('PRIVATE-UNKNOWN').toString('base64');
  const result = parseUsbHelperResult(JSON.stringify(input));
  assert.equal(result.ok, false); assert.equal(result.rows[3]!.valueState, 'hidden'); assert.equal(result.closed, true);
  assert.deepEqual(result.steps.map(x => x.id), [27, 28, 25, 87]);
  assert.ok(!JSON.stringify(result).includes('PRIVATE-UNKNOWN'));
});

test('实机替身读完自动关闭；并发和旧参数快照被隔离；模拟不会清零历史实机计数', async () => {
  let complete!: (x: UsbReadResult) => void;
  const service = new DebugService(() => new Promise(resolve => { complete = resolve; }));
  await service.simulate('snapshot');
  const request = service.connectHardware();
  assert.equal(service.snapshot().source, 'camera-usb'); assert.equal(service.snapshot().rows.length, 0);
  assert.throws(() => service.connectHardware(), deny('BUSY'));
  assert.throws(() => service.reset(), deny('BUSY'));
  complete(parseUsbHelperResult(JSON.stringify(fixture())));
  const snapshot = await request;
  assert.equal(snapshot.hardwareRequests, 6); assert.equal(snapshot.hardwareConnected, false);
  assert.equal(snapshot.rows[0]!.value, '4.2.0');
  assert.equal(snapshot.events.length, 8); // 原有模拟记录 + 六项通信阶段 + 批次结论。
  assert.equal(snapshot.events[1]!.parameterId, 61);
  assert.ok(snapshot.events[1]!.detail.includes('不是闪光或曝光时序'));
  await service.simulate('snapshot');
  assert.equal(service.report().source, 'simulated'); assert.equal(service.report().hardwareRequests, 6);
  service.reset(); assert.equal(service.report().hardwareRequests, 6);
});

test('USB 辅助进程失联不能报告零请求或已正常断开', async () => {
  const unknown: UsbReadResult = { ok: false, rows: [], requests: null, opened: null, closed: null, error: 'USB_HELPER_TIMEOUT',
    win32: null, elapsedMs: 30000, replyBytes: 0, interfaceNumber: null, pipeIn: null, pipeOut: null, steps: [] };
  const service = new DebugService(async () => unknown);
  const result = await service.connectHardware();
  assert.equal(result.hardwareRequests, null); assert.equal(result.hardwareConnected, null);
  assert.equal(result.events[0]!.outcome, 'USB_HELPER_TIMEOUT');
});
