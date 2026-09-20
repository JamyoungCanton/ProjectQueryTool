const form = document.querySelector('#queryForm');
const searchButton = document.querySelector('#searchButton');
const startButton = document.querySelector('#startButton');
const stopButton = document.querySelector('#stopButton');
const exportButton = document.querySelector('#exportButton');
const stageText = document.querySelector('#stageText');
const progressText = document.querySelector('#progressText');
const progressBar = document.querySelector('#progressBar');
const formError = document.querySelector('#formError');
const modal = document.querySelector('#modal');
const previousPageButton = document.querySelector('#previousPageButton');
const nextPageButton = document.querySelector('#nextPageButton');
const pageNumberInput = document.querySelector('#pageNumberInput');
const goToPageButton = document.querySelector('#goToPageButton');
let currentQueryId = null;
let pollTimer = null;
let candidates = [];
let selectedProjects = new Map();
let catalogSearch = null;
let currentPage = 1;
let totalPages = 0;
let nextCatalogPage = 2;
let hasMoreCatalog = false;
let pageHistory = [];
let scannedTo = 1;
let catalogBusy = false;
let queryRunning = false;

const labels = {
  project_name: '项目名称', project_code: '项目代码', construction_unit: '建设单位', project_company: '项目公司',
  actual_investor: '实际投资主体', location: '建设地点', construction_scale: '建设规模', storage_scale: '储能规模',
  total_investment: '总投资', filing_status: '备案状态', filing_time: '备案时间', planned_start: '计划开工时间',
  planned_grid_connection: '计划并网时间', land_status: '土地落实情况', land_preapproval: '用地预审',
  site_opinion: '选址意见', construction_land_approval: '建设用地批复', land_transaction: '土地成交/划拨信息',
  eia: '环评', epc_tender: 'EPC招标', epc_winner: 'EPC中标单位', grid_access: '接入系统',
  grid_support: '电网支持意见', construction_status: '开工情况', grid_connection_status: '并网情况'
};
const logStatusLabels = {running: '查询中', retry: '重试', success: '成功', empty: '未匹配', error: '失败', manual: '需人工确认', stopped: '已停止'};

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (catalogBusy || queryRunning) return;
  const values = Object.fromEntries(new FormData(form).entries());
  if (values.start_date && values.end_date && values.start_date > values.end_date) {
    formError.textContent = '开始日期不能晚于结束日期。';
    return;
  }
  catalogSearch = {keyword: values.keyword.trim(), city: values.city.trim(), start_date: values.start_date, end_date: values.end_date};
  selectedProjects = new Map();
  candidates = [];
  pageHistory = [];
  document.querySelector('#candidatePanel').classList.add('hidden');
  await loadCatalogPage(1);
});

previousPageButton.addEventListener('click', () => {
  if (pageHistory.length) loadCatalogPage(pageHistory[pageHistory.length - 1], 'previous');
});
nextPageButton.addEventListener('click', () => loadCatalogPage(nextCatalogPage, 'next'));
goToPageButton.addEventListener('click', () => {
  const target = Number(pageNumberInput.value);
  if (!Number.isInteger(target) || target < 1 || target > totalPages) {
    formError.textContent = `请输入 1 到 ${totalPages} 之间的官网页码。`;
    return;
  }
  if (target !== currentPage) loadCatalogPage(target, 'next');
});
pageNumberInput.addEventListener('keydown', event => {
  if (event.key === 'Enter') { event.preventDefault(); goToPageButton.click(); }
});

async function loadCatalogPage(page, direction = 'first') {
  if (!catalogSearch || catalogBusy || queryRunning || page < 1 || page > 10000) return;
  catalogBusy = true;
  formError.textContent = '';
  searchButton.disabled = true;
  previousPageButton.disabled = true;
  nextPageButton.disabled = true;
  goToPageButton.disabled = true;
  pageNumberInput.disabled = true;
  nextPageButton.textContent = '正在加载…';
  startButton.disabled = true;
  updateProgress(`正在查询备案目录第 ${page} 页……`, 3);
  try {
    const response = await fetch('/api/catalog/search', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({...catalogSearch, page})});
    if (!response.ok) throw new Error(await response.text());
    const data = await response.json();
    if (direction === 'next') pageHistory.push(currentPage);
    if (direction === 'previous') pageHistory.pop();
    candidates = data.items || [];
    currentPage = Number(data.page) || page;
    totalPages = Number(data.total_pages) || 0;
    pageNumberInput.max = String(Math.max(totalPages, 1));
    pageNumberInput.value = String(currentPage);
    scannedTo = Number(data.scanned_to) || currentPage;
    nextCatalogPage = Number(data.next_page) || scannedTo + 1;
    hasMoreCatalog = Boolean(data.has_more);
    renderCandidates(data);
    updateProgress(candidates.length ? '请选择需要深度查询的项目' : data.has_more ? '本批未匹配日期，可继续检索下一批' : '备案目录未找到匹配项目', 8);
  } catch (error) {
    formError.textContent = `搜索失败：${friendlyError(error)}`;
    updateProgress('项目搜索失败', 0);
  } finally {
    catalogBusy = false;
    searchButton.disabled = false;
    nextPageButton.textContent = '下一页';
    previousPageButton.disabled = pageHistory.length === 0;
    nextPageButton.disabled = !hasMoreCatalog || queryRunning;
    goToPageButton.disabled = totalPages === 0 || queryRunning;
    pageNumberInput.disabled = totalPages === 0 || queryRunning;
    updateSelection();
  }
}

startButton.addEventListener('click', async () => {
  const selected = [...selectedProjects.values()];
  if (!selected.length) return;
  const values = Object.fromEntries(new FormData(form).entries());
  formError.textContent = '';
  setRunning(true);
  resetResults();
  updateProgress(`正在创建 ${selected.length} 个项目的查询任务……`, 2);
  try {
    const response = await fetch('/api/queries/batch', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({projects: selected, keyword: values.keyword, city: values.city, district: values.district, keywords: values.keywords})});
    if (!response.ok) throw new Error(await response.text());
    const data = await response.json();
    currentQueryId = data.id;
    pollTimer = window.setInterval(loadCurrent, 1200);
    await loadCurrent();
  } catch (error) {
    setRunning(false);
    formError.textContent = `无法开始查询：${friendlyError(error)}`;
    updateProgress('查询未启动', 0);
  }
});

document.querySelector('#selectAll').addEventListener('change', event => {
  if (event.target.checked) {
    for (const candidate of candidates) {
      if (selectedProjects.size >= 10) break;
      selectedProjects.set(candidateKey(candidate), candidate);
    }
    if (candidates.length > 10 || selectedProjects.size >= 10 && candidates.some(item => !selectedProjects.has(candidateKey(item)))) {
      formError.textContent = '一次最多选择 10 个项目。';
    }
  } else {
    for (const candidate of candidates) selectedProjects.delete(candidateKey(candidate));
    formError.textContent = '';
  }
  syncVisibleSelection();
  updateSelection();
});
stopButton.addEventListener('click', async () => {
  if (!currentQueryId) return;
  stopButton.disabled = true;
  updateProgress('正在停止，请等待当前页面任务结束……', Number(progressBar.dataset.value || 0));
  await fetch(`/api/queries/${currentQueryId}/stop`, {method: 'POST'});
});
exportButton.addEventListener('click', () => { if (currentQueryId) window.location.href = `/api/queries/${currentQueryId}/export`; });
document.querySelector('#historyButton').addEventListener('click', showHistory);
document.querySelector('#logsButton').addEventListener('click', showLogs);
document.querySelector('#closeModal').addEventListener('click', () => modal.close());

function renderCandidates(data) {
  const panel = document.querySelector('#candidatePanel');
  panel.classList.remove('hidden');
  document.querySelector('#candidateSummary').textContent = data.date_filtered
    ? `按备案通过日期筛选：已检索官网第 ${currentPage}–${scannedTo} 页，本批匹配 ${candidates.length} 条；可跨批勾选，最多 10 个项目。官网共 ${data.total} 条未筛选记录。`
    : `官网共找到 ${data.total} 条，每页最多 ${data.page_size} 条；可跨页勾选，最多 10 个项目。`;
  document.querySelector('#candidateBody').innerHTML = candidates.length ? candidates.map((item, index) => `
    <tr><td><input class="project-select" data-index="${index}" type="checkbox" aria-label="选择 ${escapeAttribute(item.project_name)}"></td>
    <td><strong>${escapeHtml(item.project_name)}</strong></td><td>${escapeHtml(item.project_code || '未标明')}</td>
    <td>${escapeHtml(item.project_company || '未标明')}</td><td>${escapeHtml(item.area || item.location || '未标明')}</td>
    <td class="scale-cell">${escapeHtml(item.storage_scale || item.construction_scale || '未标明')}</td>
    <td>${escapeHtml(item.filing_status || '未标明')}</td><td>${escapeHtml(item.filing_time || '未标明')}</td></tr>`).join('') : `<tr><td colspan="8" class="table-empty">${data.has_more && data.date_filtered ? '本批没有符合日期的项目，可点击下一页继续检索。' : '未找到匹配项目'}</td></tr>`;
  document.querySelectorAll('.project-select').forEach(item => item.addEventListener('change', event => {
    const candidate = candidates[Number(event.target.dataset.index)];
    const key = candidateKey(candidate);
    if (event.target.checked && !selectedProjects.has(key) && selectedProjects.size >= 10) {
      event.target.checked = false;
      formError.textContent = '一次最多选择 10 个项目。';
    } else {
      if (event.target.checked) selectedProjects.set(key, candidate);
      else selectedProjects.delete(key);
      formError.textContent = '';
    }
    updateSelection();
  }));
  syncVisibleSelection();
  updateSelection();
}

function updateSelection() {
  const checked = selectedProjects.size;
  startButton.disabled = checked === 0 || catalogBusy || queryRunning;
  startButton.textContent = checked ? `查询所选项目（${checked}）` : '查询所选项目';
  document.querySelector('#pageStatus').textContent = catalogSearch?.start_date || catalogSearch?.end_date
    ? `官网第 ${currentPage}–${scannedTo} / ${Math.max(totalPages, 1)} 页 · 本批匹配 ${candidates.length} 条 · 已选 ${checked} 个`
    : `第 ${currentPage} / ${Math.max(totalPages, 1)} 页 · 本页 ${candidates.length} 条 · 已选 ${checked} 个`;
  document.querySelector('#selectAll').checked = candidates.length > 0 && candidates.every(item => selectedProjects.has(candidateKey(item)));
}

function syncVisibleSelection() {
  document.querySelectorAll('.project-select').forEach(item => {
    const candidate = candidates[Number(item.dataset.index)];
    item.checked = selectedProjects.has(candidateKey(candidate));
  });
}

function candidateKey(item) { return item.project_code || item.catalog_id; }

async function loadCurrent() {
  if (!currentQueryId) return;
  try {
    const response = await fetch(`/api/queries/${currentQueryId}`);
    if (!response.ok) throw new Error(await response.text());
    const data = await response.json();
    updateProgress(data.stage, data.progress);
    if (['completed', 'failed', 'stopped'].includes(data.status)) {
      window.clearInterval(pollTimer); pollTimer = null; setRunning(false);
      exportButton.disabled = data.status !== 'completed';
      if (data.projects.length) renderResult(data);
      if (data.status === 'failed') formError.textContent = `查询失败：${data.error || '请查看日志'}`;
    }
  } catch (error) {
    window.clearInterval(pollTimer); pollTimer = null; setRunning(false);
    formError.textContent = `读取查询状态失败：${friendlyError(error)}`;
  }
}

function renderResult(detail) {
  document.querySelector('#emptyState').classList.add('hidden');
  document.querySelector('#resultTableWrap').classList.remove('hidden');
  document.querySelector('#resultSummary').textContent = `已整理 ${detail.projects.length} 个项目，保存 ${detail.sources.length} 个来源页面。点击项目行查看完整字段和证据。`;
  const columns = ['project_name', 'location', 'storage_scale', 'total_investment', 'filing_status', 'land_status', 'eia', 'epc_tender'];
  document.querySelector('#resultBody').innerHTML = detail.projects.map(record => {
    const count = detail.sources.filter(source => source.project_id === record.id).length;
    return `<tr class="result-row" data-project-id="${record.id}">${columns.map(key => `<td>${escapeHtml(record.data[key])}</td>`).join('')}<td>${count}</td></tr>`;
  }).join('');
  document.querySelectorAll('.result-row').forEach(row => row.addEventListener('click', () => showProject(detail, Number(row.dataset.projectId))));
  showProject(detail, detail.projects[0].id);
}

function showProject(detail, projectId) {
  const record = detail.projects.find(item => item.id === projectId);
  if (!record) return;
  const sources = detail.sources.filter(item => item.project_id === projectId);
  document.querySelectorAll('.result-row').forEach(row => row.classList.toggle('active-row', Number(row.dataset.projectId) === projectId));
  const grid = document.querySelector('#detailGrid');
  grid.classList.remove('hidden');
  grid.innerHTML = Object.entries(labels).map(([key, label]) => `<div class="detail-item ${key === 'land_status' ? 'land-result' : ''}"><span>${label}</span><strong>${escapeHtml(record.data[key])}</strong></div>`).join('');
  document.querySelector('#sourceSection').classList.remove('hidden');
  document.querySelector('#sourceList').innerHTML = sources.length ? sources.map(source => `
    <article class="source-card"><div class="source-meta"><span class="grade">${escapeHtml(source.grade)}级</span><strong>${escapeHtml(source.page_title || source.source_site)}</strong><span>${escapeHtml(source.published_at || '发布日期未标明')}</span><span>${escapeHtml(source.fetched_at)}</span></div>
    <a href="${escapeAttribute(source.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(source.url)}</a>
    <details><summary>查看原始文本</summary><pre class="raw-text">${escapeHtml(source.raw_text_preview)}</pre></details></article>`).join('') : '<div class="empty-state"><strong>未核验到相关原始页面</strong></div>';
}

async function showHistory() {
  const rows = await (await fetch('/api/history')).json();
  document.querySelector('#modalTitle').textContent = '历史查询';
  document.querySelector('#modalContent').innerHTML = rows.length ? `<div class="table-wrap"><table class="history-table"><thead><tr><th>时间</th><th>查询内容</th><th>地区</th><th>状态</th><th>进度</th></tr></thead><tbody>${rows.map(row => { const names = row.conditions.projects?.map(item => item.project_name).join('、') || row.conditions.project_name || row.conditions.keyword || ''; return `<tr class="history-row" data-id="${row.id}"><td>${escapeHtml(row.created_at)}</td><td>${escapeHtml(names)}</td><td>${escapeHtml([row.conditions.province, row.conditions.city, row.conditions.district].filter(Boolean).join(' '))}</td><td>${escapeHtml(row.stage)}</td><td>${row.progress}%</td></tr>`; }).join('')}</tbody></table></div>` : '<div class="empty-state"><strong>没有历史查询</strong></div>';
  modal.showModal();
  document.querySelectorAll('.history-row').forEach(row => row.addEventListener('click', async () => {
    currentQueryId = Number(row.dataset.id); modal.close();
    const detail = await (await fetch(`/api/queries/${currentQueryId}`)).json();
    updateProgress(detail.stage, detail.progress); if (detail.projects.length) renderResult(detail);
    exportButton.disabled = detail.status !== 'completed';
  }));
}

async function showLogs() {
  if (!currentQueryId) {
    document.querySelector('#modalTitle').textContent = '查询日志';
    document.querySelector('#modalContent').innerHTML = '<div class="empty-state"><strong>请先开始或打开一次历史查询</strong></div>';
    modal.showModal(); return;
  }
  const detail = await (await fetch(`/api/queries/${currentQueryId}`)).json();
  document.querySelector('#modalTitle').textContent = `查询日志 #${currentQueryId}`;
  document.querySelector('#modalContent').innerHTML = detail.logs.length ? `<div class="log-list">${detail.logs.map(log => `<div class="log-item ${log.status === 'error' ? 'log-error' : ''}"><span>${escapeHtml(log.created_at)}</span><strong>${escapeHtml(log.stage)}</strong><span>${escapeHtml(logStatusLabels[log.status] || log.status)}</span><span>${escapeHtml(log.target)}<br>${escapeHtml(log.message)}</span></div>`).join('')}</div>` : '<div class="empty-state"><strong>暂无日志</strong></div>';
  modal.showModal();
}

function updateProgress(stage, progress) {
  const value = Math.max(0, Math.min(100, Number(progress) || 0));
  stageText.textContent = stage; progressText.textContent = `${value}%`;
  progressBar.style.width = `${value}%`; progressBar.dataset.value = value;
}
function setRunning(running) {
  queryRunning = running;
  searchButton.disabled = running; stopButton.disabled = !running;
  previousPageButton.disabled = running || catalogBusy || pageHistory.length === 0;
  nextPageButton.disabled = running || catalogBusy || !hasMoreCatalog;
  goToPageButton.disabled = running || catalogBusy || totalPages === 0;
  pageNumberInput.disabled = running || catalogBusy || totalPages === 0;
  [...form.elements].filter(item => item.tagName === 'INPUT').forEach(input => { input.disabled = running; });
  document.querySelectorAll('.project-select').forEach(input => { input.disabled = running; });
  document.querySelector('#selectAll').disabled = running;
  updateSelection();
}
function resetResults() {
  exportButton.disabled = true; document.querySelector('#emptyState').classList.remove('hidden');
  document.querySelector('#resultTableWrap').classList.add('hidden'); document.querySelector('#detailGrid').classList.add('hidden');
  document.querySelector('#sourceSection').classList.add('hidden'); document.querySelector('#resultSummary').textContent = '正在查询公开网站，请稍候。';
}
function friendlyError(error) { return String(error.message || error).replace(/[{}\[\]"]/g, '').slice(0, 240); }
function escapeHtml(value) { return String(value ?? '').replace(/[&<>"]/g, char => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[char])); }
function escapeAttribute(value) { return escapeHtml(value).replace(/'/g, '&#39;'); }
