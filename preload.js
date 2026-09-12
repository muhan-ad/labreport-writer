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
  readSampleData: (expPath) => ipcRenderer.invoke('read-sample-data', expPath),
  writeData: (expPath, data) => ipcRenderer.invoke('write-data', expPath, data),
  readRag: (expPath) => ipcRenderer.invoke('read-rag', expPath),
  readSections: (expPath) => ipcRenderer.invoke('read-sections', expPath),
  // 报告管理（设置页）
  listReports: () => ipcRenderer.invoke('list-reports'),
  deleteReport: (filePath) => ipcRenderer.invoke('delete-report', filePath),
  showInFolder: (filePath) => ipcRenderer.invoke('show-in-folder', filePath),
  // AI 润色技能文件（userData/skills）
  listSkills: () => ipcRenderer.invoke('list-skills'),
  importSkill: () => ipcRenderer.invoke('import-skill'),
  deleteSkill: (id) => ipcRenderer.invoke('delete-skill', id),
  openSkillsFolder: () => ipcRenderer.invoke('open-skills-folder'),
  // 报告预览
  docxToHtml: (filePath) => ipcRenderer.invoke('docx-to-html', filePath),
  readDocxBuffer: (filePath) => ipcRenderer.invoke('read-docx-buffer', filePath),
  // 内置音频（彩蛋播放）
  readAudioFile: () => ipcRenderer.invoke('read-audio-file'),
  // 检查更新（Gitee Release / 自定义清单）
  getAppVersion: () => ipcRenderer.invoke('get-app-version'),
  checkForUpdate: (cfg) => ipcRenderer.invoke('check-for-update', cfg),
  downloadUpdate: (payload) => ipcRenderer.invoke('download-update', payload),
  cancelUpdateDownload: () => ipcRenderer.send('cancel-update-download'),
  // 实验数据热更新（免重装）
  getDataInfo: () => ipcRenderer.invoke('get-data-info'),
  checkDataUpdate: () => ipcRenderer.invoke('check-data-update'),
  downloadDataPackage: (payload) => ipcRenderer.invoke('download-data-package', payload),
  applyDataPackage: (payload) => ipcRenderer.invoke('apply-data-package', payload),
  cancelDataDownload: () => ipcRenderer.send('cancel-data-download'),
  onDataProgress: (callback) => {
    ipcRenderer.on('data-update-progress', (_, data) => callback(data));
  },
  onUpdateProgress: (callback) => {
    ipcRenderer.on('update-download-progress', (_, data) => callback(data));
  },
  // AI 对话
  aiChat: (params) => ipcRenderer.invoke('ai-chat', params),
  // 变体组合
  loadVariants: (expPath) => ipcRenderer.invoke('load-variants', expPath),
  saveVariants: (expPath, variants) => ipcRenderer.invoke('save-variants', expPath, variants),
  // 用户自建变体库
  listCustomVariants: () => ipcRenderer.invoke('list-custom-variants'),
  readCustomVariants: (expId) => ipcRenderer.invoke('read-custom-variants', expId),
  saveCustomVariant: (expId, section, text) => ipcRenderer.invoke('save-custom-variant', expId, section, text),
  deleteCustomVariant: (expId, section, index) => ipcRenderer.invoke('delete-custom-variant', expId, section, index),
  exportCustomVariants: (payload) => ipcRenderer.invoke('export-custom-variants', payload),
  importCustomVariants: () => ipcRenderer.invoke('import-custom-variants'),
  // 渲染进程事件转发到主进程日志
  logEvent: (msg) => ipcRenderer.send('log-event', msg),
  // 关闭前未保存提示
  setDataModified: (dirty) => ipcRenderer.send('data-modified', dirty),
  onSaveAndClose: (callback) => {
    ipcRenderer.on('app-save-and-close', () => callback());
  },
  confirmClose: () => ipcRenderer.send('app-confirm-close'),
});
