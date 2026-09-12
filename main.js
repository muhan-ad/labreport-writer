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

// ── 实验数据目录（热更新支持）──
// 数据包下载解压到 userData，扫描时 userData 有有效清单则优先于安装目录（同名实验以 userData 为准）
// ── 用户自建变体库（userData/自建变体/<实验名>.json，结构与 variants.json 同构）──
function getCustomVariantsDir() {
  const dir = path.join(app.getPath('userData'), '自建变体');
  try { fs.mkdirSync(dir, { recursive: true }); } catch (e) { /* 忽略 */ }
  return dir;
}

// 自建变体库认可的标准章节名（"实验结论"兼容 26 个实验中的键名差异）
const CUSTOM_SECTION_NAMES = ['实验原理', '实验方法', '误差分析', '结论', '实验结论'];

// 实验名 → 自建库文件绝对路径；非法名返回 null
function customVariantPathFor(expId) {
  const name = String(expId || '').replace(/[\\/:*?"<>|\r\n]+/g, '_').trim();
  if (!name || name === '.' || name === '..') return null;
  return path.join(getCustomVariantsDir(), name + '.json');
}

function readCustomVariantsFile(expId) {
  const p = customVariantPathFor(expId);
  if (!p || !fs.existsSync(p)) return null;
  try {
    const v = JSON.parse(fs.readFileSync(p, 'utf-8'));
    return (v && typeof v === 'object') ? v : null;
  } catch (e) {
    return null;
  }
}

function hasCustomVariantsFor(expId) {
  const v = readCustomVariantsFile(expId);
  if (!v) return false;
  return CUSTOM_SECTION_NAMES.some(s => Array.isArray(v[s]) && v[s].length > 0);
}

function getDataRoots() {
  const udRoot = path.join(app.getPath('userData'), '实验数据', '实验脚本');
  const mfPath = path.join(app.getPath('userData'), '实验数据', 'data-manifest.json');
  // userData 根无条件激活：安装目录为只读出厂数据，用户的实验数据/报告一律落 userData
  try { fs.mkdirSync(udRoot, { recursive: true }); } catch (e) { /* 忽略 */ }
  const roots = [];
  if (fs.existsSync(udRoot)) {
    roots.push({ dir: udRoot, source: 'userData' });
  }
  if (fs.existsSync(EXPERIMENTS_DIR)) {
    roots.push({ dir: EXPERIMENTS_DIR, source: 'builtin' });
  }
  return { roots, udRoot, mfPath };
}

// 递归复制目录（源/目标各受独立根边界约束）
function copyDirTo(src, dest, srcRoot, destRoot) {
  fs.mkdirSync(dest, { recursive: true });
  for (const f of fs.readdirSync(src)) {
    const s = ensureInside(path.join(src, f), srcRoot);
    const d = ensureInside(path.join(dest, f), destRoot);
    const st = fs.statSync(s);
    if (st.isDirectory()) copyDirTo(s, d, srcRoot, destRoot);
    else fs.copyFileSync(s, d);
  }
}

let lastCommonSyncAt = 0;   // common 公共库上次同步时间（节流）

// 用户数据隔离：写操作前若实验目录仍在安装目录（builtin），先镜像/同步到 userData 并返回新路径。
// - userData 无该实验：整目录镜像（含 data.json/variants.json 出厂值）
// - 已有副本：按热更新合并语义刷新（data.json 与用户改过的 variants.json 永不覆盖、报告 docx 不动）
// - 每次同步公共库 common（generate.py 依赖 from common import *，必须与安装目录同版本）
function ensureUserCopy(expPath) {
  try {
    const p = path.resolve(expPath);
    const builtinRoot = path.resolve(EXPERIMENTS_DIR);
    const { udRoot } = getDataRoots();
    const udRootRes = path.resolve(udRoot);
    if (!fs.existsSync(builtinRoot)) return p;
    if (p.startsWith(udRootRes + path.sep)) return p;          // 已在 userData
    if (!p.startsWith(builtinRoot + path.sep)) return p;      // 非安装目录内的路径原样返回
    const name = path.relative(builtinRoot, p).split(path.sep).shift();
    if (!name || name === 'common' || name.startsWith('.')) return p;
    const src = ensureInside(path.join(builtinRoot, name), builtinRoot);
    if (!fs.existsSync(src)) return p;
    const dst = ensureInside(path.join(udRootRes, name), udRootRes);
    // 同步公共库 common（generate.py 依赖 from common import *；10 分钟节流，进程重启即强制同步，
    // 保证重装新版本后 common 与 generate.py 匹配）
    const builtinCommon = ensureInside(path.join(builtinRoot, 'common'), builtinRoot);
    const udCommon = ensureInside(path.join(udRootRes, 'common'), udRootRes);
    if (fs.existsSync(builtinCommon) && Date.now() - lastCommonSyncAt > 10 * 60 * 1000) {
      fs.rmSync(udCommon, { recursive: true, force: true });
      copyDirTo(builtinCommon, udCommon, builtinRoot, udRootRes);
      lastCommonSyncAt = Date.now();
    }
    if (!fs.existsSync(dst)) {
      fs.mkdirSync(dst, { recursive: true });
      copyDirTo(src, dst, builtinRoot, udRootRes);
    } else {
      const warnings = [];
      mergeDataTree(src, dst, src, warnings, true);
    }
    return dst;
  } catch (e) {
    return path.resolve(expPath);   // 迁移失败退化为原路径，保持可写
  }
}

function scanDirEntry(d, source) {
  const expPath = path.join(d.dir, d.name);
  const generatePy = path.join(expPath, 'generate.py');
  if (!fs.existsSync(generatePy)) return null;
  const files = fs.readdirSync(expPath);
  const hasDataJson = files.includes('data.json');
  const hasSchemaJson = files.includes('schema.json');
  const docx = files.find(f => f.endsWith('.docx') && !f.startsWith('~$') && !f.includes('.~saving'));
  return {
    id: d.name,
    name: d.name,
    path: expPath,
    hasData: hasDataJson || hasSchemaJson,
    hasReport: !!docx,
    dataFile: hasDataJson
      ? path.join(expPath, 'data.json')
      : (hasSchemaJson ? path.join(expPath, 'schema.json') : null),
    reportFile: docx ? path.join(expPath, docx) : null,
    source,
    hasCustomVariants: hasCustomVariantsFor(d.name),
  };
}

// ── IPC: 扫描实验列表 ──
ipcMain.handle('scan-experiments', () => {
  const { roots } = getDataRoots();
  const results = [];
  const seen = new Set();
  for (const root of roots) {
    let dirs = [];
    try { dirs = fs.readdirSync(root.dir, { withFileTypes: true }); } catch (e) { continue; }
    for (const d of dirs) {
      if (!d.isDirectory() || d.name === 'common' || d.name.startsWith('.') || seen.has(d.name)) continue;
      const entry = scanDirEntry({ dir: root.dir, name: d.name }, root.source);
      if (entry) { seen.add(d.name); results.push(entry); }
    }
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

// ── IPC: 读取 sample.json（内置测试数据快照，供「填入默认数据」恢复）──
ipcMain.handle('read-sample-data', (_, expPath) => {
  try {
    const p = path.join(expPath, 'sample.json');
    if (!fs.existsSync(p)) return { ok: true, data: null };
    return { ok: true, data: JSON.parse(fs.readFileSync(p, 'utf-8')) };
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

// ── IPC: 写入 data.json（方式三：保存表单数据；用户数据落 userData 副本）──
ipcMain.handle('write-data', (_, expPath, data) => {
  try {
    const p = ensureUserCopy(expPath);
    fs.writeFileSync(path.join(p, 'data.json'), JSON.stringify(data, null, 2), 'utf-8');
    return { ok: true, path: p };
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

// ═══════════════════════════════════════════════
// 用户自建变体库（userData/自建变体，独立于实验目录与数据热更新）
// ═══════════════════════════════════════════════

// 列出所有有自建变体的实验
ipcMain.handle('list-custom-variants', () => {
  try {
    const dir = getCustomVariantsDir();
    const out = [];
    for (const f of fs.readdirSync(dir)) {
      if (!f.endsWith('.json')) continue;
      const expId = f.slice(0, -5);
      const v = readCustomVariantsFile(expId);
      if (!v) continue;
      const sections = {};
      let count = 0;
      for (const s of CUSTOM_SECTION_NAMES) {
        if (Array.isArray(v[s]) && v[s].length) {
          sections[s] = v[s].length;
          count += v[s].length;
        }
      }
      if (count > 0) out.push({ expId, sections, count });
    }
    out.sort((a, b) => a.expId.localeCompare(b.expId, 'zh'));
    return { ok: true, list: out };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

// 读取某实验的自建变体（结构与 variants.json 同构）
ipcMain.handle('read-custom-variants', (_, expId) => {
  try {
    const v = readCustomVariantsFile(expId);
    return { ok: true, data: v };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

// 新增一条自建变体（同文本去重）
ipcMain.handle('save-custom-variant', (_, expId, section, text) => {
  try {
    if (!CUSTOM_SECTION_NAMES.includes(section)) return { ok: false, error: '无效的章节名' };
    if (typeof text !== 'string' || !text.trim()) return { ok: false, error: '变体文本为空' };
    const p = customVariantPathFor(expId);
    if (!p) return { ok: false, error: '无效的实验名' };
    const v = readCustomVariantsFile(expId) || {};
    const arr = Array.isArray(v[section]) ? v[section] : [];
    if (!arr.includes(text)) arr.push(text);
    v[section] = arr;
    fs.writeFileSync(p, JSON.stringify(v, null, 1), 'utf-8');
    return { ok: true, total: arr.length };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

// 删除一条自建变体；章节清空删键、文件清空删除
ipcMain.handle('delete-custom-variant', (_, expId, section, index) => {
  try {
    if (!CUSTOM_SECTION_NAMES.includes(section)) return { ok: false, error: '无效的章节名' };
    const p = customVariantPathFor(expId);
    if (!p) return { ok: false, error: '无效的实验名' };
    const v = readCustomVariantsFile(expId);
    if (!v) return { ok: true };
    const arr = Array.isArray(v[section]) ? v[section] : [];
    if (typeof index !== 'number' || index < 0 || index >= arr.length) {
      return { ok: false, error: '无效的变体序号' };
    }
    arr.splice(index, 1);
    if (arr.length) v[section] = arr; else delete v[section];
    const anyLeft = Object.values(v).some(a => Array.isArray(a) && a.length);
    if (anyLeft) fs.writeFileSync(p, JSON.stringify(v, null, 1), 'utf-8');
    else if (fs.existsSync(p)) fs.unlinkSync(p);
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

// 导出：单实验（save 对话框）或全部（选文件夹逐实验写 自建变体_<实验名>.json）
ipcMain.handle('export-custom-variants', async (_, payload) => {
  try {
    const exportAll = !!(payload && payload.exportAll);
    const dir = getCustomVariantsDir();
    let targetIds = [];
    if (exportAll) {
      for (const f of fs.readdirSync(dir)) {
        if (!f.endsWith('.json')) continue;
        const expId = f.slice(0, -5);
        if (hasCustomVariantsFor(expId)) targetIds.push(expId);
      }
    } else {
      const one = String((payload && payload.expId) || '');
      if (one && hasCustomVariantsFor(one)) targetIds = [one];
    }
    if (!targetIds.length) {
      return { ok: false, error: exportAll ? '自建变体库为空' : '该实验没有自建变体' };
    }
    if (exportAll) {
      const { canceled, filePaths } = await dialog.showOpenDialog(mainWindow, {
        title: '选择存放自建变体的文件夹',
        properties: ['openDirectory', 'createDirectory'],
      });
      if (canceled || !filePaths || !filePaths.length) return { ok: true, canceled: true, count: 0 };
      const destDir = filePaths[0];
      let n = 0;
      const errors = [];
      for (const eid of targetIds) {
        try {
          fs.copyFileSync(path.join(dir, eid + '.json'), path.join(destDir, '自建变体_' + eid + '.json'));
          n += 1;
        } catch (e) {
          errors.push(eid + ': ' + e.message);
        }
      }
      return { ok: true, canceled: false, count: n, errors };
    }
    const expId = targetIds[0];
    const { canceled, filePath } = await dialog.showSaveDialog(mainWindow, {
      title: '导出自建变体',
      defaultPath: path.join(app.getPath('documents'), '自建变体_' + expId + '.json'),
      filters: [{ name: 'JSON 文件', extensions: ['json'] }],
    });
    if (canceled || !filePath) return { ok: true, canceled: true };
    const v = readCustomVariantsFile(expId);
    if (!v) return { ok: false, error: '读取自建变体失败' };
    fs.writeFileSync(filePath, JSON.stringify(v, null, 1), 'utf-8');
    return { ok: true, canceled: false, count: 1 };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

// 导入（批量）：多选 .json，文件名取实验名（前导「自建变体_」自动剥离），结构校验后合并去重
ipcMain.handle('import-custom-variants', async () => {
  try {
    const { canceled, filePaths } = await dialog.showOpenDialog(mainWindow, {
      title: '导入自建变体文件（可多选批量导入）',
      filters: [{ name: '自建变体 JSON', extensions: ['json'] }],
      properties: ['openFile', 'multiSelection'],
    });
    if (canceled || !filePaths || !filePaths.length) return { ok: true, imported: [], errors: [] };
    // 已安装的全部实验名（内置 + userData 双根）
    const known = new Set();
    const { roots } = getDataRoots();
    for (const r of roots) {
      try {
        for (const dEntry of fs.readdirSync(r.dir, { withFileTypes: true })) {
          if (dEntry.isDirectory() && dEntry.name !== 'common' && !dEntry.name.startsWith('.')) known.add(dEntry.name);
        }
      } catch (e) { /* 忽略 */ }
    }
    const imported = [];
    const errors = [];
    for (const src of filePaths) {
      try {
        let expId = path.basename(src, path.extname(src));
        if (expId.startsWith('自建变体_')) expId = expId.slice('自建变体_'.length);
        if (!known.has(expId)) {
          errors.push(path.basename(src) + ': 未找到匹配实验「' + expId + '」');
          continue;
        }
        const v = JSON.parse(fs.readFileSync(src, 'utf-8'));
        if (!v || typeof v !== 'object') {
          errors.push(path.basename(src) + ': 文件结构无效');
          continue;
        }
        const existing = readCustomVariantsFile(expId) || {};
        let added = 0;
        for (const [section, texts] of Object.entries(v)) {
          if (!CUSTOM_SECTION_NAMES.includes(section)) continue;
          if (!Array.isArray(texts)) continue;
          const arr = Array.isArray(existing[section]) ? existing[section] : [];
          for (const t of texts) {
            if (typeof t === 'string' && t.trim() && !arr.includes(t)) { arr.push(t); added += 1; }
          }
          if (arr.length) existing[section] = arr;
        }
        if (!added) {
          errors.push(path.basename(src) + ': 无新增条目（内容已存在或为空）');
          continue;
        }
        const p = customVariantPathFor(expId);
        if (!p) {
          errors.push(path.basename(src) + ': 无效的实验名');
          continue;
        }
        fs.writeFileSync(p, JSON.stringify(existing, null, 1), 'utf-8');
        imported.push(expId);
      } catch (e) {
        errors.push(path.basename(src) + ': ' + e.message);
      }
    }
    return { ok: true, imported, errors };
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
    const { roots } = getDataRoots();
    if (!roots.length) return { ok: true, reports: out };
    const seen = new Set();
    for (const root of roots) {
      if (root.source === 'userData') {
        // userData 优先：与其同名的实验直接跳过安装目录版本，避免重复
        for (const d of fs.readdirSync(root.dir, { withFileTypes: true })) {
          if (d.isDirectory()) seen.add(d.name);
        }
      }
      let dirs = [];
      try { dirs = fs.readdirSync(root.dir, { withFileTypes: true }); } catch (e) { continue; }
      for (const d of dirs) {
        if (!d.isDirectory() || d.name === 'common' || d.name.startsWith('.')) continue;
        if (root.source === 'builtin' && seen.has(d.name)) continue;
        const expPath = path.join(root.dir, d.name);
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
    const { roots } = getDataRoots();
    if (!p.toLowerCase().endsWith('.docx')) return { ok: false, error: '仅允许删除 .docx 报告' };
    const inside = roots.some(r => {
      const root = path.resolve(r.dir);
      return p !== root && p.startsWith(root + path.sep);
    });
    if (!inside) return { ok: false, error: '仅允许删除实验目录内的报告' };
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
// 实验数据热更新（COS 数据包 → userData，免重装）
// ═══════════════════════════════════════════════
const DATA_MANIFEST_URL = 'https://labreport-1485394950.cos.ap-guangzhou.myqcloud.com/data-manifest.json';
// 内置实验数据版本（未应用任何数据包时的基准版本，独立于应用版本号）
const DATA_BUILTIN_VERSION = '1.0.0';

function readLocalDataManifest() {
  try {
    return JSON.parse(fs.readFileSync(getDataRoots().mfPath, 'utf-8'));
  } catch (e) {
    return null;
  }
}

// 路径边界断言：p 必须位于 root 内
function ensureInside(p, root) {
  const rp = path.resolve(p);
  const rr = path.resolve(root);
  if (rp !== rr && !rp.startsWith(rr + path.sep)) throw new Error('路径越界: ' + p);
  return rp;
}

// ── IPC: 实验数据版本信息（本地）
ipcMain.handle('get-data-info', () => {
  const mf = readLocalDataManifest();
  return {
    ok: true,
    localVersion: (mf && mf.dataVersion) || null,   // 无热更新数据时为空，即内置版本
    notes: (mf && mf.notes) || '',
    updatedAt: (mf && mf.updatedAt) || null,
    builtinVersion: DATA_BUILTIN_VERSION,
  };
});

// ── IPC: 检查实验数据更新（远端 data-manifest.json）
ipcMain.handle('check-data-update', async () => {
  try {
    const u = assertPublicUrl(DATA_MANIFEST_URL);
    if (!(await checkPublicDns(u.hostname))) throw new Error('更新地址无法解析或指向本地地址');
    let mf;
    try {
      mf = await httpsGetJson(u.href);
    } catch (e) {
      // 云端尚未发布任何数据包（404）：视为已是最新，而非报错
      if (/HTTP 404/.test(e.message)) {
        const local = readLocalDataManifest();
        return {
          ok: true,
          hasUpdate: false,
          noRemote: true,
          localVersion: local ? String(local.dataVersion).replace(/^v/i, '') : DATA_BUILTIN_VERSION,
          remoteVersion: '',
        };
      }
      throw e;
    }
    const remote = String(mf.dataVersion || '').replace(/^v/i, '');
    const local = readLocalDataManifest();
    const localVer = local ? String(local.dataVersion).replace(/^v/i, '') : DATA_BUILTIN_VERSION;
    const hasUpdate = !!(remote && compareVersions(remote, localVer) > 0);
    return {
      ok: true,
      hasUpdate,
      localVersion: localVer,
      remoteVersion: remote,
      notes: String(mf.notes || '').trim(),
      url: String(mf.url || '').trim(),
    };
  } catch (err) {
    return { ok: false, error: err.message, hasUpdate: false };
  }
});

// ── IPC: 下载实验数据包（zip，进度经 'data-update-progress' 回传）
let activeDataReq = null;
ipcMain.handle('download-data-package', async (event, payload) => {
  const rawUrl = String((payload && payload.url) || '');
  let url;
  try {
    const u = assertPublicUrl(rawUrl);
    if (!(await checkPublicDns(u.hostname))) throw new Error('下载地址无法解析或指向本地地址');
    url = u.href;
  } catch (err) {
    return { ok: false, error: err.message };
  }
  const dataRoot = path.join(app.getPath('userData'), '实验数据');
  fs.mkdirSync(dataRoot, { recursive: true });
  const dest = ensureInside(path.join(dataRoot, '_package.zip'), dataRoot);
  const sendProgress = (percent) => {
    try { event.sender.send('data-update-progress', { percent }); } catch (e) { /* 忽略 */ }
  };
  return new Promise((resolve) => {
    const req = https.get(url, { headers: { 'User-Agent': 'labreport-writer-updater' } }, (res) => {
      if (res.statusCode !== 200) {
        res.resume();
        activeDataReq = null;
        return resolve({ ok: false, error: `下载失败 HTTP ${res.statusCode}` });
      }
      const total = parseInt(res.headers['content-length'] || '0', 10) || 0;
      let received = 0;
      const out = fs.createWriteStream(dest);
      res.pipe(out);
      res.on('data', (chunk) => {
        received += chunk.length;
        if (total) sendProgress(Math.min(95, Math.round(received * 100 / total)));
      });
      out.on('finish', () => { activeDataReq = null; sendProgress(100); resolve({ ok: true, filePath: dest }); });
      out.on('error', (e) => { activeDataReq = null; res.destroy(); resolve({ ok: false, error: e.message }); });
      res.on('error', (e) => { activeDataReq = null; out.destroy(); resolve({ ok: false, error: e.message }); });
    });
    req.on('error', (e) => { activeDataReq = null; resolve({ ok: false, error: e.message }); });
    activeDataReq = req;
  });
});

ipcMain.on('cancel-data-download', () => {
  if (activeDataReq) {
    try { activeDataReq.destroy(); } catch (e) { /* 忽略 */ }
    activeDataReq = null;
  }
});

// 用内置 Python 安全解压 zip（条目路径校验防 zip-slip）
const UNZIP_SCRIPT = [
  'import sys, zipfile',
  'z, dest = sys.argv[1], sys.argv[2]',
  "with zipfile.ZipFile(z) as zf:",
  "    for n in zf.namelist():",
  "        p = n.replace(chr(92), '/')",
  "        if p.startswith('/') or any(s == '..' for s in p.split('/')):",
  "            raise SystemExit('bad entry: ' + n)",
  '    zf.extractall(dest)',
].join('\n');

function unzipSafe(zipPath, destDir) {
  return new Promise((resolve, reject) => {
    const pythonExe = resolvePythonExe();
    if (!pythonExe) return reject(new Error('未找到内置 Python 运行时'));
    const proc = spawn(pythonExe, ['-c', UNZIP_SCRIPT, zipPath, destDir]);
    let errOut = '';
    proc.stderr.on('data', (d) => { errOut += d.toString(); });
    proc.on('error', reject);
    proc.on('close', (code) => {
      if (code === 0) resolve();
      else reject(new Error('解压失败：' + errOut.trim().slice(-300)));
    });
  });
}

function copyDir(src, dest, boundRoot) {
  ensureInside(src, boundRoot);
  ensureInside(dest, boundRoot);
  fs.mkdirSync(dest, { recursive: true });
  for (const name of fs.readdirSync(src)) {
    const s = ensureInside(path.join(src, name), boundRoot);
    const d = ensureInside(path.join(dest, name), boundRoot);
    const st = fs.statSync(s);
    if (st.isDirectory()) copyDir(s, d, boundRoot);
    else fs.copyFileSync(s, d);
  }
}

// 递归合并数据包目录到 userData：data.json 永不覆盖；variants.json 用户改过则保留
// skipDocs=true 时跳过 .docx（供 ensureUserCopy 使用，避免安装目录残留报告覆盖用户报告）
function mergeDataTree(stagingDir, udRoot, builtinRoot, warnings, skipDocs) {
  if (!fs.existsSync(stagingDir)) return;
  for (const entry of fs.readdirSync(stagingDir)) {
    const src = ensureInside(path.join(stagingDir, entry), stagingDir);
    const st = fs.statSync(src);
    if (skipDocs && st.isFile() && entry.toLowerCase().endsWith('.docx')) continue;
    const dst = ensureInside(path.join(udRoot, entry), udRoot);
    if (st.isDirectory()) {
      if (entry === 'common') {
        // common 整目录覆盖（公共库，用户不改）
        fs.rmSync(dst, { recursive: true, force: true });
        copyDir(src, dst, udRoot);
        continue;
      }
      // 实验目录：先合并文件
      fs.mkdirSync(dst, { recursive: true });
      mergeDataTree(src, dst, path.join(builtinRoot, entry), warnings);
      // data.json 保障：userData 无而安装目录有时，复制安装目录的用户数据
      const bd = ensureInside(path.join(builtinRoot, entry, 'data.json'), EXPERIMENTS_DIR);
      const dd = ensureInside(path.join(dst, 'data.json'), udRoot);
      if (fs.existsSync(bd) && !fs.existsSync(dd)) {
        fs.copyFileSync(bd, dd);
      }
    } else {
      const name = entry;
      const dstExists = fs.existsSync(dst);
      if (name === 'data.json') {
        if (!dstExists) fs.copyFileSync(src, dst);   // 新实验示例数据允许落盘；已有用户数据永不覆盖
        continue;
      }
      if (name === 'variants.json' && dstExists) {
        // 用户本地改过（与安装目录原版不同）则保留用户版
        const builtinV = ensureInside(path.join(builtinRoot, name), EXPERIMENTS_DIR);
        let userModified = false;
        try {
          const a = fs.readFileSync(builtinV, 'utf-8');
          const b = fs.readFileSync(dst, 'utf-8');
          userModified = a !== b;
        } catch (e) {
          userModified = true;
        }
        if (userModified) {
          warnings.push(`${entry.replace('.json', '')} 的变体已由用户修改，保留本地版本`);
          continue;
        }
      }
      fs.copyFileSync(src, dst);
    }
  }
}

// ── IPC: 应用数据包（解压 + 合并到 userData + 写 manifest）
ipcMain.handle('apply-data-package', async (_, payload) => {
  try {
    const zipPath = String((payload && payload.filePath) || '');
    const version = String((payload && payload.version) || '').trim();
    const notes = String((payload && payload.notes) || '').trim();
    if (!/\.zip$/i.test(path.basename(zipPath))) return { ok: false, error: '数据包应为 zip 文件' };
    const dataRoot = path.join(app.getPath('userData'), '实验数据');
    if (!ensureInside(zipPath, dataRoot)) return { ok: false, error: '无效的数据包路径' };
    if (!fs.existsSync(zipPath)) return { ok: false, error: '数据包文件不存在' };
    const { udRoot, mfPath } = getDataRoots();
    const staging = ensureInside(path.join(dataRoot, '_staging'), dataRoot);
    fs.rmSync(staging, { recursive: true, force: true });
    fs.mkdirSync(staging, { recursive: true });
    await unzipSafe(zipPath, staging);
    // 包内结构约定：zip 内直接是 实验脚本 树（本目录开头）
    const warnings = [];
    const stagingRoot = fs.existsSync(path.join(staging, '实验脚本'))
      ? path.join(staging, '实验脚本')
      : staging;
    mergeDataTree(stagingRoot, udRoot, EXPERIMENTS_DIR, warnings);
    ensureInside(mfPath, path.join(app.getPath('userData'), '实验数据'));
    fs.writeFileSync(mfPath, JSON.stringify({
      dataVersion: version,
      notes,
      updatedAt: new Date().toISOString(),
    }, null, 2), 'utf-8');
    // 清理
    fs.rmSync(staging, { recursive: true, force: true });
    try { fs.unlinkSync(zipPath); } catch (e) { /* 忽略 */ }
    return { ok: true, warnings };
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

// 检查更新：读取更新清单 latest.json（{ version, notes, downloads:[{name,url,hint}] }），仅做版本校对，
// 不下载不安装——把下载入口交给用户（浏览器打开对应链接）
ipcMain.handle('check-for-update', async (_, cfg) => {
  try {
    const manifestUrl = String((cfg && cfg.manifestUrl) || '').trim();
    const current = app.getVersion();
    if (!manifestUrl) {
      return { ok: false, error: '请先在设置中填写自定义更新清单地址' };
    }
    const u = assertPublicUrl(manifestUrl);
    if (!(await checkPublicDns(u.hostname))) {
      throw new Error('更新地址无法解析或指向本地地址');
    }
    const mf = await httpsGetJson(u.href);
    const latest = String(mf.version || '').replace(/^v/i, '');
    const hasUpdate = !!(latest && compareVersions(latest, current) > 0);
    const downloads = [];
    for (const d of (Array.isArray(mf.downloads) ? mf.downloads : [])) {
      const name = String(d.name || '').trim();
      const rawUrl = String(d.url || '').trim();
      if (!name || !rawUrl) continue;
      try {
        const du = assertPublicUrl(rawUrl);
        if (!(await checkPublicDns(du.hostname))) continue;   // 非法/本地入口直接跳过
        downloads.push({ name, url: du.href, hint: String(d.hint || '').trim() });
      } catch (e) { /* 跳过非法下载入口 */ }
    }
    // 兼容旧格式清单（{ url, fileName } 单直链）：downloads 为空时回退构造一个入口
    if (!downloads.length) {
      const legacyUrl = String(mf.url || '').trim();
      if (legacyUrl) {
        try {
          const du = assertPublicUrl(legacyUrl);
          if (await checkPublicDns(du.hostname)) {
            downloads.push({ name: '安装包直链', url: du.href, hint: '' });
          }
        } catch (e) { /* 忽略非法旧地址 */ }
      }
    }
    return {
      ok: true,
      hasUpdate,
      current,
      latest,
      notes: String(mf.notes || '').trim(),
      downloads,
    };
  } catch (err) {
    return { ok: false, error: err.message, hasUpdate: false };
  }
});

// ── IPC: 浏览器打开下载链接（仅允许公网 http/https）──
ipcMain.handle('open-external', async (_, rawUrl) => {
  try {
    const u = assertPublicUrl(rawUrl);
    if (!(await checkPublicDns(u.hostname))) {
      return { ok: false, error: '链接无法解析或指向本地地址' };
    }
    await shell.openExternal(u.href);
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

// ═══════════════════════════════════════════════
// 贡献数据上传（COS 直传：凭证云函数返回预签名 PUT 地址，密钥不进应用）
// ═══════════════════════════════════════════════
// 凭证云函数 URL（部署后替换；为空表示未启用，应用侧会给出明确提示）
const CONTRIBUTE_FN_URL = '';

// 请求上传凭证：云函数校验 key 前缀（contributions/variants|reports）并返回预签名 PUT 地址
ipcMain.handle('contribute-get-credentials', async (_, payload) => {
  try {
    const fnUrl = String((payload && payload.fnUrl) || CONTRIBUTE_FN_URL || '').trim();
    if (!fnUrl) return { ok: false, error: '贡献上传服务未配置（请联系开发者部署凭证云函数）' };
    const keys = Array.isArray((payload && payload.keys) || []) ? payload.keys : [];
    if (!keys.length || keys.length > 20) return { ok: false, error: '文件数量无效' };
    for (const k of keys) {
      if (typeof k !== 'string') return { ok: false, error: '文件名格式无效' };
      const m = String(k).match(/^contributions\/(variants|reports)\/([^/]+)\/([^/]+)$/);
      if (!m) return { ok: false, error: '贡献路径无效：' + String(k).slice(0, 120) };
    }
    const u = assertPublicUrl(fnUrl);
    if (!(await checkPublicDns(u.hostname))) {
      return { ok: false, error: '凭证服务地址无法解析或指向本地地址' };
    }
    const body = JSON.stringify({ keys });
    const resp = await new Promise((resolve, reject) => {
      const r = https.request(u, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(body),
          'User-Agent': 'labreport-writer-contributor',
        },
        timeout: 15000,
      }, res => {
        let data = '';
        res.setEncoding('utf8');
        res.on('data', c => { data += c; });
        res.on('end', () => {
          try { resolve(JSON.parse(data)); } catch (e) { reject(new Error('凭证响应解析失败')); }
        });
      });
      r.on('error', reject);
      r.on('timeout', () => r.destroy(new Error('凭证请求超时')));
      r.write(body);
      r.end();
    });
    const items = Array.isArray(resp && resp.items) ? resp.items : [];
    const out = [];
    for (const it of items) {
      const putUrl = String(it.putUrl || '').trim();
      if (!putUrl) continue;
      try {
        const pu = assertPublicUrl(putUrl);
        if (!(await checkPublicDns(pu.hostname))) continue;
        out.push({ key: String(it.key || ''), putUrl: pu.href });
      } catch (e) { /* 跳过非法凭证 */ }
    }
    if (!out.length) return { ok: false, error: '凭证服务未返回有效上传地址' };
    return { ok: true, items: out };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

// 直传单个文件到预签名 PUT 地址（仅公网 https；单文件上限 20MB）
ipcMain.handle('contribute-upload', async (_, payload) => {
  try {
    const rawUrl = String((payload && payload.putUrl) || '');
    const u = assertPublicUrl(rawUrl);
    if (!(await checkPublicDns(u.hostname))) {
      return { ok: false, error: '上传地址无效或指向本地地址' };
    }
    const rawData = payload && payload.data;
    if (!(rawData instanceof Uint8Array || rawData instanceof ArrayBuffer || Buffer.isBuffer(rawData))) {
      return { ok: false, error: '上传内容无效' };
    }
    const buf = Buffer.isBuffer(rawData) ? rawData : Buffer.from(rawData);
    if (buf.length > 20 * 1024 * 1024) return { ok: false, error: '单个文件不能超过 20MB' };
    const contentType = String((payload && payload.contentType) || 'application/octet-stream');
    const resp = await new Promise((resolve, reject) => {
      const r = https.request(u, {
        method: 'PUT',
        headers: {
          'Content-Type': contentType,
          'Content-Length': buf.length,
          'User-Agent': 'labreport-writer-contributor',
        },
        timeout: 120000,
      }, res => {
        res.resume();
        res.on('end', () => resolve({ status: res.statusCode }));
      });
      r.on('error', reject);
      r.on('timeout', () => r.destroy(new Error('上传超时')));
      r.write(buf);
      r.end();
    });
    if (resp.status !== 200 && resp.status !== 204) {
      return { ok: false, error: `上传失败 HTTP ${resp.status}` };
    }
    return { ok: true };
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
// variants.compose 向 stdout 打印的章节原文标记（供应用侧按章节润色/导入重生成）
const SECTIONS_MARKER = '.LAB_SECTIONS_JSON:';
ipcMain.handle('run-generate', async (_, expPath, studentInfo, variants, polish) => {
  // 生成报告属写操作：迁移/复用 userData 副本，报告与章节缓存不再落入安装目录
  expPath = ensureUserCopy(expPath);
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

// ── IPC: AI 对话（requestId 支持取消：ai-chat-cancel 中止对应请求）──
const aiAbortControllers = new Map();   // requestId -> AbortController
ipcMain.handle('ai-chat', async (_, params) => {
  const { provider, apiKey, apiUrl, model, messages, temperature = 0.7, requestId } = params;
  const controller = new AbortController();
  if (requestId) aiAbortControllers.set(String(requestId), controller);
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
      signal: controller.signal,
    });

    if (!response.ok) {
      const errText = await response.text();
      return { ok: false, error: `API 请求失败 (${response.status}): ${errText.slice(0, 200)}` };
    }

    const data = await response.json();
    const content = data.choices?.[0]?.message?.content || '';
    return { ok: true, content, usage: data.usage };
  } catch (err) {
    if (controller.signal.aborted) {
      return { ok: false, cancelled: true, error: '已取消生成' };
    }
    return { ok: false, error: err.message };
  } finally {
    if (requestId) aiAbortControllers.delete(String(requestId));
  }
});

// 取消一次进行中的 AI 请求
ipcMain.on('ai-chat-cancel', (_, requestId) => {
  const c = aiAbortControllers.get(String(requestId || ''));
  if (c) {
    try { c.abort(); } catch (e) { /* 忽略 */ }
    aiAbortControllers.delete(String(requestId || ''));
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

// ── 变体组合：保存实验的 variants.json（AI 调整结果写回；用户数据落 userData 副本）──
ipcMain.handle('save-variants', async (_, expPath, variants) => {
  try {
    if (!variants || typeof variants !== 'object') {
      return { ok: false, error: '变体数据无效' };
    }
    const p = ensureUserCopy(expPath);
    fs.writeFileSync(path.join(p, 'variants.json'), JSON.stringify(variants, null, 1), 'utf-8');
    return { ok: true, path: p };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});
