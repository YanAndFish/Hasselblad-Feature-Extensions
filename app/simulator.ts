import http from 'node:http';
import { performance } from 'node:perf_hooks';
import { AddressInfo } from 'node:net';
import { assertReadSpec, DiagnosticError, MAX_BODY_BYTES, READ_SPEC, REQUEST_TIMEOUT_MS, parseParameterBody } from './protocol';

export const SCENARIOS = ['snapshot', 'unauthorized', 'redirect', 'oversize', 'timeout', 'malformed'] as const;
export type Scenario = typeof SCENARIOS[number];
export function isScenario(value: unknown): value is Scenario { return SCENARIOS.includes(value as Scenario); }
const row = (value: string, canSet = false) => ({ can_get: true, can_set: canSet, range: '', value });
/** 只有外形来自静态证据；每一个值都是人工模拟，绝非相机采集。 */
export const SIMULATED_WIRE_BODY = JSON.stringify({
  '15': row('4.2.0'), '17': row('1'), '23': row('42'), '25': row('2', true),
  '27': row('4.2.0'), '28': row('1'), '46': row('55'), '47': row('80'),
  '61': row('1'), '74': row('1.2.3'), '75': row('55'), '87': row('0', true),
  '88': row('0', true), '91': row('500'), '118': row('0', true), '120': row('XCD 55V'),
  '122': row('0'), '136': row('1'),
  '22': row('SYNTHETIC_PRIVATE_IDENTIFIER'), '112': row('SYNTHETIC_LENS_IDENTIFIER')
});

interface WireResult { body: Buffer; status: number; bytes: number; elapsedMs: number; }

// 私有函数：端口只来自当前进程创建的模拟器；渲染层无法提交目标或请求。
function readOwnedLoopback(port: number): Promise<WireResult> {
  assertReadSpec(READ_SPEC.method, READ_SPEC.path);
  const start = performance.now();
  return new Promise((resolve, reject) => {
    const agent = new http.Agent({ keepAlive: false, maxSockets: 1 });
    let settled = false;
    let bytes = 0;
    const chunks: Buffer[] = [];
    const finish = (error?: DiagnosticError, body?: Buffer, status?: number) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      req.destroy();
      agent.destroy();
      chunks.length = 0;
      if (error) reject(error);
      else resolve({ body: body!, status: status!, bytes, elapsedMs: Math.round((performance.now() - start) * 10) / 10 });
    };
    // 明确 IPv4 回环与源地址。自建 Agent 不从 HTTP(S)_PROXY 或全局 Agent 取路由。
    const req = http.request({ hostname: '127.0.0.1', localAddress: '127.0.0.1', family: 4, port,
      method: READ_SPEC.method, path: READ_SPEC.path, agent, maxHeaderSize: 8192,
      headers: { Accept: 'application/json', 'Accept-Encoding': 'identity', Connection: 'close' }
    }, res => {
      const status = res.statusCode ?? 0;
      if (status === 401) { finish(new DiagnosticError('HTTP_UNAUTHORIZED')); return; }
      if (status >= 300 && status < 400) { finish(new DiagnosticError('REDIRECT_DENIED')); return; }
      if (status !== 200) { finish(new DiagnosticError('HTTP_ERROR')); return; }
      if (!/^application\/json(?:\s*;.*)?$/i.test(res.headers['content-type'] ?? '') || res.headers['content-encoding']) {
        finish(new DiagnosticError('CONTENT_TYPE_DENIED')); return;
      }
      const length = res.headers['content-length'];
      if (length && (!/^\d+$/.test(length) || Number(length) > MAX_BODY_BYTES)) { finish(new DiagnosticError('BODY_TOO_LARGE')); return; }
      res.on('data', (chunk: Buffer) => {
        bytes += chunk.length;
        if (bytes > MAX_BODY_BYTES) finish(new DiagnosticError('BODY_TOO_LARGE'));
        else chunks.push(chunk);
      });
      res.on('end', () => finish(undefined, Buffer.concat(chunks), status));
      res.on('error', () => finish(new DiagnosticError('NETWORK_ERROR')));
      res.on('aborted', () => finish(new DiagnosticError('NETWORK_ERROR')));
    });
    const timer = setTimeout(() => finish(new DiagnosticError('TIMEOUT')), REQUEST_TIMEOUT_MS);
    req.on('error', () => finish(new DiagnosticError('NETWORK_ERROR')));
    req.end();
  });
}

export async function runSimulation(scenario: Scenario) {
  if (!isScenario(scenario)) throw new DiagnosticError('IPC_DENIED');
  const server = http.createServer((req, res) => {
    if (req.method !== READ_SPEC.method || req.url !== READ_SPEC.path) { res.writeHead(403).end(); return; }
    switch (scenario) {
      case 'unauthorized': res.writeHead(401).end(); return;
      case 'redirect': res.writeHead(302, { Location: 'http://127.0.0.1:1/blocked' }).end(); return;
      case 'timeout': return;
      case 'oversize': res.writeHead(200, { 'Content-Type': 'application/json', 'Content-Length': MAX_BODY_BYTES + 1 }).end(); return;
      case 'malformed': res.writeHead(200, { 'Content-Type': 'application/json' }).end('{'); return;
      default: res.writeHead(200, { 'Content-Type': 'application/json' }).end(SIMULATED_WIRE_BODY);
    }
  });
  server.requestTimeout = REQUEST_TIMEOUT_MS + 1000;
  server.headersTimeout = REQUEST_TIMEOUT_MS + 1000;
  server.maxHeadersCount = 20;
  await new Promise<void>((resolve, reject) => {
    server.once('error', () => reject(new DiagnosticError('NETWORK_ERROR')));
    server.listen(0, '127.0.0.1', resolve);
  });
  try {
    const wire = await readOwnedLoopback((server.address() as AddressInfo).port);
    const parsed = parseParameterBody(wire.body);
    wire.body.fill(0);
    return { ...parsed, status: wire.status, bytes: wire.bytes, elapsedMs: wire.elapsedMs };
  } finally {
    await new Promise<void>(resolve => { server.close(() => resolve()); server.closeAllConnections(); });
  }
}
