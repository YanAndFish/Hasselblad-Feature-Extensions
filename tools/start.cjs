const root = require('./runtime-env.cjs')();
const { spawn } = require('node:child_process');
const child = spawn(require('electron'), [root], { cwd: root, env: process.env, windowsHide: true, stdio: 'inherit' });
child.on('exit', code => { process.exitCode = code ?? 1; });
child.on('error', () => { console.error('桌面客户端启动失败。'); process.exitCode = 1; });
