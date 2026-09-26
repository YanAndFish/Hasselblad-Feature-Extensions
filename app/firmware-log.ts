import catalog from '../research/firmware-observer-events.json';
import { DiagnosticError } from './protocol';

export const FIRMWARE_LOG_LIMIT = 512 * 1024;
export const FIRMWARE_EVENT_CATALOG = catalog;
export interface FirmwareEvent {
  sequence: number; inputLine: number; id: string; label: string; function: string;
  emissionVa: string; sourceLine: number; meaning: string;
  fields: { key: string; label: string; value: string; unit: string }[];
}
export interface FirmwareLogData {
  events: FirmwareEvent[]; ignoredLines: number; inputBytes: number;
  ordering: 'log-output-order'; physicalTimingMeasured: false;
}
const escapeRegex = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const patterns = catalog.events.map(definition => {
  const pieces = definition.bodyFormat.split(/(%(?:ld|d|f))/g);
  const pattern = pieces.map(part => part === '%f' ? '([0-9]{1,10}\\.[0-9]{6})'
    : part === '%d' || part === '%ld' ? '(-?(?:0|[1-9][0-9]{0,10}))' : escapeRegex(part)).join('');
  return { definition, regex: new RegExp('^' + pattern + '$') };
});

/** 仅接受固定发射点的 payload；路径、PID、任务名和未知行不会进入输出。 */
export function parseFirmwareLog(body: Uint8Array): FirmwareLogData {
  if (body.byteLength > FIRMWARE_LOG_LIMIT) throw new DiagnosticError('FW_LOG_TOO_LARGE');
  let text: string;
  try { text = new TextDecoder('utf-8', { fatal: true }).decode(body); }
  catch { throw new DiagnosticError('FW_LOG_ENCODING'); }
  if (/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(text)) throw new DiagnosticError('FW_LOG_ENCODING');
  const lines = text.split(/\r?\n/);
  if (lines.length > 5000) throw new DiagnosticError('FW_LOG_TOO_LARGE');
  const events: FirmwareEvent[] = [];
  let ignoredLines = 0;
  for (let index = 0; index < lines.length; index++) {
    const line = lines[index]!;
    if (!line) continue;
    // AOSP logcat brief 的级别/标签/PID 前缀；单独导入时也允许只有固件消息体。
    const message = line.replace(/^[VDIWEF]\/DUSS51\s*\(\s*\d{1,10}\):\s*/, '');
    const match = /^\[rcam\]: \[[^\]\r\n]{1,80}\]\[(Camx_PreStartExpo|Camx_StartExpo|Camx_FlashEnable):(\d{1,4})\](.{1,500})$/.exec(message);
    let accepted = false;
    if (match && line.length <= 2048) {
      for (const { definition: d, regex } of patterns) {
        if (d.function !== match[1] || d.sourceLine !== Number(match[2])) continue;
        const values = regex.exec(match[3]!);
        if (!values || values.length - 1 !== d.fields.length) continue;
        const fields: FirmwareEvent['fields'] = [];
        for (let f = 0; f < d.fields.length; f++) {
          const definition = d.fields[f]!, value = values[f + 1]!;
          const numeric = Number(value);
          if (!Number.isFinite(numeric) || numeric < definition.min || numeric > definition.max
              || definition.type === 'int' && !Number.isSafeInteger(numeric)) break;
          fields.push({ key: definition.key, label: definition.label, value, unit: definition.unit });
        }
        if (fields.length !== d.fields.length) continue;
        if (events.length === 300) throw new DiagnosticError('FW_LOG_TOO_LARGE');
        events.push({ sequence: events.length + 1, inputLine: index + 1, id: d.id, label: d.label,
          function: d.function, emissionVa: d.emissionVa, sourceLine: d.sourceLine, meaning: d.meaning, fields });
        accepted = true;
        break;
      }
    }
    if (!accepted) ignoredLines++;
  }
  return { events, ignoredLines, inputBytes: body.byteLength, ordering: 'log-output-order', physicalTimingMeasured: false };
}

// 严格依据上面的真实固件格式创建测试输入；所有数值为人工值，不能用作相机证据。
export function firmwareReplayFixture(): Buffer {
  const samples: Record<string, string[]> = {
    exposure_requested: ['250000.000000', '24'], eshutter_parameters: ['1000000', '250000'],
    sensor_flush_failed: ['2'], long_exposure_branch: ['24', '250000'], fsync_setup_failed: ['-1']
  };
  return Buffer.from(catalog.events.map(d => {
    let index = 0;
    const body = d.bodyFormat.replace(/%(?:ld|d|f)/g, () => samples[d.id]![index++]!);
    return `I/DUSS51( 100): [rcam]: [fixture][${d.function}:${d.sourceLine}]${body}`;
  }).join('\n') + '\n');
}
