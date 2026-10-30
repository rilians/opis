'use strict';

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const icon = (name, extra = '') => `<svg class="icon ${extra}" aria-hidden="true"><use href="#i-${name}"></use></svg>`;
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pages = { overview:'Overview', endpoints:'Endpoint', incidents:'Insiden', sla:'Laporan SLA', alerts:'Notifikasi', settings:'Pengaturan' };
const periods = { '24h':'24 jam terakhir', '7d':'7 hari terakhir', '30d':'30 hari terakhir' };
const periodShort = { '24h':'24 jam', '7d':'7 hari', '30d':'30 hari' };
const statusText = { up:'Operasional', down:'Gangguan', degraded:'Degradasi', pending:'Menunggu', paused:'Dijeda', open:'Aktif', resolved:'Pulih', closed:'Ditutup' };
const state = { page:'overview', period:'24h', reportPeriod:'7d', dashboard:null, settings:null, incidents:[], report:null, alerts:[], endpointFilter:'all', incidentFilter:'all', search:'', loading:0 };

async function api(path, options = {}) {
  const config = {...options, headers:{...(options.body ? {'Content-Type':'application/json'} : {}), ...(options.headers || {})}};
  const response = await fetch(path, config);
  let data;
  try { data = await response.json(); } catch { data = {}; }
  if (!response.ok) {
    let detail = data.detail || 'Terjadi kesalahan. Silakan coba lagi.';
    if (Array.isArray(detail)) detail = detail.map(item => `${item.loc?.slice(-1)[0] || 'Input'}: ${item.msg}`).join('; ');
    throw new Error(typeof detail === 'string' ? detail : 'Permintaan tidak dapat diproses.');
  }
  return data;
}
const number = n => new Intl.NumberFormat('id-ID', {maximumFractionDigits:1}).format(n ?? 0);
const pct = n => n == null ? '—' : `${new Intl.NumberFormat('id-ID', {minimumFractionDigits:2, maximumFractionDigits:2}).format(n)}%`;
const targetPct = n => `${new Intl.NumberFormat('id-ID', {maximumFractionDigits:3}).format(n ?? 99.9)}%`;
const ms = n => n == null ? '—' : `${number(n)} ms`;
function dateTime(value, withYear = false) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return new Intl.DateTimeFormat('id-ID', {day:'numeric', month:'short', ...(withYear ? {year:'numeric'} : {}), hour:'2-digit', minute:'2-digit'}).format(date).replace(/\./g, ':');
}
function relative(value) {
  if (!value) return 'Belum pernah';
  const difference = Math.max(0, (Date.now() - new Date(value).getTime()) / 1000);
  if (difference < 60) return 'Baru saja';
  if (difference < 3600) return `${Math.floor(difference / 60)} menit lalu`;
  if (difference < 86400) return `${Math.floor(difference / 3600)} jam lalu`;
  if (difference < 7 * 86400) return `${Math.floor(difference / 86400)} hari lalu`;
  return dateTime(value, true);
}
function duration(seconds) {
  if (seconds == null) return '—';
  seconds = Math.max(0, Math.floor(seconds));
  const days = Math.floor(seconds / 86400), hours = Math.floor((seconds % 86400) / 3600), minutes = Math.floor((seconds % 3600) / 60);
  if (days) return `${days}h ${hours}j`;
  if (hours) return `${hours}j ${minutes}m`;
  if (minutes) return `${minutes} menit`;
  return `${seconds} detik`;
}
function intervalText(seconds) {
  if (seconds % 3600 === 0) return `${seconds / 3600} jam`;
  if (seconds % 60 === 0) return `${seconds / 60} menit`;
  return `${seconds} detik`;
}
function safeURL(url) {
  try { const u = new URL(url); return `${u.host}${u.pathname === '/' ? '' : u.pathname}${u.search ? '?…' : ''}`; }
  catch { return url || '—'; }
}
function demoBadge(isDemo) { return isDemo ? '<span class="demo-pill">Demo</span>' : ''; }
function statusBadge(status) { return `<span class="status ${esc(status)}">${esc(statusText[status] || status)}</span>`; }
function endpointAvatar(index) {
  const icons = ['layers','shield','activity','server','send'];
  return `<span class="endpoint-avatar color-${index % 5}">${icon(icons[index % 5])}</span>`;
}
function segmentBars(segments, max = 18) {
  const items = segments || [];
  if (!items.length) return '';
  let compact = items;
  if (items.length > max) {
    compact = [];
    for (let i=0; i<max; i++) {
      const group = items.slice(Math.floor(i*items.length/max), Math.floor((i+1)*items.length/max));
      compact.push(group.includes('down') ? 'down' : group.includes('degraded') ? 'degraded' : group.some(v => v === 'up') ? 'up' : 'empty');
    }
  }
  return `<span class="segments" aria-label="Riwayat pemeriksaan"><span class="sr-only"></span>${compact.map(item => `<i class="${esc(item)}"></i>`).join('')}</span>`;
}
function selectPeriod(value, action = 'period') {
  return `<label class="period-select">${icon('calendar')}<select data-change="${action}" aria-label="Pilih periode">${Object.entries(periods).map(([k,v]) => `<option value="${k}" ${k === value ? 'selected' : ''}>${v}</option>`).join('')}</select>${icon('down','chevron')}</label>`;
}
function toast(message, isError = false) {
  const item = document.createElement('div');
  item.className = `toast${isError ? ' error' : ''}`;
  item.innerHTML = `${icon(isError ? 'incident' : 'check-circle')}<span>${esc(message)}</span>`;
  $('#toastRoot').appendChild(item);
  setTimeout(() => item.remove(), 4700);
}
function pageTitle(title, description, actions = '', eyebrow = 'WORKSPACE') {
  return `<div class="page-intro"><div><div class="eyebrow"><span></span>${esc(eyebrow)}</div><h1>${esc(title)}</h1><p>${esc(description)}</p></div><div class="page-intro-actions">${actions}</div></div>`;
}
function demoBanner(count) {
  if (!count) return '';
  return `<div class="demo-banner"><div class="demo-banner-icon">${icon('info')}</div><div class="demo-banner-text"><strong>Anda sedang melihat data demo.</strong><span>${number(count)} endpoint dan riwayatnya adalah simulasi, bukan pemeriksaan langsung.</span></div><button class="text-link" data-page="settings">Kelola data demo ${icon('right')}</button></div>`;
}
function emptyState(title, text, action = '') {
  return `<div class="empty-state"><div class="empty-icon">${icon('activity')}</div><strong>${esc(title)}</strong><p>${esc(text)}</p>${action}</div>`;
}
function updateChrome() {
  const d = state.dashboard, settings = state.settings;
  if (!d || !settings) return;
  $('#breadcrumbPage').textContent = pages[state.page];
  $('#endpointCount').textContent = number(d.total_endpoints);
  $('#incidentCount').textContent = number(d.active_incidents);
  $('#incidentCount').hidden = !d.active_incidents;
  $('#notificationDot').hidden = !d.active_incidents;
  $('#sideTarget').textContent = targetPct(settings.sla_target);
  $('#topSystem').classList.toggle('offline', !settings.scheduler_enabled);
  $('#topSystem span:last-child').textContent = settings.scheduler_enabled ? 'Monitoring aktif' : 'Scheduler nonaktif';
  $$('.nav-item').forEach(item => item.classList.toggle('active', item.dataset.page === state.page));
  document.title = `${pages[state.page]} · Opis`;
}
async function loadData({quiet = false} = {}) {
  const seq = ++state.loading;
  const currentPage = state.page;
  try {
    const tasks = [api(`/api/dashboard?period=${state.period}`), api('/api/settings')];
    if (currentPage === 'incidents') tasks.push(api('/api/incidents'));
    else if (currentPage === 'sla') tasks.push(api(`/api/reports/sla?period=${state.reportPeriod}`));
    else if (currentPage === 'alerts') tasks.push(api('/api/alerts'));
    const [dashboard, settings, extra] = await Promise.all(tasks);
    if (seq !== state.loading || currentPage !== state.page) return;
    state.dashboard = dashboard; state.settings = settings;
    if (currentPage === 'incidents') state.incidents = extra;
    if (currentPage === 'sla') state.report = extra;
    if (currentPage === 'alerts') state.alerts = extra;
    updateChrome();
    render();
  } catch (error) {
    if (seq !== state.loading) return;
    if (!state.dashboard && !quiet) $('#view').innerHTML = emptyState('Tidak dapat terhubung ke Opis', 'Pastikan server aplikasi dan database berjalan, lalu coba lagi.', `<button class="button button-secondary" data-action="refresh">${icon('refresh')} Coba lagi</button>`);
    else if (!quiet) toast(error.message, true);
  }
}
function navigate(page) {
  if (!pages[page]) return;
  $('#sidebar').classList.remove('open'); $('#sidebarScrim').classList.remove('show');
  if (location.hash !== `#${page}`) location.hash = page;
  else if (state.page !== page) { state.page = page; loadData(); }
}
function render() {
  const view = $('#view');
  if (!state.dashboard) return;
  switch (state.page) {
    case 'overview': view.innerHTML = renderOverview(); break;
    case 'endpoints': view.innerHTML = renderEndpoints(); break;
    case 'incidents': view.innerHTML = renderIncidents(); break;
    case 'sla': view.innerHTML = renderSLA(); break;
    case 'alerts': view.innerHTML = renderAlerts(); break;
    case 'settings': view.innerHTML = renderSettings(); break;
  }
}
function metric(label, value, unit, iconName, iconClass, footer) {
  return `<article class="metric-card"><div class="metric-top"><span>${esc(label)}</span><span class="metric-icon ${iconClass}">${icon(iconName)}</span></div><div class="metric-number">${esc(value)}${unit ? `<small>${esc(unit)}</small>` : ''}</div><div class="metric-foot">${footer}</div></article>`;
}
function responseChart(data, period) {
  const values = data.map(item => item.response_ms);
  const available = values.filter(value => value !== null && Number.isFinite(value));
  if (!available.length) return `<div class="chart-empty">Belum ada data pemeriksaan pada periode ini.</div>`;
  const max = Math.max(100, Math.ceil(Math.max(...available) / 50) * 50);
  const x0 = 39, x1 = 690, y0 = 10, y1 = 126;
  const point = (i, value) => [x0 + (x1-x0)*(data.length <= 1 ? 0 : i/(data.length-1)), y1 - (value/max)*(y1-y0)];
  const groups = [];
  let group = [];
  data.forEach((item, i) => {
    if (item.response_ms == null) { if (group.length) groups.push(group); group = []; }
    else group.push(point(i, item.response_ms));
  });
  if (group.length) groups.push(group);
  const paths = groups.map(points => {
    let line = `M ${points[0][0].toFixed(1)} ${points[0][1].toFixed(1)}`;
    for (let i = 1; i < points.length; i++) {
      const [px,py] = points[i-1], [x,y] = points[i], mid = (px+x)/2;
      line += ` C ${mid.toFixed(1)} ${py.toFixed(1)}, ${mid.toFixed(1)} ${y.toFixed(1)}, ${x.toFixed(1)} ${y.toFixed(1)}`;
    }
    const area = `${line} L ${points[points.length-1][0].toFixed(1)} ${y1} L ${points[0][0].toFixed(1)} ${y1} Z`;
    return `<path d="${area}" fill="url(#chartGradient)"/><path d="${line}" fill="none" stroke="#67b982" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>${points.length === 1 ? `<circle cx="${points[0][0]}" cy="${points[0][1]}" r="3" fill="#67b982"/>` : ''}`;
  }).join('');
  const grid = Array.from({length:4}, (_, i) => {
    const y = y0 + i*(y1-y0)/3, label = Math.round(max*(3-i)/3);
    return `<line class="chart-grid" x1="${x0}" y1="${y}" x2="${x1}" y2="${y}"/><text class="chart-axis-label" x="${x0-8}" y="${y+3}" text-anchor="end">${label}</text>`;
  }).join('');
  const indexes = [0, Math.floor((data.length-1)/3), Math.floor((data.length-1)*2/3), data.length-1];
  const labels = indexes.map((index, i) => {
    const date = new Date(data[index].at), x = x0 + (x1-x0)*index/(data.length-1 || 1);
    const label = period === '24h' ? new Intl.DateTimeFormat('id-ID',{hour:'2-digit', minute:'2-digit'}).format(date).replace('.', ':') : new Intl.DateTimeFormat('id-ID',{day:'numeric',month:'short'}).format(date);
    return `<text class="chart-axis-label" x="${x}" y="150" text-anchor="${i===0?'start':i===3?'end':'middle'}">${esc(label)}</text>`;
  }).join('');
  return `<svg viewBox="0 0 700 160" preserveAspectRatio="none" role="img" aria-label="Grafik rata-rata waktu respons selama ${esc(periods[period])}"><defs><linearGradient id="chartGradient" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stop-color="#9dd8ad" stop-opacity=".28"/><stop offset="100%" stop-color="#a9ddb7" stop-opacity=".02"/></linearGradient></defs>${grid}${paths}${labels}</svg>`;
}
function healthDonut(d) {
  const counts = d.status_counts, total = d.total_endpoints;
  const parts = [[counts.up,'#75c492'],[counts.down,'#e8a28c'],[counts.degraded,'#e4c487'],[counts.pending,'#dce6de'],[counts.paused,'#c8d5cc']];
  let angle = 0, stops = [];
  for (const [count,color] of parts) {
    if (!count) continue;
    const from = angle; angle += count / (total || 1) * 100;
    stops.push(`${color} ${from}% ${angle}%`);
  }
  if (!stops.length) stops = ['#e8efea 0% 100%'];
  const legend = [[counts.up,'Beroperasi',''],[counts.down,'Gangguan','red'],[counts.degraded,'Degradasi','amber'],[counts.pending + counts.paused,'Menunggu / jeda','grey']];
  return `<div class="health-body"><div class="donut" style="background:conic-gradient(${stops.join(',')})"><div class="donut-center"><strong>${counts.up}<span style="display:inline;font-size:15px;color:#b3c2b7;font-weight:600">/${total}</span></strong><span>operasional</span></div></div><div class="health-legend">${legend.map(([v,label,cls]) => `<div class="health-legend-row"><i class="${cls}"></i><span>${label}</span><strong>${v}</strong></div>`).join('')}</div></div>`;
}
function overviewEndpointRow(ep, index) {
  return `<tr><td><div class="endpoint-cell">${endpointAvatar(index)}<button class="endpoint-name row-link" data-action="endpoint-detail" data-id="${ep.id}"><strong>${esc(ep.name)}${demoBadge(ep.is_demo)}</strong><span>${esc(safeURL(ep.url))}</span></button></div></td><td>${statusBadge(ep.status)}</td><td><div class="uptime-cell">${segmentBars(ep.segments, 15)} <span>${pct(ep.uptime_percent)}</span></div></td><td><span class="small-number">${ms(ep.last_response_ms)}</span></td></tr>`;
}
function overviewFeed(incidents) {
  if (!incidents.length) return emptyState('Belum ada insiden', 'Insiden akan muncul di sini ketika pemeriksaan gagal.');
  return `<div class="incident-feed">${incidents.slice(0,3).map(inc => `<div class="feed-item"><div class="feed-icon ${inc.status === 'resolved' ? 'resolved' : ''}">${icon(inc.status === 'resolved' ? 'check-circle' : 'incident')}</div><div class="feed-main"><button class="feed-link" data-action="incident-detail" data-id="${inc.id}"><div class="feed-top"><strong>${esc(inc.endpoint_name)}${demoBadge(inc.is_demo)}</strong>${statusBadge(inc.status)}</div><p>${esc(inc.title)}</p><small>${esc(relative(inc.started_at))}${inc.first_status_code ? ` &nbsp;·&nbsp; HTTP ${inc.first_status_code}` : ''}</small></button></div></div>`).join('')}</div>`;
}
function renderOverview() {
  const d = state.dashboard, c = d.status_counts;
  const belowTarget = d.meets_target === false;
  const endFoot = `<span class="dot"></span><strong>${c.up} operasional</strong><span> · ${c.down + c.degraded} gangguan</span>`;
  const uptimeFoot = d.uptime_percent == null ? 'Belum ada pemeriksaan' : `<span class="mini-badge ${belowTarget?'amber':'green'}">${belowTarget?'Di bawah target':'Sesuai target'}</span><span>Target ${targetPct(d.target_sla)}</span>`;
  const incidentFoot = d.active_incidents ? `<span class="dot red"></span><strong class="red">Membutuhkan perhatian</strong>` : `<span class="dot"></span><strong>Tidak ada insiden aktif</strong>`;
  return `${pageTitle('Semua sistem, satu pandangan.', 'Pantau kesehatan dan performa layanan API Anda di satu tempat.', selectPeriod(state.period), 'MONITORING OVERVIEW')}
    ${demoBanner(d.demo_count)}
    <div class="metric-grid">
      ${metric('Endpoint dipantau', number(d.total_endpoints), 'endpoint', 'server', '', endFoot)}
      ${metric('Ketersediaan', d.uptime_percent == null ? '—' : pct(d.uptime_percent).replace('%',''), d.uptime_percent == null ? '' : '%', 'shield', 'blue', uptimeFoot)}
      ${metric('Rata-rata respons', d.avg_response_ms == null ? '—' : number(d.avg_response_ms), d.avg_response_ms == null ? '' : 'ms', 'activity', 'amber', `<span>Dari ${number(d.total_checks)} pemeriksaan</span>`)}
      ${metric('Insiden aktif', number(d.active_incidents), 'insiden', 'incident', 'red', incidentFoot)}
    </div>
    <div class="dashboard-grid">
      <section class="card chart-card"><div class="card-heading"><div><h2>Waktu respons</h2><p>Rata-rata dari seluruh endpoint yang dipantau</p></div><span class="card-chip">${esc(periodShort[state.period].toUpperCase())}</span></div><div class="chart-summary"><strong>${d.avg_response_ms == null ? '—' : number(d.avg_response_ms)}<small>${d.avg_response_ms == null ? '' : 'ms'}</small></strong><span>rata-rata waktu respons</span></div><div class="chart-wrap">${responseChart(d.chart, state.period)}</div><div class="chart-legend"><span class="legend-line"></span> Respons rata-rata <span style="margin-left:auto">Termasuk pemeriksaan gagal</span></div></section>
      <section class="card health-card"><div class="card-heading"><div><h2>Kondisi endpoint</h2><p>Status terbaru dari setiap endpoint</p></div>${icon('more','muted-icon')}</div>${healthDonut(d)}<div class="card-footer-link"><span>Diperbarui ${esc(relative(d.to))}</span><button class="text-link" data-page="endpoints">Lihat endpoint ${icon('right')}</button></div></section>
    </div>
    <div class="bottom-grid">
      <section class="card list-card"><div class="card-heading"><div><h2>Endpoint yang dipantau</h2><p>Gambaran status layanan API Anda</p></div><button class="text-link" data-page="endpoints">Lihat semua ${icon('right')}</button></div>${d.endpoints.length ? `<div class="table-wrap"><table class="overview-table"><thead><tr><th>Endpoint</th><th>Status</th><th>Uptime · ${periodShort[state.period]}</th><th>Respons</th></tr></thead><tbody>${d.endpoints.slice(0,5).map(overviewEndpointRow).join('')}</tbody></table></div>` : emptyState('Belum ada endpoint', 'Tambahkan endpoint pertama untuk memulai pemantauan.', `<button class="button button-light" data-action="add-endpoint">${icon('plus')} Tambah endpoint</button>`)}</section>
      <section class="card list-card"><div class="card-heading"><div><h2>Insiden terbaru</h2><p>Aktivitas yang membutuhkan perhatian</p></div><button class="text-link" data-page="incidents">Lihat semua ${icon('right')}</button></div>${overviewFeed(d.recent_incidents)}</section>
    </div>`;
}

function endpointMatches(ep) {
  const needle = state.search.trim().toLowerCase();
  const matchSearch = !needle || `${ep.name} ${ep.url}`.toLowerCase().includes(needle);
  const matchStatus = state.endpointFilter === 'all' || (state.endpointFilter === 'attention' ? ['down','degraded'].includes(ep.status) : ep.status === state.endpointFilter);
  return matchSearch && matchStatus;
}
function endpointTableRows() {
  const endpoints = state.dashboard.endpoints.filter(endpointMatches);
  if (!endpoints.length) return `<tr><td colspan="7">${emptyState('Endpoint tidak ditemukan', 'Coba kata kunci atau filter yang lain.')}</td></tr>`;
  return endpoints.map((ep, index) => `<tr>
    <td><div class="endpoint-cell">${endpointAvatar(index)}<button class="endpoint-name row-link" data-action="endpoint-detail" data-id="${ep.id}"><strong>${esc(ep.name)}${demoBadge(ep.is_demo)}</strong><span>${esc(safeURL(ep.url))}</span></button></div></td>
    <td>${statusBadge(ep.status)}</td><td><span class="method-tag">${esc(ep.method)}</span></td><td>${esc(intervalText(ep.interval_seconds))}${ep.is_demo ? ' <span class="muted">(simulasi)</span>' : ''}</td>
    <td><div class="uptime-cell">${segmentBars(ep.segments, 14)} ${pct(ep.uptime_percent)}</div></td><td><span class="small-number">${ms(ep.last_response_ms)}</span><br><span style="font-size:9.5px;color:#aab7ad">${esc(relative(ep.last_checked_at))}</span></td>
    <td><div class="table-actions"><button class="icon-button" data-action="endpoint-detail" data-id="${ep.id}" title="Lihat detail" aria-label="Lihat detail ${esc(ep.name)}">${icon('more')}</button>${!ep.is_demo ? `<button class="icon-button" data-action="check-endpoint" data-id="${ep.id}" ${!ep.enabled?'disabled':''} title="Periksa sekarang" aria-label="Periksa ${esc(ep.name)}">${icon('refresh')}</button><button class="icon-button" data-action="edit-endpoint" data-id="${ep.id}" title="Ubah" aria-label="Ubah ${esc(ep.name)}">${icon('edit')}</button>` : ''}<button class="icon-button" data-action="archive-endpoint" data-id="${ep.id}" title="Arsipkan" aria-label="Arsipkan ${esc(ep.name)}">${icon('trash')}</button></div></td>
  </tr>`).join('');
}
function renderEndpoints() {
  const d = state.dashboard, c = d.status_counts;
  const filterOptions = [['all','Semua',d.total_endpoints],['up','Operasional',c.up],['attention','Gangguan',c.down+c.degraded],['pending','Menunggu',c.pending],['paused','Dijeda',c.paused]];
  return `${pageTitle('Endpoint', 'Kelola dan pantau seluruh endpoint API Anda.', `${selectPeriod(state.period)} <button class="button button-primary" data-action="add-endpoint">${icon('plus')} Tambah endpoint</button>`, 'PEMANTAUAN')}
    ${demoBanner(d.demo_count)}
    <section class="card page-card"><div class="toolbar"><div class="tabs">${filterOptions.map(([key,label,count]) => `<button class="tab ${state.endpointFilter===key?'active':''}" data-action="endpoint-filter" data-value="${key}">${label}<span class="tab-count">${count}</span></button>`).join('')}</div><label class="search-box">${icon('search')}<input id="endpointSearch" type="search" placeholder="Cari endpoint..." value="${esc(state.search)}" aria-label="Cari endpoint"></label></div>
      <div class="table-wrap"><table class="full-table"><thead><tr><th>Endpoint</th><th>Status</th><th>Metode</th><th>Interval</th><th>Uptime · ${periodShort[state.period]}</th><th>Pemeriksaan terakhir</th><th></th></tr></thead><tbody id="endpointRows">${endpointTableRows()}</tbody></table></div><div class="table-note">Uptime dihitung dari jumlah pemeriksaan berhasil selama ${periods[state.period]}. Klik nama endpoint untuk melihat riwayat.</div></section>
    <div class="page-note">${icon('info')}<span>Endpoint demo menggunakan data simulasi dan tidak melakukan permintaan jaringan. Endpoint yang Anda tambahkan diperiksa sesuai interval selama scheduler aktif.</span></div>`;
}
function incidentRows() {
  const rows = state.incidents.filter(inc => state.incidentFilter === 'all' || inc.status === state.incidentFilter);
  if (!rows.length) return `<tr><td colspan="6">${emptyState('Tidak ada insiden', 'Belum ada insiden untuk filter yang dipilih.')}</td></tr>`;
  return rows.map(inc => `<tr><td><button class="row-link" data-action="incident-detail" data-id="${inc.id}"><div class="issue-cell"><span class="feed-icon ${inc.status==='resolved'?'resolved':''}">${icon(inc.status==='resolved'?'check-circle':'incident')}</span><div><strong>${esc(inc.title)} ${demoBadge(inc.is_demo)}</strong><span>#${String(inc.id).padStart(4,'0')} · ${esc(inc.endpoint_name)}</span></div></div></button></td><td>${statusBadge(inc.status)}</td><td>${esc(dateTime(inc.started_at, true))}</td><td>${esc(duration(inc.duration_seconds))}</td><td>${inc.first_status_code ? `HTTP ${inc.first_status_code}` : esc(inc.first_error_type || '—')}</td><td><button class="text-link" data-action="incident-detail" data-id="${inc.id}">Lihat detail ${icon('right')}</button></td></tr>`).join('');
}
function renderIncidents() {
  const incidents = state.incidents;
  const counts = {all:incidents.length, open:incidents.filter(i=>i.status==='open').length, resolved:incidents.filter(i=>i.status==='resolved').length, closed:incidents.filter(i=>i.status==='closed').length};
  return `${pageTitle('Riwayat insiden', 'Pahami apa yang terjadi dan dokumentasikan proses investigasi.', `<button class="button button-secondary" data-action="refresh">${icon('refresh')} Perbarui</button>`, 'INCIDENT REPORTER')}
    ${demoBanner(state.dashboard.demo_count)}
    <div class="insight-grid"><div class="card insight-card"><span class="label">Total insiden</span><strong>${number(counts.all)}</strong><small>Dalam riwayat yang dimuat</small></div><div class="card insight-card"><span class="label">Insiden aktif</span><strong>${number(counts.open)}</strong><small>Memerlukan perhatian</small></div><div class="card insight-card"><span class="label">Telah pulih</span><strong>${number(counts.resolved)}</strong><small>Berdasarkan pemeriksaan pemulihan</small></div></div>
    <section class="card page-card"><div class="toolbar"><div class="tabs">${[['all','Semua'],['open','Aktif'],['resolved','Pulih'],['closed','Ditutup']].map(([key,label]) => `<button class="tab ${state.incidentFilter===key?'active':''}" data-action="incident-filter" data-value="${key}">${label}<span class="tab-count">${counts[key]}</span></button>`).join('')}</div><span style="color:#a2afa6;font-size:10px">Menampilkan hingga 100 insiden terbaru</span></div><div class="table-wrap"><table class="full-table"><thead><tr><th>Insiden / Endpoint</th><th>Status</th><th>Mulai</th><th>Durasi</th><th>Hasil awal</th><th></th></tr></thead><tbody>${incidentRows()}</tbody></table></div></section>
    <div class="page-note">${icon('info')}<span>Insiden dibuka setelah ambang kegagalan tercapai. Ringkasan dan saran investigasi adalah petunjuk, <strong>bukan penyebab yang sudah terkonfirmasi.</strong></span></div>`;
}
function renderSLA() {
  const r = state.report;
  if (!r) return `<div class="loading-state"><span class="spinner"></span> Memuat laporan...</div>`;
  const incidents = r.endpoints.reduce((sum,ep) => sum + ep.incident_count, 0);
  const below = r.meets_target === false;
  return `${pageTitle('Laporan SLA', 'Lihat ketersediaan layanan dan hasil pemeriksaan dalam satu laporan.', `${selectPeriod(state.reportPeriod,'report-period')} <a class="button button-secondary" href="/api/reports/sla.csv?period=${state.reportPeriod}">${icon('download')} Ekspor CSV</a>`, 'SERVICE LEVEL REPORT')}
    ${demoBanner(r.demo_count)}
    <div class="metric-grid">
      ${metric('Ketersediaan gabungan', r.uptime_percent == null ? '—' : pct(r.uptime_percent).replace('%',''), r.uptime_percent == null ? '' : '%', 'shield','',r.uptime_percent == null ? 'Belum ada data' : `<span class="mini-badge ${below?'amber':'green'}">${below?'Di bawah target':'Sesuai target'}</span><span>Target ${targetPct(r.target_sla)}</span>`)}
      ${metric('Pemeriksaan berhasil',number(r.successful_checks),'pemeriksaan','check-circle','blue',`<span>Dari ${number(r.total_checks)} pemeriksaan</span>`)}
      ${metric('Pemeriksaan gagal',number(r.total_checks-r.successful_checks),'pemeriksaan','activity','amber',`<span>Selama ${periods[state.reportPeriod]}</span>`)}
      ${metric('Insiden pada periode',number(incidents),'insiden','incident','red',`<span>Termasuk insiden yang masih aktif</span>`)}
    </div>
    <div class="page-note">${icon('info')}<span><strong>Metode perhitungan:</strong> ${esc(r.methodology)} Nilai gabungan diberi bobot berdasarkan jumlah pemeriksaan; bukan rata-rata durasi uptime. Data demo turut dihitung dan diberi label.</span></div>
    <section class="card page-card"><div class="card-heading" style="padding:20px"><div><h2>Performa per endpoint</h2><p>Periode ${esc(dateTime(r.from, true))} – ${esc(dateTime(r.to, true))} · waktu lokal browser</p></div><span class="card-chip">TARGET ${targetPct(r.target_sla)}</span></div><div class="table-wrap"><table class="full-table"><thead><tr><th>Endpoint</th><th>Ketersediaan</th><th>Berhasil / total</th><th>Insiden</th><th>Durasi insiden</th><th>Target</th></tr></thead><tbody>${r.endpoints.length ? r.endpoints.map((ep,index)=>`<tr><td><div class="endpoint-cell">${endpointAvatar(index)}<div class="endpoint-name"><strong>${esc(ep.name)}${demoBadge(ep.is_demo)}${ep.archived ? '<span class="demo-pill">Arsip</span>' : ''}</strong><span>${esc(safeURL(ep.url))}</span></div></div></td><td><div class="uptime-cell">${segmentBars(ep.segments, 14)} ${pct(ep.uptime_percent)}</div></td><td>${number(ep.successful_checks)} / ${number(ep.total_checks)}</td><td>${number(ep.incident_count)}</td><td>${esc(duration(ep.incident_duration_seconds))}</td><td>${ep.meets_target == null ? statusBadge('pending') : `<span class="mini-badge ${ep.meets_target?'green':'amber'}">${ep.meets_target?'Tercapai':'Di bawah target'}</span>`}</td></tr>`).join('') : `<tr><td colspan="6">${emptyState('Belum ada laporan', 'Tambahkan endpoint untuk mulai mengumpulkan data SLA.')}</td></tr>`}</tbody></table></div></section>`;
}
function eventName(value) { return ({'incident.opened':'Insiden dibuka', 'incident.resolved':'Insiden pulih', 'test':'Pengujian webhook'})[value] || value; }
function renderAlerts() {
  const s = state.settings, deliveries = state.alerts;
  return `${pageTitle('Notifikasi', 'Atur bagaimana Anda menerima kabar saat layanan mengalami gangguan.', '', 'PREFERENSI')}
    <div class="config-grid">
      <section class="card config-card"><div class="card-heading"><div class="config-title-wrap"><span class="config-icon">${icon('bell')}</span><div><h2>Di dalam aplikasi</h2><p>Indikator dan riwayat insiden</p></div></div><span class="config-status">Aktif</span></div><div class="config-divider"></div><p>Insiden muncul di dashboard dan menu Insiden ketika batas kegagalan terpenuhi. Status diperbarui kembali setelah pemulihan terkonfirmasi.</p><div class="config-divider"></div><div class="config-list"><div class="config-list-row"><span>Insiden dibuka</span><strong>Aktif</strong></div><div class="config-list-row"><span>Pemulihan terdeteksi</span><strong>Aktif</strong></div></div></section>
      <section class="card config-card"><div class="card-heading"><div class="config-title-wrap"><span class="config-icon">${icon('send')}</span><div><h2>Webhook</h2><p>Teruskan peristiwa ke layanan Anda</p></div></div><span class="config-status ${s.webhook_configured?'':'off'}">${s.webhook_configured?'Terhubung':'Belum diatur'}</span></div><div class="config-divider"></div><p>Opis mengirim POST JSON untuk <strong>incident.opened</strong> dan <strong>incident.resolved</strong>. Endpoint demo tidak mengirim webhook.</p>${s.webhook_configured ? `<p style="margin-top:9px">Host terdaftar: <strong style="color:#678170">${esc(s.webhook_host)}</strong> · URL lengkap disembunyikan.</p>` : ''}
        <form id="webhookForm" class="inline-form"><div class="field"><label for="webhookUrl">URL webhook ${s.webhook_configured?'baru':''}</label><input id="webhookUrl" name="webhook_url" type="url" placeholder="https://example.com/webhook" required></div><button class="button button-primary" type="submit">Simpan</button></form>
        <div class="drawer-actions"><button class="button button-secondary" data-action="test-webhook" ${s.webhook_configured?'':'disabled'}>${icon('send')} Kirim tes</button>${s.webhook_configured ? `<button class="button button-danger" data-action="clear-webhook">${icon('trash')} Hapus webhook</button>` : ''}</div><div id="webhookError" class="form-error"></div></section>
    </div>
    <section class="card delivery-card"><div class="card-heading"><div><h2>Riwayat pengiriman</h2><p>Hasil percobaan pengiriman webhook terbaru</p></div></div><div class="table-wrap"><table class="full-table"><thead><tr><th>Peristiwa</th><th>Waktu</th><th>Status</th><th>Respons / Keterangan</th></tr></thead><tbody>${deliveries.length ? deliveries.map(d=>`<tr><td><strong style="color:#52685a">${esc(eventName(d.event_type))}</strong></td><td>${esc(dateTime(d.created_at,true))}</td><td><span class="status ${d.success?'resolved':'open'}">${d.success?'Terkirim':'Gagal'}</span></td><td>${esc(d.error_message || (d.status_code ? `HTTP ${d.status_code}` : '—'))}</td></tr>`).join('') : `<tr><td colspan="4">${emptyState('Belum ada pengiriman', 'Riwayat akan muncul setelah webhook dikonfigurasi dan peristiwa dikirim.')}</td></tr>`}</tbody></table></div></section>
    <div class="page-note" style="margin-top:16px">${icon('shield')}<span>Webhook dikirim sekali untuk setiap transisi. Pengiriman yang gagal dicatat tetapi <strong>tidak diulang otomatis</strong>. Jangan gunakan URL yang mengandung rahasia jika aplikasi dapat diakses oleh pihak yang tidak tepercaya.</span></div>`;
}
function renderSettings() {
  const s = state.settings;
  return `${pageTitle('Pengaturan', 'Sesuaikan target layanan dan kelola workspace Opis Anda.', '', 'PREFERENSI')}
    <div class="config-grid">
      <section class="card config-card"><div class="config-title-wrap"><span class="config-icon">${icon('shield')}</span><div><h2>Target SLA</h2><p>Target untuk perbandingan di dashboard dan laporan</p></div></div><div class="config-divider"></div><p>Target ini tidak memengaruhi pemeriksaan atau memicu notifikasi. Ketersediaan dihitung berdasarkan pemeriksaan berhasil.</p><form id="settingsForm" class="inline-form"><div class="field"><label for="slaTarget">Target ketersediaan (%)</label><input id="slaTarget" type="number" name="sla_target" min="0" max="100" step="0.001" value="${s.sla_target}" required></div><button class="button button-primary" type="submit">Simpan target</button></form><div id="settingsError" class="form-error"></div></section>
      <section class="card config-card"><div class="config-title-wrap"><span class="config-icon">${icon('activity')}</span><div><h2>Mesin pemantauan</h2><p>Konfigurasi lingkungan server</p></div></div><div class="config-divider"></div><div class="config-list"><div class="config-list-row"><span>Scheduler</span><strong>${s.scheduler_enabled?'Aktif':'Nonaktif'}</strong></div><div class="config-list-row"><span>Alamat privat / lokal</span><strong>${s.allow_private_targets?'Diizinkan':'Diblokir'}</strong></div><div class="config-list-row"><span>Pemeriksaan demo</span><strong>Simulasi, tanpa jaringan</strong></div></div><div class="config-divider"></div><p>Ubah konfigurasi melalui variabel lingkungan. Alamat privat hanya boleh diaktifkan di jaringan tepercaya.</p></section>
      <section class="card config-card danger-zone"><div class="config-title-wrap"><span class="config-icon">${icon('trash')}</span><div><h2>Data demo</h2><p>Kelola data simulasi bawaan</p></div></div><div class="config-divider"></div><p>Terdapat <strong>${number(s.demo_count_all)}</strong> endpoint demo, termasuk yang telah diarsipkan. Hapus data demo untuk menghilangkan endpoint, pemeriksaan, dan insiden simulasinya. Data nyata tidak terpengaruh.</p><div class="drawer-actions"><button class="button button-danger" data-action="remove-demo" ${s.demo_count_all?'':'disabled'}>${icon('trash')} Hapus data demo</button></div></section>
      <section class="card config-card"><div class="config-title-wrap"><span class="config-icon">${icon('info')}</span><div><h2>Tentang workspace</h2><p>Opis · API Health Monitor & Incident Reporter</p></div></div><div class="config-divider"></div><p>Opis mencatat status, waktu respons, insiden, dan hasil pengiriman webhook. Untuk keamanan, gunakan aplikasi ini di jaringan tepercaya; versi ini belum menyediakan autentikasi pengguna.</p><div class="drawer-actions"><a class="button button-secondary" href="/docs" target="_blank" rel="noreferrer">${icon('file')} Dokumentasi API ${icon('arrow-up-right')}</a></div></section>
    </div>`;
}

function openModal(content, drawer = false) {
  $('#modalRoot').innerHTML = `<div class="modal-overlay ${drawer?'drawer-overlay':''}" data-action="overlay"><section class="modal ${drawer?'drawer':''}" role="dialog" aria-modal="true">${content}</section></div>`;
  document.body.style.overflow = 'hidden';
  setTimeout(() => $('#modalRoot input, #modalRoot textarea, #modalRoot button')?.focus(), 30);
}
function closeModal() { $('#modalRoot').innerHTML = ''; document.body.style.overflow = ''; }
function endpointById(id) { return state.dashboard?.endpoints.find(endpoint => endpoint.id === Number(id)); }
function field(label, name, value, options = {}) {
  const full = options.full ? ' full' : '';
  const attrs = `${options.type ? `type="${options.type}"` : 'type="text"'} ${options.min != null ? `min="${options.min}"` : ''} ${options.max != null ? `max="${options.max}"` : ''} ${options.step != null ? `step="${options.step}"` : ''} ${options.required === false ? '' : 'required'} ${options.maxlength ? `maxlength="${options.maxlength}"` : ''}`;
  return `<div class="field${full}"><label for="f-${name}">${esc(label)}</label><input id="f-${name}" name="${name}" ${attrs} value="${esc(value ?? '')}" placeholder="${esc(options.placeholder || '')}">${options.help ? `<small>${esc(options.help)}</small>` : ''}</div>`;
}
function endpointForm(ep = null) {
  const edit = !!ep;
  const method = ep?.method || 'GET';
  openModal(`<div class="modal-head"><div><h2>${edit?'Ubah endpoint':'Tambah endpoint'}</h2><p>${edit?'Perbarui konfigurasi pemeriksaan endpoint ini.':'Mulai pantau kesehatan endpoint API Anda.'}</p></div><button class="icon-button" data-action="close-modal" aria-label="Tutup">${icon('x')}</button></div>
    <form id="endpointForm" data-id="${ep?.id || ''}"><div class="modal-body"><div class="form-grid">
      ${field('Nama endpoint','name',ep?.name,{full:true,maxlength:80,placeholder:'Contoh: Payment API'})}
      ${field('URL endpoint','url',ep?.url,{full:true,type:'url',placeholder:'https://api.example.com/health',help:'HTTP atau HTTPS; jangan masukkan kredensial di URL.'})}
      <div class="field"><label for="f-method">Metode</label><select id="f-method" name="method"><option value="GET" ${method==='GET'?'selected':''}>GET</option><option value="HEAD" ${method==='HEAD'?'selected':''}>HEAD</option></select></div>
      ${field('Status HTTP yang diharapkan','expected_status',ep?.expected_status ?? 200,{type:'number',min:100,max:599})}
      ${field('Interval pemeriksaan (detik)','interval_seconds',ep?.interval_seconds ?? 60,{type:'number',min:30,max:86400,help:'Minimal 30 detik.'})}
      ${field('Batas waktu (detik)','timeout_seconds',ep?.timeout_seconds ?? 10,{type:'number',min:1,max:30})}
      ${field('Ambang gagal berturut-turut','failure_threshold',ep?.failure_threshold ?? 2,{type:'number',min:1,max:10,help:'Insiden dibuka setelah ambang tercapai.'})}
      ${field('Ambang pulih berturut-turut','recovery_threshold',ep?.recovery_threshold ?? 1,{type:'number',min:1,max:10,help:'Insiden pulih setelah ambang tercapai.'})}
    </div><div class="form-hint">${icon('info')}<span>${edit?'Perubahan URL, metode, status yang diharapkan, atau timeout akan menutup insiden aktif sebagai perubahan konfigurasi, bukan sebagai pemulihan.':'Alamat lokal atau privat diblokir secara default. Pemeriksaan awal dijadwalkan segera setelah endpoint ditambahkan.'}</span></div><div id="endpointError" class="form-error" role="alert"></div></div><div class="modal-footer"><button type="button" class="button button-secondary" data-action="close-modal">Batal</button><button type="submit" class="button button-primary">${edit?'Simpan perubahan':'Tambah endpoint'}</button></div></form>`);
}
async function endpointDetail(id) {
  const ep = endpointById(id);
  if (!ep) { toast('Endpoint tidak ditemukan.', true); return; }
  try {
    const checks = await api(`/api/endpoints/${id}/checks?limit=25`);
    openModal(`<div class="modal-head"><div><h2>Detail endpoint</h2><p>Status terbaru dan riwayat pemeriksaan</p></div><button class="icon-button" data-action="close-modal" aria-label="Tutup">${icon('x')}</button></div><div class="modal-body">
      <div class="drawer-section"><div class="detail-title"><h3>${esc(ep.name)}</h3>${demoBadge(ep.is_demo)} ${statusBadge(ep.status)}</div><p>${esc(safeURL(ep.url))} · ${esc(ep.method)} · HTTP ${ep.expected_status}</p><div class="detail-grid"><div class="detail-tile"><span>Pemeriksaan terakhir</span><strong>${esc(dateTime(ep.last_checked_at))}</strong></div><div class="detail-tile"><span>Waktu respons terakhir</span><strong>${ms(ep.last_response_ms)}</strong></div><div class="detail-tile"><span>Uptime · ${periodShort[state.period]}</span><strong>${pct(ep.uptime_percent)}</strong></div></div>
      <div class="drawer-actions">${ep.is_demo ? '<span class="mini-badge amber">Data simulasi · tidak diperiksa langsung</span>' : `<button class="button button-primary" data-action="check-endpoint" data-id="${ep.id}" ${ep.enabled?'':'disabled'}>${icon('refresh')} Periksa sekarang</button><button class="button button-secondary" data-action="edit-endpoint" data-id="${ep.id}">${icon('edit')} Ubah</button><button class="button button-secondary" data-action="toggle-endpoint" data-id="${ep.id}">${icon(ep.enabled?'pause':'play')} ${ep.enabled?'Jeda':'Lanjutkan'}</button>`}</div></div>
      <div class="drawer-section"><h3>Konfigurasi pemeriksaan</h3><div class="config-list"><div class="config-list-row"><span>Interval</span><strong>${esc(intervalText(ep.interval_seconds))}</strong></div><div class="config-list-row"><span>Batas waktu</span><strong>${ep.timeout_seconds} detik</strong></div><div class="config-list-row"><span>Ambang insiden / pulih</span><strong>${ep.failure_threshold} gagal / ${ep.recovery_threshold} berhasil</strong></div><div class="config-list-row"><span>Status HTTP terakhir</span><strong>${ep.last_status_code || '—'}</strong></div></div></div>
      <div class="drawer-section"><h3>Pemeriksaan terbaru</h3>${checks.length ? `<div class="evidence-list">${checks.map(c=>`<div class="evidence-row"><i class="evidence-dot ${c.is_up?'up':''}"></i><time>${esc(dateTime(c.checked_at, true))}</time><span>${c.status_code ? `HTTP ${c.status_code}` : esc(c.error_type || '—')}</span><strong>${ms(c.response_ms)}</strong></div>`).join('')}</div>` : `<p>Belum ada pemeriksaan yang dicatat.</p>`}</div>
      ${ep.incident_id ? `<div class="drawer-actions"><button class="button button-light" data-action="incident-detail" data-id="${ep.incident_id}">${icon('incident')} Lihat insiden aktif</button></div>` : ''}
    </div>`, true);
  } catch (error) { toast(error.message, true); }
}
async function incidentDetail(id) {
  try {
    const inc = await api(`/api/incidents/${id}`);
    const endedLabel = inc.status === 'open' ? 'Masih berlangsung' : inc.end_reason === 'archived' ? 'Ditutup: diarsipkan' : inc.end_reason === 'config_changed' ? 'Ditutup: konfigurasi berubah' : dateTime(inc.ended_at, true);
    openModal(`<div class="modal-head"><div><h2>Detail insiden <span style="color:#a6b4aa">#${String(inc.id).padStart(4,'0')}</span></h2><p>Ringkasan dan bukti untuk analisis lebih lanjut</p></div><button class="icon-button" data-action="close-modal" aria-label="Tutup">${icon('x')}</button></div><div class="modal-body">
      <div class="drawer-section"><div class="detail-title"><h3>${esc(inc.endpoint_name)}</h3>${demoBadge(inc.is_demo)} ${statusBadge(inc.status)}</div><p>${esc(inc.method)} ${esc(safeURL(inc.endpoint_url))} · Status diharapkan HTTP ${inc.expected_status}</p><div class="detail-grid"><div class="detail-tile"><span>Gagal pertama</span><strong>${esc(dateTime(inc.started_at, true))}</strong></div><div class="detail-tile"><span>Insiden terdeteksi</span><strong>${esc(dateTime(inc.detected_at, true))}</strong></div><div class="detail-tile"><span>Berakhir</span><strong>${esc(endedLabel)}</strong></div></div><p style="margin-top:10px">Durasi insiden: <strong style="color:#60776a">${esc(duration(inc.duration_seconds))}</strong> · ${number(inc.failure_count)} pemeriksaan gagal</p></div>
      <div class="drawer-section"><h3>Ringkasan insiden</h3><p>${esc(inc.summary)}</p><div class="investigation"><strong>Yang perlu diverifikasi</strong><p>${esc(inc.investigation)}</p><p style="margin-top:5px">Ini adalah petunjuk investigasi, bukan penyebab yang terkonfirmasi.</p></div></div>
      <div class="drawer-section"><h3>Bukti pemeriksaan</h3>${inc.checks.length ? `<div class="evidence-list">${inc.checks.map(c=>`<div class="evidence-row"><i class="evidence-dot ${c.is_up?'up':''}"></i><time>${esc(dateTime(c.checked_at, true))}</time><span>${c.status_code ? `HTTP ${c.status_code}` : esc(c.error_type || '—')}</span><strong>${ms(c.response_ms)}</strong></div>`).join('')}</div><p style="margin-top:8px">Menampilkan hingga 100 pemeriksaan selama insiden.</p>` : '<p>Tidak ada bukti pemeriksaan dalam rentang insiden.</p>'}</div>
      <div class="drawer-section"><h3>Catatan investigasi</h3><p style="margin-bottom:10px">Simpan temuan, tindakan, atau penyebab yang telah dikonfirmasi.</p><form id="notesForm" data-id="${inc.id}"><div class="field"><textarea name="notes" maxlength="5000" placeholder="Tambahkan catatan investigasi...">${esc(inc.notes)}</textarea></div><div class="drawer-actions"><button class="button button-primary" type="submit">Simpan catatan</button></div><div class="form-error" id="notesError"></div></form></div>
    </div>`, true);
  } catch (error) { toast(error.message, true); }
}
function confirmation(title, text, action, id = '') {
  openModal(`<div class="modal-head"><div><h2>${esc(title)}</h2><p>Konfirmasi tindakan</p></div><button class="icon-button" data-action="close-modal" aria-label="Tutup">${icon('x')}</button></div><div class="modal-body"><p style="color:#819389;font-size:12px;line-height:1.7;margin:0">${esc(text)}</p></div><div class="modal-footer"><button class="button button-secondary" data-action="close-modal">Batal</button><button class="button button-danger" data-action="${action}" ${id ? `data-id="${id}"` : ''}>${icon('trash')} Ya, lanjutkan</button></div>`);
}
function showFormError(id, message) { const element = $(`#${id}`); if (element) { element.textContent = message; element.classList.add('show'); } }
async function withButton(button, operation) {
  const old = button?.innerHTML;
  if (button) { button.disabled = true; button.innerHTML = `<span class="spinner" style="width:13px;height:13px"></span> Memproses`; }
  try { await operation(); }
  finally { if (button && button.isConnected) { button.disabled = false; button.innerHTML = old; } }
}

document.addEventListener('click', async event => {
  const target = event.target.closest('[data-action], [data-page]');
  if (!target || target.disabled) return;
  if (target.dataset.page) { navigate(target.dataset.page); return; }
  const action = target.dataset.action, id = Number(target.dataset.id || 0);
  try {
    switch (action) {
      case 'overlay': if (event.target === target) closeModal(); break;
      case 'close-modal': closeModal(); break;
      case 'add-endpoint': endpointForm(); break;
      case 'edit-endpoint': { const ep = endpointById(id); if (ep && !ep.is_demo) endpointForm(ep); else toast('Endpoint demo tidak dapat diubah.',true); break; }
      case 'endpoint-detail': await endpointDetail(id); break;
      case 'incident-detail': await incidentDetail(id); break;
      case 'endpoint-filter': state.endpointFilter = target.dataset.value; render(); break;
      case 'incident-filter': state.incidentFilter = target.dataset.value; render(); break;
      case 'refresh': await withButton(target, async()=>{ await loadData(); toast('Data berhasil diperbarui.'); }); break;
      case 'check-endpoint': {
        const ep = endpointById(id); if (!ep || ep.is_demo) { toast('Endpoint demo hanya berupa simulasi.', true); break; }
        await withButton(target, async()=>{
          const result = await api(`/api/endpoints/${id}/check`, {method:'POST'});
          closeModal();
          toast(result.is_up ? 'Pemeriksaan berhasil. Endpoint merespons sesuai harapan.' : `Pemeriksaan gagal: ${result.error_message || 'endpoint tidak tersedia'}.`, !result.is_up);
          await loadData();
        }); break;
      }
      case 'toggle-endpoint': {
        const ep = endpointById(id); if (!ep) break;
        await withButton(target, async()=>{ await api(`/api/endpoints/${id}/enabled`, {method:'PATCH',body:JSON.stringify({enabled:!ep.enabled})}); closeModal(); await loadData(); toast(ep.enabled ? 'Pemantauan dijeda. Insiden aktif tetap terbuka.' : 'Pemantauan dilanjutkan.'); }); break;
      }
      case 'archive-endpoint': {
        const ep = endpointById(id); if (ep) confirmation('Arsipkan endpoint?', `Pemantauan ${ep.name} akan dihentikan. Riwayat pemeriksaan dan insiden tetap tersedia. Insiden aktif ditutup sebagai arsip, bukan dinyatakan pulih.`, 'confirm-archive', id); break;
      }
      case 'confirm-archive': await withButton(target, async()=>{ await api(`/api/endpoints/${id}`, {method:'DELETE'}); closeModal(); await loadData(); toast('Endpoint diarsipkan; riwayat tetap tersimpan.'); }); break;
      case 'remove-demo': confirmation('Hapus seluruh data demo?', 'Semua endpoint, pemeriksaan, insiden, dan pengiriman demo akan dihapus permanen. Data nyata tidak terpengaruh.', 'confirm-remove-demo'); break;
      case 'confirm-remove-demo': await withButton(target, async()=>{ const result=await api('/api/demo',{method:'DELETE'}); closeModal(); await loadData(); toast(`${result.removed_endpoints} endpoint demo telah dihapus.`); }); break;
      case 'test-webhook': await withButton(target, async()=>{ const result=await api('/api/alerts/test',{method:'POST'}); await loadData(); toast(result.success ? `Webhook berhasil dikirim (HTTP ${result.status_code}).` : `Webhook gagal: ${result.error_message || 'tidak ada respons'}.`, !result.success); }); break;
      case 'clear-webhook': confirmation('Hapus webhook?', 'Notifikasi di dalam aplikasi tetap tersedia. Pengiriman webhook akan dihentikan hingga URL baru dikonfigurasi.', 'confirm-clear-webhook'); break;
      case 'confirm-clear-webhook': await withButton(target, async()=>{ await api('/api/alerts/config',{method:'PUT',body:JSON.stringify({webhook_url:null})}); closeModal(); await loadData(); toast('Webhook dihapus.'); }); break;
    }
  } catch (error) { toast(error.message, true); }
});

document.addEventListener('change', event => {
  const target = event.target.closest('[data-change]');
  if (!target) return;
  if (target.dataset.change === 'period' && periods[target.value]) { state.period = target.value; loadData(); }
  if (target.dataset.change === 'report-period' && periods[target.value]) { state.reportPeriod = target.value; loadData(); }
});
document.addEventListener('input', event => {
  if (event.target.id === 'endpointSearch') {
    state.search = event.target.value;
    const rows = $('#endpointRows'); if (rows) rows.innerHTML = endpointTableRows();
  }
});
document.addEventListener('submit', async event => {
  const form = event.target;
  if (!['endpointForm','settingsForm','webhookForm','notesForm'].includes(form.id)) return;
  event.preventDefault();
  const button = form.querySelector('[type=submit]');
  try {
    await withButton(button, async()=>{
      const data = Object.fromEntries(new FormData(form).entries());
      if (form.id === 'endpointForm') {
        ['expected_status','interval_seconds','timeout_seconds','failure_threshold','recovery_threshold'].forEach(key => {data[key] = Number(data[key]);});
        const id = Number(form.dataset.id || 0);
        await api(id ? `/api/endpoints/${id}` : '/api/endpoints', {method:id?'PATCH':'POST',body:JSON.stringify(data)});
        closeModal(); await loadData();
        toast(id ? 'Konfigurasi endpoint disimpan.' : (state.settings.scheduler_enabled ? 'Endpoint ditambahkan. Pemeriksaan akan segera dimulai.' : 'Endpoint ditambahkan. Scheduler nonaktif; gunakan Periksa sekarang.'));
        if (state.settings.scheduler_enabled) setTimeout(()=> { if (!$('#modalRoot').innerHTML) loadData({quiet:true}); }, 3500);
      } else if (form.id === 'settingsForm') {
        await api('/api/settings',{method:'PUT',body:JSON.stringify({sla_target:Number(data.sla_target)})});
        await loadData(); toast('Target SLA berhasil disimpan.');
      } else if (form.id === 'webhookForm') {
        await api('/api/alerts/config',{method:'PUT',body:JSON.stringify({webhook_url:data.webhook_url})});
        await loadData(); toast('Webhook berhasil disimpan.');
      } else if (form.id === 'notesForm') {
        await api(`/api/incidents/${form.dataset.id}`,{method:'PATCH',body:JSON.stringify({notes:data.notes})});
        toast('Catatan investigasi disimpan.');
      }
    });
  } catch(error) {
    const errorId = {endpointForm:'endpointError',settingsForm:'settingsError',webhookForm:'webhookError',notesForm:'notesError'}[form.id];
    showFormError(errorId, error.message);
  }
});
$('#notificationButton').addEventListener('click', () => { state.incidentFilter = 'open'; navigate('incidents'); });
$('#mobileMenu').addEventListener('click', () => { $('#sidebar').classList.add('open'); $('#sidebarScrim').classList.add('show'); });
$('#sidebarScrim').addEventListener('click', () => { $('#sidebar').classList.remove('open'); $('#sidebarScrim').classList.remove('show'); });
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') { closeModal(); $('#sidebar').classList.remove('open'); $('#sidebarScrim').classList.remove('show'); }
});
window.addEventListener('hashchange', () => {
  const page = location.hash.slice(1);
  state.page = pages[page] ? page : 'overview';
  closeModal(); window.scrollTo(0,0); loadData();
});
state.page = pages[location.hash.slice(1)] ? location.hash.slice(1) : 'overview';
loadData();
setInterval(() => {
  if (document.visibilityState === 'visible' && !$('#modalRoot').innerHTML && !['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName)) loadData({quiet:true});
}, 30000);
