// renderer.js — 渲染进程逻辑
let experiments = [];
let currentExp = null;
let currentCategory = 'all';
let isGenerating = false;
let selectedIds = new Set();
let isBatchRunning = false;
// 方式三·生成队列状态
let genQueue = [];        // [{id, name, exp, status:'queued|running|done|failed|cancelled', elapsed, error}]
let queueState = 'idle';  // idle | running | paused | cancelled
let queueResume = null;   // 暂停时唤醒调度循环的 resolve
// 数据未保存标记（表单编辑）
let isDataModified = false;

const $ = (id) => document.getElementById(id);

// ── 实验标准名称映射（文件夹名 → 教材标准名称）──
// 目录已按知识库（lab_部分1.pdf）目录名统一，此处保留映射以备将来目录名调整时兜底
const STANDARD_NAMES = {
  '长度与体积的测量': '长度与体积的测量',
  '扭摆法测量钢丝切变模量': '扭摆法测量钢丝切变模量',
  '重力加速度的测量': '重力加速度的测量',
  '刚体转动惯量的测量': '刚体转动惯量的测量',
  '简谐振动的合成': '简谐振动的合成',
  '声速的测量（水中）': '声速的测量（水中）',
  '声速的测量（空气）': '声速的测量（空气）',
  '薄透镜焦距的测量': '薄透镜焦距的测量',
  '衍射光强分布的测量': '衍射光强分布的测量',
  '三棱镜顶角的测量': '三棱镜顶角的测量',
  '平凸透镜曲率半径的测量': '平凸透镜曲率半径的测量',
  '光的偏振特性测量': '光的偏振特性测量',
  '激光波长的测量': '激光波长的测量',
  '光栅光谱的测量': '光栅光谱的测量',
  '电表的改装与校准': '电表的改装与校准',
  '电子元件伏安特性的测量': '电子元件伏安特性的测量',
  '电子偏转特性的测量': '电子偏转特性的测量',
  '灵敏电流计特性的测量': '灵敏电流计特性的测量',
  '静电场的模拟': '静电场的模拟',
  '霍尔效应实验': '霍尔效应实验',
  '直螺线管磁场分布的测量': '直螺线管磁场分布的测量',
  '低电阻的测量': '低电阻的测量',
  '拉伸法测量钢丝杨氏弹性模量': '拉伸法测量钢丝杨氏弹性模量',
  '电容与高电阻的测量': '电容与高电阻的测量',
  '劈尖干涉': '劈尖干涉',
  '理想气体状态方程': '理想气体状态方程',
};

function getDisplayName(exp) {
  return STANDARD_NAMES[exp.id] || exp.name;
}

// ── Toast 通知 ──
function showToast(type, title, detail = '', duration = 3000) {
  const container = $('toastContainer');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;

  const icons = {
    success: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>',
    error: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
    warning: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
    info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
  };

  toast.innerHTML = `
    <div class="toast-icon">${icons[type] || icons.info}</div>
    <div class="toast-content">
      <div class="toast-title">${title}</div>
      ${detail ? `<div class="toast-detail">${detail}</div>` : ''}
    </div>
    <button class="toast-close">×</button>
  `;

  // 新弹窗出现时删除上一个，避免弹窗堆积
  container.innerHTML = '';
  container.appendChild(toast);

  const close = () => {
    toast.classList.add('leaving');
    setTimeout(() => toast.remove(), 200);
  };
  toast.querySelector('.toast-close').onclick = close;
  if (duration > 0) setTimeout(close, duration);
}

// ── 实验分类 ──
const CATEGORY_RULES = {
  mechanics: ['扭摆', '重力', '转动惯量', '简谐振动', '拉伸法', '杨氏', '复摆', '三线摆', '音叉', '动量', '碰撞'],
  optics: ['薄透镜', '衍射', '三棱镜', '平凸', '牛顿环', '偏振', '激光波长', '光栅', '劈尖', '迈克尔逊', '焦距', '光强'],
  electromagnetism: ['电表', '电子元件', '伏安', '电子束', '电子偏转', '灵敏电流计', '静电场', '霍尔', '螺线管', '磁场', '低电阻', '电容', '高电阻', 'RLC', '马吕斯', '单臂电桥', '电流场', '双臂电桥', '电动势', '电位差计'],
};

function getCategory(name) {
  for (const [cat, keywords] of Object.entries(CATEGORY_RULES)) {
    if (keywords.some(kw => name.includes(kw))) return cat;
  }
  return 'other';
}

const CATEGORY_NAMES = {
  all: '全部实验',
  mechanics: '力学',
  optics: '光学',
  electromagnetism: '电磁学',
  other: '其他',
};

// ── 学生信息（localStorage）──
function loadStudentInfo() {
  try {
    return JSON.parse(localStorage.getItem('studentInfo') || '{}');
  } catch { return {}; }
}
function saveStudentInfo(info) {
  localStorage.setItem('studentInfo', JSON.stringify(info));
}

function loadSettings() {
  try {
    return JSON.parse(localStorage.getItem('appSettings') || '{}');
  } catch { return {}; }
}
function saveSettings(settings) {
  localStorage.setItem('appSettings', JSON.stringify(settings));
}

// ── 初始化 ──
async function init() {
  experiments = await window.labAPI.scanExperiments();
  experiments.forEach(e => { e.category = getCategory(e.name); });

  updateCategoryCounts();
  renderList();
  updateEmptyStats();
  updateStudentDisplay();
  bindEvents();
}

// ── 分类计数 ──
function updateCategoryCounts() {
  const counts = { all: experiments.length, mechanics: 0, optics: 0, electromagnetism: 0, other: 0 };
  experiments.forEach(e => { counts[e.category]++; });
  $('count-all').textContent = counts.all;
  $('count-mechanics').textContent = counts.mechanics;
  $('count-optics').textContent = counts.optics;
  $('count-em').textContent = counts.electromagnetism;
  $('count-other').textContent = counts.other;
}

// ── 渲染实验列表 ──
function renderList(keyword = '') {
  const list = $('expList');
  list.innerHTML = '';

  let filtered = experiments;
  if (currentCategory !== 'all') {
    filtered = filtered.filter(e => e.category === currentCategory);
  }
  if (keyword) {
    const kw = keyword.toLowerCase();
    filtered = filtered.filter(e => e.name.toLowerCase().includes(kw));
  }

  $('listTitle').textContent = CATEGORY_NAMES[currentCategory];
  $('listCount').textContent = filtered.length;

  // 按分类排序
  const catOrder = { mechanics: 0, optics: 1, electromagnetism: 2, other: 3 };
  filtered.sort((a, b) => {
    if (a.category !== b.category) return catOrder[a.category] - catOrder[b.category];
    return a.name.localeCompare(b.name, 'zh');
  });

  for (const exp of filtered) {
    const li = document.createElement('li');
    const isSelected = selectedIds.has(exp.id);
    const isActive = currentExp && currentExp.id === exp.id;
    li.className = 'exp-item' + (isActive ? ' active' : '') + (isSelected ? ' selected' : '');
    li.innerHTML = `
      <div class="exp-checkbox ${isSelected ? 'checked' : ''}" data-id="${exp.id}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
      </div>
      <span class="exp-dot ${exp.hasReport ? 'done' : ''}"></span>
      <span class="exp-name">${getDisplayName(exp)}</span>
      <span class="exp-cat">${CATEGORY_NAMES[exp.category].slice(0, 2)}</span>
    `;
    // checkbox 点击只切换选中，不打开详情
    li.querySelector('.exp-checkbox').onclick = (e) => {
      e.stopPropagation();
      toggleSelect(exp.id);
    };
    li.onclick = () => selectExperiment(exp);
    list.appendChild(li);
  }
  updateBatchButton();
  updateSelectAllButton();
}

// ── 选中实验 ──
function selectExperiment(exp) {
  currentExp = exp;
  $('emptyState').style.display = 'none';
  $('detailPanel').style.display = 'block';
  $('batchPanel').style.display = 'none';

  $('expName').textContent = getDisplayName(exp);
  $('expCat').textContent = CATEGORY_NAMES[exp.category];

  $('metaData').textContent = exp.hasData ? '数据已就绪' : '无数据模板';
  $('metaData').className = 'meta-dot' + (exp.hasData ? ' ok' : '');
  $('metaReport').textContent = exp.hasReport ? '报告已生成' : '未生成';
  $('metaReport').className = 'meta-dot' + (exp.hasReport ? ' ok' : '');

  $('dataFileName').textContent = exp.dataFile ? exp.dataFile.split(/[\\/]/).pop() : 'data.json（保存后生成）';
  $('dataFilePath').textContent = exp.dataFile || '—';

  $('btnOpenData').disabled = !exp.hasData;
  $('btnOpenData2').disabled = !exp.hasData;
  $('btnOpenReport').disabled = !exp.hasReport;
  $('btnOpenReport2').disabled = !exp.hasReport;

  // 结果区
  setResultState(exp.hasReport && exp.reportFile ? 'success' : 'empty', exp.reportFile);

  $('logContent').textContent = '等待生成...';

  // 切换到数据录入 tab
  switchTab('data');
  renderList($('searchInput').value);

  // 方式三：检测 schema，加载表单
  loadExperimentData(exp);
  // 加载变体组合面板
  loadVariantsUI(exp);
  // 重置预览状态
  previewLoaded = false;
  // 更新 AI 状态（润色对象/技能/导入提示）
  updateAiStatus();
  refreshAiScopeOptions(false);
  loadSkillList();
  updateOverrideBar();
}

// ── 多选与批量生成 ──
function toggleSelect(id) {
  if (selectedIds.has(id)) selectedIds.delete(id);
  else selectedIds.add(id);
  renderList($('searchInput').value);
}

function toggleSelectAll() {
  const list = $('expList');
  const visibleIds = Array.from(list.querySelectorAll('.exp-checkbox')).map(cb => cb.dataset.id);
  const allSelected = visibleIds.every(id => selectedIds.has(id));
  if (allSelected) {
    visibleIds.forEach(id => selectedIds.delete(id));
  } else {
    visibleIds.forEach(id => selectedIds.add(id));
  }
  renderList($('searchInput').value);
}

function updateSelectAllButton() {
  const list = $('expList');
  const visibleIds = Array.from(list.querySelectorAll('.exp-checkbox')).map(cb => cb.dataset.id);
  const btn = $('btnSelectAll');
  if (visibleIds.length > 0 && visibleIds.every(id => selectedIds.has(id))) {
    btn.classList.add('active');
  } else {
    btn.classList.remove('active');
  }
}

function updateBatchButton() {
  const btn = $('btnBatch');
  const count = selectedIds.size;
  if (count > 0 && !isBatchRunning) {
    btn.disabled = false;
    btn.textContent = `批量生成 (${count})`;
  } else if (isBatchRunning) {
    btn.disabled = true;
    btn.textContent = '生成中...';
  } else {
    btn.disabled = true;
    btn.textContent = '批量生成';
  }
}

async function runBatchGenerate() {
  // 队列活跃（running/paused）时点击只是回面板查看，不重建
  if (queueState === 'running' || queueState === 'paused') { openQueuePanel(); return; }
  const sel = experiments.filter(e => selectedIds.has(e.id));
  if (sel.length === 0) { showToast('warning', '未选择实验', '请先在列表勾选要生成的实验'); return; }
  genQueue = sel.map(e => ({ id: e.id, name: e.name, exp: e, status: 'queued', elapsed: 0, error: '' }));
  if ($('batchLog')) $('batchLog').textContent = '';
  openQueuePanel();
  await pumpQueue();
}

function openQueuePanel() {
  $('emptyState').style.display = 'none';
  $('detailPanel').style.display = 'none';
  $('batchPanel').style.display = 'block';
  renderQueue(); renderQueueControls(); updateQueueProgress();
}

async function pumpQueue() {
  queueState = 'running'; isBatchRunning = true;
  renderQueue(); renderQueueControls(); updateQueueProgress(); updateBatchButton();
  const studentInfo = loadStudentInfo();
  for (const q of genQueue) {
    if (q.status !== 'queued') continue;
    while (queueState === 'paused') await new Promise(res => { queueResume = res; });
    if (queueState === 'cancelled') break;
    q.status = 'running'; q.startedAt = Date.now(); q.error = '';
    renderQueue(); renderQueueControls(); updateQueueProgress();
    $('batchLog').textContent += `\n▶ ${getDisplayName(q.exp)}\n`;
    try {
      const r = await window.labAPI.runGenerate(q.exp.path, studentInfo, null, expOverrides(q.exp.id));
      q.elapsed = (Date.now() - q.startedAt) / 1000;
      q.status = r.ok ? 'done' : (r.cancelled ? 'cancelled' : 'failed');
      if (!r.ok) q.error = r.error || ('exit ' + r.exitCode);
    } catch (err) {
      q.elapsed = (Date.now() - q.startedAt) / 1000;
      q.status = 'failed'; q.error = err.message;
    }
    $('batchLog').textContent += `  ${q.status === 'done' ? '✓' : '✗'} ${q.elapsed.toFixed(1)}s${q.error ? ' · ' + q.error : ''}\n`;
    $('batchLog').scrollTop = $('batchLog').scrollHeight;
    renderQueue(); updateQueueProgress();
  }
  if (queueState === 'cancelled') genQueue.forEach(q => { if (q.status === 'queued') q.status = 'cancelled'; });
  queueState = 'idle'; isBatchRunning = false; queueResume = null;
  renderQueue(); renderQueueControls(); updateQueueProgress(); updateBatchButton();
  try {
    experiments = await window.labAPI.scanExperiments();
    experiments.forEach(e => { e.category = getCategory(e.name); });
    updateCategoryCounts(); updateEmptyStats(); renderList($('searchInput').value);
  } catch (e) { /* 刷新失败不影响队列结果 */ }
}

function pauseQueue() { if (queueState === 'running') { queueState = 'paused'; renderQueueControls(); } }
function resumeQueue() {
  if (queueState === 'paused') {
    queueState = 'running'; renderQueueControls();
    if (queueResume) { const r = queueResume; queueResume = null; r(); }
  }
}
function cancelAllQueue() {
  if (queueState !== 'running' && queueState !== 'paused') return;
  queueState = 'cancelled'; renderQueueControls();
  try { window.labAPI.cancelGenerate(); } catch (e) {}
  if (queueResume) { const r = queueResume; queueResume = null; r(); }
}
function cancelQueueItem(id) {
  const q = genQueue.find(x => x.id === id); if (!q) return;
  if (q.status === 'queued') { q.status = 'cancelled'; renderQueue(); updateQueueProgress(); }
  else if (q.status === 'running') { try { window.labAPI.cancelGenerate(); } catch (e) {} }
}
function removeQueueItem(id) {
  const q = genQueue.find(x => x.id === id);
  if (!q || q.status === 'running') return;
  genQueue = genQueue.filter(x => x.id !== id);
  renderQueue(); updateQueueProgress();
}
function moveQueueItem(id, dir) {
  const i = genQueue.findIndex(x => x.id === id); const j = i + dir;
  if (i < 0 || j < 0 || j >= genQueue.length) return;
  if (genQueue[i].status !== 'queued' || genQueue[j].status === 'running') return;
  [genQueue[i], genQueue[j]] = [genQueue[j], genQueue[i]];
  renderQueue();
}
function clearFinishedQueue() {
  genQueue = genQueue.filter(q => q.status === 'queued' || q.status === 'running');
  renderQueue(); updateQueueProgress();
}

const QUEUE_STATUS_TEXT = { queued: '等待', running: '生成中…', done: '✓ 完成', failed: '✗ 失败', cancelled: '已取消' };
// 顶栏"队列"入口：队列非空即可回到面板；运行/暂停时高亮提示
function updateQueueEntry() {
  const btn = $('btnQueuePanel');
  if (!btn) return;
  const n = genQueue.length;
  const active = queueState === 'running' || queueState === 'paused';
  btn.disabled = n === 0;
  btn.textContent = n > 0 ? `队列 (${n})` : '队列';
  btn.className = 'btn btn-sm ' + (active ? 'btn-primary' : 'btn-ghost');
  btn.title = active ? '队列运行中，点击查看' : '打开生成队列面板';
}

function renderQueue() {
  updateQueueEntry();
  const list = $('queueList'); if (!list) return;
  if (!genQueue.length) { list.innerHTML = '<div class="queue-empty">队列为空</div>'; renderQueueControls(); return; }
  let html = '';
  for (const q of genQueue) {
    const acts = [];
    if (q.status === 'queued') {
      acts.push(`<button class="qbtn" data-act="up" data-id="${q.id}" title="上移">↑</button>`);
      acts.push(`<button class="qbtn" data-act="down" data-id="${q.id}" title="下移">↓</button>`);
      acts.push(`<button class="qbtn qbtn-danger" data-act="cancel" data-id="${q.id}" title="取消">✕</button>`);
    } else if (q.status === 'running') {
      acts.push(`<button class="qbtn qbtn-danger" data-act="cancel" data-id="${q.id}" title="终止当前">■</button>`);
    } else {
      acts.push(`<button class="qbtn" data-act="remove" data-id="${q.id}" title="移除">－</button>`);
    }
    const meta = q.error ? escapeHtml(q.error) : (q.elapsed ? q.elapsed.toFixed(1) + 's' : '');
    html += `<div class="queue-item q-${q.status}">`
      + `<span class="q-status">${QUEUE_STATUS_TEXT[q.status]}</span>`
      + `<span class="q-name">${escapeHtml(getDisplayName(q.exp))}</span>`
      + `<span class="q-meta">${meta}</span>`
      + `<span class="q-acts">${acts.join('')}</span>`
      + `</div>`;
  }
  list.innerHTML = html;
}

function renderQueueControls() {
  const badge = $('queueStateBadge');
  if (badge) {
    const m = { idle: '空闲', running: '运行中', paused: '已暂停', cancelled: '取消中' };
    badge.textContent = m[queueState] || queueState;
    badge.className = 'queue-state-badge qs-' + queueState;
  }
  const pause = $('btnQueuePause'), resume = $('btnQueueResume');
  if (pause) pause.style.display = (queueState === 'running') ? '' : 'none';
  if (resume) resume.style.display = (queueState === 'paused') ? '' : 'none';
  const active = queueState === 'running' || queueState === 'paused';
  if ($('btnQueueCancelAll')) $('btnQueueCancelAll').disabled = !active;
  if ($('btnQueueClear')) $('btnQueueClear').disabled = active;
}

function updateQueueProgress() {
  const total = genQueue.length;
  const done = genQueue.filter(q => q.status === 'done' || q.status === 'failed' || q.status === 'cancelled').length;
  if ($('batchProgressFill')) $('batchProgressFill').style.width = (total ? (done / total * 100) : 0) + '%';
  if ($('batchProgressText')) $('batchProgressText').textContent = `${done} / ${total}`;
}

// ── 事件日志 ──
function logEvent(msg) {
  try {
    if (window.labAPI && window.labAPI.logEvent) window.labAPI.logEvent(msg);
  } catch (e) { /* 忽略 */ }
}

// ══════════════════════════════════════════════════════════
// 方式三：表单模式（schema 驱动，data.json 为数据真相）
// 全部实验均有 schema.json，统一走表单渲染；无 schema 时提示未迁移
// ══════════════════════════════════════════════════════════
let currentSchema = null;   // 当前实验 schema（null = 未迁移）
let currentData = null;     // 当前表单数据

function escapeHtml(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

async function loadExperimentData(exp) {
  let sr = { ok: false, schema: null };
  try { sr = await window.labAPI.readSchema(exp.path); } catch (e) { /* 按未迁移处理 */ }
  if (sr.ok && sr.schema) {
    currentSchema = sr.schema;
    await loadFormData(exp);
  } else {
    currentSchema = null;
    currentData = null;
    $('dataTableWrap').innerHTML = '<div class="data-table-empty">该实验尚未迁移，暂不能在应用内填写</div>';
    $('sheetTabs').style.display = 'none';
    $('btnClearFormData').disabled = true;
  }
}

async function loadFormData(exp) {
  let result = { ok: false, data: null };
  try { result = await window.labAPI.readData(exp.path); } catch (e) { /* 忽略 */ }
  currentData = (result.ok && result.data) ? result.data : {};
  isDataModified = false;
  $('btnSaveData').disabled = true;
  $('btnClearFormData').disabled = false;
  notifyDataModified();
  $('sheetTabs').style.display = 'none';   // 表单模式无 sheet 切换
  $('dataIssueBar').style.display = 'none';
  renderForm();
  refreshFormCheck();
}

// 清除表单全部可输入数据（置空，便于从头填写；需点"保存修改"才写入 data.json）
function clearFormData() {
  if (!currentSchema || !currentExp) return;
  if (!confirm('清除当前实验表单中已填写的全部数据？\n所有字段将置为空值，清除后需点击「保存修改」才会写入数据文件。')) return;
  for (const group of (currentSchema.groups || [])) {
    for (const fld of (group.fields || [])) {
      if (fld.type === 'array') {
        currentData[fld.key] = new Array(fld.length || 0).fill(null);
      } else if (fld.type === 'matrix') {
        currentData[fld.key] = Array.from({ length: fld.rows || 0 }, () => new Array(fld.cols || 0).fill(null));
      } else {
        currentData[fld.key] = null;
      }
    }
  }
  renderForm();
  isDataModified = true;
  notifyDataModified();
  $('btnSaveData').disabled = false;
  refreshFormCheck();
  showToast('info', '已清除', '全部字段已置空，填写后请点击「保存修改」');
}

function renderForm() {
  const wrap = $('dataTableWrap');
  if (!currentSchema) { wrap.innerHTML = ''; return; }
  let html = '<div class="schema-form">';
  for (const group of (currentSchema.groups || [])) {
    html += '<div class="form-group">';
    if (group.name) html += `<div class="form-group-title">${escapeHtml(group.name)}</div>`;
    for (const fld of (group.fields || [])) html += renderField(fld);
    html += '</div>';
  }
  html += '</div>';
  wrap.innerHTML = html;
  wrap.querySelectorAll('input[data-key]').forEach(inp => {
    inp.addEventListener('input', onFormInput);
    // 禁止鼠标滚轮改变 number 输入框的值（聚焦时滚轮应滚动页面而非改数）
    if (inp.type === 'number') inp.addEventListener('wheel', (e) => { e.currentTarget.blur(); }, { passive: true });
  });
}

function renderField(fld) {
  const key = fld.key;
  const label = escapeHtml(fld.label || key);
  const unit = fld.unit ? `<span class="field-unit">${escapeHtml(fld.unit)}</span>` : '';
  const val = currentData ? currentData[key] : null;
  const hasVal = (v) => v !== null && v !== undefined && v !== '';

  if (fld.type === 'number') {
    const v = hasVal(val) ? val : (fld.default !== undefined ? fld.default : '');
    return `<div class="form-field form-field-number">`
      + `<label class="field-label">${label}</label>`
      + `<input type="number" step="any" class="field-input" data-key="${escapeHtml(key)}" value="${escapeHtml(v)}">`
      + unit + `</div>`;
  }
  if (fld.type === 'array') {
    const len = fld.length || (Array.isArray(val) ? val.length : 0);
    let cells = '';
    for (let i = 0; i < len; i++) {
      const av = (Array.isArray(val) && hasVal(val[i])) ? val[i] : '';
      cells += `<label class="array-cell"><span class="cell-idx">${i + 1}</span>`
        + `<input type="number" step="any" class="field-input array-input" data-key="${escapeHtml(key)}" data-idx="${i}" value="${escapeHtml(av)}"></label>`;
    }
    return `<div class="form-field form-field-array">`
      + `<div class="field-head"><span class="field-label">${label}</span>${unit}</div>`
      + `<div class="array-grid">${cells}</div></div>`;
  }
  if (fld.type === 'matrix') {
    const rows = fld.rows || 0, cols = fld.cols || 0;
    const rowLabels = fld.rowLabels || [], colLabels = fld.colLabels || [];
    let table = '<div class="matrix-scroll"><table class="matrix-input">';
    table += '<thead><tr><th class="matrix-corner"></th>';
    for (let c = 0; c < cols; c++) {
      const cl = (colLabels[c] != null) ? colLabels[c] : (c + 1);
      table += `<th class="matrix-col-label">${escapeHtml(String(cl))}</th>`;
    }
    table += '</tr></thead><tbody>';
    for (let r = 0; r < rows; r++) {
      const rl = (rowLabels[r] != null) ? rowLabels[r] : (r + 1);
      table += `<tr><td class="matrix-row-label">${escapeHtml(String(rl))}</td>`;
      for (let c = 0; c < cols; c++) {
        const mv = (Array.isArray(val) && val[r] && hasVal(val[r][c])) ? val[r][c] : '';
        table += `<td><input type="number" step="any" class="field-input matrix-cell" data-key="${escapeHtml(key)}" data-row="${r}" data-col="${c}" value="${escapeHtml(mv)}"></td>`;
      }
      table += '</tr>';
    }
    table += '</tbody></table></div>';
    return `<div class="form-field form-field-matrix">`
      + `<div class="field-head"><span class="field-label">${label}</span>${unit}</div>` + table + `</div>`;
  }
  // text 兜底
  const v = hasVal(val) ? val : '';
  return `<div class="form-field">`
    + `<label class="field-label">${label}</label>`
    + `<input type="text" class="field-input" data-key="${escapeHtml(key)}" value="${escapeHtml(v)}">`
    + unit + `</div>`;
}

function onFormInput() {
  if (!isDataModified) {
    isDataModified = true;
    $('btnSaveData').disabled = false;
    notifyDataModified();
  }
}

function readFormData() {
  const data = {};
  if (!currentSchema) return data;
  for (const group of (currentSchema.groups || [])) {
    for (const fld of (group.fields || [])) {
      const key = fld.key;
      if (fld.type === 'number') {
        const inp = document.querySelector(`input[data-key="${key}"]:not([data-idx]):not([data-row])`);
        data[key] = (inp && inp.value !== '') ? parseFloat(inp.value) : null;
      } else if (fld.type === 'array') {
        const inputs = document.querySelectorAll(`input[data-key="${key}"][data-idx]`);
        data[key] = Array.from(inputs).map(i => i.value !== '' ? parseFloat(i.value) : null);
      } else if (fld.type === 'matrix') {
        const rows = fld.rows || 0, cols = fld.cols || 0;
        const m = [];
        for (let r = 0; r < rows; r++) {
          const row = [];
          for (let c = 0; c < cols; c++) {
            const inp = document.querySelector(`input[data-key="${key}"][data-row="${r}"][data-col="${c}"]`);
            row.push(inp && inp.value !== '' ? parseFloat(inp.value) : null);
          }
          m.push(row);
        }
        data[key] = m;
      } else {
        const inp = document.querySelector(`input[data-key="${key}"]`);
        data[key] = inp ? (inp.value === '' ? null : inp.value) : null;
      }
    }
  }
  return data;
}

async function saveFormData() {
  if (!currentExp || !currentSchema) return false;
  const data = readFormData();
  const result = await window.labAPI.writeData(currentExp.path, data);
  if (result.ok) {
    currentData = data;
    isDataModified = false;
    $('btnSaveData').disabled = true;
    notifyDataModified();
    showToast('success', '数据已保存', getDisplayName(currentExp));
    refreshFormCheck();
    return true;
  }
  showToast('error', '保存失败', result.error, 5000);
  return false;
}

function refreshFormCheck() {
  if (!currentSchema) return;
  const data = readFormData();
  const missing = [];
  for (const group of (currentSchema.groups || [])) {
    for (const fld of (group.fields || [])) {
      if (!fld.required) continue;
      const v = data[fld.key];
      if (v === null || v === undefined) { missing.push(fld.label || fld.key); continue; }
      if (Array.isArray(v)) {
        const flat = (v.length && Array.isArray(v[0])) ? v.flat() : v;
        if (flat.some(x => x === null || x === undefined)) missing.push(fld.label || fld.key);
      }
    }
  }
  const bar = $('dataIssueBar');
  if (missing.length > 0) {
    bar.style.display = 'block';
    bar.innerHTML = `<span class="issue-text">未填 ${missing.length} 项必填数据：${escapeHtml(missing.join('、'))}</span>`;
  } else {
    bar.style.display = 'none';
  }
}

// 通知主进程当前是否有未保存的数据（用于关闭前提示）
function notifyDataModified() {
  if (window.labAPI && window.labAPI.setDataModified) {
    window.labAPI.setDataModified(isDataModified);
  }
}

async function saveExcelData() {
  if (currentSchema) return saveFormData();  // 方式三：统一走表单保存
  return false;
}

async function reloadExcelData() {
  if (isDataModified && !confirm('有未保存的修改，确定重新加载吗？')) return;
  await loadExperimentData(currentExp);
}

// ── 报告预览 ──
let previewLoaded = false;

async function getReportText() {
  if (!currentExp || !currentExp.reportFile) return '';
  const result = await window.labAPI.docxToHtml(currentExp.reportFile);
  if (!result.ok) return '';
  const div = document.createElement('div');
  div.innerHTML = result.html;
  return div.textContent || div.innerText || '';
}

function extractSection(text, scope) {
  if (scope === 'full') return text.trim();

  const patterns = {
    principle: ['实验原理', '实验目的', '实验原理与'],
    analysis: ['结果分析', '数据处理', '实验结果', '结果与分析', '数据记录与处理'],
  };

  const keywords = patterns[scope] || [];
  for (const kw of keywords) {
    const idx = text.indexOf(kw);
    if (idx !== -1) {
      // 找到下一个章节标题（以"一、""二、""三、"等开头的行）
      const after = text.slice(idx + kw.length);
      const nextSection = after.search(/\n[一二三四五六七八九十]+、/);
      if (nextSection !== -1) {
        return (kw + after.slice(0, nextSection)).trim();
      }
      return (kw + after).trim();
    }
  }
  // 没找到对应章节，返回全文
  return text.trim();
}

function getAiStylePrompt(style) {
  const styles = {
    rigorous: '严谨学术风格：使用规范的物理学术语，逻辑严密，表述精确，符合大学物理实验报告的学术规范。',
    concise: '简洁明了风格：语言简练，直击要点，避免冗余修饰，用最少的文字表达完整的实验内容。',
    detailed: '详细充实风格：内容丰富，对实验现象和数据进行深入分析，补充必要的物理意义解释，使报告更加充实完整。',
  };
  return styles[style] || styles.rigorous;
}

// ── AI 润色：章节源文缓存 / 技能 / 导入覆盖 ──
let currentSections = null;      // .lab_sections.json 内容 {章节: 原文(含 $ 公式)}
let lastPolishResults = [];      // 本轮润色结果 [{section, displayScope, original, polished} | {error}]

function loadAllOverrides() { try { return JSON.parse(localStorage.getItem('polishOverrides') || '{}'); } catch { return {}; } }
function saveAllOverrides(all) { localStorage.setItem('polishOverrides', JSON.stringify(all)); }
function expOverrides(expId) { return loadAllOverrides()[expId] || {}; }
function setPolishOverride(expId, section, text) {
  const all = loadAllOverrides();
  (all[expId] = all[expId] || {})[section] = text;
  saveAllOverrides(all);
}
function clearPolishOverrides(expId) {
  const all = loadAllOverrides();
  delete all[expId];
  saveAllOverrides(all);
}

function updateOverrideBar() {
  const bar = $('aiOverrideBar');
  if (!bar) return;
  const keys = currentExp ? Object.keys(expOverrides(currentExp.id)) : [];
  if (!keys.length) { bar.style.display = 'none'; return; }
  $('aiOverrideText').textContent = `已导入润色章节：${keys.join('、')} —— 重新生成报告时将直接采用润色文本`;
  bar.style.display = 'flex';
}

async function refreshAiScopeOptions(keepValue) {
  currentSections = null;
  try {
    if (currentExp) {
      const r = await window.labAPI.readSections(currentExp.path);
      if (r && r.ok && r.sections) currentSections = r.sections;
    }
  } catch (e) { /* 无缓存按仅复制处理 */ }
  const box = $('aiScopeGroup');
  if (!box) return;
  const prev = keepValue ? new Set([...box.querySelectorAll('input:checked')].map(i => i.value)) : new Set();
  box.innerHTML = '';
  const add = (v, t) => {
    const label = document.createElement('label');
    label.className = 'ai-check';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.value = v;
    if (prev.has(v)) cb.checked = true;
    label.appendChild(cb);
    label.appendChild(document.createTextNode(t));
    box.appendChild(label);
  };
  if (currentSections) {
    for (const sec of Object.keys(currentSections)) add('sec:' + sec, sec + '（可导入）');
  }
  add('analysis', '结果分析（取自报告 · 仅复制）');
  add('full', '全文（仅复制）');
  if (!prev.size) {
    const first = box.querySelector('input');
    if (first) first.checked = true;
  }
}

// ── AI 润色技能（文件制：userData/skills，由外部 Skill 文件导入）──
let skillsCache = [];   // [{id,name,description,content}]

function getSkillStates() {
  const s = loadSettings();
  return (s.skillStates && typeof s.skillStates === 'object') ? s.skillStates : {};
}
function setSkillState(id, enabled) {
  const s = loadSettings();
  s.skillStates = Object.assign({}, getSkillStates());
  s.skillStates[id] = enabled;
  saveSettings(s);
}
function getEnabledSkills() {
  const st = getSkillStates();
  return skillsCache.filter(sk => st[sk.id] !== false);
}
function renderSkillOptions(keepValue) {
  const box = $('aiSkillGroup');
  if (!box) return;
  const prev = keepValue ? new Set([...box.querySelectorAll('input:checked')].map(i => i.value)) : new Set();
  box.innerHTML = '';
  const skills = getEnabledSkills();
  if (!skills.length) {
    const span = document.createElement('span');
    span.className = 'ai-check-empty';
    span.textContent = '暂无已启用的技能（可在「设置 → AI 润色技能」导入）';
    box.appendChild(span);
    return;
  }
  for (const sk of skills) {
    const label = document.createElement('label');
    label.className = 'ai-check';
    label.title = sk.description || sk.name;
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.value = sk.id;
    if (prev.has(sk.id)) cb.checked = true;
    label.appendChild(cb);
    label.appendChild(document.createTextNode(sk.name));
    box.appendChild(label);
  }
}

async function loadSkillList() {
  try {
    const r = await window.labAPI.listSkills();
    skillsCache = (r && r.ok && Array.isArray(r.skills)) ? r.skills : [];
  } catch (e) { skillsCache = []; }
  renderSkillRows();
  renderSkillOptions(true);
}

function renderSkillRows() {
  const list = $('skillList');
  if (!list) return;
  list.innerHTML = '';
  if (!skillsCache.length) {
    const empty = document.createElement('div');
    empty.className = 'skill-empty';
    empty.textContent = '暂无技能 —— 点击下方「导入 skill」添加开源 Skill 文件（.md）';
    list.appendChild(empty);
    return;
  }
  const states = getSkillStates();
  for (const sk of skillsCache) {
    const row = document.createElement('div');
    row.className = 'skill-row';

    const info = document.createElement('div');
    info.className = 'skill-info';
    const nameEl = document.createElement('div');
    nameEl.className = 'skill-name-text';
    nameEl.textContent = sk.name;
    info.appendChild(nameEl);
    if (sk.description) {
      const d = document.createElement('div');
      d.className = 'skill-desc';
      d.textContent = sk.description;
      d.title = sk.description;
      info.appendChild(d);
    }

    const toggle = document.createElement('label');
    toggle.className = 'checkbox-label skill-toggle';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = states[sk.id] !== false;
    cb.onchange = () => { setSkillState(sk.id, cb.checked); renderSkillOptions(true); };
    toggle.appendChild(cb);
    toggle.appendChild(document.createTextNode('启用'));

    const del = document.createElement('button');
    del.type = 'button';
    del.className = 'btn btn-sm btn-ghost skill-del';
    del.textContent = '删除';
    del.onclick = async () => {
      if (!confirm('删除技能「' + sk.name + '」？\n技能文件将从配置文件夹中移除。')) return;
      const rr = await window.labAPI.deleteSkill(sk.id);
      if (rr && rr.ok) { showToast('success', '已删除', sk.name); await loadSkillList(); }
      else showToast('error', '删除失败', (rr && rr.error) || '未知错误', 5000);
    };

    row.appendChild(info);
    row.appendChild(toggle);
    row.appendChild(del);
    list.appendChild(row);
  }
}

async function importSkillFiles() {
  const r = await window.labAPI.importSkill();
  if (!r || !r.ok) { showToast('error', '导入失败', (r && r.error) || '未知错误', 5000); return; }
  if (r.imported && r.imported.length) {
    showToast('success', '已导入 ' + r.imported.length + ' 个技能', r.imported.join('、'));
    await loadSkillList();
  }
  if (r.errors && r.errors.length) showToast('warning', '部分导入失败', r.errors.join('；'), 6000);
}

async function runAiPolish() {
  if (!currentExp || !currentExp.reportFile) {
    showToast('warning', '请先生成报告', '需要先生成报告才能进行 AI 润色');
    return;
  }

  const settings = loadSettings();
  if (!settings.apiKey) {
    showToast('warning', '未配置 API Key', '请在设置中配置 API Key 后再使用');
    return;
  }

  const style = document.querySelector('input[name="aiStyle"]:checked')?.value || 'rigorous';
  const scopeVals = [...document.querySelectorAll('#aiScopeGroup input[type="checkbox"]:checked')].map(i => i.value);
  if (!scopeVals.length) {
    showToast('warning', '未选择润色对象', '请至少勾选一个章节或范围');
    return;
  }
  const skillIds = [...document.querySelectorAll('#aiSkillGroup input[type="checkbox"]:checked')].map(i => i.value);
  const kbOnly = $('chkKbOnly').checked;

  // 知识库与技能指令：本轮所有润色对象共用
  let ragText = '';
  if (kbOnly) {
    try {
      const rr = await window.labAPI.readRag(currentExp.path);
      if (rr && rr.ok && rr.text) ragText = rr.text;
    } catch (e) { /* 读取失败时降级为软约束 */ }
  }
  const kbBlock = kbOnly
    ? `\n\n【知识库硬性约束——本实验教材原理是唯一权威依据】\n${ragText ? ragText.slice(0, 8000) : '（本实验未提供知识库文本）'}\n只能使用知识库与原文中有依据的表述：不得新增两者中不存在的公式、数据、常数或结论，不得凭常识臆造。${ragText ? '' : '当前无知识库：只做语言层面的改写，禁止补充任何物理内容。'}`
    : '';
  const skillBlock = skillIds
    .map(id => skillsCache.find(s => s.id === id))
    .filter(Boolean)
    .map(s => `\n【技能·${s.name}（优先遵循）】${(s.content || '').slice(0, 2000)}`)
    .join('');
  const formatBlock = '\n\n【输出格式硬性要求】只输出改写后的正文（Markdown）：任何数学表达（含 \\pi、\\Delta 等符号和上下标）一律用 $...$ 包裹，独立公式用单行 $$...$$（定界符与公式同一行）；不得输出裸的 \\frac、^、_ 等未包裹的 LaTeX；不得改变任何数值、单位与变量符号；不要输出章节编号标题（如"一、"），不要输出任何解释。';

  // 显示加载状态
  $('aiResultCard').style.display = 'none';
  $('aiLoadingCard').style.display = 'block';
  $('btnAiPolish').disabled = true;

  // "结果分析/全文"取自 docx 纯文本，只提取一次
  let fullText = '';
  if (scopeVals.some(v => !v.startsWith('sec:'))) {
    try { fullText = await getReportText(); } catch (e) { fullText = ''; }
  }

  const results = [];
  try {
    for (let i = 0; i < scopeVals.length; i++) {
      const scopeVal = scopeVals[i];
      $('aiLoadingText').textContent = `AI 正在润色中...（${i + 1}/${scopeVals.length}）`;

      let sectionText = '', displayScope = '', section = null;
      if (scopeVal.startsWith('sec:')) {
        section = scopeVal.slice(4);
        sectionText = (currentSections && currentSections[section]) || '';
        displayScope = section;
        if (!sectionText) {
          results.push({ section, displayScope, error: '缺少章节源文，请先生成一次报告' });
          continue;
        }
      } else {
        displayScope = scopeVal === 'full' ? '全文' : '结果分析';
        if (!fullText) {
          results.push({ section: null, displayScope, error: '无法读取报告内容' });
          continue;
        }
        sectionText = extractSection(fullText, scopeVal);
      }

      const messages = [
        {
          role: 'system',
          content: `你是一个大学物理实验报告润色助手。${getAiStylePrompt(style)}${skillBlock}请对用户提供的实验报告内容进行个性化改写，保持科学准确性和数据真实性，避免与原文措辞重复，使报告更具个人特色，降低重复检测风险。只输出改写后的内容，不要输出解释或说明。${formatBlock}${kbBlock}`,
        },
        {
          role: 'user',
          content: `请润色以下实验报告的「${displayScope}」部分：\n\n${sectionText.slice(0, 6000)}`,
        },
      ];

      try {
        const result = await window.labAPI.aiChat({
          provider: settings.provider || 'deepseek',
          apiKey: settings.apiKey,
          apiUrl: settings.apiUrl,
          model: settings.model,
          messages,
          temperature: 0.8,
        });
        if (result.ok) results.push({ section, displayScope, original: sectionText, polished: result.content || '' });
        else results.push({ section, displayScope, error: result.error || '润色失败' });
      } catch (err) {
        results.push({ section, displayScope, error: err.message });
      }
    }

    lastPolishResults = results;
    renderAiResults();
    const okCount = results.filter(r => r.polished).length;
    if (okCount) {
      showToast('success', '润色完成', `${okCount}/${results.length} 个对象完成，可导入章节支持一键重新生成`);
    } else {
      showToast('error', '润色失败', (results[0] && results[0].error) || '全部失败', 5000);
    }
  } catch (err) {
    showToast('error', '润色异常', err.message, 5000);
  } finally {
    $('aiLoadingCard').style.display = 'none';
    $('aiLoadingText').textContent = 'AI 正在润色中...';
    $('btnAiPolish').disabled = false;
  }
}

// 渲染多对象润色结果（每项：原文/润色后对比 + 复制 + 可导入章节的导入按钮）
function renderAiResults() {
  const wrap = $('aiResultsWrap');
  if (!wrap) return;
  wrap.innerHTML = '';
  let importable = 0;
  for (const r of lastPolishResults) {
    const block = document.createElement('div');
    block.className = 'ai-result-block';

    const head = document.createElement('div');
    head.className = 'ai-result-head';
    const title = document.createElement('span');
    title.className = 'ai-result-title';
    title.textContent = r.displayScope + (r.section ? '（可导入）' : '（仅复制）');
    head.appendChild(title);

    if (r.error) {
      const err = document.createElement('span');
      err.className = 'ai-result-error';
      err.textContent = '失败：' + r.error;
      head.appendChild(err);
      block.appendChild(head);
      wrap.appendChild(block);
      continue;
    }

    const copyBtn = document.createElement('button');
    copyBtn.type = 'button';
    copyBtn.className = 'btn btn-sm btn-outline';
    copyBtn.textContent = '复制结果';
    copyBtn.onclick = () => {
      navigator.clipboard.writeText(r.polished).then(() => {
        showToast('success', '已复制', r.displayScope + ' 润色结果已复制到剪贴板');
      }).catch(() => {
        showToast('error', '复制失败', '请手动选择复制');
      });
    };
    head.appendChild(copyBtn);

    if (r.section) {
      importable++;
      const impBtn = document.createElement('button');
      impBtn.type = 'button';
      impBtn.className = 'btn btn-sm btn-primary';
      impBtn.textContent = '导入此章节';
      impBtn.onclick = () => {
        if (!currentExp) return;
        setPolishOverride(currentExp.id, r.section, r.polished);
        updateOverrideBar();
        showToast('info', '已导入', `「${r.section}」将在下次生成报告时生效`);
      };
      head.appendChild(impBtn);
    }

    block.appendChild(head);
    const cmp = document.createElement('div');
    cmp.className = 'ai-compare';
    cmp.innerHTML = '<div class="ai-compare-col"><div class="ai-compare-label">原文</div><div class="ai-compare-text"></div></div>'
      + '<div class="ai-compare-col"><div class="ai-compare-label">润色后</div><div class="ai-compare-text ai-polished"></div></div>';
    const texts = cmp.querySelectorAll('.ai-compare-text');
    texts[0].textContent = (r.original || '').slice(0, 3000);
    texts[1].textContent = r.polished;
    block.appendChild(cmp);
    wrap.appendChild(block);
  }
  $('btnImportAi').style.display = importable ? '' : 'none';
  $('aiResultCard').style.display = 'block';
}

function updateAiStatus() {
  const settings = loadSettings();
  const hasKey = !!settings.apiKey;
  const hasReport = !!(currentExp && currentExp.reportFile);
  const model = settings.model || getDefaultModel(settings.provider);

  $('aiStatus').textContent = hasKey ? `已配置 · ${model}` : '未配置 API Key';
  $('aiStatus').style.color = hasKey ? 'var(--accent)' : 'var(--warning)';
  $('btnAiPolish').disabled = !hasKey || !hasReport;
}

function getDefaultModel(provider) {
  const defaults = {
    deepseek: 'deepseek-v4-pro',
    doubao: 'doubao-seed-2-1-pro-260628',
    qwen: 'qwen-plus',
    custom: 'gpt-4o',
  };
  return defaults[provider] || defaults.deepseek;
}

// 常用模型快速选择
const POPULAR_MODELS = {
  deepseek: [
    { name: 'deepseek-v4-pro', desc: '最新旗舰' },
    { name: 'deepseek-v4-flash', desc: '快速版' },
    { name: 'deepseek-chat', desc: '旧版兼容' },
  ],
  doubao: [
    { name: 'doubao-seed-2-1-pro-260628', desc: '最新旗舰' },
    { name: 'doubao-seed-2-1-turbo-260628', desc: '性价比' },
    { name: 'doubao-seed-2-0-pro-260215', desc: '2.0旗舰' },
  ],
  qwen: [
    { name: 'qwen-plus', desc: '均衡型' },
    { name: 'qwen-max', desc: '旗舰型' },
    { name: 'qwen3.8-max', desc: '最新旗舰' },
    { name: 'qwen-flash', desc: '快速版' },
  ],
  custom: [
    { name: 'gpt-4o', desc: 'GPT-4o' },
    { name: 'gpt-4o-mini', desc: '轻量版' },
    { name: 'claude-sonnet-4-20250514', desc: 'Claude' },
  ],
};

// 各平台默认 API URL
const DEFAULT_API_URLS = {
  deepseek: 'https://api.deepseek.com/v1',
  doubao: 'https://ark.cn-beijing.volces.com/api/v3',
  qwen: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
  custom: '',
};

// ── Tab 切换 ──

async function loadPreview() {
  if (!currentExp || !currentExp.reportFile) {
    $('previewWrap').innerHTML = `
      <div class="preview-empty">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
        <p>生成报告后可在此预览</p>
      </div>`;
    return;
  }
  $('previewWrap').innerHTML = '<div class="preview-empty"><p>加载中...</p></div>';
  try {
    const result = await window.labAPI.readDocxBuffer(currentExp.reportFile);
    if (!result.ok) {
      $('previewWrap').innerHTML = `<div class="preview-empty"><p>预览失败：${result.error}</p></div>`;
      showToast('error', '预览失败', result.error, 5000);
      return;
    }
    // base64 转 ArrayBuffer
    const binary = atob(result.buffer);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    // 清空容器并渲染
    $('previewWrap').innerHTML = '';
    if (window.docxPreview && window.docxPreview.renderAsync) {
      await window.docxPreview.renderAsync(bytes.buffer, $('previewWrap'), null, {
        inWrapper: true,
        ignoreWidth: true,
        breakPages: false,
        useBase64URL: true,
      });
    }
    // docx-preview 对 Word COM 生成的公式(OMML)支持有限；渲染结果为空则回退 mammoth 文本版
    if (!$('previewWrap').querySelector('section, p, table, img, canvas')) {
      await previewFallback('未渲染出内容');
    }
    previewLoaded = true;
  } catch (err) {
    await previewFallback(err.message);
  }
}

// docx-preview 失败/空白时的回退：用 mammoth 转 HTML（正文/表格/图可读，公式可能不显示）
async function previewFallback(reason) {
  try {
    const h = await window.labAPI.docxToHtml(currentExp.reportFile);
    if (h.ok && h.html) {
      $('previewWrap').innerHTML =
        `<div class="docx-html-preview">${h.html}</div>`
        + `<p class="preview-note">公式等复杂内容预览受限，已切换为文本预览模式。</p>`;
      return;
    }
  } catch (e) { /* 回退失败则走下方错误提示 */ }
  $('previewWrap').innerHTML = `<div class="preview-empty"><p>预览失败：${escapeHtml(reason || '')}</p></div>`;
}

// ── Tab 切换 ──
function switchTab(tabId) {
  document.querySelectorAll('.tab-item').forEach(t => {
    t.classList.toggle('active', t.dataset.tab === tabId);
  });
  document.querySelectorAll('.tab-pane').forEach(p => {
    p.classList.toggle('active', p.id === 'tab-' + tabId);
  });
  if (tabId === 'preview' && !previewLoaded) {
    loadPreview();
  }
}

// ── 空状态统计 ──
function updateEmptyStats() {
  $('statTotal').textContent = experiments.length;
  $('statDone').textContent = experiments.filter(e => e.hasReport).length;
}

// ── 学生信息显示 ──
function updateStudentDisplay() {
  const info = loadStudentInfo();
  $('stuName').textContent = info.name || '未设置';
  $('stuId').textContent = info.id || '未设置';
  $('stuClass').textContent = info.class || '未设置';
  $('stuDate').textContent = info.date || new Date().toLocaleDateString('zh-CN');
}

// ── 事件绑定 ──
function bindEvents() {
  // 主进程请求"保存后退出"：保存当前数据，成功则确认关闭
  if (window.labAPI && window.labAPI.onSaveAndClose) {
    window.labAPI.onSaveAndClose(async () => {
      const saved = await saveExcelData();
      if (saved) {
        if (window.labAPI.confirmClose) window.labAPI.confirmClose();
      } else {
        showToast('error', '保存失败', '未能保存数据，已取消关闭', 5000);
      }
    });
  }

  // 分类导航
  document.querySelectorAll('.cat-item').forEach(btn => {
    btn.onclick = () => {
      document.querySelectorAll('.cat-item').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentCategory = btn.dataset.cat;
      renderList($('searchInput').value);
    };
  });

  // 搜索
  $('searchInput').addEventListener('input', (e) => {
    renderList(e.target.value);
  });

  // Tab
  document.querySelectorAll('.tab-item').forEach(t => {
    t.onclick = () => switchTab(t.dataset.tab);
  });

  // 打开数据模板
  $('btnOpenData').onclick = openDataFile;
  $('btnOpenData2').onclick = openDataFile;

  // 打开报告
  $('btnOpenReport').onclick = openReportFile;
  $('btnOpenReport2').onclick = openReportFile;

  // 生成报告
  $('btnGenerate').onclick = runGenerate;
  $('btnCancelGenerate').onclick = cancelGenerate;

  // 清空日志
  $('btnClearLog').onclick = () => { $('logContent').textContent = ''; };

  // 学生信息
  $('btnStudentInfo').onclick = () => openModal('studentModal');
  $('btnEditStudent').onclick = () => openModal('studentModal');
  $('btnCloseStudent').onclick = () => closeModal('studentModal');
  $('btnCancelStudent').onclick = () => closeModal('studentModal');
  $('btnSaveStudent').onclick = saveStudent;

  // 设置
  $('btnSettings').onclick = () => { openModal('settingsModal'); loadSettingsForm(); switchSettingsPane('ai'); };
  $('btnNavAi').onclick = () => switchSettingsPane('ai');
  $('btnNavReports').onclick = () => { switchSettingsPane('reports'); loadReportsList(); };
  $('btnRefreshReports').onclick = loadReportsList;
  $('btnNavHelp').onclick = () => switchSettingsPane('help');
  $('btnNavDanger').onclick = () => switchSettingsPane('danger');
  $('btnNavUpdate').onclick = () => { switchSettingsPane('update'); loadUpdatePane(); };
  $('btnCheckUpdate').onclick = checkForUpdate;
  $('btnUpdateDownload').onclick = downloadUpdate;
  $('btnUpdateLater').onclick = () => {
    if (updateDownloading) window.labAPI.cancelUpdateDownload();
    closeModal('updateModal');
  };
  $('btnCloseUpdateModal').onclick = () => {
    if (updateDownloading) window.labAPI.cancelUpdateDownload();
    closeModal('updateModal');
  };
  $('btnDangerGo').onclick = startDangerFlow;
  $('btnDangerExit').onclick = exitDangerFlow;
  $('btnDangerProceed').onclick = proceedDangerFlow;
  $('btnDeleteAllReports').onclick = deleteAllReports;
  $('btnCloseSettings').onclick = () => closeModal('settingsModal');
  $('btnCancelSettings').onclick = () => closeModal('settingsModal');
  $('btnSaveSettings').onclick = saveAppSettings;
  $('btnAiConfig').onclick = () => { closeModal('studentModal'); openModal('settingsModal'); loadSettingsForm(); };
  $('selectProvider').onchange = () => {
    renderModelChips();
    autoFillApiUrl();
  };

  // 批量生成（预留）
  $('btnBatch').onclick = runBatchGenerate;
  $('btnQueuePanel').onclick = openQueuePanel;
  $('btnSelectAll').onclick = toggleSelectAll;
  $('btnBatchClose').onclick = () => {
    $('batchPanel').style.display = 'none';
    if (currentExp) $('detailPanel').style.display = 'block';
    else $('emptyState').style.display = 'flex';
  };
  // 生成队列控制
  if ($('btnQueuePause')) $('btnQueuePause').onclick = pauseQueue;
  if ($('btnQueueResume')) $('btnQueueResume').onclick = resumeQueue;
  if ($('btnQueueCancelAll')) $('btnQueueCancelAll').onclick = cancelAllQueue;
  if ($('btnQueueClear')) $('btnQueueClear').onclick = clearFinishedQueue;
  const _ql = $('queueList');
  if (_ql) _ql.addEventListener('click', (e) => {
    const b = e.target.closest('button[data-act]'); if (!b) return;
    const id = b.dataset.id, act = b.dataset.act;
    if (act === 'up') moveQueueItem(id, -1);
    else if (act === 'down') moveQueueItem(id, 1);
    else if (act === 'cancel') cancelQueueItem(id);
    else if (act === 'remove') removeQueueItem(id);
  });

  // 监听运行日志
  window.labAPI.onGenerateLog((data) => {
    if ($('logContent').textContent === '等待生成...') {
      $('logContent').textContent = '';
    }
    $('logContent').textContent += data;
    $('logContent').scrollTop = $('logContent').scrollHeight;
  });

  // 点击遮罩关闭弹窗
  document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.onclick = (e) => {
      if (e.target === overlay) overlay.classList.remove('show');
    };
  });

  // 窗口控制
  $('btnMinimize').onclick = () => window.labAPI.minimize();
  $('btnMaximize').onclick = () => window.labAPI.toggleMaximize();
  $('btnClose').onclick = () => window.labAPI.close();

  // 数据录入
  $('btnSaveData').onclick = saveExcelData;
  $('btnReloadData').onclick = reloadExcelData;
  $('btnClearFormData').onclick = clearFormData;

  // 报告预览
  $('btnRefreshPreview').onclick = () => { previewLoaded = false; loadPreview(); };
  $('btnOpenReportPreview').onclick = openReportFile;

  // AI 润色
  $('btnAiPolish').onclick = runAiPolish;
  $('btnAiConfig').onclick = () => openModal('settingsModal');
  $('btnImportAi').onclick = importPolishAndRegenerate;
  $('btnClearOverrides').onclick = () => {
    if (!currentExp) return;
    clearPolishOverrides(currentExp.id);
    updateOverrideBar();
    showToast('info', '已清除', '导入的润色文本已移除，下次生成恢复变体库文本');
  };
  $('chkKbOnly').onchange = () => {
    const s = loadSettings();
    s.kbOnly = $('chkKbOnly').checked;
    saveSettings(s);
  };
  $('btnImportSkill').onclick = importSkillFiles;
  $('btnOpenSkillsFolder').onclick = () => window.labAPI.openSkillsFolder();
  // 润色面板初始状态（实验相关部分由 selectExperiment 刷新）
  $('chkKbOnly').checked = loadSettings().kbOnly !== false;
  loadSkillList();
  refreshAiScopeOptions(false);
}

function openModal(id) { $(id).classList.add('show'); }
function closeModal(id) { $(id).classList.remove('show'); }

async function openDataFile() {
  if (currentExp && currentExp.dataFile) {
    const r = await window.labAPI.openFile(currentExp.dataFile);
    if (!r.ok) showToast('error', '无法打开文件', '数据文件不存在或已被移动', 5000);
  }
}

async function openReportFile() {
  if (currentExp && currentExp.reportFile) {
    const r = await window.labAPI.openFile(currentExp.reportFile);
    if (!r.ok) showToast('error', '无法打开文件', '报告文件不存在或已被移动', 5000);
  }
}

// ── 保存学生信息 ──
function saveStudent() {
  const info = {
    name: $('inputName').value.trim(),
    id: $('inputId').value.trim(),
    class: $('inputClass').value.trim(),
    date: new Date().toLocaleDateString('zh-CN'),
  };
  saveStudentInfo(info);
  updateStudentDisplay();
  closeModal('studentModal');
  showToast('success', '已保存', '学生信息已更新');
}

// ── 加载设置表单 ──
// 设置模块导航切换
function switchSettingsPane(name) {
  $('btnNavAi').classList.toggle('active', name === 'ai');
  $('paneAi').classList.toggle('active', name === 'ai');
  $('btnNavReports').classList.toggle('active', name === 'reports');
  $('paneReports').classList.toggle('active', name === 'reports');
  $('btnNavHelp').classList.toggle('active', name === 'help');
  $('paneHelp').classList.toggle('active', name === 'help');
  $('btnNavDanger').classList.toggle('active', name === 'danger');
  $('paneDanger').classList.toggle('active', name === 'danger');
  $('btnNavUpdate').classList.toggle('active', name === 'update');
  $('paneUpdate').classList.toggle('active', name === 'update');
}

// ── 检查更新（Gitee Release，国内高速）──
let updateInfo = null;   // 最近一次检查结果（含 assets）
let updateDownloading = false;

function loadUpdatePane() {
  const st = loadSettings();
  // 内置默认更新清单地址（腾讯云 COS 默认域名，永久有效；换桶时可在下方修改）
  $('inputManifestUrl').value = st.manifestUrl
    || 'https://labreport-1485394950.cos.ap-guangzhou.myqcloud.com/latest.json';
  window.labAPI.getAppVersion().then(v => {
    $('inputCurrentVersion').value = 'v' + v;
  }).catch(() => { $('inputCurrentVersion').value = '未知'; });
}

function saveUpdateSource() {
  const st = loadSettings();
  st.manifestUrl = $('inputManifestUrl').value.trim();
  saveSettings(st);
}

async function checkForUpdate() {
  saveUpdateSource();
  const btn = $('btnCheckUpdate');
  btn.disabled = true;
  btn.textContent = '检查中…';
  $('updateResult').textContent = '正在连接更新服务器…';
  try {
    const r = await window.labAPI.checkForUpdate({
      manifestUrl: $('inputManifestUrl').value.trim(),
    });
    if (!r.ok) {
      $('updateResult').textContent = '检查失败：' + r.error;
      return;
    }
    updateInfo = r;
    if (r.hasUpdate) {
      $('updateResult').textContent = `发现新版本 v${r.latest}，正在自动下载…`;
      openUpdateModal(r);
      // 发现新版本后自动开始下载
      setTimeout(() => downloadUpdate(), 400);
    } else {
      $('updateResult').textContent = `已是最新版本 v${r.current}`;
    }
  } catch (err) {
    $('updateResult').textContent = '检查失败：' + err.message;
  } finally {
    btn.disabled = false;
    btn.textContent = '检查更新';
  }
}

function openUpdateModal(r) {
  $('updateModalTitle').textContent = `发现新版本 v${r.latest}`;
  $('updateMeta').textContent = `当前版本 v${r.current} → 最新版本 v${r.latest}`;
  const notesEl = $('updateNotes');
  notesEl.textContent = r.notes || '（本次更新未填写说明）';
  // 优先 exe 安装包，其次 zip
  const exe = r.assets.find(a => /\.exe$/i.test(a.name));
  const asset = exe || r.assets[0] || null;
  $('btnUpdateDownload').disabled = !asset;
  if (!asset) {
    $('btnUpdateDownload').textContent = '暂无安装包';
  } else {
    $('btnUpdateDownload').textContent = '立即下载' + (exe ? '' : '（压缩包）');
  }
  $('updateProgressWrap').style.display = 'none';
  openModal('updateModal');
}

async function downloadUpdate() {
  if (!updateInfo || !updateInfo.assets.length || updateDownloading) return;
  const asset = updateInfo.assets.find(a => /\.exe$/i.test(a.name)) || updateInfo.assets[0];
  updateDownloading = true;
  $('btnUpdateDownload').disabled = true;
  $('btnUpdateLater').disabled = true;
  $('updateProgressWrap').style.display = 'block';
  $('updateProgressFill').style.width = '0%';
  $('updateProgressText').textContent = '正在连接下载服务器…';
  window.labAPI.onUpdateProgress(({ percent }) => {
    $('updateProgressFill').style.width = percent + '%';
    $('updateProgressText').textContent = `下载中 ${percent}%`;
  });
  try {
    const r = await window.labAPI.downloadUpdate({ url: asset.url, name: asset.name });
    if (r.ok) {
      $('updateProgressText').textContent = '下载完成';
      showToast('success', '更新下载完成', '即将打开安装程序', 4000);
      window.labAPI.openFile(r.filePath);
      closeModal('updateModal');
    } else {
      $('updateProgressText').textContent = '下载失败：' + r.error;
      showToast('error', '下载失败', r.error, 5000);
    }
  } catch (err) {
    $('updateProgressText').textContent = '下载异常：' + err.message;
  } finally {
    updateDownloading = false;
    $('btnUpdateDownload').disabled = false;
    $('btnUpdateLater').disabled = false;
  }
}

// ── 请勿点击：高危警告多级确认 + 彩蛋音频 ──
let dangerStep = 0;          // 0 一级 / 1 二级 / 2 三级
let dangerAudio = null;      // 当前 Audio 对象（防止 GC 中断播放）

const DANGER_STEPS = [
  {
    msg: '高危警告！！！请勿点击，点击后若出现任何情况，开发者概不负责！！！',
    proceed: '我不听！',
  },
  {
    msg: '开发者已经做出明确警告与责任声明，你是否继续？',
    proceed: '继续',
  },
  {
    msg: '最后一次确认，你真的要继续吗？',
    proceed: '继续',
  },
];

function startDangerFlow() {
  dangerStep = 0;
  showDangerStep(0);
  openModal('dangerModal');
}

function showDangerStep(step) {
  const cfg = DANGER_STEPS[step];
  $('dangerMsg').textContent = cfg.msg;
  $('btnDangerProceed').textContent = cfg.proceed;
  // 一级“我不听！”用描边样式，二三级“继续”用红色危险样式
  const red = step > 0;
  $('btnDangerProceed').classList.toggle('btn-danger', red);
  $('btnDangerProceed').classList.toggle('btn-outline', !red);
}

function proceedDangerFlow() {
  if (dangerStep < 2) {
    dangerStep += 1;
    showDangerStep(dangerStep);
    return;
  }
  // 三级确认通过：关闭弹窗，播放内置音频
  closeModal('dangerModal');
  playDangerAudio();
}

function exitDangerFlow() {
  if (dangerAudio) { dangerAudio.pause(); dangerAudio = null; }
  closeModal('dangerModal');
  showToast('info', '已退出', '还好你及时收手了', 2500);
}

async function playDangerAudio() {
  try {
    const r = await window.labAPI.readAudioFile();
    if (!r.ok) throw new Error(r.error);
    const url = `data:${r.mime};base64,${r.data}`;
    const audio = new Audio(url);
    dangerAudio = audio;
    await audio.play();
    audio.onended = () => { dangerAudio = null; backToMain(); };
    audio.onerror = () => { dangerAudio = null; backToMain(); };
  } catch (err) {
    dangerAudio = null;
    showToast('error', '播放失败', err.message, 4000);
    backToMain();
  }
}

function backToMain() {
  // 关闭所有弹窗，回到主界面（生成页）
  closeModal('settingsModal');
  closeModal('dangerModal');
  switchTab('generate');
}

// ── 报告管理（设置页）──
let lastReportsList = [];   // 最近一次列表结果（供"删除全部"使用）

function fmtSize(bytes) {
  if (bytes >= 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + ' MB';
  if (bytes >= 1024) return Math.round(bytes / 1024) + ' KB';
  return bytes + ' B';
}

async function loadReportsList() {
  const list = $('reportsList');
  const summary = $('reportsSummary');
  if (!list || !summary) return;
  summary.textContent = '加载中…';
  list.innerHTML = '';
  let reports = [];
  try {
    const r = await window.labAPI.listReports();
    reports = (r && r.ok && Array.isArray(r.reports)) ? r.reports : [];
  } catch (e) { reports = []; }
  lastReportsList = reports;
  const delAllBtn = $('btnDeleteAllReports');
  if (delAllBtn) delAllBtn.disabled = !reports.length;
  if (!reports.length) {
    summary.textContent = '暂无已生成的报告。先选择实验并点击「生成报告」。';
    return;
  }
  summary.textContent = `共 ${reports.length} 份报告 · 按生成时间倒序 · 「删除」仅移除报告文件，不影响测量数据与变体`;
  for (const rep of reports) {
    const row = document.createElement('div');
    row.className = 'report-row';

    const info = document.createElement('div');
    info.className = 'report-info';
    const nameEl = document.createElement('div');
    nameEl.className = 'report-name';
    nameEl.textContent = rep.exp;
    const metaEl = document.createElement('div');
    metaEl.className = 'report-meta';
    metaEl.textContent = `${new Date(rep.mtime).toLocaleString('zh-CN', { hour12: false })} · ${fmtSize(rep.size)} · ${rep.file}`;
    metaEl.title = rep.path;
    info.appendChild(nameEl);
    info.appendChild(metaEl);

    const actions = document.createElement('div');
    actions.className = 'report-actions';
    const mkBtn = (label, cls, fn) => {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'btn btn-sm ' + cls; b.textContent = label; b.onclick = fn;
      return b;
    };
    actions.appendChild(mkBtn('打开', 'btn-outline', () => window.labAPI.openFile(rep.path)));
    actions.appendChild(mkBtn('文件夹', 'btn-outline', () => window.labAPI.showInFolder(rep.path)));
    actions.appendChild(mkBtn('删除', 'btn-ghost report-del', async () => {
      if (!confirm(`删除「${rep.exp}」的报告 ${rep.file}？\n（测量数据与变体不受影响）`)) return;
      const rr = await window.labAPI.deleteReport(rep.path);
      if (rr && rr.ok) {
        showToast('success', '已删除', rep.file);
        await refreshAfterReportChange();
      } else {
        showToast('error', '删除失败', (rr && rr.error) || '未知错误', 5000);
      }
    }));

    row.appendChild(info);
    row.appendChild(actions);
    list.appendChild(row);
  }
}

// 报告增删后同步：刷新管理列表 + 实验列表状态（角标/报告文件/预览可用性）
async function refreshAfterReportChange() {
  await loadReportsList();
  experiments = await window.labAPI.scanExperiments();
  experiments.forEach(e => { e.category = getCategory(e.name); });
  updateCategoryCounts();
  updateEmptyStats();
  renderList($('searchInput').value);
  if (currentExp) {
    const updated = experiments.find(e => e.id === currentExp.id);
    if (updated) selectExperiment(updated);
  }
}

async function deleteAllReports() {
  const reports = lastReportsList || [];
  if (!reports.length) return;
  if (!confirm(`删除全部 ${reports.length} 份已生成报告？\n（仅移除报告文件，测量数据、变体与已导入润色不受影响）`)) return;
  let ok = 0, fail = 0;
  for (const rep of reports) {
    try {
      const rr = await window.labAPI.deleteReport(rep.path);
      if (rr && rr.ok) ok++; else fail++;
    } catch (e) { fail++; }
  }
  if (fail) showToast('warning', `已删除 ${ok} 份`, `${fail} 份删除失败（可能被 Word 占用，关闭后重试）`, 6000);
  else showToast('success', '已删除全部报告', `共 ${ok} 份`);
  await refreshAfterReportChange();
}

// ── 导入润色结果并重新生成报告（导入本轮全部可导入章节）──
async function importPolishAndRegenerate() {
  if (!currentExp) return;
  const ok = (lastPolishResults || []).filter(r => r.section && r.polished && r.polished.trim());
  if (!ok.length) {
    showToast('warning', '无法导入', '本次结果中没有可导入的章节（仅"可导入"章节支持注入重生成）');
    return;
  }
  for (const r of ok) setPolishOverride(currentExp.id, r.section, r.polished);
  updateOverrideBar();
  showToast('info', '已导入 ' + ok.length + ' 个章节', ok.map(r => r.section).join('、') + ' —— 正在重新生成报告…');
  await runGenerate();
}

function loadSettingsForm() {
  const s = loadSettings();
  $('selectProvider').value = s.provider || 'deepseek';
  $('inputApiKey').value = s.apiKey || '';
  $('inputModel').value = s.model || '';
  $('inputApiUrl').value = s.apiUrl || '';
  $('chkAiPolish').checked = !!s.aiPolish;
  $('chkKbOnly').checked = s.kbOnly !== false;
  loadSkillList();
  renderModelChips();
}

// 渲染常用模型快速选择按钮
function renderModelChips() {
  const provider = $('selectProvider').value;
  const models = POPULAR_MODELS[provider] || [];
  const container = $('modelQuickSelect');
  if (!container) return;
  container.innerHTML = models.map(m =>
    `<button type="button" class="model-chip" data-model="${m.name}">
      <span>${m.name}</span>
      <span class="chip-desc">${m.desc}</span>
    </button>`
  ).join('');
  container.querySelectorAll('.model-chip').forEach(btn => {
    btn.onclick = () => {
      $('inputModel').value = btn.dataset.model;
    };
  });
}

// 切换提供商时自动填充默认 API URL（仅当当前为空或是上一个默认值时）
function autoFillApiUrl() {
  const provider = $('selectProvider').value;
  const currentUrl = $('inputApiUrl').value.trim();
  const defaultUrl = DEFAULT_API_URLS[provider] || '';
  const isDefault = Object.values(DEFAULT_API_URLS).includes(currentUrl);
  if (!currentUrl || isDefault) {
    $('inputApiUrl').value = defaultUrl;
  }
}

// ── 保存设置 ──
function saveAppSettings() {
  const settings = {
    provider: $('selectProvider').value,
    apiKey: $('inputApiKey').value.trim(),
    model: $('inputModel').value.trim(),
    apiUrl: $('inputApiUrl').value.trim(),
    aiPolish: $('chkAiPolish').checked,
    kbOnly: $('chkKbOnly').checked,
    skillStates: getSkillStates(),
  };
  saveSettings(settings);
  closeModal('settingsModal');
  showToast('success', '已保存', '设置已更新');
  updateAiStatus();
  renderSkillOptions(false);
}

// ── 运行生成报告 ──
async function runGenerate() {
  if (!currentExp || isGenerating) return;
  isGenerating = true;
  let genOk = false;

  const btn = $('btnGenerate');
  btn.disabled = true;
  btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10" stroke-dasharray="40 20" stroke-linecap="round"><animateTransform attributeName="transform" type="rotate" from="0 12 12" to="360 12 12" dur="1s" repeatCount="indefinite"/></circle></svg> 生成中...';
  // 生成期间：结果区显示"报告生成中"，禁用"打开报告"，显示"取消生成"按钮
  setResultState('generating');
  $('btnOpenReport').disabled = true;
  $('btnOpenReport2').disabled = true;
  $('btnCancelGenerate').style.display = 'inline-flex';
  $('logContent').textContent = '开始生成报告...\n';
  switchTab('generate');

  try {
    genOk = await runGenerateReport(btn, currentExp.id);
  } catch (err) {
    $('logContent').textContent += `\n❌ 异常: ${err.message}\n`;
    showToast('error', '运行异常', err.message, 5000);
  } finally {
    isGenerating = false;
    btn.disabled = false;
    btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg> 生成报告';
    $('btnCancelGenerate').style.display = 'none';
    // 生成结束：成功时结果区已由 refreshExperimentAfterGenerate 置为"报告生成成功"；
    // 失败/取消则按当前实验已有报告状态恢复（有旧报告 → 可继续打开旧报告；无 → 显示尚未生成）
    if (!genOk && currentExp) {
      $('btnOpenReport').disabled = !currentExp.hasReport;
      $('btnOpenReport2').disabled = !currentExp.hasReport;
      setResultState(currentExp.hasReport && currentExp.reportFile ? 'success' : 'empty', currentExp.reportFile);
    }
  }
}

// 取消生成
async function cancelGenerate() {
  if (!isGenerating) return;
  $('btnCancelGenerate').disabled = true;
  $('btnCancelGenerate').textContent = '正在取消...';
  $('logContent').textContent += '\n⏹ 正在取消生成...\n';
  try {
    await window.labAPI.cancelGenerate();
  } catch (err) {
    $('logContent').textContent += `\n⚠️ 取消失败: ${err.message}\n`;
  } finally {
    // 恢复按钮（runGenerate 的 finally 会完成后续状态恢复）
    $('btnCancelGenerate').disabled = false;
    $('btnCancelGenerate').innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/></svg> 取消生成';
  }
}

// 生成结果区统一状态：empty=尚未生成 / generating=报告生成中 / success=报告生成成功
function setResultState(state, path) {
  $('resultEmpty').style.display = state === 'empty' ? 'block' : 'none';
  $('resultGenerating').style.display = state === 'generating' ? 'block' : 'none';
  $('resultSuccess').style.display = state === 'success' ? 'flex' : 'none';
  if (path) $('resultPath').textContent = path;
}

// 生成后只刷新结果区/按钮状态，不重置日志、不切换 tab、不重载数据
function refreshExperimentAfterGenerate(updated) {
  if (!updated) return;
  currentExp = updated;
  $('metaReport').textContent = '报告已生成';
  $('metaReport').className = 'meta-dot ok';
  $('btnOpenReport').disabled = false;
  $('btnOpenReport2').disabled = false;
  setResultState('success', updated.reportFile);
}

// 实验报告：Python generate.py 生成 Word
async function runGenerateReport(btn, genExpId) {
  const genExp = experiments.find(e => e.id === genExpId) || currentExp;
  const studentInfo = loadStudentInfo();
  // 学生信息未填写时提醒（报告头部将显示"（未填写）"）
  if (!studentInfo.name || !studentInfo.id || !studentInfo.class) {
    showToast('warning', '学生信息未填写', '报告头部将显示（未填写），可在右上角「学生信息」中填写', 5000);
  }
  // 收集变体组合选择（值为 -1 的"随机"在此真正随机）
  const variantChoices = {};
  document.querySelectorAll('.variant-select').forEach(sel => {
    const idx = parseInt(sel.value, 10);
    const sec = sel.dataset.section;
    if (idx === -1 && currentVariants && currentVariants[sec]) {
      variantChoices[sec] = Math.floor(Math.random() * currentVariants[sec].length);
    } else {
      variantChoices[sec] = idx;
    }
  });
  const result = await window.labAPI.runGenerate(genExp.path, studentInfo, variantChoices, expOverrides(genExp.id));
  if (result.cancelled) {
    $('logContent').textContent += '\n⏹ 生成已取消\n';
    showToast('info', '生成已取消', getDisplayName(genExp));
    return false;
  }
  if (result.ok) {
    $('logContent').textContent += '\n✅ 报告生成成功！\n';
    if (result.reportFile) $('logContent').textContent += `📄 ${result.reportFile}\n`;
    showToast('success', '报告生成成功', getDisplayName(genExp));
    // 刷新实验列表
    experiments = await window.labAPI.scanExperiments();
    experiments.forEach(e => { e.category = getCategory(e.name); });
    updateCategoryCounts();
    updateEmptyStats();
    const updated = experiments.find(e => e.id === genExpId);
    // 若用户仍停留在发起生成的实验，则刷新其结果区；中途切换则不影响当前页面
    if (updated && currentExp && currentExp.id === genExpId) {
      refreshExperimentAfterGenerate(updated);
    }
    // 刷新预览
    previewLoaded = false;
    if (document.querySelector('.tab-item.active')?.dataset.tab === 'preview') {
      loadPreview();
    }
    // 更新 AI 状态；章节源文缓存刚随本次生成落盘，同步润色对象选项
    updateAiStatus();
    await refreshAiScopeOptions(true);
    updateOverrideBar();
    return true;
  } else {
    $('logContent').textContent += `\n❌ 生成失败（退出码 ${result.exitCode}）\n`;
    if (result.error) $('logContent').textContent += `错误: ${result.error}\n`;
    const reason = result.error || `退出码 ${result.exitCode}`;
    showToast('error', '生成失败', reason, 6000);
    return false;
  }
}

// ── 变体组合 ──
let currentVariants = null;   // {章节: [变体文本...]}
let aiVariantSection = '';    // 当前 AI 调整的章节

function getSavedVariantChoices() {
  try { return JSON.parse(localStorage.getItem('variantChoices') || '{}'); } catch { return {}; }
}
function saveVariantChoices(choices) {
  localStorage.setItem('variantChoices', JSON.stringify(choices));
}

async function loadVariantsUI(exp) {
  const card = $('variantsCard');
  const list = $('variantsList');
  list.innerHTML = '';
  card.style.display = 'none';
  currentVariants = null;
  try {
    const res = await window.labAPI.loadVariants(exp.path);
    if (!res.ok || !res.variants || Object.keys(res.variants).length === 0) return;
    currentVariants = res.variants;
    renderVariantsPanel();
    card.style.display = '';
  } catch (e) { /* 静默：无变体库时不显示面板 */ }
}

function renderVariantsPanel() {
  const list = $('variantsList');
  list.innerHTML = '';
  const saved = getSavedVariantChoices();
  const expKey = currentExp ? currentExp.id : '';
  const savedForExp = saved[expKey] || {};
  for (const [section, texts] of Object.entries(currentVariants)) {
    const row = document.createElement('div');
    row.className = 'variant-row';

    const label = document.createElement('span');
    label.className = 'variant-label';
    label.textContent = section;

    const select = document.createElement('select');
    select.className = 'variant-select';
    select.dataset.section = section;
    const opts = [['-1', '随机']].concat(texts.map((_, i) => [String(i), `变体 ${i + 1}`]));
    for (const [val, txt] of opts) {
      const o = document.createElement('option');
      o.value = val; o.textContent = txt;
      select.appendChild(o);
    }
    if (savedForExp[section] !== undefined && savedForExp[section] >= -1 && savedForExp[section] < texts.length) {
      select.value = String(savedForExp[section]);
    }
    select.onchange = () => {
      const choices = collectVariantChoices();
      const all = getSavedVariantChoices();
      all[expKey] = choices;
      saveVariantChoices(all);
    };

    const pvBtn = document.createElement('button');
    pvBtn.className = 'btn btn-sm btn-outline variant-preview-btn';
    pvBtn.textContent = '预览';
    pvBtn.onclick = () => previewVariant(section, texts);

    const aiBtn = document.createElement('button');
    aiBtn.className = 'btn btn-sm btn-outline variant-ai-btn';
    aiBtn.textContent = 'AI 调整';
    aiBtn.onclick = () => openVariantAI(section);

    row.append(label, select, pvBtn, aiBtn);
    list.appendChild(row);
  }
}

function collectVariantChoices() {
  const choices = {};
  document.querySelectorAll('.variant-select').forEach(sel => {
    choices[sel.dataset.section] = parseInt(sel.value, 10);
  });
  return choices;
}

function randomizeVariants() {
  const expKey = currentExp ? currentExp.id : '';
  const choices = {};
  document.querySelectorAll('.variant-select').forEach(sel => {
    const count = (currentVariants[sel.dataset.section] || []).length;
    choices[sel.dataset.section] = count > 0 ? Math.floor(Math.random() * count) : -1;
    sel.value = String(choices[sel.dataset.section]);
  });
  const all = getSavedVariantChoices();
  all[expKey] = choices;
  saveVariantChoices(all);
  showToast('info', '已随机组合', '已为各章节随机选择变体');
}

function previewVariant(section, texts) {
  const sel = document.querySelector(`.variant-select[data-section="${CSS.escape(section)}"]`);
  let idx = sel ? parseInt(sel.value, 10) : 0;
  if (idx < 0 || idx >= texts.length) idx = 0;
  $('variantPreviewTitle').textContent = `${section} — 变体 ${idx + 1}`;
  $('variantPreviewText').textContent = texts[idx];
  openModal('variantPreviewModal');
}

function openVariantAI(section) {
  const texts = currentVariants[section] || [];
  if (texts.length === 0) return;
  const sel = document.querySelector(`.variant-select[data-section="${CSS.escape(section)}"]`);
  let idx = sel ? parseInt(sel.value, 10) : 0;
  if (idx < 0 || idx >= texts.length) idx = 0;
  aiVariantSection = section;
  $('variantAITitle').textContent = `AI 调整变体 — ${section}（变体 ${idx + 1}）`;
  $('variantAIInstruction').value = '';
  $('variantAIOriginal').value = texts[idx];
  $('variantAIResult').value = '';
  openModal('variantAIModal');
}

async function runVariantAI() {
  const instruction = $('variantAIInstruction').value.trim();
  const original = $('variantAIOriginal').value;
  if (!original) { showToast('error', '内容为空', '没有可调整的原文本'); return; }
  const settings = loadSettings();
  if (!settings.apiKey) {
    showToast('error', '未配置 API Key', '请先在设置中填写 API Key');
    return;
  }
  $('btnVariantAIRetry').disabled = true;
  $('btnVariantAIRetry').textContent = '生成中...';
  try {
    const messages = [
      {
        role: 'system',
        content: '你是大学物理实验报告写作助手。根据用户的调整指令，对给定的实验章节文本进行改写：保持物理原理与实验事实正确；必须原样保留 $...$ 公式和 %%DATA:xxx%% 数据占位符；使表达更具个人特色、避免与原文措辞重复。只输出改写后的完整文本，不要输出任何解释或前后缀说明。',
      },
      {
        role: 'user',
        content: `调整指令：${instruction || '换一种措辞风格，使表达更有个人特色，避免与原文重复'}\n\n章节文本：\n${original}`,
      },
    ];
    const result = await window.labAPI.aiChat({
      provider: settings.provider || 'deepseek',
      apiKey: settings.apiKey,
      apiUrl: settings.apiUrl,
      model: settings.model,
      messages,
      temperature: 0.8,
    });
    if (result.ok) {
      $('variantAIResult').value = result.content.trim();
      showToast('success', '生成完成', 'AI 已生成新变体，可编辑后保存');
    } else {
      showToast('error', '生成失败', result.error, 5000);
    }
  } catch (err) {
    showToast('error', '生成异常', err.message, 5000);
  } finally {
    $('btnVariantAIRetry').disabled = false;
    $('btnVariantAIRetry').textContent = '生成/重试';
  }
}

async function saveVariantAI() {
  const newText = $('variantAIResult').value.trim();
  if (!newText) { showToast('error', '内容为空', '请先生成或填写变体文本'); return; }
  if (!currentVariants[aiVariantSection]) currentVariants[aiVariantSection] = [];
  currentVariants[aiVariantSection].push(newText);
  const res = await window.labAPI.saveVariants(currentExp.path, currentVariants);
  if (res.ok) {
    renderVariantsPanel();
    closeModal('variantAIModal');
    const n = currentVariants[aiVariantSection].length;
    showToast('success', '已保存', `已为"${aiVariantSection}"新增变体 ${n}`);
  } else {
    showToast('error', '保存失败', res.error, 5000);
  }
}

function bindVariantsEvents() {
  $('btnRandomVariants').onclick = randomizeVariants;
  $('btnRefreshVariants').onclick = () => { if (currentExp) loadVariantsUI(currentExp); };
  $('btnCloseVariantAI').onclick = () => closeModal('variantAIModal');
  $('btnCancelVariantAI').onclick = () => closeModal('variantAIModal');
  $('btnVariantAIRetry').onclick = runVariantAI;
  $('btnSaveVariantAI').onclick = saveVariantAI;
  $('btnCloseVariantPreview').onclick = () => closeModal('variantPreviewModal');
}

init();
bindVariantsEvents();
