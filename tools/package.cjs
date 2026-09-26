const root = require('./runtime-env.cjs')();
const fs = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');

(async () => {
  const metadata = require('../package.json');
  const destination = path.join(root, 'release', `Hasselblad-Debug-${metadata.version}`);
  if (!destination.startsWith(root + path.sep)) throw new Error('输出必须位于当前项目');
  const electronRoot = path.dirname(require('electron'));
  await fs.mkdir(destination, { recursive: true });
  // 只复制明确的构建产物；不包含固件、第三方解包源码或研究缓存。
  await fs.cp(electronRoot, destination, { recursive: true, filter: source => path.basename(source) !== 'electron.exe' });
  await fs.copyFile(path.join(electronRoot, 'electron.exe'), path.join(destination, 'Hasselblad-Debug.exe'));
  const appRoot = path.join(destination, 'resources', 'app');
  await fs.mkdir(path.join(appRoot, 'app'), { recursive: true });
  await fs.writeFile(path.join(appRoot, 'package.json'), JSON.stringify({name: metadata.name, version: metadata.version, main: metadata.main},null,2));
  for (const name of ['index.html','style.css']) await fs.copyFile(path.join(root,'app',name),path.join(appRoot,'app',name));
  for (const name of ['app','renderer','research','native']) await fs.cp(path.join(root,'dist',name),path.join(appRoot,'dist',name),{recursive:true});
  await fs.writeFile(path.join(destination,'README.zh-CN.md'), [
    '# Hasselblad 只读调试客户端 ' + metadata.version,
    '',
    '启动同目录的 Hasselblad-Debug.exe，并保留所有随附运行文件。无需安装 Python 或提供相机固件。',
    '',
    '已实现：默认离线、本地 HTTP 模拟诊断、参数 JSON 导入、脱敏报告、研究证据浏览和六项固定 USB 调试读取。',
    '在“连接与证据”点击“读取六项调试快照”，固定读取版本、运行标志、回电等待设置、闪光 EV、电子快门启用和镜头挂载标志，随后关闭本次 USB 句柄。六项已完成一次实机验证，当前快照以本次读取为准。',
    'USB 读取要求 Windows x64、现有正常 WinUSB 控制驱动和已唤醒的第一代 X2D 100C；不安装或修改驱动。无线 HTTP 会话与完整 Phocus 拍摄客户端登记尚未实现。',
    '没有拍摄、写参数、照片读取、地区修改或固件更新功能。模拟值不是实机数据。',
    '“固件内部事件”已实现 10 类真实固件格式的解码、详情显示，以及面向已运行且已授权 ADB server 的固定日志读取模块。该模块尚未实机验证；量产相机合法开启 ADB 的入口尚未证实。',
    'ADB 日志模块先核对两份机内程序哈希，再读取已有 DUSS51 日志；不启动 ADB server，不改变调试、日志或 USB 配置。人工回放仅验证格式和界面。',
    '',
    '导出的报告位于 resources/app/.app-data/desktop/exports。',
    '这只是本地调试构建，未进行提交或远程发布。启动应用不会自动访问相机。',
    '',
    '在原项目目录内可查看 [完整使用说明](../../README.md)、[协议证据](../../research/PROTOCOL_EVIDENCE.md) 和 [电子快门分支分析](../../research/ESHUTTER_BRANCH_ANALYSIS.md)。移动本目录后，这些源项目文档链接可能不可用。',
    ''
  ].join('\n'),'utf8');
  const executable = path.join(destination,'Hasselblad-Debug.exe');
  const sha256 = crypto.createHash('sha256').update(await fs.readFile(executable)).digest('hex');
  const nativeSha256 = crypto.createHash('sha256').update(await fs.readFile(path.join(appRoot,'dist','native','HasselbladUsbReadOnly.exe'))).digest('hex');
  await fs.writeFile(path.join(destination,'build-info.json'),JSON.stringify({applicationVersion:metadata.version,electronVersion:require('electron/package.json').version,builtAt:new Date().toISOString(),executableSha256:sha256,nativeSha256,hardwareTransportReady:true,usbReadIds:[27,28,25,87,88,61],firmwareLogParserReady:true,firmwareLogAdapterReady:true,firmwareLogHardwareValidated:false,firmwareDebugEnablePathVerified:false,hardwareValidation:'USB 六项另见实机报告；ADB 日志与调试详情回传仍未实机验证'},null,2)+'\n');
  console.log(JSON.stringify({directory:destination,executable,hardwareTransportReady:true,usbReadIds:[27,28,25,87,88,61]},null,2));
})().catch(error => { console.error(error.message); process.exitCode = 1; });
