// preload.js — 预加载脚本，暴露安全的 IPC 接口
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('labAPI', {
  scanExperiments: () => ipcRenderer.invoke('scan-experiments'),
  openFile: (filePath) => ipcRenderer.invoke('open-file', filePath),
  runGenerate: (expPath, studentInfo, variants, polish) => ipcRenderer.invoke('run-generate', expPath, studentInfo, variants, polish),
  cancelGenerate: () => ipcRenderer.invoke('cancel-generate'),
  onGenerateLog: (callback) => {
    ipcRenderer.on('generate-log', (_, data) => callback(data));
  },
  // 窗口控制
  minimize: () => ipcRenderer.send('window-minimize'),
  toggleMaximize: () => ipcRenderer.send('window-maximize'),
  close: () => ipcRenderer.send('window-close'),
  // 方式三：schema/data 读写（表单模式）
  readSchema: (expPath) => ipcRenderer.invoke('read-schema', expPath),
  readData: (expPath) => ipcRenderer.invoke('read-data', expPath),
  writeData: (expPath, data) => ipcRenderer.invoke('write-data', expPath, data),
  readRag: (expPath) => ipcRenderer.invoke('read-rag', expPath),
  readSections: (expPath) => ipcRenderer.invoke('read-sections', expPath),
  // 报告管理（设置页）
  listReports: () => ipcRenderer.invoke('list-reports'),
  deleteReport: (filePath) => ipcRenderer.invoke('delete-report', filePath),
  showInFolder: (filePath) => ipcRenderer.invoke('show-in-folder', filePath),
  // 报告预览
  docxToHtml: (filePath) => ipcRenderer.invoke('docx-to-html', filePath),
  readDocxBuffer: (filePath) => ipcRenderer.invoke('read-docx-buffer', filePath),
  // AI 对话
  aiChat: (params) => ipcRenderer.invoke('ai-chat', params),
  // 变体组合
  loadVariants: (expPath) => ipcRenderer.invoke('load-variants', expPath),
  saveVariants: (expPath, variants) => ipcRenderer.invoke('save-variants', expPath, variants),
  // 渲染进程事件转发到主进程日志
  logEvent: (msg) => ipcRenderer.send('log-event', msg),
  // 关闭前未保存提示
  setDataModified: (dirty) => ipcRenderer.send('data-modified', dirty),
  onSaveAndClose: (callback) => {
    ipcRenderer.on('app-save-and-close', () => callback());
  },
  confirmClose: () => ipcRenderer.send('app-confirm-close'),
});
