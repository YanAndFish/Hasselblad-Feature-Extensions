// 默认仅输出接入条件；显式 --read-existing 才访问已经运行的本机 ADB server。
const fs = require('node:fs/promises');
const path = require('node:path');
const { readFirmwareLogSnapshot, FIRMWARE_COMMANDS } = require('../dist/app/adb-log');
const root = path.resolve(__dirname, '..');
(async () => {
  const args = process.argv.slice(2);
  if (!args.length) {
    console.log(JSON.stringify({mode:'requirements',hardwareRequests:0,
      requirement:'相机已有合法授权的 ADB 调试连接、本机 ADB server 已运行、当次已唤醒。量产 ADB 合法开启入口未证实。',
      commands:FIRMWARE_COMMANDS,argument:'--read-existing',endToEndHardwareValidated:false},null,2));
    return;
  }
  if (args.length !== 1 || args[0] !== '--read-existing') throw new Error('仅支持默认条件说明或固定 --read-existing');
  const result = await readFirmwareLogSnapshot();
  const target = path.join(root,'research','validation','hardware','firmware-logs-'+new Date().toISOString().replace(/[:.]/g,'-')+'.json');
  await fs.mkdir(path.dirname(target),{recursive:true});
  await fs.writeFile(target,JSON.stringify({schemaVersion:1,...result},null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify({report:target,...result},null,2));
  if (!result.ok) process.exitCode=1;
})().catch(() => { console.error('固件日志读取或报告保存未完成；未重试。'); process.exitCode=1; });
