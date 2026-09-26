import { performance } from 'node:perf_hooks';
import { EVIDENCE } from './evidence';
import { DiagnosticError, ERROR_MESSAGES, parseParameterBody, ParsedParameters, SafeParameter, Source } from './protocol';
import { isScenario, runSimulation, Scenario } from './simulator';
import { USB_READ_IDS, UsbReadResult } from './usb';
import { FirmwareReadResult } from './adb-log';
import { FirmwareLogData, firmwareReplayFixture, parseFirmwareLog, FIRMWARE_EVENT_CATALOG } from './firmware-log';

export interface DiagnosticEvent {
  time: string; source: Source; operation: string; outcome: string; detail: string;
  status?: number; bytes?: number; elapsedMs?: number;
  parameterId?: number; sequence?: number; writeCompleted?: boolean; replyCompleted?: boolean;
}
export interface Snapshot {
  source: Source; sourceLabel: string; hardwareConnected: boolean | null; hardwareRequests: number | null;
  hardwareEnabled: boolean; lastHardware: UsbReadResult | null;
  rows: SafeParameter[]; hiddenFieldCount: number; events: DiagnosticEvent[]; evidence: typeof EVIDENCE;
  firmware: { source: 'not-read' | 'offline-replay' | 'adb-existing'; enabled: boolean; data: FirmwareLogData | null;
    lastRead: FirmwareReadResult | null; issue: string | null; catalog: typeof FIRMWARE_EVENT_CATALOG };
}
const labels: Record<Source, string> = { 'offline-static': '离线研究 · 无参数快照', 'simulated': '模拟诊断 · 参数值为人工样例', 'offline-import': '离线导入 · 未核实采集来源', 'camera-usb': '实机 USB · 本次受限读取' };

export class DebugService {
  private source: Source = 'offline-static';
  private rows: SafeParameter[] = [];
  private hidden = 0;
  private events: DiagnosticEvent[] = [];
  private busy = false;
  private hardwareRequests: number | null = 0;
  private lastHardware: UsbReadResult | null = null;
  private firmwareSource: 'not-read' | 'offline-replay' | 'adb-existing' = 'not-read';
  private firmwareData: FirmwareLogData | null = null;
  private lastFirmware: FirmwareReadResult | null = null;
  constructor(private readonly readHardware: (() => Promise<UsbReadResult>) | null = null,
    private readonly readFirmware: (() => Promise<FirmwareReadResult>) | null = null) {}
  snapshot(): Snapshot {
    const hardwareConnected = !this.lastHardware || this.lastHardware.closed === true || this.lastHardware.opened === false ? false : null;
    return structuredClone({ source: this.source, sourceLabel: labels[this.source], hardwareConnected,
      hardwareRequests: this.hardwareRequests, hardwareEnabled: this.readHardware !== null, lastHardware: this.lastHardware,
      rows: this.rows, hiddenFieldCount: this.hidden, events: this.events, evidence: EVIDENCE,
      firmware: { source: this.firmwareSource, enabled: this.readFirmware !== null, data: this.firmwareData,
        lastRead: this.lastFirmware, issue: this.lastFirmware?.error ? ERROR_MESSAGES[this.lastFirmware.error] ?? '固件日志读取未完成。' : null,
        catalog: FIRMWARE_EVENT_CATALOG } });
  }
  private add(event: Omit<DiagnosticEvent, 'time'>) { this.events.unshift({ time: new Date().toISOString(), ...event }); this.events.length = Math.min(this.events.length, 80); }
  private replace(parsed: ParsedParameters, source: Source) { this.rows = parsed.rows; this.hidden = parsed.hiddenFieldCount; this.source = source; }
  async simulate(input: unknown): Promise<Snapshot> {
    if (!isScenario(input)) throw new DiagnosticError('IPC_DENIED');
    if (this.busy) throw new DiagnosticError('BUSY');
    this.busy = true;
    this.replace({ rows: [], hiddenFieldCount: 0 }, 'simulated');
    const started = performance.now();
    try {
      const result = await runSimulation(input as Scenario);
      this.replace(result, 'simulated');
      this.add({ source: 'simulated', operation: 'GET /v1/parameters', outcome: 'OK',
        detail: '仅请求本进程的 IPv4 回环模拟器。所有参数值均为人工样例。', status: result.status, bytes: result.bytes, elapsedMs: result.elapsedMs });
    } catch (error) {
      const code = error instanceof DiagnosticError ? error.code : 'INTERNAL_ERROR';
      this.add({ source: 'simulated', operation: 'GET /v1/parameters', outcome: code,
        detail: ERROR_MESSAGES[code] ?? ERROR_MESSAGES.INTERNAL_ERROR!, status: code === 'HTTP_UNAUTHORIZED' ? 401 : code === 'REDIRECT_DENIED' ? 302 : undefined,
        elapsedMs: Math.round((performance.now() - started) * 10) / 10 });
    } finally { this.busy = false; }
    return this.snapshot();
  }
  importBody(body: Uint8Array): Snapshot {
    if (this.busy) throw new DiagnosticError('BUSY');
    this.replace({ rows: [], hiddenFieldCount: 0 }, 'offline-import');
    try {
      const parsed = parseParameterBody(body);
      this.replace(parsed, 'offline-import');
      this.add({ source: 'offline-import', operation: '导入参数 JSON', outcome: 'OK', bytes: body.byteLength,
        detail: '只保留显示白名单；文件名、未知字段、身份数据及未审查原文不进入诊断记录。' });
    } catch (error) {
      const code = error instanceof DiagnosticError ? error.code : 'IMPORT_INVALID';
      this.add({ source: 'offline-import', operation: '导入参数 JSON', outcome: code, detail: ERROR_MESSAGES[code] ?? ERROR_MESSAGES.IMPORT_INVALID! });
    }
    return this.snapshot();
  }
  reset(): Snapshot {
    if (this.busy) throw new DiagnosticError('BUSY');
    this.source = 'offline-static'; this.rows = []; this.hidden = 0; this.events = [];
    this.firmwareSource = 'not-read'; this.firmwareData = null;
    return this.snapshot();
  }
  replayFirmware(): Snapshot {
    if (this.busy) throw new DiagnosticError('BUSY');
    const body = firmwareReplayFixture();
    try { this.firmwareData = parseFirmwareLog(body); } finally { body.fill(0); }
    this.firmwareSource = 'offline-replay';
    return this.snapshot();
  }
  async captureFirmware(): Promise<Snapshot> {
    if (!this.readFirmware) throw new DiagnosticError('HARDWARE_DISABLED');
    if (this.busy) throw new DiagnosticError('BUSY');
    this.busy = true; this.firmwareData = null; this.firmwareSource = 'adb-existing';
    try { this.lastFirmware = await this.readFirmware(); this.firmwareData = this.lastFirmware.data; }
    finally { this.busy = false; }
    return this.snapshot();
  }
  connectHardware(): Promise<Snapshot> {
    if (!this.readHardware) throw new DiagnosticError('HARDWARE_DISABLED');
    if (this.busy) throw new DiagnosticError('BUSY');
    return this.captureHardware();
  }
  private async captureHardware(): Promise<Snapshot> {
    this.busy = true;
    this.replace({ rows: [], hiddenFieldCount: 0 }, 'camera-usb');
    try {
      const result = await this.readHardware!();
      this.lastHardware = result;
      this.hardwareRequests = this.hardwareRequests === null || result.requests === null ? null : this.hardwareRequests + result.requests;
      this.replace({ rows: result.rows, hiddenFieldCount: 0 }, 'camera-usb');
      const accepted = result.rows.filter(row => row.valueState === 'accepted').length;
      for (const step of result.steps) this.add({ source: 'camera-usb', operation: `USB ReadParameter · ID ${step.id}`,
        outcome: step.replyCompleted ? 'REPLY_RECEIVED' : step.writeCompleted ? 'REPLY_INCOMPLETE' : 'WRITE_INCOMPLETE',
        detail: `主机写入${step.writeCompleted ? '完整完成' : '未确认完成'}，参数回复${step.replyCompleted ? '已取得' : '未完成'}。耗时仅表示主机通信与处理，不是闪光或曝光时序。`,
        parameterId: step.id, sequence: step.sequence, writeCompleted: step.writeCompleted, replyCompleted: step.replyCompleted,
        elapsedMs: step.elapsedMs, bytes: step.replyBytes });
      const detail = result.ok ? `USB 读取已回复，接受 ${accepted}/${USB_READ_IDS.length} 项显示值。` : (ERROR_MESSAGES[result.error ?? ''] ?? 'USB 读取未完成，已停止。');
      this.add({ source: 'camera-usb', operation: `USB 调试快照 · ${USB_READ_IDS.join(', ')}`, outcome: result.ok ? 'OK' : result.error ?? 'USB_INTERNAL',
        detail: detail + (result.closed ? ' 本次主机句柄已关闭。' : ' 句柄清理状态未确认。') + (result.win32 ? ` Windows 错误码 ${result.win32}。` : ''),
        elapsedMs: result.elapsedMs, bytes: result.replyBytes });
    } finally { this.busy = false; }
    return this.snapshot();
  }
  disconnect(): Snapshot {
    if (this.busy) throw new DiagnosticError('BUSY');
    this.add({ source: 'offline-static', operation: '断开连接', outcome: 'NO_SESSION', detail: 'USB 读取在完成或失败时自动关闭本次句柄；当前没有持续会话，未发送额外报文。' });
    return this.snapshot();
  }
  report() {
    const s = this.snapshot();
    return { schemaVersion: 1, application: 'Hasselblad 只读调试客户端', createdAt: new Date().toISOString(),
      source: s.source, sourceLabel: s.sourceLabel, hardwareConnected: s.hardwareConnected, hardwareRequests: s.hardwareRequests,
      requestCountBasis: '本程序提交的 ReadParameter 次数，不等于总 USB 帧数',
      lastHardware: s.lastHardware,
      rows: s.rows, hiddenFieldCount: s.hiddenFieldCount, events: s.events,
      firmware: s.firmware,
      analysisBaseline: { model: EVIDENCE.model, firmware: EVIDENCE.firmware, sha256: EVIDENCE.manifest.sha256 }, limitations: EVIDENCE.limitations };
  }
}
