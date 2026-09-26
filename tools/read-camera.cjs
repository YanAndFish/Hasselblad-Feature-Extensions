// 默认仅查看 Windows 设备接口元数据，不打开设备。
const root = require('./runtime-env.cjs')();
const fs = require('node:fs/promises');
const path = require('node:path');
const { probeUsb, readUsbSnapshot } = require('../dist/app/usb.js');
(async () => {
  const args = process.argv.slice(2);
  if (!args.length) return console.log(JSON.stringify(await probeUsb(root)));
  if (args.length !== 1 || args[0] !== '--read') throw new Error('只接受默认元数据模式或 --read');
  const result = await readUsbSnapshot(root);
  const report = { schemaVersion: 1, source: 'camera-usb', capturedAt: new Date().toISOString(), modelScope: '第一代 X2D 100C',
    requestCountBasis: '本程序提交的 ReadParameter 次数，不等于总 USB 帧数',
    analysisBaseline: '官方固件 4.2.0；实机版本以 rows 中 ID 27 的已接受值为准', ...result };
  const directory = path.join(root, 'research', 'validation', 'hardware');
  await fs.mkdir(directory, { recursive: true });
  const reportPath = path.join(directory, 'usb-' + report.capturedAt.replace(/[:.]/g, '-') + '.json');
  await fs.writeFile(reportPath, JSON.stringify(report, null, 2) + '\n', { flag: 'wx' });
  console.log(JSON.stringify({ ...report, reportPath }, null, 2));
})().catch(() => { console.error('USB 调试未完成；没有输出未经审查的原始信息。'); process.exitCode = 1; });
