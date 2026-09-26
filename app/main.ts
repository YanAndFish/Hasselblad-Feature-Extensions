import { app, BrowserWindow, dialog, ipcMain, IpcMainInvokeEvent, session, protocol } from 'electron';
import path from 'node:path';
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import { DebugService } from './service';
import { DiagnosticError, ERROR_MESSAGES, MAX_BODY_BYTES } from './protocol';
import { readUsbSnapshot } from './usb';
import { readFirmwareLogSnapshot } from './adb-log';

const productRoot = app.getAppPath();
const stateRoot = path.join(productRoot, '.app-data', process.argv.includes('--smoke') ? 'smoke' : 'desktop');
for (const directory of ['profile', 'session', 'logs', 'tmp', 'exports']) fs.mkdirSync(path.join(stateRoot, directory), { recursive: true });
app.setPath('userData', path.join(stateRoot, 'profile'));
app.setPath('sessionData', path.join(stateRoot, 'session'));
app.setPath('temp', path.join(stateRoot, 'tmp'));
app.setAppLogsPath(path.join(stateRoot, 'logs'));
app.commandLine.appendSwitch('disable-background-networking');
app.commandLine.appendSwitch('disable-component-update');
app.commandLine.appendSwitch('disable-sync');
const entry = path.join(productRoot, 'app', 'index.html');
const entryURL = 'hasselblad://app/index.html';
protocol.registerSchemesAsPrivileged([{ scheme: 'hasselblad', privileges: { standard: true, secure: true, corsEnabled: true } }]);
// UI 冒烟测试始终没有实机适配器；正常启动也只在用户点击固定读取按钮时打开。
const service = new DebugService(process.argv.includes('--smoke') ? null : () => readUsbSnapshot(productRoot),
  process.argv.includes('--smoke') ? null : () => readFirmwareLogSnapshot());
let window: BrowserWindow | null = null;

function validCaller(event: IpcMainInvokeEvent) {
  return !!window && event.sender === window.webContents && event.senderFrame === window.webContents.mainFrame
    && event.senderFrame?.url === entryURL;
}
function register(channel: string, handler: (...args: unknown[]) => unknown | Promise<unknown>) {
  ipcMain.handle(channel, async (event, ...args: unknown[]) => {
    try {
      if (!validCaller(event)) throw new DiagnosticError('IPC_DENIED');
      return { ok: true, data: await handler(...args) };
    } catch (error) {
      const code = error instanceof DiagnosticError ? error.code : 'INTERNAL_ERROR';
      return { ok: false, code, message: ERROR_MESSAGES[code] ?? ERROR_MESSAGES.INTERNAL_ERROR };
    }
  });
}
const noArgs = (args: unknown[]) => { if (args.length) throw new DiagnosticError('IPC_DENIED'); };

register('debug:snapshot', (...args) => { noArgs(args); return service.snapshot(); });
register('debug:simulate', (...args) => {
  if (args.length !== 1) throw new DiagnosticError('IPC_DENIED');
  return service.simulate(args[0]);
});
register('debug:reset', (...args) => { noArgs(args); return service.reset(); });
register('debug:connect', (...args) => { noArgs(args); return service.connectHardware(); });
register('debug:disconnect', (...args) => { noArgs(args); return service.disconnect(); });
register('debug:firmware-replay', (...args) => { noArgs(args); return service.replayFirmware(); });
register('debug:firmware-read', (...args) => { noArgs(args); return service.captureFirmware(); });
register('debug:import', async (...args) => {
  noArgs(args);
  const selected = await dialog.showOpenDialog(window!, { title: '导入离线参数响应（不从相机采集）',
    filters: [{ name: '参数 JSON', extensions: ['json'] }], properties: ['openFile'] });
  if (selected.canceled || !selected.filePaths[0]) return service.snapshot();
  const file = selected.filePaths[0];
  // 路径与文件原文都不进入 renderer、日志或报告。
  try {
    const stat = await fsp.lstat(file);
    if (!stat.isFile() || stat.isSymbolicLink() || stat.size > MAX_BODY_BYTES || path.extname(file).toLowerCase() !== '.json') throw new Error();
    const handle = await fsp.open(file, 'r');
    try {
      const bytes = Buffer.alloc(MAX_BODY_BYTES + 1);
      let count = 0;
      while (count < bytes.length) {
        const result = await handle.read(bytes, count, bytes.length - count, count);
        if (!result.bytesRead) break;
        count += result.bytesRead;
      }
      if (count > MAX_BODY_BYTES) throw new Error();
      const result = service.importBody(bytes.subarray(0, count));
      bytes.fill(0);
      return result;
    } finally { await handle.close(); }
  } catch { throw new DiagnosticError('IMPORT_INVALID'); }
});
register('debug:export', async (...args) => {
  noArgs(args);
  const name = 'diagnostic-' + new Date().toISOString().replace(/[:.]/g, '-') + '.json';
  const target = path.join(stateRoot, 'exports', name);
  try { await fsp.writeFile(target, JSON.stringify(service.report(), null, 2) + '\n', { encoding: 'utf-8', flag: 'wx' }); }
  catch { throw new DiagnosticError('EXPORT_FAILED'); }
  return { path: target, name };
});

app.whenReady().then(() => {
  // Chromium 渲染会话只读本地应用资源。设备/模拟 HTTP 仅存在于 Node 主进程。
  session.defaultSession.setPermissionRequestHandler((_wc, _permission, callback) => callback(false));
  session.defaultSession.setPermissionCheckHandler(() => false);
  session.defaultSession.on('will-download', event => event.preventDefault());
  const resources = new Map([
    [entryURL, { file: entry, type: 'text/html; charset=utf-8' }],
    ['hasselblad://app/style.css', { file: path.join(productRoot, 'app/style.css'), type: 'text/css' }],
    ['hasselblad://app/dist/renderer/renderer.js', { file: path.join(productRoot, 'dist/renderer/renderer.js'), type: 'text/javascript' }]
  ]);
  protocol.handle('hasselblad', async request => {
    const resource = resources.get(request.url);
    if (request.method !== 'GET' || !resource) return new Response(null, { status: 404 });
    return new Response(await fsp.readFile(resource.file), { headers: { 'Content-Type': resource.type, 'X-Content-Type-Options': 'nosniff' } });
  });
  session.defaultSession.webRequest.onBeforeRequest((details, callback) => callback({ cancel: !resources.has(details.url) }));
  window = new BrowserWindow({ width: 1400, height: 940, minWidth: 1080, minHeight: 740,
    backgroundColor: '#101214', title: 'Hasselblad · 只读调试客户端', show: false, autoHideMenuBar: true,
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false,
      sandbox: true, webSecurity: true, allowRunningInsecureContent: false, spellcheck: false, devTools: false } });
  window.setMenu(null);
  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  window.webContents.on('will-navigate', event => event.preventDefault());
  window.webContents.on('will-attach-webview', event => event.preventDefault());
  window.once('ready-to-show', () => { if (process.argv.includes('--smoke')) window?.showInactive(); else window?.show(); });
  void window.loadURL(entryURL);
  window.on('closed', () => { window = null; });
});
app.on('window-all-closed', () => app.quit());
