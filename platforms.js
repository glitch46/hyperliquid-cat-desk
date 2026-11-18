'use strict';

const byId = (id) => document.getElementById(id);
const view = { data: null, history: [], platform: new URLSearchParams(location.search).get('platform') || 'all',
  coin: new URLSearchParams(location.search).get('pair') || 'xyz:NVDA', cohort: 8,
  positions: 10, investors: 10, expanded: new Set() };
const names = { hyperliquid: 'Hyperliquid / XYZ', etoro: 'eToro', robinhood: 'Robinhood', schwab: 'Schwab', ibkr: 'IBKR' };
const pnlNames = { 8: 'Money Printer', 9: 'Smart Money', 10: 'Consistent Grinder', 11: 'Humble Earner', 12: 'Exit Liquidity', 13: 'Semi-Rekt', 14: 'Full Rekt', 15: 'Giga-Rekt' };
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const known = (n) => n != null && Number.isFinite(Number(n));
const count = (n) => known(n) ? Number(n).toLocaleString('en-US') : '—';
const pct = (n, digits = 1) => known(n) ? `${(Number(n) * 100).toFixed(digits)}%` : '—';
const points = (n) => known(n) ? `${Number(n).toFixed(2)}%` : '—';
const signedPct = (n) => known(n) ? `${n > 0 ? '+' : ''}${pct(n)}` : '—';
const tone = (n) => !known(n) || n === 0 ? '' : n > 0 ? 'positive' : 'negative';
const dollars = (value) => {
  if (!known(value)) return '—';
  const n = Number(value), a = Math.abs(n), suffix = a >= 1e9 ? 'B' : a >= 1e6 ? 'M' : a >= 1e3 ? 'K' : '';
  return `${n < 0 ? '−' : ''}$${(a / ({ B: 1e9, M: 1e6, K: 1e3 }[suffix] || 1)).toLocaleString('en-US', { maximumFractionDigits: 2 })}${suffix}`;
};
const signedDollars = (n) => known(n) ? `${n > 0 ? '+' : ''}${dollars(n)}` : '—';
const price = (n) => known(n) ? Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: Math.abs(n) < 1 ? 6 : 2 }) : '—';
const when = (s) => s && Number.isFinite(Date.parse(s)) ? new Date(s).toLocaleString('en-GB', { timeZone: 'UTC', day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }) + ' UTC' : 'Not available';
const age = (s) => s && Number.isFinite(Date.parse(s)) ? (Date.now() - Date.parse(s)) / 36e5 : Infinity;
const sum = (rows, key) => rows.reduce((s, row) => s + (Number(row[key]) || 0), 0);
const symbol = (coin) => coin.split(':').at(-1);
const empty = (cols, text) => `<tr><td class="empty-cell" colspan="${cols}">${esc(text)}</td></tr>`;
const src = (key) => view.data.platforms[key];
const pair = (key, coin = view.coin) => src(key)?.pairs?.[coin];
const chosen = () => view.platform === 'all' ? [...document.querySelectorAll('#compare-sources input:checked')].map((node) => node.value) : [view.platform];
const includes = (key) => chosen().includes(key);
const refTag = (row) => row?.mapping?.kind === 'reference' ? '<span class="reference-tag">REFERENCE</span>' : '';
const sourceLink = (url) => /^https:\/\//i.test(url || '') ? esc(url) : '#';
const notReported = (text = 'Not reported') => `<span class="muted">${esc(text)}</span>`;

function hasFact(key, coin) {
  const row = pair(key, coin);
  if (key === 'hyperliquid') return Boolean(row?.cohorts?.some((c) => c.id === view.cohort));
  if (key === 'etoro') return known(row?.market?.reportedBuyShare);
  if (key === 'robinhood') return known(row?.rank);
  if (key === 'schwab') return Boolean(row?.direction);
  return false;
}

function renderKpis() {
  const scope = view.data.universe;
  const e = src('etoro');
  const multi = scope.filter((row) => chosen().filter((key) => hasFact(key, row.coin)
    && (key !== 'etoro' || pair(key, row.coin)?.mapping?.kind === 'same_underlying')).length >= 2).length;
  const cards = [
    ['XYZ COMPARISON UNIVERSE', count(scope.length), 'Highest-volume twenty pairs in source snapshot'],
    ['ETORO INSTRUMENT MATCHES', `${count(e?.matchedPairs || 0)} / ${scope.length}`, 'Reference contracts are labeled separately'],
    ['PUBLIC ETORO PORTFOLIOS CHECKED', count(e?.sample?.checked), `${count(e?.sample?.holdingTrackedPairs)} hold a tracked direct position`],
    ['MULTI-SOURCE UNDERLYING COVERAGE', `${multi} / ${scope.length}`, 'At least two selected sources have a reported fact'],
  ];
  byId('platform-kpis').innerHTML = cards.map(([label, value, note]) => `<article class="kpi"><p class="kpi-label">${label}</p><p class="kpi-value">${value}</p><p class="kpi-sub">${note}</p></article>`).join('');
}

function cell(key, coin) {
  const row = pair(key, coin);
  if (key === 'hyperliquid') {
    const c = row?.cohorts?.find((c) => c.id === view.cohort);
    if (!c) return notReported();
    return `<span class="metric-cell">${pct(c.longShare)} long<span class="subvalue ${tone(c.net)}">${signedDollars(c.net)} net notional</span><span class="subvalue">${dollars(c.gross)} gross · ${count(c.positions)} positions</span></span>`;
  }
  if (key === 'etoro') {
    if (!row?.mapping?.matched) return notReported('No validated match');
    return `<span class="metric-cell">${known(row.market?.reportedBuyShare) ? pct(row.market.reportedBuyShare) + ' buy' : 'Holdings split unavailable'}${refTag(row)}<span class="subvalue">${esc(row.market?.symbol)} · reported holdings split</span></span>`;
  }
  if (key === 'robinhood') return row ? `<span class="metric-cell">#${count(row.rank)}<span class="subvalue">Published Investor Index top ten</span></span>` : notReported('Not in published top ten');
  if (key === 'schwab') return row ? `<span class="metric-cell ${row.direction === 'net_buy' ? 'positive' : 'negative'}">${row.direction === 'net_buy' ? 'Net buy' : 'Net sell'} #${count(row.rank)}<span class="subvalue">Monthly STAX list</span></span>` : notReported('Not in published lists');
  return notReported('Not connected');
}

function renderComparison() {
  const keys = chosen();
  document.body.classList.toggle('single-platform', keys.length === 1);
  byId('compare-sources').hidden = view.platform !== 'all';
  byId('comparison-head').innerHTML = `<tr><th scope="col">XYZ pair</th>${keys.map((key) => `<th scope="col">${esc(names[key])}${key === 'hyperliquid' ? `<span class="subvalue">${esc(pnlNames[view.cohort])}</span>` : ''}</th>`).join('')}<th scope="col">Direct source facts</th></tr>`;
  byId('comparison-rows').innerHTML = view.data.universe.map((row) => {
    const facts = keys.filter((key) => hasFact(key, row.coin) && (key !== 'etoro' || pair(key, row.coin)?.mapping?.kind === 'same_underlying')).length;
    return `<tr class="${row.coin === view.coin ? 'pair-selected' : ''}"><td><button type="button" class="pair-select-button" data-coin="${esc(row.coin)}" aria-pressed="${row.coin === view.coin}">${esc(row.symbol)}</button><span class="subvalue">#${row.volumeRank} XYZ volume</span></td>${keys.map((key) => `<td>${cell(key, row.coin)}</td>`).join('')}<td class="coverage-badge">${facts} / ${keys.length}</td></tr>`;
  }).join('');
  byId('comparison-coverage').textContent = `${view.data.universe.length} PAIRS · ${keys.length} SELECTED SOURCES · NO MIXED-UNIT TOTAL`;
  const cards = keys.length ? keys : [];
  byId('platform-cards').innerHTML = cards.map((key) => {
    const source = src(key);
    return `<article class="platform-card"><div class="card-title"><h3>${esc(names[key])}</h3><span class="source-status ${esc(source?.status || 'unavailable')}">${esc((source?.status || 'unavailable').replaceAll('_', ' ').toUpperCase())}</span></div><p>${esc(source?.note || 'No source snapshot available.')}</p><p class="source-time">As of ${when(source?.observedAt)}<br>${esc(source?.period || 'No connected feed')}</p><a href="${sourceLink(source?.sourceUrl)}" target="_blank" rel="noopener noreferrer">Source / methodology ↗</a></article>`;
  }).join('');
}

function renderPair() {
  byId('platform-pair-select').value = view.coin;
  byId('platform-pair-heading').textContent = `${symbol(view.coin)} / platform evidence`;
  byId('pair-facts').innerHTML = chosen().map((key) => `<article class="pair-fact"><p class="eyebrow">${esc(names[key])}</p><strong>${headline(key)}</strong><p>${pairNote(key)}</p><p>As of ${when(src(key)?.observedAt)}</p></article>`).join('');
  const e = src('etoro'), ep = pair('etoro');
  byId('etoro-cohorts').hidden = !includes('etoro');
  byId('etoro-sample-note').textContent = `${count(e?.sample?.checked)} public portfolios checked; ${count(e?.sample?.failed)} failed. ${count(e?.sample?.holdingTrackedPairs)} contain a direct position in the twenty-pair universe. Discovery is bounded; these cohorts are not all eToro customers. ${ep?.mapping?.note || ''}`;
  byId('etoro-cohort-rows').innerHTML = ep?.mapping?.matched && e?.sample?.checked
    ? ep.cohorts.map((c) => `<tr><td>${esc(c.label)}</td><td>${count(c.sampledPortfolios)}</td><td>${count(c.holders)}</td><td><span class="positive">${count(c.longHolders)} L</span> / <span class="negative">${count(c.shortHolders)} S</span></td><td>${allocationSplit(c)}</td><td>${points(c.meanAllocationPct)}</td></tr>`).join('')
    : empty(6, ep?.mapping?.matched ? 'No successful public portfolio sample is available. This does not establish a flat platform.' : 'No validated eToro instrument mapping is available for this pair. Cohort exposure is unknown, not zero.');
  renderPositions(); renderInvestors(); renderHistory();
}

function headline(key) {
  const row = pair(key);
  if (key === 'hyperliquid') return pct(row?.cohorts?.find((c) => c.id === view.cohort)?.longShare) + ' long';
  if (key === 'etoro') return row?.market && known(row.market.reportedBuyShare) ? pct(row.market.reportedBuyShare) + ' buy' : '—';
  if (key === 'robinhood') return row ? `#${row.rank}` : 'Not listed';
  if (key === 'schwab') return row ? row.direction === 'net_buy' ? 'Net buy' : 'Net sell' : 'Not listed';
  return 'Not connected';
}

function pairNote(key) {
  const row = pair(key);
  if (key === 'hyperliquid') return `${esc(pnlNames[view.cohort])} · long notional ÷ gross notional. <a href="xyz.html?pair=${encodeURIComponent(view.coin)}#pair-detail">Full XYZ cohort book ↗</a>`;
  if (key === 'etoro') return `${esc(row?.market?.name || 'Unmapped instrument')} ${refTag(row)}<br>${esc(row?.mapping?.note || 'No mapping returned.')}<br>Source-reported buy/sell holdings split; dollar weighting unspecified.`;
  if (key === 'robinhood') return row ? `Rank ${row.rank} in the published monthly top ten. No per-stock allocation weight is published in this payload.` : 'Not present in the published top ten. Customer ownership is not assumed zero.';
  if (key === 'schwab') return row ? `Rank ${row.rank} in the reported monthly ${row.direction === 'net_buy' ? 'net-buy' : 'net-sell'} list. This is flow, not a current long/short position.` : 'Not present in either monthly top-five list. Direction and position size are unknown.';
  return esc(src(key)?.note || 'No source connected.');
}

function allocationSplit(c) {
  if (!known(c.allocationLongShare)) return notReported(c.sampledPortfolios ? 'No sampled direct exposure' : 'No portfolios in this cohort');
  const long = Math.max(0, Math.min(100, c.allocationLongShare * 100));
  return `<div class="bias-bar" role="img" aria-label="${long.toFixed(1)} percent of sampled allocation points long"><span class="long" style="width:${long}%"></span><span class="short" style="width:${100 - long}%"></span></div><div class="bias-labels"><span>${long.toFixed(1)}% L</span><span>${(100 - long).toFixed(1)}% S</span></div>`;
}

function passesInvestor(trader) {
  const filter = byId('public-cohort-filter').value;
  return filter === 'all' || (filter === 'positive' ? trader.gain >= 0 : filter === 'negative' ? trader.gain < 0 : trader.bucket === filter);
}

function renderPositions() {
  const rows = [];
  if (includes('etoro')) {
    const etoro = src('etoro');
    for (const trader of etoro?.traders || []) {
      if (!passesInvestor(trader)) continue;
      for (const position of trader.positions.filter((p) => p.coin === view.coin)) rows.push({ source: 'etoro', trader, position });
    }
    rows.sort((a, b) => b.position.allocationPct - a.position.allocationPct);
  }
  if (includes('hyperliquid')) {
    for (const position of pair('hyperliquid')?.positions || []) rows.push({ source: 'hyperliquid', position });
  }
  const etoroCount = rows.filter((row) => row.source === 'etoro').length;
  byId('public-position-coverage').textContent = `${symbol(view.coin)} · ${etoroCount} matching eToro direct positions · ${rows.length - etoroCount} Hyperliquid sample positions. Sources are grouped, not ranked against each other by incompatible sizes.`;
  byId('public-position-rows').innerHTML = rows.slice(0, view.positions).map((row) => {
    const p = row.position, isEtoro = row.source === 'etoro', t = row.trader;
    const shortAddress = p.address ? `${p.address.slice(0, 6)}…${p.address.slice(-4)}` : 'Wallet';
    const label = isEtoro ? t.username : p.name || shortAddress;
    const url = isEtoro ? t.profileUrl : `https://app.hyperliquid.xyz/explorer/address/${encodeURIComponent(p.address)}`;
    const perf = isEtoro ? `${p.positionReturnPct > 0 ? '+' : ''}${points(p.positionReturnPct)}` : signedDollars(p.unrealizedPnl);
    return `<tr><td><a href="${sourceLink(url)}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a><span class="position-source">${esc(names[row.source])}</span></td><td><span class="side-tag ${p.side === 'long' ? 'long' : 'short'}">${p.side === 'long' ? 'LONG' : 'SHORT'}</span></td><td>${isEtoro ? points(p.allocationPct) : dollars(p.value)}<span class="subvalue">${isEtoro ? 'Source portfolio allocation' : 'USD gross notional'}</span></td><td>${price(p.entry)}</td><td class="${tone(isEtoro ? p.positionReturnPct : p.unrealizedPnl)}">${perf}<span class="subvalue">${isEtoro ? 'Position return / source %' : 'Unrealized PnL / USD'}</span></td><td>${isEtoro ? `<span class="${tone(t.gain)}">${signedPct(t.gain)} MTD</span>` : esc((p.pnlCohortIds || []).map((id) => pnlNames[id]).join(', ') || 'PnL cohort unreported')}</td></tr>`;
  }).join('') || empty(6, 'No matching public sample positions. This does not establish zero broker or cohort exposure.');
  byId('more-public-positions').hidden = rows.length <= view.positions;
  byId('more-public-positions').textContent = `Show ${Math.min(10, rows.length - view.positions)} more positions ↓`;
}

function renderInvestors() {
  byId('etoro-investors').hidden = !includes('etoro');
  const rows = (src('etoro')?.traders || []).filter((row) => row.positions.length && passesInvestor(row)).sort((a, b) => b.gain - a.gain);
  byId('investor-rows').innerHTML = rows.slice(0, view.investors).map((row) => `<tr><td><a href="${sourceLink(row.profileUrl)}" target="_blank" rel="noopener noreferrer">${esc(row.username)} ↗</a></td><td class="${tone(row.gain)}">${signedPct(row.gain)}</td><td>${points(sum(row.positions, 'allocationPct'))}</td><td>${row.positions.length}</td><td>${count(row.copiers)}</td><td>${count(row.riskScore)} / 10</td></tr>`).join('') || empty(6, 'No sampled public investors match this filter with a direct position in the tracked universe.');
  byId('more-investors').hidden = rows.length <= view.investors;
}

function renderActivity() {
  byId('activity-boards').innerHTML = chosen().map((key) => {
    const source = src(key), leaders = source?.leaders || [];
    const shown = view.expanded.has(key) ? leaders : leaders.slice(0, 10);
    return `<section class="panel activity-board"><div class="panel-heading"><div><p class="eyebrow">${esc(source?.activityLabel || 'NO CONNECTED ACTIVITY SOURCE')}</p><h3>${esc(names[key])}</h3></div><span class="chip">${esc(source?.activityKind?.replaceAll('_', ' ') || 'Not connected')}</span></div><p class="source-caption">As of ${when(source?.observedAt)} · ${esc(source?.period || 'No reporting period')}</p>${leaders.length ? `<div class="table-scroll"><table><thead><tr><th scope="col">Ticker / source rank</th><th scope="col">Reported measure</th><th scope="col">Tracked XYZ overlap</th></tr></thead><tbody>${shown.map((row) => `<tr class="${row.overlaps?.length ? 'overlap-row' : ''}"><td>${esc(row.symbol)}<span class="subvalue">#${row.rank}${row.direction ? row.direction === 'net_buy' ? ' net buys' : ' net sells' : ''}</span></td><td>${key === 'hyperliquid' ? dollars(row.value) : key === 'etoro' ? count(row.value) : '#' + row.rank}<span class="subvalue">${esc(row.unit)}</span></td><td>${(row.overlaps || []).map((coin) => `<button class="overlap-link" type="button" data-overlap="${esc(coin)}">${esc(symbol(coin))} →</button>`).join('') || '<span class="muted">Outside comparison set</span>'}</td></tr>`).join('')}</tbody></table></div>${leaders.length > 10 ? `<button type="button" class="more-button" data-activity="${key}">${view.expanded.has(key) ? 'Show first 10 ↑' : `Show all ${leaders.length} published rows ↓`}</button>` : ''}` : `<p class="activity-unavailable">${esc(source?.note || source?.refreshError || 'No verified activity feed available.')}</p>`}</section>`;
  }).join('') || '<p class="muted">Select at least one platform to compare its facts and activity.</p>';
}

function renderHistory() {
  byId('history-note').textContent = `${view.history.length} daily record${view.history.length === 1 ? '' : 's'}${view.history.length < 2 ? ' · history builds with each collection day' : ''}`;
  const rows = view.history.slice(-14).reverse();
  const keys = chosen();
  const headings = { hyperliquid: 'HL Money Printer / long notional share', etoro: 'eToro / reported buy holdings share', robinhood: 'Robinhood / published rank', schwab: 'Schwab / reported direction', ibkr: 'IBKR / no connected feed' };
  byId('platform-history-head').innerHTML = `<tr><th scope="col">Collection date / UTC</th>${keys.map((key) => `<th scope="col">${headings[key]}</th>`).join('')}</tr>`;
  byId('platform-history-rows').innerHTML = rows.map((day) => {
    const row = day.pairs?.[view.coin];
    if (!row) return `<tr><td>${esc(day.date)}</td><td colspan="${Math.max(1, keys.length)}" class="muted">Not tracked in this day’s twenty-pair universe.</td></tr>`;
    const cells = { hyperliquid: `${pct(row.hyperliquidMoneyPrinterLongShare)}<span class="subvalue">${when(row.hyperliquidObservedAt)}</span>`,
      etoro: `${pct(row.etoroReportedBuyShare)}<span class="subvalue">${when(row.etoroObservedAt)}</span>`,
      robinhood: known(row.robinhoodRank) ? '#' + row.robinhoodRank : 'Not in published top ten',
      schwab: row.schwabDirection ? row.schwabDirection === 'net_buy' ? 'Net buy' : 'Net sell' : 'Not in published lists', ibkr: 'Not connected' };
    return `<tr><td>${esc(day.date)}</td>${keys.map((key) => `<td>${cells[key]}</td>`).join('')}</tr>`;
  }).join('') || empty(keys.length + 1, 'No daily observations have been published yet.');
}

function renderStatus() {
  const warnings = [];
  for (const key of ['hyperliquid', 'etoro', 'robinhood', 'schwab']) {
    const source = src(key);
    if (!source || source.status === 'unavailable') { warnings.push(`${names[key]}: ${source?.refreshError || 'snapshot unavailable'}.`); continue; }
    if (source.status === 'retained') warnings.push(`${names[key]} refresh failed; the original observation is retained.`);
    if (age(source.observedAt) > (['robinhood', 'schwab'].includes(key) ? 45 * 24 : 72)) warnings.push(`${names[key]} observations are stale (${when(source.observedAt)}).`);
  }
  byId('platform-notice').hidden = !warnings.length;
  byId('platform-notice').textContent = warnings.join(' ');
  byId('platform-freshness').innerHTML = `<span class="status-dot" aria-hidden="true"></span>PLATFORM COLLECTION · ${when(view.data.generatedAt)}`;
  byId('platform-build-time').textContent = `Snapshot ${when(view.data.generatedAt)}`;
}

function render() {
  renderKpis(); renderComparison(); renderPair(); renderActivity(); renderStatus();
}

function selectCoin(coin) {
  if (!view.data.universe.some((row) => row.coin === coin)) return;
  view.coin = coin; view.positions = 10;
  renderComparison(); renderPair();
}

async function loadPlatforms() {
  byId('platform-reload').disabled = true;
  try {
    const response = await fetch(`data/platforms.json?t=${Date.now()}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`Snapshot HTTP ${response.status}`);
    const data = await response.json();
    if (data.schemaVersion !== 1 || !data.universe?.length || !data.platforms) throw new Error('Unrecognized platform snapshot');
    view.data = data;
    if (!view.data.universe.some((row) => row.coin === view.coin)) view.coin = data.universe[0].coin;
    if (!Object.hasOwn(names, view.platform)) view.platform = 'all';
    byId('platform-view').value = view.platform;
    byId('platform-pair-select').innerHTML = data.universe.map((row) => `<option value="${esc(row.coin)}">${esc(row.symbol)} · #${row.volumeRank} XYZ volume</option>`).join('');
    byId('hl-cohort').innerHTML = Object.entries(pnlNames).map(([id, name]) => `<option value="${id}">${esc(name)}</option>`).join('');
    byId('hl-cohort').value = String(view.cohort);
    try {
      const history = await fetch(`data/platforms_history.json?t=${Date.now()}`, { cache: 'no-store' });
      if (history.ok) view.history = (await history.json()).days || [];
    } catch { view.history = []; }
    render();
  } catch (error) {
    byId('platform-notice').hidden = false;
    byId('platform-notice').textContent = `Could not load platform data: ${error.message}. Use Reload snapshot to retry.`;
    if (!view.data) byId('platform-freshness').textContent = 'PLATFORM SNAPSHOT UNAVAILABLE';
  } finally { byId('platform-reload').disabled = false; }
}

byId('platform-view').addEventListener('change', () => { if (view.data) { view.platform = byId('platform-view').value; view.positions = 10; render(); } });
byId('compare-sources').addEventListener('change', () => { if (view.data) render(); });
byId('hl-cohort').addEventListener('change', () => { if (view.data) { view.cohort = Number(byId('hl-cohort').value); renderComparison(); renderPair(); } });
byId('platform-pair-select').addEventListener('change', () => { if (view.data) selectCoin(byId('platform-pair-select').value); });
byId('public-cohort-filter').addEventListener('change', () => { if (view.data) { view.positions = 10; view.investors = 10; renderPositions(); renderInvestors(); } });
byId('more-public-positions').addEventListener('click', () => { view.positions += 10; renderPositions(); });
byId('more-investors').addEventListener('click', () => { view.investors += 10; renderInvestors(); });
byId('platform-reload').addEventListener('click', loadPlatforms);
document.addEventListener('click', (event) => {
  if (!view.data) return;
  const ticker = event.target.closest('[data-coin]');
  const overlap = event.target.closest('[data-overlap]');
  const activity = event.target.closest('[data-activity]');
  if (ticker) selectCoin(ticker.dataset.coin);
  if (overlap) { selectCoin(overlap.dataset.overlap); byId('platform-pair').scrollIntoView({ behavior: 'smooth' }); }
  if (activity) { const key = activity.dataset.activity; if (view.expanded.has(key)) view.expanded.delete(key); else view.expanded.add(key); renderActivity(); }
});
loadPlatforms();
