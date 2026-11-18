'use strict';

const el = (id) => document.getElementById(id);
const desk = { data: null, limit: '10', pair: new URLSearchParams(location.search).get('pair') || 'xyz:NVDA', cohort: 8, tradeLimit: 10, tradfiGroup: 'all', tradfiLimit: 40 };
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const known = (value) => value != null && Number.isFinite(Number(value));
const usd = (value) => {
  if (!known(value)) return '—';
  const n = Number(value), a = Math.abs(n);
  const unit = a >= 1e9 ? 'B' : a >= 1e6 ? 'M' : a >= 1e3 ? 'K' : '';
  const scale = { B: 1e9, M: 1e6, K: 1e3 }[unit] || 1;
  return `${n < 0 ? '−' : ''}$${(a / scale).toLocaleString('en-US', { minimumFractionDigits: unit ? 2 : 0, maximumFractionDigits: 2 })}${unit}`;
};
const signed = (n) => known(n) ? `${n > 0 ? '+' : ''}${usd(n)}` : '—';
const pct = (n, digits = 1) => known(n) ? `${(n * 100).toFixed(digits)}%` : '—';
const num = (n) => known(n) ? Number(n).toLocaleString('en-US') : '—';
const price = (n) => known(n) ? Number(n).toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: Math.abs(n) < 1 ? 6 : 2 }) : '—';
const tone = (n) => !known(n) || Number(n) === 0 ? '' : n > 0 ? 'positive' : 'negative';
const symbol = (coin) => coin.startsWith('xyz:') ? coin.slice(4) : coin;
const date = (s) => s && Number.isFinite(Date.parse(s)) ? new Date(s).toLocaleString('en-GB', { timeZone: 'UTC', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false }) + ' UTC' : 'Unavailable';
const stale = (s) => !s || !Number.isFinite(Date.parse(s)) || Date.now() - Date.parse(s) > 6 * 36e5;
const total = (rows, key) => rows.reduce((sum, row) => sum + (Number(row[key]) || 0), 0);
const cohorts = () => desk.data.cohorts.items.filter((row) => row.category === 'pnl').sort((a, b) => a.id - b.id);
const markets = () => desk.data.xyz.items.slice().sort((a, b) => a.volumeRank - b.volumeRank);
const shown = () => markets().slice(0, desk.limit === 'all' ? undefined : Number(desk.limit));
const current = () => markets().find((row) => row.coin === desk.pair);
const cohortName = (id) => cohorts().find((row) => row.id === id)?.name || 'Unclassified';
const noRows = (columns, text) => `<tr><td colspan="${columns}" class="empty-cell">${esc(text)}</td></tr>`;
const GROUPS = [['all', 'All TradFi'], ['indices', 'Indices'], ['commodities', 'Commodities & energy'],
                ['fx', 'FX & rates'], ['etfs', 'ETFs & funds'], ['equities', 'Single-name equities']];
const GROUP_LABEL = Object.fromEntries(GROUPS);

function pnlRange(criteria) {
  const lo = criteria.minPnl, hi = criteria.maxPnl;
  return lo != null && hi != null ? `${usd(lo)} to < ${usd(hi)}` : lo != null ? `≥ ${usd(lo)}` : `< ${usd(hi)}`;
}

function split(row) {
  if (!row || !row.gross) return '<span class="muted">Flat · no open notional</span>';
  const share = Math.max(0, Math.min(100, row.long / row.gross * 100));
  return `<div class="bias-bar" role="img" aria-label="${share.toFixed(1)}% long, ${(100 - share).toFixed(1)}% short"><span class="long" style="width:${share}%"></span><span class="short" style="width:${100 - share}%"></span></div><div class="bias-labels"><span>${share.toFixed(1)}% L</span><span>${(100 - share).toFixed(1)}% S</span></div>`;
}

function renderKpis() {
  const rows = shown();
  const printer = rows.map((row) => row.cohorts.find((cohort) => cohort.id === 8)).filter(Boolean);
  const reported = total(rows.map((row) => ({ count: row.cohorts.length })), 'count');
  const cards = [
    ['SHOWN PAIRS / 24H VOLUME', usd(total(rows, 'volume24h')), `${rows.length} pairs, ranked by executed notional`],
    ['SHARE OF XYZ VOLUME', pct(desk.data.xyz.totalXyzVolume24h ? total(rows, 'volume24h') / desk.data.xyz.totalXyzVolume24h : null), `of ${num(desk.data.xyz.xyzMarketCount)} active xyz markets`],
    ['MONEY PRINTER / SHOWN PAIRS', `${printer.length < rows.length ? '≥ ' : ''}${usd(total(printer, 'gross'))}`, `${signed(total(printer, 'net'))} net · ${printer.length}/${rows.length} pairs reported`],
    ['COHORT CELLS REPORTED', `${reported} / ${rows.length * cohorts().length}`, `${rows.filter((row) => row.cohortCoverageComplete).length}/${rows.length} pairs have all eight cohorts`],
  ];
  el('xyz-kpis').innerHTML = cards.map(([label, value, note]) => `<article class="kpi"><p class="kpi-label">${label}</p><p class="kpi-value">${value}</p><p class="kpi-sub">${note}</p></article>`).join('');
}

function renderMatrix() {
  const rows = shown();
  el('matrix-head').innerHTML = `<tr><th scope="col" class="matrix-cohort">All-time PnL cohort<span class="subvalue">Long % / net notional</span></th>${rows.map((row) => `<th scope="col"><button class="matrix-market" type="button" data-pair="${esc(row.coin)}" aria-label="Inspect ${esc(row.coin)}"><span class="matrix-rank">#${row.volumeRank} BY VOLUME</span><strong>${esc(symbol(row.coin))}</strong><span>${usd(row.volume24h)} / 24h</span></button></th>`).join('')}</tr>`;
  el('matrix-body').innerHTML = cohorts().map((cohort) => `<tr><th scope="row" class="matrix-cohort"><span>${esc(cohort.name)}</span><span class="range">${esc(pnlRange(cohort.criteria))}</span></th>${rows.map((market) => {
    const row = market.cohorts.find((item) => item.id === cohort.id);
    const tilt = !row || row.gross === 0 ? 'no-exposure' : row.longShare >= .55 ? 'long-heavy' : row.longShare <= .45 ? 'short-heavy' : 'mixed';
    const selected = market.coin === desk.pair && cohort.id === desk.cohort;
    const body = !row ? '<strong>—</strong><span>Not reported</span>' : row.gross === 0 ? '<strong>Flat</strong><span>$0 open notional</span>' : `<strong>${pct(row.longShare, 0)} L</strong><span>${signed(row.net)} net</span><small>${usd(row.gross)} gross</small>`;
    const label = row ? `${cohort.name} on ${market.coin}: ${row.gross ? `${pct(row.longShare)} long, ${signed(row.net)} net, ${usd(row.gross)} gross` : 'flat'}` : `${cohort.name} on ${market.coin}: unavailable`;
    return `<td><button type="button" class="matrix-cell ${tilt}" data-pair="${esc(market.coin)}" data-cohort="${cohort.id}" aria-pressed="${selected}" aria-label="${esc(label)}">${body}</button></td>`;
  }).join('')}</tr>`).join('');
  el('matrix-coverage').textContent = `${rows.length} PAIRS × ${cohorts().length} PNL COHORTS · 24H VOLUME ORDER · SCROLL FOR MORE PAIRS →`;
}

function renderPair() {
  const pair = current();
  if (!pair) return;
  el('pair-select').value = desk.pair;
  el('pair-heading').textContent = `${symbol(pair.coin)} / cohort breakdown`;
  const quote = [
    ['MARK', price(pair.mark), `${pair.change24h > 0 ? '+' : ''}${pct(pair.change24h)} / 24h`, tone(pair.change24h)],
    ['24H VOLUME', usd(pair.volume24h), `#${pair.volumeRank} on xyz`, ''],
    ['OPEN INTEREST', usd(pair.openInterest), 'One-sided exchange OI', ''],
    ['HOURLY FUNDING', `${pair.fundingHourly > 0 ? '+' : ''}${pct(pair.fundingHourly, 4)}`, 'Positive = longs pay', ''],
  ];
  el('pair-tape').innerHTML = `<div class="pair-identity"><span class="eyebrow">XYZ PERPETUAL</span><strong>${esc(symbol(pair.coin))}</strong><a href="https://app.hyperliquid.xyz/trade/${encodeURIComponent(pair.coin)}" target="_blank" rel="noopener noreferrer">${esc(pair.coin)} ↗</a></div>${quote.map(([label, value, sub, color]) => `<div class="tape-stat"><span>${label}</span><strong>${value}</strong><small class="${color}">${sub}</small></div>`).join('')}`;
  const stamps = [...new Set(pair.cohorts.map((row) => row.sourceUpdatedAt).filter(Boolean))].sort();
  el('pair-source-time').textContent = `Market observed ${date(desk.data.xyz.marketObservedAt)} · Cohort source ${stamps.length ? date(stamps[0]) + (stamps.length > 1 ? ` to ${date(stamps.at(-1))}` : '') : 'unavailable'} · ${pair.cohorts.length}/8 PnL cohorts reported.`;
  const gross = total(pair.cohorts, 'gross');
  el('pair-cohort-rows').innerHTML = cohorts().map((cohort) => {
    const row = pair.cohorts.find((item) => item.id === cohort.id);
    return `<tr class="${cohort.id === desk.cohort ? 'pair-cohort-selected' : ''}"><td><button type="button" data-cohort="${cohort.id}" class="cohort-name" aria-pressed="${cohort.id === desk.cohort}">${esc(cohort.name)}</button><span class="range">${esc(pnlRange(cohort.criteria))}</span></td>${row ? `<td class="positive">${usd(row.long)}</td><td class="negative">${usd(row.short)}</td><td class="${tone(row.net)}">${signed(row.net)}</td><td class="pair-split">${split(row)}</td><td>${usd(row.gross)}<span class="subvalue">${pct(gross ? row.gross / gross : null)} of reported pair gross</span></td><td>${num(row.positions)}</td>` : '<td colspan="6" class="missing-cohort">Not reported by source — no zero exposure assumed.</td>'}</tr>`;
  }).join('');
  el('cohort-comparison').innerHTML = [
    ['Lifetime non-negative PnL cohorts', pair.cohorts.filter((row) => row.criteria.minPnl != null && row.criteria.minPnl >= 0), 'Money Printer → Humble Earner'],
    ['Lifetime negative PnL cohorts', pair.cohorts.filter((row) => row.criteria.maxPnl != null && row.criteria.maxPnl <= 0), 'Exit Liquidity → Giga-Rekt'],
  ].map(([label, rows, names]) => {
    const value = total(rows, 'gross'), long = total(rows, 'long'), net = total(rows, 'net');
    return `<article><p class="eyebrow">${esc(label)}</p><div><strong>${rows.length ? pct(value ? long / value : null) : '—'} <small>long</small></strong><span class="${tone(net)}">${rows.length ? signed(net) : '—'} net</span></div><p>${esc(names)} · ${rows.length}/4 cohorts reported · ${rows.length ? usd(value) : '—'} gross</p></article>`;
  }).join('');
  el('xyz-cohort-source').href = pair.cohortSourceUrl;
  el('xyz-position-source').href = pair.positionSourceUrl;
  renderTrades();
}

function renderTrades() {
  const pair = current();
  if (!pair) return;
  const cohort = el('trade-cohort').value, side = el('trade-side').value;
  const rows = pair.positions.filter((row) => (cohort === 'all' || row.pnlCohortIds.includes(Number(cohort))) && (side === 'all' || row.side === side));
  el('trade-coverage').textContent = `${pair.coin} · ${rows.length} matching public positions from a ${pair.positions.length}-position sample · ${cohort === 'all' ? 'All PnL cohorts' : cohortName(Number(cohort))} · Sample fetched ${date(pair.fetchedAt)}${pair.positionsAvailable ? '' : ' · Position sample unavailable'}`;
  el('xyz-trade-rows').innerHTML = rows.slice(0, desk.tradeLimit).map((row) => {
    const address = /^0x[a-f\d]{40}$/i.test(row.address || '') ? `${row.address.slice(0, 6)}…${row.address.slice(-4)}` : 'Unknown wallet';
    const names = row.pnlCohortIds.map(cohortName).join(', ') || 'PnL cohort not reported';
    return `<tr><td><a href="https://app.hyperliquid.xyz/explorer/address/${encodeURIComponent(row.address)}" target="_blank" rel="noopener noreferrer">${row.name ? `<span class="wallet-name">${esc(row.name)}</span>` : ''}<span class="wallet-address">${esc(address)} ↗</span></a><span class="subvalue">${esc(names)}</span></td><td><span class="side-tag ${row.side === 'long' ? 'long' : 'short'}">${row.side === 'long' ? 'LONG' : 'SHORT'}</span></td><td>${usd(row.value)}</td><td>${price(row.entry)}</td><td>${price(row.mark)}</td><td class="${tone(row.unrealizedPnl)}">${signed(row.unrealizedPnl)}</td><td>${known(row.liquidation) && Number(row.liquidation) > 0 ? price(row.liquidation) : '—'}</td><td>${known(row.leverage) && row.leverage > 0 ? `${num(row.leverage)}×` : '—'}</td></tr>`;
  }).join('') || noRows(8, pair.positionsAvailable ? 'No matching trades in this public sample. Use the full-cohort aggregates above for exposure; a missing sample match is not a flat book.' : 'The per-pair public position sample is unavailable. Cohort aggregates above remain independent.');
  el('more-xyz-trades').hidden = rows.length <= desk.tradeLimit;
  el('more-xyz-trades').textContent = `Show ${Math.min(10, rows.length - desk.tradeLimit)} more trades ↓`;
}

function tradFiRows() {
  const source = desk.data.markets?.items || [];
  return source.filter((row) => row.coin.startsWith('xyz:') && row.group)
    .slice().sort((a, b) => b.volume24h - a.volume24h);
}

function renderTradFiTabs() {
  el('tradfi-tabs').innerHTML = GROUPS.map(([id, label]) =>
    `<button type="button" data-tradfi="${id}" aria-pressed="${desk.tradfiGroup === id}">${esc(label)}</button>`).join('');
}

function renderTradFi() {
  const all = tradFiRows();
  if (!all.length) {
    el('tradfi-count').textContent = 'UNAVAILABLE';
    el('more-tradfi').hidden = true;
    el('tradfi-rows').innerHTML = noRows(8, 'The market snapshot is unavailable, so the TradFi table cannot be built.');
    return;
  }
  const rows = desk.tradfiGroup === 'all' ? all : all.filter((row) => row.group === desk.tradfiGroup);
  const visible = rows.slice(0, desk.tradfiLimit);
  const tracked = new Set(markets().map((row) => row.coin));
  el('tradfi-count').textContent = `${num(rows.length)} OF ${num(all.length)} MARKETS`;
  el('more-tradfi').hidden = rows.length <= desk.tradfiLimit;
  el('more-tradfi').textContent = `Show all ${num(rows.length)} markets ↓`;
  el('tradfi-rows').innerHTML = visible.map((row) => `<tr><td><a href="https://app.hyperliquid.xyz/trade/${encodeURIComponent(row.coin)}" target="_blank" rel="noopener noreferrer">${esc(symbol(row.coin))} ↗</a><span class="subvalue">${esc(row.coin)}</span></td><td><span class="group-tag">${esc(GROUP_LABEL[row.group] || row.group)}</span></td><td>${price(row.mark)}</td><td class="${tone(row.change24h)}">${known(row.change24h) ? `${row.change24h > 0 ? '+' : ''}${pct(row.change24h)}` : '—'}</td><td>${usd(row.volume24h)}</td><td>${usd(row.openInterest)}</td><td class="${tone(-row.fundingHourly)}">${row.fundingHourly > 0 ? '+' : ''}${pct(row.fundingHourly, 4)}</td><td>${tracked.has(row.coin) ? `<button type="button" class="mini-link" data-open-pair="${esc(row.coin)}">Open cohorts →</button>` : '<span class="muted small">not in top 20</span>'}</td></tr>`).join('');
}

function applyHash() {
  const match = /^#tradfi(?:-(indices|commodities|fx|etfs|equities))?$/.exec(location.hash);
  if (!match) return false;
  desk.tradfiGroup = match[1] || 'all';
  desk.tradfiLimit = 40;
  renderTradFiTabs();
  renderTradFi();
  return true;
}

function renderStatus() {
  const xyz = desk.data.xyz;
  const warnings = [];
  const oldMarkets = stale(xyz.marketObservedAt);
  if (oldMarkets) warnings.push(`The market-volume ranking is stale (${date(xyz.marketObservedAt)}).`);
  const oldPairs = xyz.items.filter((pair) => pair.cohorts.some((row) => stale(row.sourceUpdatedAt)));
  if (oldPairs.length) warnings.push(`${oldPairs.length} tracked pairs have cohort observations older than six hours or no valid source time.`);
  const incomplete = xyz.items.filter((row) => !row.cohortCoverageComplete);
  if (incomplete.length) warnings.push(`${incomplete.length} pairs have incomplete cohort coverage; missing cells are unavailable, not zero.`);
  const missingSamples = xyz.items.filter((row) => !row.positionsAvailable);
  if (missingSamples.length) warnings.push(`${missingSamples.length} public position samples are unavailable.`);
  for (const error of desk.data.errors || []) if (['xyz', 'markets'].includes(error.section)) warnings.push(`${error.section} refresh failed; retained values keep their original timestamps.`);
  el('xyz-notice').hidden = !warnings.length;
  el('xyz-notice').textContent = warnings.join(' ');
  el('xyz-freshness').classList.toggle('stale', oldMarkets || oldPairs.length > 0);
  el('xyz-freshness').innerHTML = `<span class="status-dot" aria-hidden="true"></span>${oldMarkets || oldPairs.length ? 'STALE DATA' : 'XYZ SOURCE SNAPSHOT'} · VOLUME RANKING ${date(xyz.marketObservedAt)}`;
  el('xyz-market-time').textContent = `Market observed ${date(xyz.marketObservedAt)} · ${xyz.xyzMarketCount} active xyz markets`;
  el('xyz-collected-time').textContent = `Collected ${date(xyz.fetchedAt)} · ${xyz.items.length} tracked pairs`;
  el('xyz-build-time').textContent = `Snapshot ${date(desk.data.generatedAt)}`;
}

function choosePair(coin, cohort = null) {
  desk.pair = coin;
  desk.tradeLimit = 10;
  if (cohort !== null) {
    desk.cohort = cohort;
    el('trade-cohort').value = String(cohort);
  } else {
    el('trade-cohort').value = 'all';
  }
  document.querySelectorAll('.matrix-cell').forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.pair === desk.pair && Number(button.dataset.cohort) === desk.cohort)));
  renderPair();
}

async function loadXyz() {
  el('xyz-reload').disabled = true;
  el('xyz-reload').textContent = 'Reading snapshot…';
  try {
    const data = await window.CatDeskData.load();
    if (data.schemaVersion !== 1 || !Array.isArray(data.xyz?.items) || !data.xyz.items.length || !Array.isArray(data.cohorts?.items)) throw new Error('xyz cohort snapshot is not available yet; run the collector with --cohorts-only');
    desk.data = data;
    window.CatDeskData.download(data);
    if (!markets().some((row) => row.coin === desk.pair)) desk.pair = markets()[0].coin;
    el('pair-select').innerHTML = markets().map((row) => `<option value="${esc(row.coin)}">#${row.volumeRank} · ${esc(symbol(row.coin))} · ${usd(row.volume24h)} / 24h</option>`).join('');
    const selected = el('trade-cohort').value;
    el('trade-cohort').innerHTML = '<option value="all">All PnL cohorts</option>' + cohorts().map((row) => `<option value="${row.id}">${esc(row.name)}</option>`).join('');
    el('trade-cohort').value = selected || 'all';
    renderKpis(); renderMatrix(); renderPair(); renderStatus();
    renderTradFiTabs(); renderTradFi();
    if (applyHash()) requestAnimationFrame(() => el('tradfi').scrollIntoView());
  } catch (error) {
    el('xyz-notice').hidden = false;
    el('xyz-notice').textContent = `Could not load the xyz desk: ${error.message}. ${location.protocol === 'file:' ? 'Serve this folder over HTTP with python -m http.server 8080.' : 'Reload the snapshot to retry.'}`;
    if (!desk.data) {
      el('xyz-freshness').textContent = 'XYZ SNAPSHOT UNAVAILABLE';
      el('xyz-kpis').textContent = 'Waiting for a verified per-pair cohort snapshot.';
    }
  } finally {
    el('xyz-reload').disabled = false;
    el('xyz-reload').textContent = 'Reload snapshot ↻';
  }
}

document.addEventListener('click', (event) => {
  if (!desk.data) return;
  const group = event.target.closest('[data-tradfi]');
  if (group) { desk.tradfiGroup = group.dataset.tradfi; desk.tradfiLimit = 40; renderTradFiTabs(); renderTradFi(); return; }
  const openPair = event.target.closest('[data-open-pair]');
  if (openPair) { choosePair(openPair.dataset.openPair); el('pair-detail').scrollIntoView({ behavior: 'smooth', block: 'start' }); return; }
  const target = event.target.closest('[data-pair], [data-cohort]');
  if (target) choosePair(target.dataset.pair || desk.pair, target.dataset.cohort ? Number(target.dataset.cohort) : null);
});
window.addEventListener('hashchange', () => { if (desk.data && applyHash()) el('tradfi').scrollIntoView(); });
el('pair-limit').addEventListener('change', () => { desk.limit = el('pair-limit').value; if (desk.data) { renderKpis(); renderMatrix(); } });
el('pair-select').addEventListener('change', () => choosePair(el('pair-select').value));
for (const id of ['trade-cohort', 'trade-side']) el(id).addEventListener('change', () => { desk.tradeLimit = 10; if (desk.data) renderTrades(); });
el('more-xyz-trades').addEventListener('click', () => { desk.tradeLimit += 10; renderTrades(); });
el('more-tradfi').addEventListener('click', () => { desk.tradfiLimit = Infinity; renderTradFi(); });
el('xyz-reload').addEventListener('click', loadXyz);
loadXyz();
setInterval(() => { if (document.visibilityState === 'visible' && !el('xyz-reload').disabled) loadXyz(); }, 300_000);
