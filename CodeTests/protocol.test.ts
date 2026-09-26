import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { assertReadSpec, DiagnosticError, MAX_BODY_BYTES, parseParameterBody } from '../app/protocol';
import { runSimulation, SIMULATED_WIRE_BODY } from '../app/simulator';
import { DebugService } from '../app/service';
const bytes = (x: unknown) => Buffer.from(JSON.stringify(x));
const entry = (value: unknown, overrides = {}) => ({ can_get: true, can_set: true, range: '', value, ...overrides });
const hasCode = (code: string) => (e: unknown) => e instanceof DiagnosticError && e.code === code;

test('白名单严格拒绝写操作、照片路由、编码变体与查询参数', () => {
  assert.doesNotThrow(() => assertReadSpec('GET', '/v1/parameters'));
  for (const method of ['POST','PUT','PATCH','DELETE','HEAD','OPTIONS','get',null]) assert.throws(() => assertReadSpec(method, '/v1/parameters'), hasCode('REQUEST_DENIED'));
  for (const path of ['/v1/parameters?x=1','/v1/parameters/','/v1/browse','/v1/download/1/2/3','/v1/delete/1','/v1/metadata/1/2/3','/%76%31/parameters','http://127.0.0.1/v1/parameters',null]) assert.throws(() => assertReadSpec('GET', path), hasCode('REQUEST_DENIED'));
});
test('只保留受审查 ID 和形状；响应 name、序列项和额外字段不外传', () => {
  const result = parseParameterBody(bytes({ '27': entry('4.2.0', { name: 'PRIVATE_NAME', extra: 'PRIVATE_EXTRA' }), '22': entry('PRIVATE_SERIAL'), '112': entry('PRIVATE_LENS'), '999': { secret: 'PRIVATE_UNKNOWN' } }));
  assert.equal(result.rows.length, 1);
  assert.equal(result.hiddenFieldCount, 3);
  assert.equal(result.rows[0]!.name, 'kFirmwareVersionCamParam');
  assert.equal(result.rows[0]!.value, '4.2.0');
  assert.equal(result.rows[0]!.cameraCanSet, true);
  assert.equal(result.rows[0]!.clientCanSet, false);
  assert.ok(!JSON.stringify(result).includes('PRIVATE_'));
});
test('未知编码和不可信范围被隐藏，can_get=false 时不显示 value', () => {
  const result = parseParameterBody(bytes({ '27': entry('UNREVIEWED_SECRET', { range: 'UNREVIEWED_SECRET' }), '74': entry('1.2.3', { can_get: false }), '88': entry('-1') }));
  assert.ok(result.rows.every(r => r.value === null));
  assert.equal(result.rows.find(r=>r.id===27)!.range, null);
  assert.equal(result.rows.find(r=>r.id===74)!.valueState, 'unavailable');
  assert.ok(!JSON.stringify(result).includes('UNREVIEWED_SECRET'));
});
test('响应总量、UTF-8、根结构和字段类型边界均拒绝错误输入', () => {
  assert.throws(() => parseParameterBody(Buffer.alloc(MAX_BODY_BYTES+1)), hasCode('BODY_TOO_LARGE'));
  assert.throws(() => parseParameterBody(Buffer.from([0xff,0xfe])), hasCode('INVALID_JSON'));
  for (const body of [[], null, {'__proto__':1, url:'x'}, {'27':entry(42)}, {'27':entry('4.2.0',{can_get:'true'})}, {'27':entry('4.2.0',{range:[]})}]) assert.throws(()=>parseParameterBody(bytes(body)),hasCode('INVALID_SCHEMA'));
  assert.throws(()=>parseParameterBody(bytes({'22':entry('PRIVATE')})),hasCode('NO_ALLOWLISTED_PARAMETERS'));
});
test('离线默认不发请求；无实机适配器时由后端阻止连接', () => {
  const service = new DebugService();
  assert.equal(service.snapshot().source, 'offline-static');
  assert.equal(service.snapshot().events.length,0);
  assert.equal(service.snapshot().evidence.connection.authorized,true);
  assert.throws(()=>service.connectHardware(),hasCode('HARDWARE_DISABLED'));
  assert.equal(service.snapshot().hardwareRequests,0);
});
test('真实 HTTP 回环验证代理隔离、固定路径、无凭据、单次请求及模拟来源', async () => {
  const original = http.request;
  const requests: http.RequestOptions[] = [];
  const oldProxy = process.env.HTTP_PROXY;
  process.env.HTTP_PROXY = 'http://127.0.0.1:1';
  http.request = ((options: http.RequestOptions, callback: any) => { requests.push(options); return original(options, callback); }) as typeof http.request;
  try {
    const service = new DebugService();
    const result = await service.simulate('snapshot');
    assert.equal(requests.length,1);
    const request = requests[0]!;
    assert.equal(request.hostname,'127.0.0.1'); assert.equal(request.localAddress,'127.0.0.1');
    assert.equal(request.method,'GET'); assert.equal(request.path,'/v1/parameters');
    assert.ok(!JSON.stringify(request.headers).toLowerCase().includes('client-id'));
    assert.equal(result.source,'simulated'); assert.equal(result.rows.length,18); assert.equal(result.hiddenFieldCount,2);
    assert.equal(result.events[0]!.status,200);
    assert.ok(!JSON.stringify(service.report()).includes('SYNTHETIC_PRIVATE_IDENTIFIER'));
    assert.equal(result.hardwareRequests,0);
  } finally { http.request = original; if (oldProxy === undefined) delete process.env.HTTP_PROXY; else process.env.HTTP_PROXY = oldProxy; }
});
test('401、重定向、超限、坏 JSON 均停止，不猜身份或跟随新目标', async () => {
  for (const [scenario, code] of [['unauthorized','HTTP_UNAUTHORIZED'],['redirect','REDIRECT_DENIED'],['oversize','BODY_TOO_LARGE'],['malformed','INVALID_JSON']] as const) await assert.rejects(runSimulation(scenario),hasCode(code));
});
test('绝对超时终止无响应，模拟器收尾，后续运行仍可成功', async () => {
  const begin = performance.now();
  await assert.rejects(runSimulation('timeout'),hasCode('TIMEOUT'));
  assert.ok(performance.now()-begin < 3500);
  assert.equal((await runSimulation('snapshot')).rows.length,18);
});
test('不接受并发诊断或任意场景；失败后不保留旧成功快照', async () => {
  const service = new DebugService();
  await assert.rejects(service.simulate({url:'http://192.0.2.1'}),hasCode('IPC_DENIED'));
  const run = service.simulate('snapshot');
  await assert.rejects(service.simulate('snapshot'),hasCode('BUSY'));
  await run;
  const failed = await service.simulate('unauthorized');
  assert.equal(failed.rows.length,0); assert.equal(failed.events[0]!.status,401);
});
test('离线导入和导出保持来源隔离，重置清除参数与诊断', () => {
  const service = new DebugService();
  service.importBody(Buffer.from(SIMULATED_WIRE_BODY));
  assert.equal(service.report().source,'offline-import');
  const serialized=JSON.stringify(service.report());
  assert.ok(!serialized.includes('SYNTHETIC_')); assert.ok(!serialized.includes('X-Phocus-Client-Id'));
  const invalid=service.importBody(Buffer.from('{'));
  assert.equal(invalid.rows.length,0); assert.equal(invalid.source,'offline-import');
  assert.equal(service.reset().events.length,0);
});
