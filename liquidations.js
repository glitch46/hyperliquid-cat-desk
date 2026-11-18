'use strict';

(() => {
  const node = (id) => document.getElementById(id);
  const watch = { data: null, overrides: new Map(), limit: 12, chartAsset: 'BTC', busy: false, liveAt: null, liveError: null, lastAutoAt: 0 };
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const number = (n) => n != null && n !== '' && typeof n !== 'boolean' && Number.isFinite(Number(n)) ? Number(n) : null;
  const money = (n) => {
    if (number(n) == null) return '—';
    const a = Math.abs(n), suffix = a >= 1e9 ? 'B' : a >= 1e6 ? 'M' : a >= 1e3 ? 'K' : '';
    return `${n < 0 ? '−' : ''}$${(a / ({ B: 1e9, M: 1e6, K: 1e3 }[suffix] || 1)).toLocaleString('en-US', { maximumFractionDigits: 2 })}${suffix}`;
  };
  const price = (n) => number(n) == null ? '—' : Number(n).toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: Math.abs(n) < 1 ? 7 : 2 });
  const percentage = (n) => number(n) == null ? '—' : `${(n * 100).toFixed(2)}%`;
  const date = (s) => s && Number.isFinite(Date.parse(s)) ? new Date(s).toLocaleString('en-GB', { timeZone: 'UTC', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }) + ' UTC' : 'Unavailable';
  const ageMinutes = (s) => (Date.now() - (Date.parse(s) || 0)) / 60_000;
  const observedAt = (p) => Date.parse(p.accountStateAt) ? p.accountStateAt : p.verifiedAt;
  const compactAddress = (s) => `${s.slice(0, 6)}…${s.slice(-4)}`;
  const sum = (rows) => rows.reduce((s, p) => s + p.value, 0);
  const sideColor = (side) => side === 'long' ? '#97e5c5' : '#d79c91';
  const denied = new Set(['PAXG', 'XAUT', 'GOLD', 'SILVER', 'XYZ100', 'SP500', 'SPY', 'QQQ', 'NVDA', 'AAPL', 'TSLA', 'MSFT', 'OIL', 'CL', 'BRENTOIL']);
  const crypto = (coin) => typeof coin === 'string' && !coin.includes(':') && !coin.includes('/') && !coin.startsWith('@') && !denied.has(coin) && watch.data?.nativeCryptoSymbols.includes(coin);

  function positions() {
    if (!watch.data) return [];
    const result = watch.data.positions.filter((p) => !watch.overrides.has(p.address));
    for (const reply of watch.overrides.values()) result.push(...reply.positions);
    return result.filter((p) => crypto(p.coin) && ['long', 'short'].includes(p.side) && number(p.value) >= 100_000
      && number(p.liquidation) > 0 && number(p.mark) > 0 && number(p.distance) != null);
  }

  function filtered() {
    const asset = node('liq-asset').value, max = Number(node('liq-distance').value);
    const minimum = Number(node('liq-minimum').value), side = node('liq-side').value;
    const rows = positions().filter((p) => p.value >= minimum && p.distance <= max
      && (asset === 'all' || p.coin === asset) && (side === 'all' || p.side === side));
    return rows.sort(node('liq-sort').value === 'distance'
      ? (a, b) => a.distance - b.distance || b.value - a.value
      : (a, b) => b.value - a.value || a.distance - b.distance);
  }

  function render() {
    if (!watch.data) return;
    const rows = filtered(), coverage = watch.data.coverage;
    const largest = rows.slice().sort((a, b) => b.value - a.value)[0];
    const closest = rows.length ? Math.min(...rows.map((p) => p.distance)) : null;
    const cards = [
      ['OPEN NOTIONAL / FILTERED SAMPLE', money(sum(rows)), `${rows.length} verified positions · not cash at risk`],
      ['WALLETS / FILTERED SAMPLE', new Set(rows.map((p) => p.address)).size, 'Public accounts, not unique people'],
      ['LARGEST MATCHING POSITION', largest ? money(largest.value) : '—', largest ? `${largest.coin} ${largest.side} · liq. ${price(largest.liquidation)}` : 'No matching sample positions'],
      ['CLOSEST ADVERSE MOVE', closest == null ? '—' : closest <= 0 ? 'At/beyond' : percentage(closest), 'Relative to that position’s verified mark'],
    ];
    node('liq-kpis').innerHTML = cards.map(([label, value, sub]) => `<article><p>${label}</p><strong>${value}</strong><small>${esc(sub)}</small></article>`).join('');
    const staleRows = rows.filter((p) => ageMinutes(observedAt(p)) > 30).length;
    const warnings = [];
    if (watch.data.status === 'retained') warnings.push('Verification refresh failed; this is the last-good observation with its original dates.');
    if (ageMinutes(watch.data.generatedAt) > 30) warnings.push('Published crypto watch is over 30 minutes old. Live checks, if enabled, only refresh the wallets they successfully verify.');
    if (staleRows) warnings.push(`${staleRows} matching position states are older than 30 minutes.`);
    if (watch.liveError) warnings.push(watch.liveError);
    node('liq-notice').hidden = !warnings.length;
    node('liq-notice').textContent = warnings.join(' ');
    node('liq-freshness').textContent = `Published ${date(watch.data.generatedAt)} · target 15 min${watch.liveAt ? ` · live check ${date(watch.liveAt)}` : ''}`;
    node('liq-coverage').textContent = `${coverage.verifiedWallets}/${coverage.requestedWallets} wallets verified from ${coverage.candidateWallets} discovery candidates · ${coverage.failedWallets} failed · ${coverage.deferredWallets} deferred · ${coverage.withoutPositiveLiquidationPrice} large native positions had no positive liquidation price. ${watch.overrides.size} wallet(s) rechecked in this browser. Bounded sample, not a global ranking.`;
    node('liq-method').textContent = watch.data.method;
    renderTable(rows); renderLadder(rows); renderDistance(rows);
  }

  function renderTable(rows) {
    node('liq-rows').innerHTML = rows.slice(0, watch.limit).map((p) => `<tr><td><a href="https://app.hyperliquid.xyz/explorer/address/${encodeURIComponent(p.address)}" target="_blank" rel="noopener noreferrer">${p.name ? `<span class="wallet-name">${esc(p.name)}</span>` : ''}<span class="wallet-address">${esc(compactAddress(p.address))} ↗</span></a><button class="liq-verify text-button" type="button" data-verify="${esc(p.address)}" ${watch.busy ? 'disabled' : ''}>Verify wallet now</button></td><td>${esc(p.coin)} <span class="side-tag ${p.side}">${p.side.toUpperCase()}</span></td><td>${money(p.value)}</td><td>${price(p.mark)}</td><td class="liq-price">${price(p.liquidation)}</td><td class="${p.distance <= .01 ? 'liq-close' : ''}">${p.distance <= 0 ? 'At/beyond estimate' : percentage(p.distance)}</td><td class="${p.unrealizedPnl < 0 ? 'negative' : 'positive'}">${money(p.unrealizedPnl)}</td><td>${number(p.leverage) == null ? '—' : p.leverage + '×'}<span class="subvalue">${esc(p.marginMode || 'Unreported')}</span></td><td title="Read at ${date(p.verifiedAt)}">${date(observedAt(p))}<span class="subvalue">${p.browserLive ? 'Live account read' : 'Scheduled account read'}${ageMinutes(observedAt(p)) > 30 ? ' · STATE STALE' : ''}</span></td></tr>`).join('')
      || '<tr><td class="empty-cell" colspan="9">No verified positions match these filters in the sampled wallets. This is not evidence that the wider crypto market has no liquidation risk.</td></tr>';
    node('more-liquidations').hidden = rows.length <= watch.limit;
    node('more-liquidations').textContent = `Show ${Math.min(12, rows.length - watch.limit)} more verified positions ↓`;
  }

  function renderLadder(rows) {
    const totals = new Map();
    for (const p of rows) totals.set(p.coin, (totals.get(p.coin) || 0) + p.value);
    const coins = [...totals.keys()].sort((a, b) => totals.get(b) - totals.get(a));
    if (!coins.includes(watch.chartAsset)) watch.chartAsset = coins[0] || '';
    node('liq-chart-asset').innerHTML = coins.length ? coins.map((coin) => `<option value="${esc(coin)}">${esc(coin)}</option>`).join('') : '<option>No matching asset</option>';
    node('liq-chart-asset').value = watch.chartAsset;
    node('liq-chart-asset').disabled = !coins.length || node('liq-asset').value !== 'all';
    const assetRows = rows.filter((p) => p.coin === watch.chartAsset).sort((a, b) => b.value - a.value).slice(0, 12);
    if (!assetRows.length) { node('liq-ladder').innerHTML = '<p class="liq-empty">No matching verified price levels to plot.</p>'; return; }
    const newest = assetRows.slice().sort((a, b) => Date.parse(observedAt(b)) - Date.parse(observedAt(a)))[0];
    const mark = newest.mark;
    const levels = assetRows.map((p) => p.liquidation).concat(mark);
    const spread = Math.max(Math.max(...levels) - Math.min(...levels), mark * .002);
    const low = Math.min(...levels) - spread * .12, high = Math.max(...levels) + spread * .12;
    const width = 680, left = 120, right = 494, height = 85 + assetRows.length * 36;
    const x = (n) => left + (n - low) / (high - low) * (right - left);
    const maxValue = Math.max(...assetRows.map((p) => p.value));
    const ticks = [0, .5, 1].map((part) => ({ value: low + (high - low) * part, x: left + (right - left) * part }));
    const dots = assetRows.map((p, index) => {
      const y = 74 + index * 36, point = x(p.liquidation), color = sideColor(p.side);
      const rightLabel = point > right - 90;
      const title = `${p.coin} ${p.side} · ${compactAddress(p.address)} · ${money(p.value)} notional · mark ${price(p.mark)} · estimated liquidation ${price(p.liquidation)} · ${p.distance <= 0 ? 'at/beyond estimate' : percentage(p.distance) + ' adverse move'} · account state ${date(observedAt(p))}`;
      return `<g><text x="3" y="${y - 1}" class="liq-svg-wallet">${esc(compactAddress(p.address))}</text><text x="3" y="${y + 11}" class="liq-svg-small" fill="${color}">${p.side.toUpperCase()}</text><line x1="${x(mark)}" y1="${y}" x2="${point}" y2="${y}" stroke="#3a5146" stroke-width="1.4"/><circle cx="${point}" cy="${y}" r="${Math.max(3, Math.sqrt(p.value / maxValue) * 12)}" fill="${color}" fill-opacity=".86" tabindex="0" role="img" aria-label="${esc(title)}"><title>${esc(title)}</title></circle><text x="${point + (rightLabel ? -14 : 14)}" y="${y - 6}" text-anchor="${rightLabel ? 'end' : 'start'}" class="liq-svg-price">${price(p.liquidation)}</text><text x="666" y="${y}" text-anchor="end" class="liq-svg-value">${money(p.value)}</text><text x="666" y="${y + 12}" text-anchor="end" class="liq-svg-small">${p.distance <= 0 ? 'At/beyond' : percentage(p.distance) + ' away'}</text></g>`;
    }).join('');
    node('liq-ladder').innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(watch.chartAsset)} estimated liquidation price ladder for the largest ${assetRows.length} matching verified positions"><text x="${left}" y="16" class="liq-svg-heading">${esc(watch.chartAsset)} · reference mark ${price(mark)}</text><text x="${left}" y="31" class="liq-svg-small">Reference observed ${date(observedAt(newest))}</text><line x1="${x(mark)}" x2="${x(mark)}" y1="46" y2="${height - 28}" stroke="#e8d3a6" stroke-dasharray="4 4"/>${dots}<line x1="${left}" x2="${right}" y1="${height - 23}" y2="${height - 23}" stroke="#3a5146"/>${ticks.map((t) => `<text x="${t.x}" y="${height - 6}" text-anchor="middle" class="liq-svg-small">${price(t.value)}</text>`).join('')}</svg>`;
  }

  function renderDistance(rows) {
    const cutoff = Number(node('liq-distance').value);
    const bands = [{ top: .01, label: '0–1%' }, { top: .03, label: '1–3%' }, { top: .05, label: '3–5%' }, { top: .1, label: '5–10%' }, { top: .2, label: '10–20%' }];
    let lower = -Infinity;
    const bins = bands.filter((b) => b.top <= cutoff).map((b) => {
      const items = rows.filter((p) => p.distance > lower && p.distance <= b.top);
      lower = b.top;
      const long = sum(items.filter((p) => p.side === 'long')), short = sum(items.filter((p) => p.side === 'short'));
      return { ...b, long, short, count: items.length, total: long + short };
    });
    const maximum = Math.max(...bins.map((b) => b.total), 1);
    const height = 100 + bins.length * 58;
    node('liq-distance-chart').innerHTML = `<svg viewBox="0 0 510 ${height}" role="img" aria-label="USD gross position notional by required adverse move to the estimated liquidation price"><rect x="24" y="14" width="7" height="7" fill="#97e5c5"/><text x="37" y="21" class="liq-svg-small">Long notional</text><rect x="166" y="14" width="7" height="7" fill="#d79c91"/><text x="180" y="21" class="liq-svg-small">Short notional</text>${bins.map((b, index) => {
      const y = 63 + index * 58;
      return `<g><title>${esc(b.label)}: ${money(b.long)} long, ${money(b.short)} short, ${b.count} positions</title><text x="24" y="${y}" class="liq-svg-wallet">${b.label}</text><text x="24" y="${y + 15}" class="liq-svg-small">${b.count} positions</text><rect x="114" y="${y - 10}" width="${b.long / maximum * 250}" height="14" fill="#97e5c5"/><rect x="${114 + b.long / maximum * 250}" y="${y - 10}" width="${b.short / maximum * 250}" height="14" fill="#d79c91"/><text x="485" y="${y + 1}" text-anchor="end" class="liq-svg-value">${money(b.total)}</text></g>`;
    }).join('')}<text x="24" y="${height - 13}" class="liq-svg-small">${rows.length} filtered positions · ${money(sum(rows))} gross notional</text></svg>`;
  }

  function normalizeLive(address, raw, metadata, time, stateTime) {
    const size = number(raw.szi), value = number(raw.positionValue), liq = number(raw.liquidationPx);
    if (!crypto(raw.coin) || !size || value == null || value < 100_000 || liq == null || liq <= 0) return null;
    const side = size > 0 ? 'long' : 'short', mark = value / Math.abs(size);
    return { id: address + ':' + raw.coin, address, name: metadata?.name, coin: raw.coin, side,
      size: Math.abs(size), value, mark, entry: number(raw.entryPx), liquidation: liq,
      distance: side === 'long' ? (mark - liq) / mark : (liq - mark) / mark,
      unrealizedPnl: number(raw.unrealizedPnl), leverage: number(raw.leverage?.value), marginMode: raw.leverage?.type,
      verifiedAt: time, accountStateAt: stateTime ? new Date(stateTime).toISOString() : null, browserLive: true };
  }

  async function verifyWallet(address) {
    if (!/^0x[a-f\d]{40}$/i.test(address)) throw new Error('Invalid public wallet address');
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 15_000);
    try {
      const response = await fetch('https://api.hyperliquid.xyz/info', { method: 'POST',
        headers: { 'Content-Type': 'application/json' }, signal: controller.signal,
        body: JSON.stringify({ type: 'clearinghouseState', user: address, dex: '' }) });
      if (!response.ok) throw new Error(`Public account read HTTP ${response.status}`);
      const state = await response.json();
      if (!Array.isArray(state.assetPositions)) throw new Error('Account reply has no position array');
      const time = new Date().toISOString(), metadata = positions().find((p) => p.address === address);
      const found = new Map();
      for (const wrapped of state.assetPositions) {
        const row = normalizeLive(address, wrapped.position, metadata, time, state.time);
        if (row) found.set(row.id, row);
      }
      watch.overrides.set(address, { positions: [...found.values()], checkedAt: time });
      watch.liveAt = time;
    } finally { clearTimeout(timer); }
  }

  async function liveTick(singleAddress = null) {
    if (watch.busy || !watch.data || (!singleAddress && (!node('liq-live').checked || document.visibilityState !== 'visible'))) return;
    if (!singleAddress && Date.now() - watch.lastAutoAt < 60_000) return;
    const addresses = singleAddress ? [singleAddress] : [...new Set(filtered().slice(0, watch.limit).map((p) => p.address))].slice(0, 5);
    if (!addresses.length) return;
    watch.busy = true;
    watch.liveError = null;
    render();
    for (const address of addresses) {
      try { await verifyWallet(address); }
      catch (error) { watch.liveError = `Live verification unavailable: ${error.message}. Earlier verified values keep their original times.`; }
    }
    watch.busy = false;
    if (!singleAddress) watch.lastAutoAt = Date.now();
    render();
  }

  async function loadWatch(force = false) {
    node('liq-reload').disabled = true;
    try {
      const response = await fetch(`data/liquidations.json${force ? '?t=' + Date.now() : ''}`, { cache: 'no-cache' });
      if (!response.ok) throw new Error(`Watch HTTP ${response.status}`);
      const data = await response.json();
      if (data.schemaVersion !== 1 || !Array.isArray(data.positions) || !Array.isArray(data.nativeCryptoSymbols) || !data.coverage) throw new Error('Unrecognized crypto watch format');
      watch.data = data;
      for (const [address, entry] of watch.overrides) {
        const checked = data.walletChecks?.[address];
        if (checked && Date.parse(entry.checkedAt) <= Date.parse(checked)) watch.overrides.delete(address);
      }
      const asset = node('liq-asset').value;
      node('liq-asset').innerHTML = '<option value="all">All crypto</option>' + [...new Set(positions().map((p) => p.coin))].sort().map((coin) => `<option value="${esc(coin)}">${esc(coin)}</option>`).join('');
      node('liq-asset').value = [...node('liq-asset').options].some((o) => o.value === asset) ? asset : 'all';
      render();
    } catch (error) {
      node('liq-notice').hidden = false;
      node('liq-notice').textContent = `Could not load the crypto liquidation watch: ${error.message}. Existing rows, if any, retain their verification times.`;
      if (!watch.data) node('liq-freshness').textContent = 'CRYPTO WATCH UNAVAILABLE';
    } finally { node('liq-reload').disabled = false; }
  }

  for (const id of ['liq-asset', 'liq-distance', 'liq-minimum', 'liq-side', 'liq-sort']) node(id).addEventListener('change', () => { watch.limit = 12; render(); });
  node('liq-chart-asset').addEventListener('change', () => { watch.chartAsset = node('liq-chart-asset').value; renderLadder(filtered()); });
  node('more-liquidations').addEventListener('click', () => { watch.limit += 12; render(); });
  node('liq-reload').addEventListener('click', () => loadWatch(true));
  node('liq-live').addEventListener('change', () => liveTick());
  node('liq-rows').addEventListener('click', (event) => { const button = event.target.closest('[data-verify]'); if (button) liveTick(button.dataset.verify); });
  setInterval(() => { if (document.visibilityState === 'visible' && !node('liq-reload').disabled) loadWatch(); }, 60_000);
  setInterval(() => liveTick(), 60_000);
  loadWatch();
})();
