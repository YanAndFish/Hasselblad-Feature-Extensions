import net from 'node:net';
import { performance } from 'node:perf_hooks';
import { DiagnosticError } from './protocol';
import { FIRMWARE_LOG_LIMIT, FirmwareLogData, parseFirmwareLog } from './firmware-log';

export const FIRMWARE_BASELINE_HASHES = Object.freeze({
  '/system/bin/camera-service': 'fbcf828f73bca13f0c8b95e7dd0b95ac483ae36954ec06179098c8a1a65f9f82',
  '/system/lib64/librcam.so': '72ebc8deebce4a29047c475e77ab4edbf2860abb1f572fea45260fe17ad0bda5'
});
export const FIRMWARE_COMMANDS = Object.freeze({
  verify: '/system/bin/sha256sum /system/bin/camera-service /system/lib64/librcam.so',
  read: "/system/bin/logcat -d -t 300 -v brief -b main -b system -b crash 'DUSS51:V' '*:S'"
});
export interface FirmwareReadResult {
  source: 'adb-existing'; ok: boolean; baselineMatched: boolean; closed: boolean;
  stage: string; error: string | null; hostRequests: number; remoteCommandsSubmitted: number;
  elapsedMs: number; data: FirmwareLogData | null;
  commands: { operation: 'verify' | 'read'; completed: boolean; stdoutBytes: number }[];
}

/** 仅连接已经运行的本机 ADB server。不会启动 server、认证、启用 ADB 或安装机内程序。 */
export class AdbChannel {
  private readonly socket: net.Socket;
  private buffer = Buffer.alloc(0);
  private total = 0;
  private failure: DiagnosticError | null = null;
  private ended = false;
  private waiter: (() => void) | null = null;
  private readonly timer: ReturnType<typeof setTimeout>;
  private rejectReady: ((reason: DiagnosticError) => void) | null = null;
  private connected = false;
  readonly ready: Promise<void>;
  constructor(port = 5037, timeoutMs = 8000) {
    this.socket = net.createConnection({ host: '127.0.0.1', port });
    this.ready = new Promise((resolve, reject) => {
      this.rejectReady = reject;
      this.socket.once('connect', () => { this.connected = true; this.rejectReady = null; resolve(); });
      this.socket.once('error', () => reject(new DiagnosticError('ADB_SERVER_UNAVAILABLE')));
    });
    // 错误文本可能包含设备标识，只使用固定错误码。
    this.socket.on('error', () => this.fail('ADB_IO'));
    this.socket.on('end', () => { this.ended = true; this.wake(); });
    this.socket.on('close', () => { this.ended = true; this.wake(); });
    this.socket.on('data', chunk => {
      this.total += chunk.length;
      if (this.total > FIRMWARE_LOG_LIMIT + 32768) { chunk.fill(0); this.fail('FW_LOG_TOO_LARGE'); return; }
      const combined = Buffer.concat([this.buffer, chunk]);
      this.buffer.fill(0); chunk.fill(0); this.buffer = combined; this.wake();
    });
    this.timer = setTimeout(() => this.fail('ADB_TIMEOUT'), timeoutMs);
  }
  private wake() { const waiter = this.waiter; this.waiter = null; waiter?.(); }
  private fail(code: string) { this.failure ??= new DiagnosticError(code); this.rejectReady?.(this.failure); this.rejectReady = null; this.wake(); this.socket.destroy(); }
  async take(size: number): Promise<Buffer> {
    if (!Number.isSafeInteger(size) || size < 0 || size > FIRMWARE_LOG_LIMIT) throw new DiagnosticError('ADB_PROTOCOL');
    while (this.buffer.length < size) {
      if (this.failure) throw this.failure;
      if (this.ended) throw new DiagnosticError('ADB_TRUNCATED');
      await new Promise<void>(resolve => { this.waiter = resolve; });
    }
    if (this.failure) throw this.failure;
    const output = Buffer.from(this.buffer.subarray(0, size));
    const remainder = Buffer.from(this.buffer.subarray(size));
    this.buffer.fill(0); this.buffer = remainder;
    return output;
  }
  async text(size: number): Promise<string> {
    const bytes = await this.take(size);
    try {
      if (bytes.some(v => v !== 9 && v !== 10 && v !== 13 && (v < 32 || v > 126))) throw new DiagnosticError('ADB_PROTOCOL');
      return bytes.toString('ascii');
    } finally { bytes.fill(0); }
  }
  async service(value: string): Promise<void> {
    await this.ready;
    if (this.failure) throw this.failure;
    const body = Buffer.from(value, 'ascii');
    const message = Buffer.concat([Buffer.from(body.length.toString(16).padStart(4, '0')), body]);
    try { await new Promise<void>((resolve, reject) => this.socket.write(message, error => error ? reject(new DiagnosticError('ADB_IO')) : resolve())); }
    finally { body.fill(0); message.fill(0); }
    const status = await this.text(4);
    if (status === 'OKAY') return;
    if (status === 'FAIL') {
      const size = await this.length();
      const discarded = await this.take(size); discarded.fill(0);
      throw new DiagnosticError('ADB_REJECTED');
    }
    throw new DiagnosticError('ADB_PROTOCOL');
  }
  async length(): Promise<number> {
    const text = await this.text(4);
    if (!/^[0-9a-fA-F]{4}$/.test(text)) throw new DiagnosticError('ADB_PROTOCOL');
    const size = Number.parseInt(text, 16);
    if (size > 8192) throw new DiagnosticError('ADB_PROTOCOL');
    return size;
  }
  close(): void { clearTimeout(this.timer); if (!this.connected) this.rejectReady?.(new DiagnosticError('ADB_TRUNCATED')); this.rejectReady = null; this.buffer.fill(0); this.buffer = Buffer.alloc(0); this.ended = true; this.wake(); this.socket.destroy(); }
}

type Dial = () => AdbChannel;
async function query(dial: Dial, request: string): Promise<string> {
  const channel = dial();
  try { await channel.service(request); return await channel.text(await channel.length()); }
  finally { channel.close(); }
}
export function selectFirmwareTransport(list: string): string {
  const lines = list.trim().split(/\r?\n/).filter(Boolean);
  if (!lines.length) throw new DiagnosticError('ADB_NOT_PRESENT');
  if (lines.length !== 1) throw new DiagnosticError('ADB_AMBIGUOUS');
  const parts = lines[0]!.trim().split(/\s+/);
  if (parts[1] !== 'device') throw new DiagnosticError('ADB_NOT_AUTHORIZED');
  const fields = new Map<string, string>();
  for (const part of parts.slice(2)) {
    const at = part.indexOf(':');
    if (at < 1 || fields.has(part.slice(0, at))) throw new DiagnosticError('ADB_PROTOCOL');
    fields.set(part.slice(0, at), part.slice(at + 1));
  }
  const id = fields.get('transport_id');
  if (!id || !/^[1-9][0-9]{0,18}$/.test(id)) throw new DiagnosticError('ADB_PROTOCOL');
  // 产品值取自官方 4.2.0 build.prop；随后还必须匹配两份运行二进制的哈希。
  if (fields.get('product') !== 'eagle2_ec1706_native' || fields.get('device') !== 'eagle2_ec1706_native'
      || fields.get('model') !== 'Android_NATIVE_on_Eagle2_EC1706'
      || parts[0]!.startsWith('emulator-') || parts[0]!.includes(':')) throw new DiagnosticError('ADB_TARGET_MISMATCH');
  return id;
}
export function verifyFirmwareHashes(text: string): void {
  const lines = text.trim().split(/\r?\n/);
  const expected = Object.entries(FIRMWARE_BASELINE_HASHES);
  if (lines.length !== expected.length) throw new DiagnosticError('FW_BASELINE_MISMATCH');
  for (let i = 0; i < expected.length; i++) {
    const [file, hash] = expected[i]!;
    if (lines[i] !== `${hash}  ${file}`) throw new DiagnosticError('FW_BASELINE_MISMATCH');
  }
}

async function runFixedShell(dial: Dial, id: string, command: keyof typeof FIRMWARE_COMMANDS, submitted: () => void): Promise<Buffer> {
  const channel = dial();
  let data = Buffer.alloc(0);
  const limit = command === 'verify' ? 512 : FIRMWARE_LOG_LIMIT;
  let packets = 0;
  try {
    await channel.service('host:transport-id:' + id);
    submitted();
    await channel.service('shell,v2,raw:' + FIRMWARE_COMMANDS[command]);
    for (;;) {
      if (++packets > 2048) throw new DiagnosticError('ADB_PROTOCOL');
      const header = await channel.take(5), type = header[0]!, length = header.readUInt32LE(1);
      header.fill(0);
      if (![1, 2, 3].includes(type) || length > 65536 || type === 3 && length !== 1) throw new DiagnosticError('ADB_PROTOCOL');
      if (type === 1 && data.length + length > limit) throw new DiagnosticError('FW_LOG_TOO_LARGE');
      const payload = await channel.take(length);
      try {
        if (type === 2 && length) throw new DiagnosticError('ADB_COMMAND_FAILED');
        if (type === 3) {
          if (payload[0] !== 0) throw new DiagnosticError('ADB_COMMAND_FAILED');
          const output = data; data = Buffer.alloc(0); return output;
        }
        if (type === 1) { const combined = Buffer.concat([data, payload]); data.fill(0); data = combined; }
      } finally { payload.fill(0); }
    }
  } finally { data.fill(0); channel.close(); }
}

/** 参数仅用于离线替身测试；产品调用固定使用 127.0.0.1:5037，UI 不接收端点或命令。 */
export async function readFirmwareLogSnapshot(dial: Dial = () => new AdbChannel()): Promise<FirmwareReadResult> {
  const start = performance.now();
  const result: FirmwareReadResult = { source: 'adb-existing', ok: false, baselineMatched: false, closed: false,
    stage: 'existing-server', error: null, hostRequests: 0, remoteCommandsSubmitted: 0, elapsedMs: 0, data: null, commands: [] };
  const submitted = (operation: 'verify' | 'read') => { result.remoteCommandsSubmitted++; result.commands.push({ operation, completed: false, stdoutBytes: 0 }); };
  try {
    result.hostRequests++;
    const id = selectFirmwareTransport(await query(dial, 'host:devices-l'));
    result.stage = 'shell-v2'; result.hostRequests++;
    const features = await query(dial, 'host-transport-id:' + id + ':features');
    if (!features.trim().split(',').includes('shell_v2')) throw new DiagnosticError('ADB_PROTOCOL');
    result.stage = 'baseline';
    const hashes = await runFixedShell(dial, id, 'verify', () => submitted('verify'));
    result.commands.at(-1)!.completed = true; result.commands.at(-1)!.stdoutBytes = hashes.length;
    try { verifyFirmwareHashes(new TextDecoder('utf-8', { fatal: true }).decode(hashes)); } finally { hashes.fill(0); }
    result.baselineMatched = true; result.stage = 'existing-log-buffer';
    const logs = await runFixedShell(dial, id, 'read', () => submitted('read'));
    result.commands.at(-1)!.completed = true; result.commands.at(-1)!.stdoutBytes = logs.length;
    try { result.data = parseFirmwareLog(logs); } finally { logs.fill(0); }
    result.ok = true; result.stage = 'complete';
  } catch (error) { result.error = error instanceof DiagnosticError ? error.code : 'ADB_IO'; }
  finally { result.closed = true; result.elapsedMs = Math.round(performance.now() - start); }
  return result;
}
