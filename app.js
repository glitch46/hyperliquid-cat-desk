'use strict';

const $ = (id) => document.getElementById(id);
const state = { data: null, group: 'pnl', cohort: 8, trader: 0, positionLimit: 10, traderPositionLimit: 10, allMarkets: false };
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const valid = (value) => value !== null && value !== undefined && Number.isFinite(Number(value));
const money = (value, compact = true) => {
  if (!valid(value)) return '—';
  const n = Number(value), a = Math.abs(n);
  const suffix = compact ? (a >= 1e9 ? 'B' : a >= 1e6 ? 'M' : a >= 1e3 ? 'K' : '') : '';
  const scale = { B: 1e9, M: 1e6, K: 1e3 }[suffix] || 1;
  return `${n < 0 ? '−' : ''}$${(a / scale).toLocaleString('en-US', { minimumFractionDigits: suffix ? 2 : 0, maximumFractionDigits: suffix ? 2 : a < 1 ? 5 : a < 100 ? 2 : 0 })}${suffix}`;
};
const signedMoney = (n) => valid(n) ? `${Number(n) > 0 ? '+' : ''}${money(n)}` : '—';
const price = (n) => valid(n) ? Number(n).toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: Math.abs(Number(n)) < 1 ? 6 : 2 }) : '—';
const count = (n) => valid(n) ? Number(n).toLocaleString('en-US') : '—';
const percent = (n, digits = 1) => valid(n) ? `${(Number(n) * 100).toFixed(digits)}%` : '—';
const tone = (n) => Number(n) < 0 ? 'negative' : Number(n) > 0 ? 'positive' : '';
const shortAddress = (s) => /^0x[a-f\d]{40}$/i.test(s || '') ? `${s.slice(0, 6)}…${s.slice(-4)}` : 'Unknown wallet';
const explorer = (s) => `https://app.hyperliquid.xyz/explorer/address/${encodeURIComponent(s)}`;
const time = (s, short = false) => {
  if (!s || !Number.isFinite(Date.parse(s))) return 'Unavailable';
  return new Date(s).toLocaleString('en-GB', { timeZone: 'UTC', day: '2-digit', month: 'short', ...(short ? {} : { year: 'numeric' }), hour: '2-digit', minute: '2-digit', hour12: false }) + ' UTC';
};
const age = (s) => (Date.now() - Date.parse(s)) / 36e5;
const sum = (rows, key) => rows.reduce((total, row) => total + (Number(row[key]) || 0), 0);
const coinName = (s) => escapeHtml(s);
const trade = (p) => `<span class="trade-label"><span>${coinName(p.coin)}</span><span class="side-tag ${p.side === 'long' ? 'long' : 'short'}">${p.side === 'long' ? 'LONG' : 'SHORT'}</span></span>`;
const empty = (columns, text) => `<tr><td colspan="${columns}" class="empty-cell">${escapeHtml(text)}</td></tr>`;
const wallet = (row, link = true) => {
  const body = `${row.name ? `<span class="wallet-name">${escapeHtml(row.name)}</span>` : ''}<span class="wallet-address">${escapeHtml(shortAddress(row.address))}${link ? ' ↗' : ''}</span>`;
  return link ? `<a href="${explorer(row.address)}" target="_blank" rel="noopener noreferrer" title="${escapeHtml(row.address)}">${body}</a>` : body;
};
const sideBar = (long, short) => {
  const total = long + short;
  const share = total ? Math.max(0, Math.min(100, 100 * long / total)) : 0;
  return `<div class="bias-bar" role="img" aria-label="${share.toFixed(1)}% long, ${(100 - share).toFixed(1)}% short"><span class="long" style="width:${share}%"></span><span class="short" style="width:${total ? 100 - share : 0}%"></span></div>`;
};
function range(criteria, category) {
  const low = criteria[category === 'pnl' ? 'minPnl' : 'minSize'];
  const high = criteria[category === 'pnl' ? 'maxPnl' : 'maxSize'];
  if (low != null && high != null) return `${money(low)} to < ${money(high)}`;
  return low != null ? `≥ ${money(low)}` : `< ${money(high)}`;
}

function renderKpis() {
  const rows = state.data.cohorts.items.filter((row) => row.category === 'pnl');
  const total = sum(rows, 'gross'), long = sum(rows, 'long'), active = sum(rows, 'activeWallets');
  const positive = rows.filter((row) => row.criteria.minPnl != null && row.criteria.minPnl >= 0);
  const cards = [
    ['OPEN GROSS EXPOSURE', money(total), `${money(long)} long / ${money(sum(rows, 'short'))} short`],
    ['WALLETS IN POSITION', count(active), `of ${count(sum(rows, 'wallets'))} PnL-classified wallets`],
    ['LONG SHARE OF OPEN BOOK', percent(total ? long / total : null), `${signedMoney(long - sum(rows, 'short'))} net exposure`],
    ['LIFETIME NON-NEGATIVE PNL', count(sum(positive, 'wallets')), `${percent(sum(rows, 'wallets') ? sum(positive, 'wallets') / sum(rows, 'wallets') : null)} of PnL-classified wallets`],
  ];
  $('kpis').innerHTML = cards.map(([label, value, sub]) => `<article class="kpi"><p class="kpi-label">${label}</p><p class="kpi-value">${value}</p><p class="kpi-sub">${sub}</p></article>`).join('');
}

function renderCohorts() {
  const rows = state.data.cohorts.items.filter((row) => row.category === state.group);
  if (!rows.some((row) => row.id === state.cohort)) state.cohort = rows[0]?.id;
  document.querySelectorAll('[data-group]').forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.group === state.group)));
  $('cohort-explanation').textContent = state.group === 'pnl'
    ? 'Cohorts use all-time perp PnL. Exposure is the current open book across the source’s tracked perp venues.'
    : 'Account-size bands use HyperTracker’s size classifications. These wallets overlap with the PnL cohorts; do not add the two lenses.';
  $('cohort-rows').innerHTML = rows.map((row) => {
    const longShare = row.gross ? row.long / row.gross : null;
    const top = row.markets[0];
    return `<tr class="${row.id === state.cohort ? 'selected' : ''}"><td><button type="button" class="cohort-name" data-cohort="${row.id}" aria-pressed="${row.id === state.cohort}">${escapeHtml(row.name)}</button><span class="range">${escapeHtml(range(row.criteria, row.category))}</span></td><td>${count(row.wallets)}<span class="subvalue">${count(row.activeWallets)} open</span></td><td>${money(row.gross)}</td><td>${sideBar(row.long, row.short)}<div class="bias-labels"><span>${percent(longShare, 0)} L</span><span>${percent(longShare == null ? null : 1 - longShare, 0)} S</span></div></td><td class="${tone(row.long - row.short)}">${signedMoney(row.long - row.short)}</td><td>${top ? `<span class="asset-pill">${coinName(top.coin)}</span><span class="subvalue">${percent(row.allocationGross ? top.value / row.allocationGross : null)} of book</span>` : '—'}</td></tr>`;
  }).join('');
  renderCohortDetail();
}

function renderCohortDetail() {
  const row = state.data.cohorts.items.find((item) => item.id === state.cohort);
  if (!row) return;
  $('selected-label').textContent = `${row.name.toUpperCase()} / ${range(row.criteria, row.category)}`;
  $('allocation-summary').innerHTML = `<strong>${money(row.allocationGross)}</strong><span>gross open notional</span>`;
  $('allocation-count').textContent = `Top ${row.markets.length} + other`;
  const max = Math.max(...row.markets.map((m) => m.value), row.otherAllocation, 1);
  const markets = row.markets.map((m) => ({ ...m, other: false }));
  if (row.otherAllocation > 0) markets.push({ coin: 'Other assets', value: row.otherAllocation, other: true });
  $('allocations').innerHTML = markets.map((m) => {
    const width = Math.min(100, m.value / max * 100);
    return `<div class="allocation-row ${m.other ? 'allocation-other' : ''}" title="${escapeHtml(m.coin)}: ${money(m.value, false)}${m.other ? '' : ` · Long ${money(m.long)} / Short ${money(m.short)}`}"><span class="allocation-name">${coinName(m.coin)}</span><div style="width:${width}%">${m.other ? '<div class="bias-bar"><span style="width:100%"></span></div>' : sideBar(m.long, m.short)}</div><span class="allocation-value">${money(m.value)}</span><span class="allocation-share">${percent(row.allocationGross ? m.value / row.allocationGross : null)}</span></div>`;
  }).join('');
  $('allocation-footnote').textContent = `Top ${row.markets.length} covers ${percent(row.allocationCoverage)} of this book. Other assets are the exact remainder; their side split is not supplied. Detail fetched ${time(row.observedAt)}.`;
  const net = row.long - row.short;
  const profitableShare = row.detailActiveWallets ? row.openProfitableWallets / row.detailActiveWallets : null;
  const stats = [
    ['NET DIRECTION', `${net >= 0 ? 'Long' : 'Short'} ${money(Math.abs(net))}`, `${percent(row.gross ? row.long / row.gross : null)} long by notional`],
    ['GROSS / ACTIVE EQUITY', row.activeEquity ? `${(row.gross / row.activeEquity).toFixed(2)}×` : '—', 'Aggregate exposure ratio'],
    ['OPEN BOOK IN PROFIT', valid(row.openProfitableWallets) ? percent(profitableShare) : '—', 'Wallets with positive open PnL'],
    ['WALLET CHANGE / 24H', valid(row.walletChange24h) ? `${row.walletChange24h > 0 ? '+' : ''}${count(row.walletChange24h)}` : '—', 'Change in cohort membership'],
  ];
  $('book-stats').innerHTML = stats.map(([label, value, sub]) => `<div class="book-stat"><span>${label}</span><strong>${value}</strong><small>${sub}</small></div>`).join('');
  renderChart(row.history);
  renderPositions();
}

function renderChart(points) {
  const series = (points || []).filter((p) => valid(p.value) && Number.isFinite(Date.parse(p.time)));
  if (series.length < 2) {
    $('exposure-chart').innerHTML = '<p class="muted small">Not enough source history to plot.</p>';
    $('history-range').textContent = '';
    return;
  }
  const width = 460, height = 116, top = 12, bottom = 92;
  const values = series.map((p) => p.value), low = Math.min(...values), high = Math.max(...values);
  const first = Date.parse(series[0].time), last = Date.parse(series.at(-1).time);
  const x = (p) => ((Date.parse(p.time) - first) / (last - first || 1)) * width;
  const y = (p) => bottom - ((p.value - low) / (high - low || 1)) * (bottom - top);
  const line = series.map((p, i) => `${i ? 'L' : 'M'}${x(p).toFixed(2)},${y(p).toFixed(2)}`).join(' ');
  $('history-range').textContent = `${new Date(first).toLocaleDateString('en-GB', { timeZone: 'UTC', day: '2-digit', month: 'short' })} – ${new Date(last).toLocaleDateString('en-GB', { timeZone: 'UTC', day: '2-digit', month: 'short' })}`;
  $('exposure-chart').innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Gross exposure ranged from ${money(low)} to ${money(high)} in the available source history; the vertical axis is cropped to this range."><path d="M0,${top}H${width} M0,${bottom}H${width}" stroke="#294034" stroke-dasharray="3 5" fill="none"/><path d="${line}" stroke="#97e5c5" stroke-width="1.6" fill="none" vector-effect="non-scaling-stroke"/><text class="chart-axis" x="0" y="${height}">${money(low)} low</text><text class="chart-axis" x="${width}" y="${height}" text-anchor="end">${money(high)} high · cropped axis</text></svg>`;
}

function positionCells(p, withWallet = false, bookTotal = null) {
  return `${withWallet ? `<td>${wallet(p)}</td>` : ''}<td>${trade(p)}</td><td title="${money(p.value, false)}">${money(p.value)}</td>${bookTotal !== null ? `<td>${percent(bookTotal ? p.value / bookTotal : null)}</td>` : ''}<td>${price(p.entry)}</td><td>${price(p.mark)}</td><td class="${tone(p.unrealizedPnl)}">${signedMoney(p.unrealizedPnl)}</td><td>${valid(p.liquidation) && Number(p.liquidation) > 0 ? price(p.liquidation) : '—'}</td><td>${valid(p.leverage) && Number(p.leverage) > 0 ? `${count(p.leverage)}×` : '—'}</td>`;
}

function renderPositions() {
  const row = state.data.cohorts.items.find((item) => item.id === state.cohort);
  if (!row) return;
  const filtered = row.largestPositions.filter((p) => ($('position-market').value === 'all' || p.coin.startsWith('xyz:')) && ($('position-side').value === 'all' || p.side === $('position-side').value));
  $('position-rows').innerHTML = filtered.slice(0, state.positionLimit).map((p) => `<tr>${positionCells(p, true)}</tr>`).join('') || empty(8, 'No matching positions in the source’s largest-position sample. This does not mean the cohort has no exposure to these markets.');
  $('position-coverage').textContent = `${row.name} · ${count(filtered.length)} matching positions from the source’s ${row.largestPositions.length}-position sample · ${count(row.activeWallets)} cohort wallets have open positions. Smaller trades are outside this sample.`;
  $('more-positions').hidden = filtered.length <= state.positionLimit;
  $('more-positions').textContent = `Show ${Math.min(10, filtered.length - state.positionLimit)} more positions ↓`;
}

function renderTraders() {
  const data = state.data.traders;
  if (!data) {
    $('trader-coverage').textContent = 'Wallet screening has not completed yet. Cohort data is available above.';
    $('trader-rows').innerHTML = empty(6, 'Verified xyz-majority traders will appear after the collector completes its first screening run.');
    $('trader-detail').hidden = true;
    $('trader-method').textContent = 'The collector screens profitable official-leaderboard wallets plus large xyz position holders. No demonstration traders are used.';
    return;
  }
  $('trader-coverage').innerHTML = `<strong>${count(data.checked)}/${count(data.candidates)}</strong> candidates checked<span class="separator">/</span><strong>${count(data.completeWindows)}</strong> complete windows<span class="separator">/</span><strong>${count(data.eligibleCount)}</strong> xyz-majority<span class="separator">/</span><strong>${count(data.incompleteWindows)}</strong> incomplete${data.deferred ? `<span class="separator">/</span><strong>${count(data.deferred)}</strong> not yet checked` : ''}<br>Fill window ends ${time(data.windowEnd, true)} · Positions observed ${time(data.fetchedAt, true)}`;
  $('trader-rows').innerHTML = data.items.map((row, index) => {
    const top = row.positions[0];
    return `<tr class="${state.trader === index ? 'selected' : ''}"><td><button type="button" class="trader-button" data-trader="${index}" aria-pressed="${state.trader === index}"><span class="rank">${String(index + 1).padStart(2, '0')}</span><span>${wallet(row, false)}</span></button></td><td class="${tone(row.pnl30d)}">${signedMoney(row.pnl30d)}<span class="subvalue">${percent(row.roi30d)} ROI</span></td><td><span class="share-meter"><span><i style="width:${Math.min(100, row.xyzShare * 100)}%"></i></span>${percent(row.xyzShare)}</span></td><td>${money(row.xyzVolume)}</td><td>${top ? trade(top) + `<span class="subvalue">${money(top.value)}</span>` : row.positionErrors.length ? 'Position data incomplete' : '<span class="muted">Flat across checked venues</span>'}</td><td>${row.positionErrors.length ? '≥ ' : ''}${money(sum(row.positions, 'value'))}</td></tr>`;
  }).join('') || empty(6, 'No traders passed the complete-window xyz-majority screen in this candidate set. See coverage below.');
  $('incomplete-count').textContent = `(${data.incompleteWindows} incomplete)`;
  $('trader-method').innerHTML = `<p>Candidate discovery takes the top ${count(data.candidateLimit)} profitable wallets by the official leaderboard’s month account PnL, expanded with profitable leaderboard wallets appearing in HyperTracker’s large xyz-position samples. Known large xyz-position holders are checked first within a time-bounded scan. ${count(data.leaderboardWallets)} wallets were present in the leaderboard; ${count(data.candidates)} were candidates, ${count(data.checked)} were successfully checked, ${count(data.deferred || 0)} were deferred by the screening budget, and ${count(data.errors.length)} checks failed.</p><p><strong>Executed-volume window:</strong> ${time(data.windowStart)} to ${time(data.windowEnd)}. Volume = |fill size| × execution price. Spot fills are excluded; perp fills from all venues form the denominator. A trader qualifies only when xyz volume share is strictly greater than 50%, account PnL is positive, and pagination completes below the 10,000-fill retention cap. The API’s retention limit and per-response limit are treated separately. Rank uses the leaderboard’s independently observed rolling-month account PnL (${time(data.leaderboardObservedAt)}), which can include trading beyond xyz and has a different observation time. Resumed scans retain their original exact fill window and account-PnL observation.</p><p>Current position sheets query ${count(data.venues.length)} registered perp venues: ${data.venues.map(escapeHtml).join(', ')}. Open orders and spot balances are outside these sheets. Subaccounts are not consolidated. The xyz closed-trade PnL shown in a wallet sheet is the sum of xyz fill closedPnl; it excludes fees, funding, and unrealized PnL.</p>${data.incompleteCandidates.length ? `<p>Highest account-PnL candidates excluded for incomplete fill coverage:</p><ul class="incomplete-list">${data.incompleteCandidates.map((row) => `<li><a href="${explorer(row.address)}" target="_blank" rel="noopener noreferrer">${escapeHtml(shortAddress(row.address))}</a> · ${signedMoney(row.pnl30d)} account PnL · ${escapeHtml(row.coverageReason)} · ${count(row.fillCount)} observed fills</li>`).join('')}</ul>` : ''}`;
  if (state.trader >= data.items.length) state.trader = 0;
  renderTraderDetail();
}

function renderTraderDetail() {
  const trader = state.data.traders?.items[state.trader];
  $('trader-detail').hidden = !trader;
  if (!trader) return;
  $('trader-detail-heading').textContent = trader.name || shortAddress(trader.address);
  $('trader-explorer').href = explorer(trader.address);
  const total = sum(trader.positions, 'value');
  $('trader-detail-meta').textContent = `${percent(trader.xyzShare)} xyz volume · ${count(trader.fillCount)} fills checked · ${signedMoney(trader.xyzClosedPnl)} xyz closed-trade PnL before fees/funding · Showing ${Math.min(state.traderPositionLimit, trader.positions.length)} of ${trader.positions.length} current positions · ${trader.positionVenues.length}/${state.data.traders.venues.length} venues checked · Positions fetched ${time(trader.positionsObservedAt)}.${trader.positionErrors.length ? ` ${trader.positionErrors.length} venue queries failed; the book is incomplete.` : ''}`;
  $('trader-position-rows').innerHTML = trader.positions.slice(0, state.traderPositionLimit).map((p) => `<tr>${positionCells(p, false, total)}</tr>`).join('') || empty(8, trader.positionErrors.length ? 'Position queries are incomplete. No positions were returned by the successful queries.' : 'No open perp positions across the checked venues at observation time.');
  $('more-trader-positions').hidden = trader.positions.length <= state.traderPositionLimit;
  $('more-trader-positions').textContent = `Show ${Math.min(10, trader.positions.length - state.traderPositionLimit)} more wallet positions ↓`;
  document.querySelectorAll('[data-trader]').forEach((button) => button.setAttribute('aria-pressed', String(Number(button.dataset.trader) === state.trader)));
}

function renderMarkets() {
  const data = state.data.markets;
  if (!data) {
    $('market-totals').textContent = 'Market source unavailable.';
    $('market-rows').innerHTML = empty(6, 'No verified market snapshot is available.');
    $('more-markets').hidden = true;
    return;
  }
  $('market-time').textContent = `Observed ${time(data.fetchedAt, true)}`;
  $('market-totals').innerHTML = `<strong>${count(data.items.length)}</strong> active markets<span class="separator">/</span><strong>${money(sum(data.items, 'volume24h'))}</strong> 24h volume<span class="separator">/</span><strong>${money(sum(data.items, 'openInterest'))}</strong> one-sided open interest`;
  $('market-rows').innerHTML = data.items.slice(0, state.allMarkets ? undefined : 10).map((row) => `<tr><td><a href="https://app.hyperliquid.xyz/trade/${encodeURIComponent(row.coin)}" target="_blank" rel="noopener noreferrer">${coinName(row.coin)} ↗</a></td><td>${price(row.mark)}</td><td class="${tone(row.change24h)}">${Number(row.change24h) > 0 ? '+' : ''}${percent(row.change24h)}</td><td>${money(row.volume24h)}</td><td>${money(row.openInterest)}</td><td class="${tone(-row.fundingHourly)}">${row.fundingHourly > 0 ? '+' : ''}${percent(row.fundingHourly, 4)}</td></tr>`).join('');
  $('more-markets').hidden = data.items.length <= 10;
  $('more-markets').textContent = state.allMarkets ? 'Show top 10 markets ↑' : `Show all ${data.items.length} xyz markets ↓`;
}

function renderSources() {
  const { cohorts, traders, markets, venice, generatedAt } = state.data;
  $('cohort-source-time').textContent = `Feed ${time(cohorts.sourceUpdatedAt)} · Collected ${time(cohorts.fetchedAt)}`;
  $('primary-source-time').textContent = `Traders ${time(traders?.fetchedAt)} · Markets ${time(markets?.fetchedAt)}`;
  $('venice-note').textContent = venice?.hyperliquidNetworks.length ? venice.status + '. The desk uses the native HyperCore API for positions and fills.' : 'The live Venice RPC network list does not include Hyperliquid or HyperEVM. HyperCore trader data comes from Hyperliquid’s public Info API.';
  if (!venice) $('venice-note').textContent = 'Venice’s network discovery was unavailable during this refresh. The desk uses Hyperliquid’s public Info API for trading data.';
  $('venice-source-time').textContent = venice ? `Network list checked ${time(venice.checkedAt)}` : 'Network check unavailable';
  $('build-time').textContent = `Snapshot ${time(generatedAt, true)}`;
  const stale = age(cohorts.sourceUpdatedAt || cohorts.fetchedAt) > 6;
  $('freshness').classList.toggle('stale', stale);
  $('freshness').innerHTML = `<span class="status-dot" aria-hidden="true"></span>${stale ? 'STALE COHORT FEED' : 'SOURCE SNAPSHOT'} · ${time(cohorts.sourceUpdatedAt || cohorts.fetchedAt)}`;
  const notices = [];
  if (stale) notices.push('The cohort feed is more than six hours old. All values retain their original observation times.');
  if (traders && age(traders.fetchedAt) > 6) notices.push(`Trader screening is stale (${time(traders.fetchedAt)}).`);
  if (markets && age(markets.fetchedAt) > 6) notices.push(`Market context is stale (${time(markets.fetchedAt)}).`);
  for (const error of state.data.errors || []) notices.push(`${error.section}: refresh failed; any retained data keeps its previous timestamp.`);
  if (traders?.errors.length) notices.push(`${traders.errors.length} candidate wallet checks failed; see screening coverage.`);
  $('notice').hidden = !notices.length;
  $('notice').textContent = notices.join(' ');
}

async function load() {
  $('reload').disabled = true;
  $('reload').textContent = 'Reading snapshot…';
  try {
    const response = await fetch(`data/snapshot.json?t=${Date.now()}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`Snapshot HTTP ${response.status}`);
    const data = await response.json();
    if (data.schemaVersion !== 1 || !Array.isArray(data.cohorts?.items)) throw new Error('Unrecognized snapshot format');
    state.data = data;
    renderKpis(); renderCohorts(); renderTraders(); renderMarkets(); renderSources();
  } catch (error) {
    $('notice').hidden = false;
    $('notice').textContent = `Could not load the snapshot: ${error.message}. ${location.protocol === 'file:' ? 'Serve this folder over HTTP with python -m http.server 8080, then open http://localhost:8080.' : 'Use Reload snapshot to retry. The collector may still be running its first refresh.'}`;
    if (!state.data) {
      $('freshness').textContent = 'SNAPSHOT UNAVAILABLE';
      $('kpis').textContent = 'Waiting for a verified source snapshot.';
      $('trader-coverage').textContent = 'Snapshot unavailable.';
    }
  } finally {
    $('reload').disabled = false;
    $('reload').textContent = 'Reload snapshot ↻';
  }
}

document.addEventListener('click', (event) => {
  const group = event.target.closest('[data-group]');
  const cohort = event.target.closest('[data-cohort]');
  const trader = event.target.closest('[data-trader]');
  if (!state.data) return;
  if (group) { state.group = group.dataset.group; state.positionLimit = 10; renderCohorts(); }
  if (cohort) { state.cohort = Number(cohort.dataset.cohort); state.positionLimit = 10; renderCohorts(); }
  if (trader) { state.trader = Number(trader.dataset.trader); state.traderPositionLimit = 10; renderTraderDetail(); }
});
for (const id of ['position-market', 'position-side']) $(id).addEventListener('change', () => { if (state.data) { state.positionLimit = 10; renderPositions(); } });
$('more-positions').addEventListener('click', () => { state.positionLimit += 10; renderPositions(); });
$('more-trader-positions').addEventListener('click', () => { state.traderPositionLimit += 10; renderTraderDetail(); });
$('more-markets').addEventListener('click', () => { state.allMarkets = !state.allMarkets; renderMarkets(); });
$('reload').addEventListener('click', load);
load();
