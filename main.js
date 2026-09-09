// main.js — Electron 主进程
const { app, BrowserWindow, ipcMain, shell, dialog } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn, spawnSync, execFile } = require('child_process');
const mammoth = require('mammoth');

// ── 生成状态（支持取消）──
let activePython = null;            // 当前正在生成的 python 子进程
let activeCancelled = false;        // 本次生成是否被用户取消
let activeWordPidsBefore = new Set(); // 生成启动前已有的 WINWORD PID（取消时只清理本次新增）

// 枚举当前 WINWORD.EXE 进程 PID（tasklist，数字列不受编码影响）
function listWinwordPids() {
  return new Promise((resolve) => {
    execFile('tasklist', ['/FI', 'IMAGENAME eq WINWORD.EXE', '/FO', 'CSV', '/NH'],
      { encoding: 'latin1' }, (err, stdout) => {
        if (err || !stdout) return resolve([]);
        const pids = [];
        stdout.trim().split(/\r?\n/).forEach(line => {
          const parts = line.replace(/"/g, '').split(',');
          if (parts.length >= 2 && /^\d+$/.test(parts[1].trim())) {
            pids.push(parseInt(parts[1].trim(), 10));
          }
        });
        resolve(pids);
      });
  });
}

// ── GPU 硬件加速：已恢复启用。此前为省 ~100-160MB 内存而禁用，但软件渲染下
//    CSS 模糊、模态切换、列表/设置滚动会严重掉帧卡顿，流畅优先，故恢复。──

// ── 工具：解析命令对应的可执行文件绝对路径（where.exe 是独立 exe，不依赖 cmd.exe）──
function resolveExe(cmd) {
  try {
    const r = spawnSync('where.exe', [cmd], { encoding: 'utf8', timeout: 3000 });
    if (r.status === 0 && r.stdout) {
      const lines = r.stdout.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
      for (const l of lines) {
        // 排除沙箱/内部运行时路径（应用进程在真实文件系统上，看不到这些路径）
        if (/\.exe$/i.test(l) && fs.existsSync(l)
            && !/sandbox_runtime|connector_runtime|codex-runtimes|\.zcode/i.test(l)) return l;
      }
      for (const l of lines) {
        if (fs.existsSync(l) && !/sandbox_runtime|connector_runtime|codex-runtimes|\.zcode/i.test(l)) return l;
      }
    }
  } catch (e) { /* 忽略 */ }
  return null;
}

// ── 工具：解析真实可用的 python.exe（优先应用自带运行时，其次 Store/常见安装）──
function resolvePythonExe() {
  // 0. 应用自带 Python 运行时（打包后: resources/python-runtime；dev: 项目根/python-runtime）
  const bundled = [
    path.join(process.resourcesPath || '', 'python-runtime', 'python.exe'),
    path.join(__dirname, 'python-runtime', 'python.exe'),
  ];
  for (const p of bundled) {
    if (p && fs.existsSync(p)) return p;
  }
  // 1. Microsoft Store Python（真实文件系统路径，alias 指向已安装的 Python）
  const storePy = path.join(process.env.LOCALAPPDATA || '', 'Microsoft', 'WindowsApps', 'python.exe');
  if (fs.existsSync(storePy)) return storePy;
  // 2. 常见安装位置
  const dirs = [
    path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Python'),
    'C:\\Python313', 'C:\\Python312', 'C:\\Python311', 'C:\\Python310', 'C:\\Python39',
    'C:\\Program Files\\Python313', 'C:\\Program Files\\Python312', 'C:\\Program Files\\Python311',
  ];
  for (const dir of dirs) {
    if (!fs.existsSync(dir)) continue;
    try {
      if (/python\.exe$/i.test(dir) && dir.endsWith('python.exe')) return dir;
      for (const sub of fs.readdirSync(dir)) {
        const exe = path.join(dir, sub, 'python.exe');
        if (fs.existsSync(exe)) return exe;
      }
    } catch (e) { /* 忽略 */ }
  }
  // 3. PATH 兜底（排除沙箱/内部运行时）
  return resolveExe('python');
}

// ── 项目根探测：dev 模式 __dirname 即项目根；打包模式从 app.asar 逐级向上找源目录 ──
// 实验脚本/配置文件必须位于真实可写文件系统（Python 子进程需要访问并写入 docx/xlsx）
// 注意：不能用 fs.existsSync 判断 dev 模式——打包版 files 含物理实验，asar 视角下 existsSync 恒为 true
function findProjectRoot() {
  // 1. dev 模式（npm start）：app.isPackaged 为 false，__dirname 就是项目根
  if (!app.isPackaged) return __dirname;
  // 2. 打包（自包含）：物理实验 与 python-runtime 已作为 extraResources 打进
  //    可写的安装目录 resources/ 下，数据读写都在此处，无需外部源目录。
  const resRoot = process.resourcesPath;
  if (resRoot && fs.existsSync(path.join(resRoot, '物理实验', '实验脚本'))) {
    return resRoot;
  }
  // 3. 兜底（旧行为）：从 asar 向上找磁盘上的源目录
  let dir = path.dirname(__dirname);
  for (let i = 0; i < 8; i++) {
    if (fs.existsSync(path.join(dir, '物理实验', '实验脚本'))) return dir;
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return resRoot || __dirname;
}
const PROJECT_ROOT = findProjectRoot();
const EXPERIMENTS_DIR = path.join(PROJECT_ROOT, '物理实验', '实验脚本');
let mainWindow = null;
// 关闭前未保存提示状态
let isDataDirty = false;
let allowClose = false;

// ── 轻量日志落盘（排查用）──
const LOG_FILE = path.join(PROJECT_ROOT, 'app.log');
function log(msg) {
  try {
    const line = `[${new Date().toLocaleString('zh-CN', { hour12: false })}] ${msg}\n`;
    fs.appendFileSync(LOG_FILE, line, 'utf-8');
  } catch (e) { /* 日志失败不影响主功能 */ }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    title: '实验报告自动编写',
    frame: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  mainWindow.loadFile(path.join(__dirname, 'src', 'index.html'));
  // mainWindow.webContents.openDevTools();

  // 关闭前提示未保存的数据
  mainWindow.on('close', (e) => {
    if (allowClose) return;
    if (!isDataDirty) return;
    e.preventDefault();
    const choice = dialog.showMessageBoxSync(mainWindow, {
      type: 'warning',
      title: '未保存的修改',
      message: '当前实验有未保存的测量数据',
      detail: '关闭应用将丢失未保存的修改。',
      buttons: ['取消', '保存后退出', '直接退出'],
      defaultId: 0,
      cancelId: 0,
      noLink: true,
    });
    if (choice === 1) {
      // 保存后退出：通知渲染进程保存，保存成功后由渲染进程确认关闭
      mainWindow.webContents.send('app-save-and-close');
    } else if (choice === 2) {
      // 直接退出
      allowClose = true;
      mainWindow.close();
    }
  });
}

// ── IPC: 未保存数据状态 / 确认关闭 ──
ipcMain.on('data-modified', (_, dirty) => {
  isDataDirty = !!dirty;});

// ── IPC: 渲染进程事件转发到日志 ──
ipcMain.on('log-event', (_, msg) => {
  log(`[renderer] ${msg}`);
});

ipcMain.on('app-confirm-close', () => {
  allowClose = true;
  if (mainWindow) mainWindow.close();
});

app.whenReady().then(() => {
  log(`app started | packaged=${app.isPackaged} | PROJECT_ROOT=${PROJECT_ROOT} | EXPERIMENTS_DIR=${EXPERIMENTS_DIR}`);
  createWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

// ── IPC: 扫描实验列表 ──
ipcMain.handle('scan-experiments', () => {
  const results = [];
  if (!fs.existsSync(EXPERIMENTS_DIR)) return results;
  const dirs = fs.readdirSync(EXPERIMENTS_DIR, { withFileTypes: true });
  for (const d of dirs) {
    if (!d.isDirectory() || d.name === 'common') continue;
    const expPath = path.join(EXPERIMENTS_DIR, d.name);
    const generatePy = path.join(expPath, 'generate.py');
    if (!fs.existsSync(generatePy)) continue;
    const files = fs.readdirSync(expPath);
    const xlsx = files.find(f => f.endsWith('.xlsx'));
    const docx = files.find(f => f.endsWith('.docx'));
    results.push({
      id: d.name,
      name: d.name,
      path: expPath,
      hasData: !!xlsx,
      hasReport: !!docx,
      dataFile: xlsx ? path.join(expPath, xlsx) : null,
      reportFile: docx ? path.join(expPath, docx) : null,
    });
  }
  results.sort((a, b) => a.name.localeCompare(b.name, 'zh'));
  return results;
});

// ── IPC: 窗口控制 ──
ipcMain.on('window-minimize', () => { if (mainWindow) mainWindow.minimize(); });
ipcMain.on('window-maximize', () => {
  if (!mainWindow) return;
  if (mainWindow.isMaximized()) mainWindow.unmaximize();
  else mainWindow.maximize();
});
ipcMain.on('window-close', () => { if (mainWindow) mainWindow.close(); });

// ── IPC: 读取 schema.json（方式三：表单模式）──
ipcMain.handle('read-schema', (_, expPath) => {
  try {
    const p = path.join(expPath, 'schema.json');
    if (!fs.existsSync(p)) return { ok: true, schema: null };
    return { ok: true, schema: JSON.parse(fs.readFileSync(p, 'utf-8')) };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

// ── IPC: 读取 data.json（方式三：表单数据真相）──
ipcMain.handle('read-data', (_, expPath) => {
  try {
    const p = path.join(expPath, 'data.json');
    if (!fs.existsSync(p)) return { ok: true, data: null };
    return { ok: true, data: JSON.parse(fs.readFileSync(p, 'utf-8')) };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

// ── IPC: 写入 data.json（方式三：保存表单数据）──
ipcMain.handle('write-data', (_, expPath, data) => {
  try {
    const p = path.join(expPath, 'data.json');
    fs.writeFileSync(p, JSON.stringify(data, null, 2), 'utf-8');
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

// ── IPC: 读取实验知识库(原理) —— AI 润色限定依据 ──
ipcMain.handle('read-rag', (_, expPath) => {
  try {
    const p = path.join(expPath, 'rag', '原理.md');
    if (!fs.existsSync(p)) return { ok: true, text: null };
    return { ok: true, text: fs.readFileSync(p, 'utf-8') };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

// ── IPC: docx 转 HTML（用于报告预览/文本提取）──
ipcMain.handle('docx-to-html', async (_, filePath) => {
  try {
    if (!fs.existsSync(filePath)) return { ok: false, error: '文件不存在' };
    const result = await mammoth.convertToHtml({ path: filePath });
    return { ok: true, html: result.value, messages: result.messages };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

// ── IPC: 读取 docx 为 Buffer（用于 docx-preview 渲染）──
ipcMain.handle('read-docx-buffer', (_, filePath) => {
  try {
    if (!fs.existsSync(filePath)) return { ok: false, error: '文件不存在' };
    const buffer = fs.readFileSync(filePath);
    return { ok: true, buffer: buffer.toString('base64') };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

// ── IPC: 用默认程序打开文件 ──
ipcMain.handle('open-file', (_, filePath) => {
  if (fs.existsSync(filePath)) {
    shell.openPath(filePath);
    return { ok: true };
  }
  return { ok: false, error: '文件不存在' };
});

// ── IPC: 运行 generate.py 生成报告 ──
ipcMain.handle('run-generate', async (_, expPath, studentInfo, variants) => {
  const generatePy = path.join(expPath, 'generate.py');
  if (!fs.existsSync(generatePy)) {
    return { ok: false, error: 'generate.py 不存在', logs: [] };
  }

  // 构建环境变量（注入学生信息）
  const env = { ...process.env };
  if (studentInfo) {
    if (studentInfo.name) env.LAB_STUDENT_NAME = studentInfo.name;
    if (studentInfo.id) env.LAB_STUDENT_ID = studentInfo.id;
    if (studentInfo.class) env.LAB_STUDENT_CLASS = studentInfo.class;
    if (studentInfo.date) env.LAB_STUDENT_DATE = studentInfo.date;
  }
  // 变体组合选择（{章节: 变体序号}），传给 generate.py
  if (variants && Object.keys(variants).length > 0) {
    env.LAB_VARIANTS = JSON.stringify(variants);
  }

  // 解析真实可用的 python.exe 直接 spawn（优先 Store Python，排除沙箱路径，不依赖 cmd.exe）
  const pythonExe = resolvePythonExe() || 'python';
  // 记录本次生成启动前的 WINWORD 进程（取消时差集清理，绝不影响用户手动打开的 Word）
  activeWordPidsBefore = new Set(await listWinwordPids());
  activeCancelled = false;

  return new Promise((resolve) => {
    const logs = [];
    const python = spawn(pythonExe, [generatePy], {
      cwd: expPath,
      shell: false,
      env,
    });
    activePython = python;

    python.stdout.on('data', (data) => {
      logs.push(data.toString());
      if (mainWindow) {
        mainWindow.webContents.send('generate-log', data.toString());
      }
    });
    python.stderr.on('data', (data) => {
      logs.push(data.toString());
      if (mainWindow) {
        mainWindow.webContents.send('generate-log', data.toString());
      }
    });

    python.on('close', (code) => {
      if (activePython === python) activePython = null;
      // 扫描生成的 docx
      let reportFile = null;
      const files = fs.readdirSync(expPath);
      for (const f of files) {
        if (f.endsWith('.docx')) {
          reportFile = path.join(expPath, f);
          break;
        }
      }
      // 退出码 0 但未产出 docx：视为失败（多数情况是测量数据未填写完整，generate.py 打印缺失列表后静默退出）
      const ok = code === 0 && !!reportFile;
      resolve({
        ok,
        exitCode: code,
        cancelled: activeCancelled,
        logs: logs.join(''),
        reportFile,
        error: !ok && code === 0 && !reportFile
          ? '未生成报告文件，请查看日志中的缺失提示（通常为测量数据未填写完整）'
          : undefined,
      });
    });

    python.on('error', (err) => {
      if (activePython === python) activePython = null;
      resolve({ ok: false, error: err.message, cancelled: activeCancelled, logs: logs.join('') });
    });
  });
});

// ── IPC: 取消生成（结束 python 进程树 + 清理其启动的 Word，保留用户手动打开的 Word）──
ipcMain.handle('cancel-generate', async () => {
  if (!activePython || activePython.exitCode !== null) {
    return { ok: false, reason: 'no-active' };
  }
  activeCancelled = true;
  try {
    execFile('taskkill', ['/PID', String(activePython.pid), '/T', '/F']);
  } catch (e) { /* 进程可能已自行退出 */ }
  // 等待 python 退出（close 事件会触发 run-generate 的 resolve）
  await new Promise((resolve) => {
    const timer = setTimeout(resolve, 8000);
    activePython.once('close', () => { clearTimeout(timer); resolve(); });
  });
  // 差集清理：仅结束本次生成启动的 Word 实例（python 被杀时其 close() 兜底不会执行）
  try {
    const now = await listWinwordPids();
    for (const pid of now) {
      if (!activeWordPidsBefore.has(pid)) {
        execFile('taskkill', ['/PID', String(pid), '/F']);
      }
    }
  } catch (e) { /* 忽略清理失败 */ }
  activePython = null;
  return { ok: true };
});

// ── AI 提供商预设 ──
const AI_PROVIDERS = {
  deepseek: {
    baseUrl: 'https://api.deepseek.com/v1',
    model: 'deepseek-v4-pro',
  },
  doubao: {
    baseUrl: 'https://ark.cn-beijing.volces.com/api/v3',
    model: 'doubao-seed-2-1-pro-260628',
  },
  qwen: {
    baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    model: 'qwen-plus',
  },
  custom: {
    baseUrl: '',
    model: 'gpt-4o',
  },
};

// ── IPC: AI 对话 ──
ipcMain.handle('ai-chat', async (_, params) => {
  const { provider, apiKey, apiUrl, model, messages, temperature = 0.7 } = params;
  try {
    const preset = AI_PROVIDERS[provider] || AI_PROVIDERS.custom;
    // 用户设置了 apiUrl 就用用户的，否则用预设默认值
    const baseUrl = apiUrl || preset.baseUrl;
    const useModel = model || preset.model;

    if (!apiKey) {
      return { ok: false, error: '未配置 API Key，请在设置中填写' };
    }
    if (!baseUrl) {
      return { ok: false, error: '未配置 API 地址' };
    }

    const response = await fetch(`${baseUrl}/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model: useModel,
        messages,
        temperature,
        stream: false,
      }),
    });

    if (!response.ok) {
      const errText = await response.text();
      return { ok: false, error: `API 请求失败 (${response.status}): ${errText.slice(0, 200)}` };
    }

    const data = await response.json();
    const content = data.choices?.[0]?.message?.content || '';
    return { ok: true, content, usage: data.usage };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

// ── 变体组合：读取实验的 variants.json ──
ipcMain.handle('load-variants', async (_, expPath) => {
  try {
    const p = path.join(expPath, 'variants.json');
    if (!fs.existsSync(p)) {
      return { ok: true, variants: null };
    }
    const variants = JSON.parse(fs.readFileSync(p, 'utf-8'));
    return { ok: true, variants };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

// ── 变体组合：保存实验的 variants.json（AI 调整结果写回）──
ipcMain.handle('save-variants', async (_, expPath, variants) => {
  try {
    if (!variants || typeof variants !== 'object') {
      return { ok: false, error: '变体数据无效' };
    }
    const p = path.join(expPath, 'variants.json');
    fs.writeFileSync(p, JSON.stringify(variants, null, 1), 'utf-8');
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});
