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
    // 方式三：数据真相为 data.json / schema.json（xlsx 为遗留模板，不再参与判定）
    const hasDataJson = files.includes('data.json');
    const hasSchemaJson = files.includes('schema.json');
    // 跳过 Word 属主文件（~$开头）与生成中的临时报告（.~saving）
    const docx = files.find(f => f.endsWith('.docx') && !f.startsWith('~$') && !f.includes('.~saving'));
    results.push({
      id: d.name,
      name: d.name,
      path: expPath,
      hasData: hasDataJson || hasSchemaJson,
      hasReport: !!docx,
      dataFile: hasDataJson
        ? path.join(expPath, 'data.json')
        : (hasSchemaJson ? path.join(expPath, 'schema.json') : null),
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

// ── IPC: 读取章节原文缓存（AI 按章节润色的数据源，由 run-generate 落盘）──
ipcMain.handle('read-sections', (_, expPath) => {
  try {
    const p = path.join(expPath, '.lab_sections.json');
    if (!fs.existsSync(p)) return { ok: true, sections: null };
    return { ok: true, sections: JSON.parse(fs.readFileSync(p, 'utf-8')) };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

// ── IPC: AI 润色技能文件管理（userData/skills，导入外部开源 Skill 文件）──
function getSkillsDir() {
  const dir = path.join(app.getPath('userData'), 'skills');
  try { fs.mkdirSync(dir, { recursive: true }); } catch (e) { /* 忽略 */ }
  return dir;
}

// 解析 SKILL.md frontmatter（--- name/description ---）；无 frontmatter 时用文件名兜底
function parseSkillMeta(text, fallbackName) {
  let name = fallbackName, description = '', body = text;
  const m = String(text).match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?/);
  if (m) {
    body = text.slice(m[0].length);
    for (const line of m[1].split(/\r?\n/)) {
      const kv = String(line).match(/^([A-Za-z_-]+)\s*:\s*(.*)$/);
      if (!kv) continue;
      const k = kv[1].toLowerCase();
      const v = kv[2].trim().replace(/^["']|["']$/g, '');
      if (k === 'name' && v) name = v;
      else if (k === 'description' && v) description = v;
    }
  }
  return { name, description, body: body.trim() };
}

ipcMain.handle('list-skills', () => {
  try {
    const dir = getSkillsDir();
    const out = [];
    for (const f of fs.readdirSync(dir)) {
      if (!/\.(md|markdown|txt)$/i.test(f)) continue;
      try {
        const meta = parseSkillMeta(fs.readFileSync(path.join(dir, f), 'utf-8'), path.basename(f, path.extname(f)));
        out.push({ id: f, name: meta.name, description: meta.description, content: meta.body });
      } catch (e) { /* 跳过损坏文件 */ }
    }
    out.sort((a, b) => String(a.name).localeCompare(String(b.name), 'zh'));
    return { ok: true, skills: out, dir };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

ipcMain.handle('import-skill', async () => {
  try {
    const { canceled, filePaths } = await dialog.showOpenDialog(mainWindow, {
      title: '导入 Skill 文件',
      filters: [{ name: 'Skill 文件', extensions: ['md', 'markdown', 'txt'] }],
      properties: ['openFile', 'multiSelection'],
    });
    if (canceled || !filePaths || !filePaths.length) return { ok: true, imported: [], errors: [] };
    const dir = getSkillsDir();
    const imported = [];
    const errors = [];
    for (const src of filePaths) {
      try {
        const text = fs.readFileSync(src, 'utf-8');
        const meta = parseSkillMeta(text, path.basename(src, path.extname(src)));
        // 目标文件名：用技能名净化生成，重名自动加序号，不覆盖已有技能
        const base = (String(meta.name).replace(/[\\/:*?"<>|\r\n]+/g, '_').trim() || 'skill').slice(0, 60);
        let target = base + '.md';
        let dup = 2;
        while (fs.existsSync(path.join(dir, target))) {
          target = base + '-' + dup + '.md';
          dup += 1;
        }
        fs.copyFileSync(src, path.join(dir, target));
        imported.push(meta.name);
      } catch (e) {
        errors.push(path.basename(src) + ': ' + e.message);
      }
    }
    return { ok: true, imported, errors };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

// 删除技能：仅允许技能文件夹内、扩展名合法的文件（拒绝路径分隔符与上级引用）
ipcMain.handle('delete-skill', (_, id) => {
  try {
    const dir = path.resolve(getSkillsDir());
    if (typeof id !== 'string' || !id || id.includes('..') || /[\\/]/.test(id)) {
      return { ok: false, error: '无效的技能标识' };
    }
    const p = path.resolve(dir, id);
    if (!p.startsWith(dir + path.sep) || !/\.(md|markdown|txt)$/i.test(p)) {
      return { ok: false, error: '仅允许删除技能文件夹内的技能文件' };
    }
    if (fs.existsSync(p)) fs.unlinkSync(p);
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

ipcMain.handle('open-skills-folder', () => {
  const dir = getSkillsDir();
  shell.openPath(dir);
  return { ok: true, dir };
});

// ── IPC: 报告管理（设置页）──
// 列出全部实验目录下已生成的 .docx（含大小/修改时间），按时间倒序
ipcMain.handle('list-reports', () => {
  const out = [];
  try {
    if (!fs.existsSync(EXPERIMENTS_DIR)) return { ok: true, reports: out };
    const dirs = fs.readdirSync(EXPERIMENTS_DIR, { withFileTypes: true });
    for (const d of dirs) {
      if (!d.isDirectory() || d.name === 'common') continue;
      const expPath = path.join(EXPERIMENTS_DIR, d.name);
      let files;
      try { files = fs.readdirSync(expPath); } catch (e) { continue; }
      for (const f of files) {
        if (!f.toLowerCase().endsWith('.docx') || f.startsWith('~$') || f.includes('.~saving')) continue;
        try {
          const st = fs.statSync(path.join(expPath, f));
          out.push({ exp: d.name, file: f, path: path.join(expPath, f), size: st.size, mtime: st.mtimeMs });
        } catch (e) { /* 单个文件异常跳过 */ }
      }
    }
    out.sort((a, b) => b.mtime - a.mtime);
    return { ok: true, reports: out };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

// 删除报告：仅允许删除实验目录之内的 .docx（规范化路径并校验包含关系）
ipcMain.handle('delete-report', (_, filePath) => {
  try {
    if (typeof filePath !== 'string' || !filePath) return { ok: false, error: '无效路径' };
    const p = path.resolve(filePath);
    const root = path.resolve(EXPERIMENTS_DIR);
    if (!p.toLowerCase().endsWith('.docx')) return { ok: false, error: '仅允许删除 .docx 报告' };
    if (p !== root && !p.startsWith(root + path.sep)) return { ok: false, error: '仅允许删除实验目录内的报告' };
    if (!fs.existsSync(p)) return { ok: true, alreadyGone: true };
    fs.unlinkSync(p);
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

// 在资源管理器中定位文件
ipcMain.handle('show-in-folder', (_, filePath) => {
  try {
    if (fs.existsSync(filePath)) shell.showItemInFolder(filePath);
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

// ── IPC: 读取内置音频（src/ 下随包分发，任何环境均可播放）──
ipcMain.handle('read-audio-file', () => {
  try {
    const filePath = path.join(__dirname, 'src', 'do-not-click.mp3');
    if (!fs.existsSync(filePath)) return { ok: false, error: '音频文件不存在' };
    const buffer = fs.readFileSync(filePath);
    return { ok: true, mime: 'audio/mpeg', data: buffer.toString('base64') };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

// ═══════════════════════════════════════════════
// 检查更新（Gitee Release / 自定义清单，国内用户高速可达）
// ═══════════════════════════════════════════════
const https = require('https');
const dns = require('dns');

function compareVersions(a, b) {
  const pa = String(a).replace(/^v/i, '').split('.').map(n => parseInt(n, 10) || 0);
  const pb = String(b).replace(/^v/i, '').split('.').map(n => parseInt(n, 10) || 0);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const x = pa[i] || 0;
    const y = pb[i] || 0;
    if (x !== y) return x < y ? -1 : 1;
  }
  return 0;
}

// 拒绝 localhost / 环回 / 私有 / 链路本地 / 组播 / 保留地址，只允许公网主机
function isBlockedHost(host) {
  const h = String(host || '').toLowerCase().replace(/^\[|\]$/g, '').split(':')[0];
  if (!h || h === 'localhost' || h.endsWith('.local') || h.endsWith('.lan')) return true;
  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(h)) {
    const p = h.split('.').map(Number);
    if (p.some(x => x > 255)) return true;
    const [a, b] = p;
    if (a === 0 || a === 10 || a === 127) return true;
    if (a === 100 && b >= 64 && b <= 127) return true;   // CGNAT 100.64.0.0/10
    if (a === 169 && b === 254) return true;             // 链路本地
    if (a === 172 && b >= 16 && b <= 31) return true;
    if (a === 192 && b === 168) return true;
    if (a === 198 && (b === 18 || b === 19)) return true;
    if (a >= 224) return true;                           // 组播/保留
    return false;
  }
  return false;
}

// 校验更新 URL：仅 http/https，host 拒绝本地/私有地址
function assertPublicUrl(rawUrl) {
  let u;
  try { u = new URL(rawUrl); } catch (e) { throw new Error('更新地址格式不正确'); }
  if (u.protocol !== 'http:' && u.protocol !== 'https:') {
    throw new Error('仅支持 http/https 地址');
  }
  if (isBlockedHost(u.hostname)) throw new Error('不允许访问本地或私有地址');
  return u;
}

// 域名解析后再次核验：解析结果必须全部为公网 IP
function checkPublicDns(hostname) {
  return new Promise((resolve) => {
    dns.lookup(hostname, { all: true }, (err, addrs) => {
      if (err || !addrs || !addrs.length) return resolve(false);
      resolve(addrs.every(a => !isBlockedHost(a.address)));
    });
  });
}

// GET JSON（跟随重定向、超时、UA）
function httpsGetJson(url, timeout = 15000) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, {
      headers: { 'User-Agent': 'labreport-writer-updater' },
      timeout,
    }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        res.resume();
        return resolve(httpsGetJson(res.headers.location, timeout));
      }
      if (res.statusCode !== 200) {
        res.resume();
        return reject(new Error(`HTTP ${res.statusCode}`));
      }
      let data = '';
      res.setEncoding('utf8');
      res.on('data', c => { data += c; });
      res.on('end', () => {
        try { resolve(JSON.parse(data)); }
        catch (e) { reject(new Error('响应解析失败')); }
      });
    });
    req.on('error', reject);
    req.on('timeout', () => req.destroy(new Error('请求超时')));
  });
}

// ── IPC: 当前应用版本 ──
ipcMain.handle('get-app-version', () => app.getVersion());

// 检查更新：优先使用自定义清单地址（latest.json），否则查询 Gitee 最新 Release
ipcMain.handle('check-for-update', async (_, cfg) => {
  try {
    const manifestUrl = String((cfg && cfg.manifestUrl) || '').trim();
    const current = app.getVersion();

    // 自定义清单：{ version, notes, url, fileName }
    if (manifestUrl) {
      const u = assertPublicUrl(manifestUrl);
      if (!(await checkPublicDns(u.hostname))) {
        throw new Error('更新地址无法解析或指向本地地址');
      }
      const mf = await httpsGetJson(u.href);
      const latest = String(mf.version || '').replace(/^v/i, '');
      const hasUpdate = !!(latest && compareVersions(latest, current) > 0);
      const dlUrl = String(mf.url || '').trim();
      let safeDlUrl = '';
      if (dlUrl) {
        const du = assertPublicUrl(dlUrl);
        if (!(await checkPublicDns(du.hostname))) {
          throw new Error('安装包下载地址无法解析或指向本地地址');
        }
        safeDlUrl = du.href;
      }
      return {
        ok: true,
        hasUpdate,
        current,
        latest,
        notes: String(mf.notes || '').trim(),
        assets: safeDlUrl
          ? [{ name: String(mf.fileName || 'update.exe'), url: safeDlUrl, size: 0 }]
          : [],
        releaseUrl: '',
      };
    }

    // Gitee Release 路径
    const owner = String((cfg && cfg.owner) || '').trim().replace(/[^\w-]/g, '');
    const repo = String((cfg && cfg.repo) || '').trim().replace(/[^\w-]/g, '');
    if (!owner || !repo) {
      return { ok: false, error: '请先在设置中填写 Gitee 用户名与仓库名，或填写自定义更新清单地址' };
    }
    const url = `https://gitee.com/api/v5/repos/${owner}/${repo}/releases/latest`;
    if (!url.startsWith('https://gitee.com/')) {
      return { ok: false, error: '更新源必须为 Gitee 地址' };
    }
    const rel = await httpsGetJson(url);
    const latest = String(rel.tag_name || '').replace(/^v/i, '');
    const hasUpdate = !!(latest && compareVersions(latest, current) > 0);
    const assets = [];
    for (const a of (rel.assets || [])) {
      if (!/\.(exe|msi|zip)$/i.test(String(a.name || ''))) continue;
      const du = assertPublicUrl(a.browser_download_url);
      if (!(await checkPublicDns(du.hostname))) continue;
      assets.push({ name: a.name, url: du.href, size: a.size || 0 });
    }
    return {
      ok: true,
      hasUpdate,
      current,
      latest,
      notes: String(rel.body || '').trim(),
      assets,
      releaseUrl: rel.html_url || '',
    };
  } catch (err) {
    return { ok: false, error: err.message, hasUpdate: false };
  }
});

// 取消下载：销毁当前更新下载请求
let activeUpdateReq = null;
ipcMain.on('cancel-update-download', () => {
  if (activeUpdateReq) {
    try { activeUpdateReq.destroy(); } catch (e) { /* 忽略 */ }
    activeUpdateReq = null;
  }
});

// 下载更新安装包（进度经 'update-download-progress' 回传）
ipcMain.handle('download-update', async (event, payload) => {
  const rawUrl = String((payload && payload.url) || '');
  let url;
  try {
    const u = assertPublicUrl(rawUrl);
    if (!(await checkPublicDns(u.hostname))) throw new Error('下载地址无法解析或指向本地地址');
    url = u.href;
  } catch (err) {
    return { ok: false, error: err.message };
  }
  const fileName = path.basename(String((payload && payload.name) || 'update.exe'));
  if (!fileName || fileName.includes('..') || /[\\/]/.test(fileName)) {
    return { ok: false, error: '非法的文件名' };
  }
  const dlRoot = path.resolve(app.getPath('downloads'));
  const dest = path.resolve(dlRoot, fileName);
  if (!dest.startsWith(dlRoot + path.sep)) {
    return { ok: false, error: '非法的文件路径' };
  }
  const sendProgress = (percent) => {
    try { event.sender.send('update-download-progress', { percent }); } catch (e) { /* 窗口可能已关闭 */ }
  };
  return new Promise((resolve) => {
    const req = https.get(url, {
      headers: { 'User-Agent': 'labreport-writer-updater' },
    }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        res.resume();
        activeUpdateReq = null;
        return resolve({ ok: false, error: '下载地址发生了重定向，请稍后重试' });
      }
      if (res.statusCode !== 200) {
        res.resume();
        activeUpdateReq = null;
        return resolve({ ok: false, error: `下载失败 HTTP ${res.statusCode}` });
      }
      const total = parseInt(res.headers['content-length'] || '0', 10) || 0;
      let received = 0;
      const out = fs.createWriteStream(dest);
      res.pipe(out);
      res.on('data', (chunk) => {
        received += chunk.length;
        if (total) sendProgress(Math.min(99, Math.round(received * 100 / total)));
      });
      out.on('finish', () => { activeUpdateReq = null; sendProgress(100); resolve({ ok: true, filePath: dest }); });
      out.on('error', (e) => { activeUpdateReq = null; res.destroy(); resolve({ ok: false, error: e.message }); });
      res.on('error', (e) => { activeUpdateReq = null; out.destroy(); resolve({ ok: false, error: e.message }); });
    });
    req.on('error', (e) => { activeUpdateReq = null; resolve({ ok: false, error: e.message }); });
    activeUpdateReq = req;
  });
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
// variants.compose 向 stdout 打印的章节原文标记（供应用侧按章节润色/导入重生成）
const SECTIONS_MARKER = '.LAB_SECTIONS_JSON:';
ipcMain.handle('run-generate', async (_, expPath, studentInfo, variants, polish) => {
  const generatePy = path.join(expPath, 'generate.py');
  if (!fs.existsSync(generatePy)) {
    return { ok: false, error: 'generate.py 不存在', logs: [] };
  }

  // 构建环境变量（注入学生信息）
  const env = { ...process.env };
  // 强制 Python 管道输出为 UTF-8：中文 Windows 默认区域编码为 GBK，
  // 而本进程按 UTF-8 解码 stdout（data.toString()），不强制会导致日志与章节缓存乱码
  env.PYTHONIOENCODING = 'utf-8';
  env.PYTHONUTF8 = '1';
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
  // AI 润色导入（{章节: Markdown 文本}），由 compose() 注入覆盖对应变体章节
  if (polish && typeof polish === 'object' && Object.keys(polish).length > 0) {
    env.LAB_POLISH = JSON.stringify(polish);
  }

  // 解析真实可用的 python.exe 直接 spawn（优先 Store Python，排除沙箱路径，不依赖 cmd.exe）
  const pythonExe = resolvePythonExe() || 'python';
  // 记录本次生成启动前的 WINWORD 进程（取消时差集清理，绝不影响用户手动打开的 Word）
  activeWordPidsBefore = new Set(await listWinwordPids());
  activeCancelled = false;

  return new Promise((resolve) => {
    const logs = [];
    let capturedSections = null;   // compose() 打印的章节原文缓存
    let stdoutCarry = '';          // 跨 chunk 的行缓冲（标记行可能分块到达）
    const python = spawn(pythonExe, [generatePy], {
      cwd: expPath,
      shell: false,
      env,
    });
    activePython = python;

    python.stdout.on('data', (data) => {
      // 按行处理：截出章节缓存标记行（不进入展示日志），其余原样转发
      const lines = (stdoutCarry + data.toString()).split(/\r?\n/);
      stdoutCarry = lines.pop();
      const keep = [];
      for (const ln of lines) {
        if (ln.startsWith(SECTIONS_MARKER)) {
          try { capturedSections = JSON.parse(ln.slice(SECTIONS_MARKER.length)); } catch (e) { /* 坏行忽略 */ }
        } else {
          keep.push(ln);
        }
      }
      if (keep.length) {
        const out = keep.join('\n') + '\n';
        logs.push(out);
        if (mainWindow) mainWindow.webContents.send('generate-log', out);
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
      // 冲刷行缓冲（子进程输出末尾可能无换行）
      if (stdoutCarry) {
        if (stdoutCarry.startsWith(SECTIONS_MARKER)) {
          try { capturedSections = JSON.parse(stdoutCarry.slice(SECTIONS_MARKER.length)); } catch (e) { /* 坏行忽略 */ }
        } else {
          logs.push(stdoutCarry);
        }
        stdoutCarry = '';
      }
      // 章节原文缓存落盘（dev=项目目录；打包=可写安装目录），供重启后润色读取
      if (capturedSections && typeof capturedSections === 'object') {
        try {
          fs.writeFileSync(path.join(expPath, '.lab_sections.json'), JSON.stringify(capturedSections, null, 1), 'utf-8');
        } catch (e) { /* 缓存失败不影响生成结果 */ }
      }
      // 扫描生成的 docx（跳过 Word 属主文件与生成中/残留的临时报告）
      let reportFile = null;
      const files = fs.readdirSync(expPath);
      for (const f of files) {
        if (f.endsWith('.docx') && !f.startsWith('~$') && !f.includes('.~saving')) {
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
        sections: capturedSections || undefined,
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
