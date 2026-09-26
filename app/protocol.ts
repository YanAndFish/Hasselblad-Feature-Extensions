/** 仅支持已核实的 4.2.0 响应外形。此模块不建立相机会话。 */
export const MAX_BODY_BYTES = 256 * 1024;
export const REQUEST_TIMEOUT_MS = 2000;
export const READ_SPEC = Object.freeze({ method: 'GET', path: '/v1/parameters' });

export type Source = 'offline-static' | 'simulated' | 'offline-import' | 'camera-usb';
export interface ParameterDefinition {
  id: number; name: string; label: string; category: 'device' | 'lens' | 'trigger' | 'region';
  unit: string; displayRule: 'version' | 'number' | 'lens'; max?: number; note: string;
}
export const DEFINITIONS: readonly ParameterDefinition[] = Object.freeze([
  { id: 15, name: 'kSensorUnitFirmwareVersionCamParam', label: '传感器单元固件标识', category: 'device', unit: '无', displayRule: 'version', note: '与 ID 27 共用 version_id 读取分支；不是独立读取传感器 MCU。' },
  { id: 17, name: 'kSensorUnitTypeCamParam', label: '传感器单元类型', category: 'device', unit: '枚举，未解码', displayRule: 'number', max: 65535, note: '来自 prodinfo 代理；名称不代表型号字符串。' },
  { id: 23, name: 'kBodyTypeCamParam', label: '机身类型', category: 'device', unit: '枚举，未解码', displayRule: 'number', max: 65535, note: '客户端机型码，不能代替实机型号核验。' },
  { id: 25, name: 'kFlashRechargeSecondsCamParam', label: '闪光回电等待设置', category: 'trigger', unit: 's（由参数名推断）', displayRule: 'number', max: 3600, note: '读取缓存的 flash_recharge_delay 设置；不是实时充电就绪、实测回电时长或 Xsync 提前量。' },
  { id: 27, name: 'kFirmwareVersionCamParam', label: '固件版本标识', category: 'device', unit: '无', displayRule: 'version', note: '读取 SystemProxyDbus::version_id；以本次已接受的实机结果确认版本。' },
  { id: 28, name: 'kRunningCamParam', label: '系统运行标志', category: 'device', unit: '布尔编码（4.2.0 静态）', displayRule: 'number', max: 1, note: '4.2.0 分支将 system_state == 1 映射为 1，其余为 0；不是完整状态枚举或曝光时序。' },
  { id: 46, name: 'kFocalLengthCamParam', label: '镜头焦距', category: 'lens', unit: '单位待核实', displayRule: 'number', max: 100000, note: '已有读取分支；传输数值与物理单位的映射待核实。' },
  { id: 47, name: 'kBatteryCamParam', label: '电池状态', category: 'device', unit: '编码待核实', displayRule: 'number', max: 65535, note: '不预设其一定是百分比。' },
  { id: 61, name: 'kLensMountedCamParam', label: '镜头挂载标志', category: 'lens', unit: '0 / 1', displayRule: 'number', max: 1, note: 'attached_lens 非零映射为 1；不是镜头快门就绪或 HasDoubleFSync 能力。' },
  { id: 74, name: 'kLensFirmwareVersionParam', label: '镜头固件标识', category: 'lens', unit: '无', displayRule: 'version', note: '读取 CameraProxyDbus::lens_version。' },
  { id: 75, name: 'kLensProductIDParam', label: '镜头产品 ID', category: 'lens', unit: '产品码', displayRule: 'number', max: 65535, note: '产品 ID 不等于设备序列号。' },
  { id: 87, name: 'kFlashEvAdjustCamParam', label: '闪光曝光补偿', category: 'trigger', unit: 'EV', displayRule: 'number', max: 100, note: 'flash_ev_adj / 12.0；USB 显示最多六位小数，按需要舍入。这是曝光补偿，不是 Fsync 时间修正。' },
  { id: 88, name: 'kEShutterCamParam', label: '电子快门启用状态', category: 'trigger', unit: '0 / 1', displayRule: 'number', max: 1, note: '读取缓存的 eshutter_current；不是曝光进行状态，不能推出传感器有效感光窗口。' },
  { id: 91, name: 'kLensMinimumObjectDistanceCamParam', label: '最近对焦距离', category: 'lens', unit: '单位待核实', displayRule: 'number', max: 100000, note: '镜头能力候选；不触发对焦。' },
  { id: 118, name: 'kLanguageCamParam', label: '菜单语言', category: 'region', unit: '协议语言枚举', displayRule: 'number', max: 255, note: 'language_index 经 Cam2Phocus_Language 转换；不能据此判断销售地区。' },
  { id: 120, name: 'kLensProductNameCamParam', label: '镜头产品名称', category: 'lens', unit: '无', displayRule: 'lens', note: '只保留符合 XCD 名称格式的显示值，其余隐藏。' },
  { id: 122, name: 'kTetheredModeCamParam', label: '联机模式', category: 'device', unit: '枚举，未解码', displayRule: 'number', max: 255, note: '模式快照；只读软件的会话仍可能影响这个状态。' },
  { id: 136, name: 'kLensSupportFocusAdjustCamParam', label: '镜头焦点微调能力', category: 'lens', unit: '状态码', displayRule: 'number', max: 1, note: '不是 HasDoubleFSync 能力位。' }
]);

export class DiagnosticError extends Error {
  constructor(public readonly code: string) { super(code); }
}
export function assertReadSpec(method: unknown, path: unknown): void {
  if (method !== READ_SPEC.method || path !== READ_SPEC.path) throw new DiagnosticError('REQUEST_DENIED');
}
export interface SafeParameter {
  id: number; name: string; label: string; category: ParameterDefinition['category'];
  wireType: 'string'; unit: string; value: string | null; valueState: 'accepted' | 'hidden' | 'unavailable';
  canGet: boolean; cameraCanSet: boolean | null; clientCanSet: false; range: string | null; note: string;
}
export interface ParsedParameters { rows: SafeParameter[]; hiddenFieldCount: number; }
const plainObject = (x: unknown): x is Record<string, unknown> => !!x && typeof x === 'object' && !Array.isArray(x);

export function safeValue(value: string, d: ParameterDefinition): string | null {
  if (value.length > 96 || /[\u0000-\u001f\u007f]/.test(value)) return null;
  // 此函数只接收已规范化文本；USB 的 ToString 编码由独立白名单解析器处理。
  if (d.displayRule === 'version') return /^\d{1,3}(?:\.\d{1,3}){1,4}$/.test(value) ? value : null;
  if (d.displayRule === 'lens') return /^XCD\s\d{1,3}(?:-\d{1,3})?(?:P|V|E)?(?:\s\d(?:\.\d)?\/\d{1,3}(?:-\d{1,3})?)?$/.test(value) ? value : null;
  if (!(d.id === 87 ? /^-?\d{1,6}(?:\.\d{1,6})?$/ : /^-?\d{1,6}(?:\.\d{1,4})?$/).test(value)) return null;
  const n = Number(value);
  return Number.isFinite(n) && n >= (d.id === 87 ? -(d.max ?? 100) : 0) && n <= (d.max ?? 65535) ? value : null;
}

export function parseParameterBody(body: Uint8Array): ParsedParameters {
  if (body.byteLength > MAX_BODY_BYTES) throw new DiagnosticError('BODY_TOO_LARGE');
  let raw: unknown;
  try { raw = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(body)); }
  catch { throw new DiagnosticError('INVALID_JSON'); }
  if (!plainObject(raw)) throw new DiagnosticError('INVALID_SCHEMA');
  const keys = Object.keys(raw);
  if (keys.length > 256 || keys.some(k => !/^[1-9]\d{0,2}$/.test(k))) throw new DiagnosticError('INVALID_SCHEMA');
  const rows: SafeParameter[] = [];
  for (const d of DEFINITIONS) {
    const entry = raw[String(d.id)];
    if (entry === undefined) continue;
    if (!plainObject(entry) || typeof entry.can_get !== 'boolean' || typeof entry.can_set !== 'boolean'
        || typeof entry.value !== 'string' || typeof entry.range !== 'string'
        || entry.range.length > 2048 || entry.value.length > 8192) throw new DiagnosticError('INVALID_SCHEMA');
    const value = entry.can_get ? safeValue(entry.value, d) : null;
    // range 的 ToString 编码未完成语义审查，不把未经审查的范围原文带入报告。
    const range = entry.range === '' ? '' : null;
    rows.push({ id: d.id, name: d.name, label: d.label, category: d.category, wireType: 'string', unit: d.unit,
      value, valueState: !entry.can_get ? 'unavailable' : value === null ? 'hidden' : 'accepted',
      canGet: entry.can_get, cameraCanSet: entry.can_set, clientCanSet: false, range, note: d.note });
  }
  if (!rows.length) throw new DiagnosticError('NO_ALLOWLISTED_PARAMETERS');
  return { rows, hiddenFieldCount: keys.length - rows.length };
}

export const ERROR_MESSAGES: Readonly<Record<string, string>> = Object.freeze({
  ADB_SERVER_UNAVAILABLE: '没有可连接的本机 ADB server；需要已经合法开启并授权的调试连接。',
  ADB_NOT_PRESENT: '本机 ADB server 未列出相机。', ADB_AMBIGUOUS: 'ADB 中存在多个设备，已停止。',
  ADB_NOT_AUTHORIZED: 'ADB 设备未处于已授权可用状态，已停止。',
  ADB_TARGET_MISMATCH: 'ADB 设备标识与官方 Eagle2 EC1706 基线不符，已停止。',
  ADB_REJECTED: 'ADB 拒绝了固定请求，已停止；不保留错误原文。',
  ADB_PROTOCOL: 'ADB 响应或 shell v2 能力不符合协议，已停止。',
  ADB_COMMAND_FAILED: '固定读取命令未成功退出，已停止。',
  ADB_IO: 'ADB 传输失败，已停止。', ADB_TIMEOUT: 'ADB 通道超时，主机连接已关闭。',
  ADB_TRUNCATED: 'ADB 响应不完整，已停止。',
  FW_BASELINE_MISMATCH: '机内两个二进制哈希未匹配 X2D 4.2.0；没有继续读取日志。',
  FW_LOG_TOO_LARGE: '日志或协议数据超出本地读取上限，已停止。',
  FW_LOG_ENCODING: '日志包含不支持的编码或控制字符，已停止。',
  REQUEST_DENIED: '请求不在只读白名单内，已拒绝。', HARDWARE_DISABLED: '当前运行实例未启用实机读取；没有打开设备或发送报文。',
  USB_REQUEST_DENIED: 'USB 请求不在固定调试白名单内，已拒绝。',
  USB_VALUE_UNREVIEWED: '收到未经审查的参数编码；已隐藏内容并停止后续读取。',
  USB_FIRMWARE_MISMATCH: '本次机身版本与 4.2.0 分析基线不同；停止后续调试读取。',
  USB_CAMERA_NOT_RUNNING: '本次系统运行标志为 0；停止后续调试读取。',
  USB_PLATFORM: 'USB 控制通道需要 Windows x64。', USB_NOT_PRESENT: 'Windows 当前未发现匹配的 X2D USB 控制接口。',
  USB_AMBIGUOUS: '存在多个匹配接口，已停止；没有自行选择设备。', USB_OPEN: 'USB 控制接口未能打开。',
  USB_INITIALIZE: '现有设备接口未能初始化为 WinUSB；没有修改驱动。',
  USB_INTERFACE_MISMATCH: '实际 USB 接口描述与已审查路径不符，已停止。', USB_PIPE_MISMATCH: '未找到符合条件的控制端点，已停止。',
  USB_READ: 'USB 回包读取未完成；停止，不自动重试。', USB_WRITE: '只读请求发送未完成；停止，不自动重试。',
  USB_HELPER_TIMEOUT: '本机 USB 辅助进程超过总时限；请求数与清理状态待确认。',
  USB_HELPER_UNAVAILABLE: '本机 USB 辅助程序不可用。', USB_HELPER_INVALID: 'USB 辅助结果不符合受限结构，原文已隐藏。',
  USB_REPLY_ROUTE: 'USB 回包路由不符合已审查协议，已停止。', USB_REPLY_SEQUENCE: 'USB 回包序号与本次请求不符，已停止。',
  USB_REPLY_TYPE: 'USB 回包类型不是参数读取响应，已停止。', USB_FRAME_LENGTH: 'USB 回包长度不符合已审查协议，已停止。',
  USB_CLOSE: '读取已结束，但 WinUSB 资源释放没有得到成功返回。',
  HTTP_UNAUTHORIZED: '访问检查未通过；停止，不重试、不猜测客户端标识。', REDIRECT_DENIED: '响应要求重定向，已拒绝跟随。',
  BODY_TOO_LARGE: '响应超过 256 KiB 上限，已终止读取。', TIMEOUT: '超过总时限，连接已关闭。',
  INVALID_JSON: '内容不是有效 UTF-8 JSON，未显示原始数据。', INVALID_SCHEMA: '响应结构不符合已核实的参数外形。',
  NO_ALLOWLISTED_PARAMETERS: '没有可显示的白名单参数。', CONTENT_TYPE_DENIED: '响应类型不受支持。',
  HTTP_ERROR: 'HTTP 响应状态不支持。', NETWORK_ERROR: '本地模拟连接失败。', BUSY: '已有诊断正在执行。',
  IMPORT_INVALID: '只接受 256 KiB 以内的普通 JSON 文件。', IPC_DENIED: '调用来源或参数不受支持。',
  EXPORT_FAILED: '报告写入失败。', INTERNAL_ERROR: '诊断未完成，原始异常信息已隐藏。'
});
