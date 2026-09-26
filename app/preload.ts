import { contextBridge, ipcRenderer } from 'electron';

// 只暴露固定方法；不暴露 ipcRenderer、channel、URL、端口、请求头或脚本能力。
contextBridge.exposeInMainWorld('debugClient', Object.freeze({
  snapshot: () => ipcRenderer.invoke('debug:snapshot'),
  simulate: (scenario: string) => ipcRenderer.invoke('debug:simulate', scenario),
  reset: () => ipcRenderer.invoke('debug:reset'),
  connect: () => ipcRenderer.invoke('debug:connect'),
  disconnect: () => ipcRenderer.invoke('debug:disconnect'),
  replayFirmware: () => ipcRenderer.invoke('debug:firmware-replay'),
  readFirmware: () => ipcRenderer.invoke('debug:firmware-read'),
  importParameters: () => ipcRenderer.invoke('debug:import'),
  exportReport: () => ipcRenderer.invoke('debug:export')
}));
