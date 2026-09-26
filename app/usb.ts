import { spawn } from 'node:child_process';
import path from 'node:path';
import fs from 'node:fs';
import { DEFINITIONS, DiagnosticError, SafeParameter, safeValue } from './protocol';

export const USB_READ_IDS = Object.freeze([27, 28, 25, 87, 88, 61] as const);
const FAILURE_CODES = new Set(['USB_REQUEST_DENIED', 'USB_FRAME_LENGTH', 'USB_REPLY_ROUTE', 'USB_REPLY_SEQUENCE', 'USB_REPLY_TYPE',
  'USB_ENUMERATE', 'USB_ENUMERATE_LIMIT', 'USB_NOT_PRESENT', 'USB_AMBIGUOUS', 'USB_OPEN', 'USB_INITIALIZE', 'USB_INTERFACE',
  'USB_INTERFACE_MISMATCH', 'USB_PIPE', 'USB_PIPE_MISMATCH', 'USB_TIMEOUT_POLICY', 'USB_WRITE', 'USB_SHORT_WRITE', 'USB_READ',
  'USB_REPLY_LIMIT', 'USB_INTERNAL', 'USB_HELPER_FAILED', 'USB_CLOSE', 'USB_VALUE_UNREVIEWED', 'USB_FIRMWARE_MISMATCH', 'USB_CAMERA_NOT_RUNNING']);
export interface UsbReadStep {
  id: number; sequence: number; writeCompleted: boolean; replyCompleted: boolean; replyBytes: number; elapsedMs: number;
}
export interface UsbReadResult {
  ok: boolean; rows: SafeParameter[]; requests: number | null; opened: boolean | null; closed: boolean | null;
  error: string | null; win32: number | null; elapsedMs: number; replyBytes: number;
  interfaceNumber: number | null; pipeIn: number | null; pipeOut: number | null;
  steps: UsbReadStep[];
}
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
const integer = (n: unknown, min: number, max: number): n is number => typeof n === 'number' && Number.isInteger(n) && n >= min && n <= max;

/** 只解码固定调试批次的 ToString 外形；陌生内容不进入显示层。 */
export function decodeUsbValue(id: number, body: Uint8Array): SafeParameter {
  const definition = DEFINITIONS.find(d => d.id === id);
  if (!definition || !USB_READ_IDS.some(x => x === id)) throw new DiagnosticError('USB_REQUEST_DENIED');
  let decoded: string | null = null;
  if (body.length <= 100) {
    let text: string | null = null;
    try { text = new TextDecoder('utf-8', { fatal: true }).decode(body); } catch { /* 隐藏未知编码 */ }
    if (text !== null && /^[\x20-\x7e]*$/.test(text)) {
      if (id === 27) {
        // type 4：单字符 sX；数组 S<字节数>,<原字符串>。固件版本存储不带 NUL。
        const match = /^S([2-9]|[1-9]\d),(.{2,96})$/.exec(text);
        if (match && Number(match[1]) === Buffer.byteLength(match[2]!, 'utf8')) {
          // camera-system 4.2.0 version_id 使用已核实的 "v%1"；显示规范化为点分版本。
          const version = match[2]!.startsWith('v') ? match[2]!.slice(1) : match[2]!;
          decoded = safeValue(version, definition);
        }
      } else if (id === 87) {
        // type 3：f + sprintf("%llx", double 的原始 64 位)，不是十进制或时间。
        if (/^f(?:0|[1-9a-f][0-9a-f]{0,15})$/.test(text)) {
          const bits = Buffer.alloc(8);
          try {
            bits.writeBigUInt64LE(BigInt('0x' + text.slice(1)));
            const value = bits.readDoubleLE();
            if (Number.isFinite(value) && Math.abs(value) <= 100 && Math.abs(value * 12 - Math.round(value * 12)) < 1e-8)
              decoded = safeValue(Number(value.toFixed(6)).toString(), definition);
          } finally { bits.fill(0); }
        }
      } else if (id === 25) {
        if (/^i(?:0|[1-9]\d{0,3})$/.test(text)) decoded = safeValue(text.slice(1), definition);
      } else if (/^i[01]$/.test(text)) decoded = text.slice(1);
    }
  }
  return { id, name: definition.name, label: definition.label, category: definition.category, wireType: 'string', unit: definition.unit,
    value: decoded, valueState: body.length === 0 ? 'unavailable' : decoded === null ? 'hidden' : 'accepted',
    canGet: body.length !== 0, cameraCanSet: null, clientCanSet: false, range: null, note: definition.note };
}

/** 对私有辅助进程输出进行第二次结构校验，不向调用者返回原始字节。 */
export function parseUsbHelperResult(body: string): UsbReadResult {
  let raw: unknown;
  try { raw = JSON.parse(body); } catch { throw new DiagnosticError('USB_HELPER_INVALID'); }
  if (!object(raw) || typeof raw.Ok !== 'boolean' || typeof raw.Opened !== 'boolean' || typeof raw.Closed !== 'boolean'
      || !integer(raw.Requests, 0, USB_READ_IDS.length) || !integer(raw.ReplyBytes, 0, 6144) || !integer(raw.ElapsedMs, 0, 35000)
      || !integer(raw.Win32, 0, 0xffffffff) || typeof raw.Error !== 'string' || !Array.isArray(raw.Values)
      || raw.Values.length > raw.Requests || raw.Values.length > USB_READ_IDS.length || !integer(raw.InterfaceNumber, -1, 255)
      || !Array.isArray(raw.Steps) || raw.Steps.length !== raw.Requests
      || !integer(raw.PipeIn, -1, 255) || !integer(raw.PipeOut, -1, 255)) throw new DiagnosticError('USB_HELPER_INVALID');
  if ((raw.Ok && (raw.Error !== '' || raw.Values.length !== USB_READ_IDS.length || !raw.Opened || !raw.Closed))
      || (!raw.Ok && !FAILURE_CODES.has(raw.Error))) throw new DiagnosticError('USB_HELPER_INVALID');
  const rows = raw.Values.map((item: unknown, index: number) => {
    if (!object(item) || !integer(item.Id, 0, 65535) || item.Id !== USB_READ_IDS[index] || typeof item.Encoded !== 'string' || item.Encoded.length > 800
        || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(item.Encoded)) throw new DiagnosticError('USB_HELPER_INVALID');
    const bytes = Buffer.from(item.Encoded, 'base64');
    try {
      if (bytes.length > 600 || bytes.toString('base64') !== item.Encoded) throw new DiagnosticError('USB_HELPER_INVALID');
      return decodeUsbValue(item.Id, bytes);
    } finally { bytes.fill(0); }
  });
  const steps: UsbReadStep[] = raw.Steps.map((step: unknown, index: number) => {
    if (!object(step) || step.Id !== USB_READ_IDS[index] || step.Sequence !== index + 1
        || typeof step.WriteCompleted !== 'boolean' || typeof step.ReplyCompleted !== 'boolean'
        || !integer(step.ReplyBytes, 0, 1024) || !integer(step.ElapsedMs, 0, 35000)
        || (step.ReplyCompleted && (!step.WriteCompleted || step.ReplyBytes < 8))
        || (index < rows.length && !step.ReplyCompleted) || (raw.Ok && !step.ReplyCompleted)) throw new DiagnosticError('USB_HELPER_INVALID');
    return { id: USB_READ_IDS[index]!, sequence: index + 1, writeCompleted: step.WriteCompleted,
      replyCompleted: step.ReplyCompleted, replyBytes: step.ReplyBytes, elapsedMs: step.ElapsedMs };
  });
  if (steps.reduce((sum, step) => sum + step.replyBytes, 0) !== raw.ReplyBytes) throw new DiagnosticError('USB_HELPER_INVALID');
  if (raw.Ok && (rows.some(row => row.valueState !== 'accepted') || rows[0]?.value !== '4.2.0' || rows[1]?.value !== '1'))
    throw new DiagnosticError('USB_HELPER_INVALID');
  return { ok: raw.Ok, rows, requests: raw.Requests, opened: raw.Opened, closed: raw.Closed, error: raw.Ok ? null : raw.Error,
    win32: raw.Win32 || null, elapsedMs: raw.ElapsedMs, replyBytes: raw.ReplyBytes,
    interfaceNumber: raw.InterfaceNumber < 0 ? null : raw.InterfaceNumber, pipeIn: raw.PipeIn < 0 ? null : raw.PipeIn, pipeOut: raw.PipeOut < 0 ? null : raw.PipeOut, steps };
}

function runHelper(root: string, mode: 'metadata' | 'snapshot'): Promise<string> {
  if (process.platform !== 'win32' || process.arch !== 'x64') throw new DiagnosticError('USB_PLATFORM');
  const executable = path.join(root, 'dist', 'native', 'HasselbladUsbReadOnly.exe');
  const temporary = path.join(root, '.app-data', 'usb-tmp');
  fs.mkdirSync(temporary, { recursive: true });
  return new Promise((resolve, reject) => {
    const child = spawn(executable, [mode], { cwd: root, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'],
      env: { SystemRoot: process.env.SystemRoot, WINDIR: process.env.WINDIR, TEMP: temporary, TMP: temporary } });
    let output = Buffer.alloc(0); let settled = false;
    const finish = (error?: string) => {
      if (settled) return; settled = true; clearTimeout(timer);
      if (error) { child.kill(); reject(new DiagnosticError(error)); } else resolve(output.toString('utf8').replace(/^\uFEFF/, ''));
      output.fill(0);
    };
    const timer = setTimeout(() => finish('USB_HELPER_TIMEOUT'), 30000);
    child.stdout.on('data', (chunk: Buffer) => {
      if (settled) return;
      if (output.length + chunk.length > 8192) return finish('USB_HELPER_INVALID');
      output = Buffer.concat([output, chunk]);
    });
    // 不把设备路径、原始异常或 stdout 内容带入应用日志。
    child.stderr.on('data', () => { /* 丢弃；错误仅使用固定代码。 */ });
    child.once('error', () => finish('USB_HELPER_UNAVAILABLE'));
    child.once('close', (code) => finish(code === 0 ? undefined : 'USB_HELPER_FAILED'));
  });
}
export async function probeUsb(root: string): Promise<{ matchingInterfaces: number; opened: false; requests: 0 }> {
  const raw: unknown = JSON.parse(await runHelper(root, 'metadata'));
  if (!object(raw) || !integer(raw.MatchingInterfaces, 0, 128) || raw.Opened !== false || raw.Requests !== 0) throw new DiagnosticError('USB_HELPER_INVALID');
  return { matchingInterfaces: raw.MatchingInterfaces, opened: false, requests: 0 };
}
export async function readUsbSnapshot(root: string): Promise<UsbReadResult> {
  const started = performance.now();
  try { return parseUsbHelperResult(await runHelper(root, 'snapshot')); }
  catch (error) {
    // 辅助进程失联时不能把请求数或清理状态写成零/已关闭。
    return { ok: false, rows: [], requests: null, opened: null, closed: null, error: error instanceof DiagnosticError ? error.code : 'USB_INTERNAL',
      win32: null, elapsedMs: Math.round(performance.now() - started), replyBytes: 0, interfaceNumber: null, pipeIn: null, pipeOut: null, steps: [] };
  }
}
