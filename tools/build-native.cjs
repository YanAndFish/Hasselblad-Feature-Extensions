// 仅编译本项目的 WinUSB 辅助程序；不安装驱动、不执行硬件读取。
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const root = require('./runtime-env.cjs')();
if (process.platform !== 'win32' || process.arch !== 'x64') throw new Error('本地 WinUSB 桥仅支持 Windows x64');
const compiler = path.join(process.env.SystemRoot || 'C:\\Windows', 'Microsoft.NET', 'Framework64', 'v4.0.30319', 'csc.exe');
fs.mkdirSync(path.join(root, 'dist', 'native'), { recursive: true });
const result = spawnSync(compiler, ['/nologo', '/target:exe', '/platform:x64', '/optimize+', '/reference:System.Web.Extensions.dll',
  '/out:' + path.join(root, 'dist', 'native', 'HasselbladUsbReadOnly.exe'), path.join(root, 'native', 'WinUsbReadOnly.cs'), path.join(root, 'native', 'Program.cs')],
{ cwd: root, windowsHide: true, encoding: 'utf8', timeout: 30000 });
if (result.status !== 0) { process.stderr.write(result.stdout || result.stderr || '本机 .NET 编译器不可用'); process.exitCode = 1; }
else process.stdout.write('WinUSB 只读辅助程序编译通过；没有打开设备。\n');
