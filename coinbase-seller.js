'use strict';

(() => {
  const el = (id) => document.getElementById(id);
  const state = { data: null, limit: 12, downloadUrl: null };
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const known = (n) => n != null && typeof n !== 'boolean' && Number.isFinite(Number(n));
  const count = (n) => known(n) ? Number(n).toLocaleString('en-US') : '—';
  const btc = (n, digits = 8) => known(n) ? (Number(n) / 1e8).toLocaleString('en-US', { maximumFractionDigits: digits }) : 'Unknown';
  const units = (n) => known(n) ? `${count(n)} BTC` : 'Unknown';
  const pct = (n) => known(n) ? `${(n * 100).toFixed(1)}%` : '—';
  const usd = (n) => {
    if (!known(n)) return '—';
    const a = Math.abs(n), suffix = a >= 1e9 ? 'B' : a >= 1e6 ? 'M' : a >= 1e3 ? 'K' : '';
    return `${n < 0 ? '−' : ''}$${(a / ({ B: 1e9, M: 1e6, K: 1e3 }[suffix] || 1)).toLocaleString('en-US', { maximumFractionDigits: 2 })}${suffix}`;
  };
  const price = (n) => known(n) ? Number(n).toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—';
  const date = (s) => s && Number.isFinite(Date.parse(s)) ? new Date(s).toLocaleString('en-GB', { timeZone: 'UTC', day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }) + ' UTC' : 'Unavailable';
  const day = (s) => String(s || '').slice(0, 10);
  const range = (start, end) => `${day(start)} to ${day(end)} (exclusive, UTC)`;
  const url = (s) => /^https:\/\//i.test(s || '') ? esc(s) : '#';
  const sum = (rows, key) => rows.reduce((total, row) => total + (Number(row[key]) || 0), 0);
  const empty = (cols, text) => `<tr><td colspan="${cols}" class="empty-cell">${esc(text)}</td></tr>`;
  const shortAddress = (s) => s ? `${s.slice(0, 10)}…${s.slice(-7)}` : 'Unspecified';
  const receipt = (id, label = `${id.slice(0, 12)}…`) => `<a href="https://mempool.space/tx/${encodeURIComponent(id)}" target="_blank" rel="noopener noreferrer" title="${esc(id)}">${esc(label)} ↗</a>`;
  const addressLink = (address) => address ? `<a href="https://mempool.space/address/${encodeURIComponent(address)}" target="_blank" rel="noopener noreferrer" title="${esc(address)}">${esc(shortAddress(address))} ↗</a>` : 'No address decoded';
  const bounds = (low, high) => !known(low) || !known(high) ? 'Unknown' : low === high ? btc(low) : `${btc(low)}–${btc(high)}`;
  const btcBounds = (low, high) => known(low) && known(high) ? `${bounds(low, high)} BTC` : 'Unknown';
  const chartEmpty = (text) => `<p class="case-empty">${esc(text)}</p>`;

  function render() {
    const d = state.data, c = d.chain, m = d.mara;
    const hasChain = Array.isArray(c?.daily);
    const forwards = hasChain ? sum(c.daily, 'forwardedLowerSats') : null;
    const upper = hasChain ? sum(c.daily, 'forwardedUpperSats') : null;
    const largestCredit = c?.incoming?.addresses.reduce((max, row) => Math.max(max, row.largestSats || 0), 0);
    const cards = [
      ['LARGEST CREDIT TO ONE WATCHED ADDRESS', btcBounds(largestCredit, largestCredit), c?.completeWindow ? range(c.windowStart, c.windowEndExclusive) : 'No complete address history'],
      ['FORWARDED TO WATCHED HUB / 14 DAYS', c?.completeWindow ? btcBounds(forwards, upper) : 'Unknown', 'On-chain transfer; hub owner unverified'],
      ['CONFIRMED WATCHSET BALANCE', known(c?.confirmedWatchsetBalanceSats) ? `${btc(c.confirmedWatchsetBalanceSats, 4)} BTC` : 'Unknown', hasChain ? `Two addresses · ${date(c.observedAt)}` : 'Beneficial owner unverified'],
      ['MARA / DISCLOSED POST-QUARTER SALES', units(m?.postQuarterSoldBtc), known(m?.postQuarterSoldBtc) ? `${m.saleWindowStart} through ${m.saleWindowEnd}` : 'Primary disclosure unavailable'],
    ];
    el('seller-kpis').innerHTML = cards.map(([label, value, sub]) => `<article class="kpi"><p class="kpi-label">${label}</p><p class="kpi-value">${value}</p><p class="kpi-sub">${esc(sub)}</p></article>`).join('');
    el('seller-verdict').textContent = known(m?.postQuarterSoldBtc) ? `MARA is a lead: its filings confirm it sold BTC, but do not name Coinbase as the execution venue. Public data does not establish a single dominant seller, or that the watched route belongs to MARA.` : 'Public data does not establish a single dominant Coinbase seller. Company disclosure data is unavailable in this snapshot.';
    el('seller-window').textContent = hasChain ? range(c.windowStart, c.windowEndExclusive) : 'ADDRESS HISTORY UNAVAILABLE';
    el('seller-freshness').textContent = `Last collection attempt: ${date(d.generatedAt)} · hourly target`;
    el('seller-build-time').textContent = `Snapshot ${date(d.generatedAt)}`;
    const warnings = [];
    for (const key of ['chain', 'mara', 'market']) {
      const source = d[key];
      if (!source || source.status === 'unavailable') warnings.push(`${key}: ${source?.refreshError || 'source unavailable'}.`);
      if (source?.status === 'retained') warnings.push(`${key}: refresh failed; showing observations from ${date(source.observedAt)}.`);
    }
    if (hasChain && !c.completeWindow) warnings.push('Address history is incomplete; a complete weekly trend is unavailable.');
    if (d.market?.status === 'partial') warnings.push('Coinbase history has missing hourly candles.');
    if (Date.now() - Date.parse(d.generatedAt) > 3 * 36e5) warnings.push('Case snapshot is older than three hours.');
    el('seller-notice').hidden = !warnings.length;
    el('seller-notice').textContent = warnings.join(' ');
    renderChain(); renderMara(); renderMarket(); renderSignals(); renderSources();
  }

  function renderChain() {
    const c = state.data.chain;
    if (!Array.isArray(c?.daily)) {
      el('seller-flow-chart').innerHTML = chartEmpty('Verified address history is unavailable. No zero activity is assumed.');
      el('balance-chart').innerHTML = chartEmpty('Verified address balances are unavailable.');
      el('seller-address-rows').innerHTML = empty(5, 'No current verified address observations are available.');
      el('flow-summary').innerHTML = '';
      el('address-attribution').textContent = '';
      renderLedger(); renderHubSpends();
      return;
    }
    const t = c.trend;
    const change = known(t?.changePct) ? `${t.changePct > 0 ? '+' : ''}${t.changePct.toFixed(0)}%.` : ({ higher: 'Higher than the prior week.', lower: 'Lower than the prior week.', unchanged: 'Unchanged.', indeterminate: 'The ranges overlap.' }[t?.direction] || 'Trend unavailable.');
    const incoming = c.incoming, topAddress = incoming?.addresses[0];
    const incomingNote = topAddress?.txCount ? `${count(topAddress.txCount)} external credits to the same address. ${incoming.singleFunderAddress ? 'All watched credits show the same input address.' : 'The credits were not funded exclusively by one address.'}` : c.completeWindow ? 'No external credits in this window.' : 'Address history is incomplete.';
    el('flow-summary').innerHTML = [
      ['LARGEST WATCHED RECIPIENT / 14 DAYS', btcBounds(topAddress?.receivedSats, topAddress?.receivedSats), incomingNote, topAddress?.txCount ? `${addressLink(topAddress.address)} · ${receipt(topAddress.largestTxid, 'Largest credit')}` : ''],
      ['LATEST 7 DAYS / WATCHED HUB FORWARDING', btcBounds(t?.latest7dSats, t?.latest7dUpperSats ?? t?.latest7dSats), `${btcBounds(t?.previous7dSats, t?.previous7dUpperSats ?? t?.previous7dSats)} in the prior seven completed UTC days. ${change} Actual entity sales pace is unknown.`],
      ['LAST 48 HOURS AT OBSERVATION / HUB', btcBounds(c.forwardedLast48hLowerSats, c.forwardedLast48hUpperSats ?? c.forwardedLast48hLowerSats), `Last observed forwarding: ${date(c.lastForwardAt)}. Confirmed transfers only, as of ${date(c.observedAt)}.`],
      ['DIRECT DEPOSITS TO VERIFIED COINBASE ADDRESSES', btcBounds(c.coinbaseSpecificDepositsSats, c.coinbaseSpecificDepositsUpperSats ?? c.coinbaseSpecificDepositsSats), c.coinbaseTargetCount ? `${count(c.coinbaseTargetCount)} verified recipient labels; terms apply to this watchset only.` : 'No verified Coinbase destination in the watched route. This leaves deposits unknown.'],
    ].map(([label, value, note, link]) => `<article><p class="eyebrow">${label}</p><strong>${value}</strong><p>${esc(note)}${link ? `<br>${link}` : ''}</p></article>`).join('');
    const rows = c.daily, maximum = Math.max(...rows.map((r) => Math.max(r.incomingSats || 0, r.forwardedUpperSats || 0)), 1);
    const width = 650, height = 285, top = 42, bottom = 235, slot = 570 / rows.length;
    el('seller-flow-chart').innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Daily external credits and funding toward the downstream hub, in BTC; not Coinbase-confirmed sales"><rect x="30" y="14" width="8" height="8" fill="#97e5c5"/><text x="44" y="22" class="seller-svg-small">External credits</text><rect x="215" y="14" width="8" height="8" fill="#e8d3a6"/><text x="230" y="22" class="seller-svg-small">Forwarded to hub</text><text x="610" y="22" text-anchor="end" class="seller-svg-small">Max ${btc(maximum)} BTC</text><line x1="30" y1="${bottom}" x2="620" y2="${bottom}" stroke="#304c3d"/>${rows.map((r, i) => {
      const x = 35 + i * slot;
      if (!known(r.incomingSats) || !known(r.forwardedLowerSats)) return `<text x="${x + 10}" y="${bottom - 8}" class="seller-svg-small">?</text>`;
      const inboundHeight = r.incomingSats / maximum * (bottom - top), outboundHeight = r.forwardedLowerSats / maximum * (bottom - top);
      return `<g><title>${esc(r.date)}: ${btc(r.incomingSats)} BTC external credit; ${bounds(r.forwardedLowerSats, r.forwardedUpperSats)} BTC toward hub</title><rect x="${x}" y="${bottom - inboundHeight}" width="${slot * .32}" height="${inboundHeight}" fill="#97e5c5"/><rect x="${x + slot * .35}" y="${bottom - outboundHeight}" width="${slot * .32}" height="${outboundHeight}" fill="#e8d3a6"/>${i % 2 === 0 || i === rows.length - 1 ? `<text x="${x + 8}" y="257" text-anchor="middle" class="seller-svg-small">${r.date.slice(5)}</text>` : ''}</g>`;
    }).join('')}<text x="30" y="279" class="seller-svg-small">${c.completeWindow ? 'Complete watched-address history for this window' : 'Incomplete address history: missing data is not zero'}</text></svg>`;
    const balanceMaximum = Math.max(...c.addresses.map((r) => r.confirmedSats), 1);
    el('balance-chart').innerHTML = `<svg viewBox="0 0 540 285" role="img" aria-label="Confirmed BTC balances of the relay and co-input address; these are not a verified company-wide treasury balance"><text x="25" y="30" class="seller-svg-title">Confirmed UTXO amounts · as observed ${date(c.observedAt)}</text>${c.addresses.map((r, i) => {
      const y = 77 + i * 75, barWidth = r.confirmedSats / balanceMaximum * 280;
      return `<g><title>${esc(r.label)} ${esc(r.address)}: ${btc(r.confirmedSats)} BTC confirmed</title><text x="25" y="${y}" class="seller-svg-small">${esc(r.label)}</text><rect x="25" y="${y + 14}" width="${barWidth}" height="16" fill="${i ? '#e8d3a6' : '#97e5c5'}"/><text x="510" y="${y + 28}" text-anchor="end" class="seller-svg-value">${btc(r.confirmedSats)} BTC</text></g>`;
    }).join('')}<text x="25" y="244" class="seller-svg-title">Current MARA-wide BTC inventory: unknown</text><text x="25" y="265" class="seller-svg-small">Hub balance excluded · block tip ${c.tipHeight}</text></svg>`;
    el('seller-address-rows').innerHTML = c.addresses.map((r) => `<tr><td><span class="address-role">${esc(r.label)}</span><a href="${url(r.sourceUrl)}" target="_blank" rel="noopener noreferrer">${esc(shortAddress(r.address))} ↗</a><span class="address-explanation">${esc(r.attribution)}</span></td><td>${btc(r.confirmedSats)}</td><td>${r.pendingDeltaSats > 0 ? '+' : ''}${btc(r.pendingDeltaSats)}</td><td>${r.completeWindow ? 'Complete window' : 'Partial / unknown'}<span class="subvalue">${count(r.transactionsRead)} transactions read</span></td><td>${r.crossProviderAgreement === true ? 'Mempool + Blockstream agree' : r.crossProviderAgreement === false ? 'Different provider observations' : 'Second provider unavailable'}<span class="subvalue">Observed ${date(r.observedAt)}</span></td></tr>`).join('');
    el('address-attribution').textContent = `${c.coinputProof?.addressesCoSpent ? 'The co-spend relationship was verified' : 'The co-spend relationship is unverified'}. This does not establish beneficial ownership. Downstream hub ${shortAddress(c.hub.address)} has ${btc(c.hub.confirmedSats)} BTC at observation, excluded because its unrelated inventory cannot be assigned to this sender.`;
    renderLedger(); renderHubSpends();
  }

  function renderLedger() {
    const c = state.data.chain, filter = el('seller-tx-filter').value;
    const flows = (c?.flows || []).filter((r) => filter === 'incoming' ? r.externalIncomingSats >= 1e8 : filter === 'forwarding' ? r.hubFundingUpperSats > 0 : true);
    el('ledger-coverage').textContent = `${flows.length} matching confirmed transactions. ${c?.completeWindow ? 'Watched-address history covers the full comparison window.' : 'A complete address-history window is not established.'} Coinbase-specific destination labels: ${c?.coinbaseTargetCount ? count(c.coinbaseTargetCount) : 'unavailable'}.`;
    const fundingLink = c?.incoming?.reusedFundingOutputs?.[0];
    el('ledger-funding-link').hidden = !fundingLink;
    el('ledger-funding-link').innerHTML = fundingLink ? `The ${receipt(fundingLink.earlierTxid, 'earlier credit')} created a ${btc(fundingLink.sats)} BTC output that was used as an input in the ${receipt(fundingLink.laterTxid, 'later credit')}. This links the transactions on-chain; it does not establish who owned the coins.` : '';
    el('seller-tx-rows').innerHTML = flows.slice(0, state.limit).map((r) => {
      const addresses = [...new Set((r.inputs || []).map((input) => input.address))];
      const inputLinks = addresses.slice(0, 4).map((address) => `<span class="subvalue">${addressLink(address)}</span>`).join('');
      return `<tr><td>${date(new Date(r.time * 1000).toISOString())}<span class="subvalue">Block ${count(r.blockHeight)}</span></td><td>${receipt(r.txid)}<span class="subvalue">Miner fee ${btc(r.feeSats)} BTC</span></td><td>${btc(r.externalIncomingSats)}</td><td>${bounds(r.hubFundingLowerSats, r.hubFundingUpperSats)}</td><td>${btc(r.returnedToWatchsetSats)}</td><td>${r.mixedInputs ? 'Mixed inputs / bounds used' : r.knownInputSats ? 'Watched inputs only' : 'External funding'}${inputLinks}${addresses.length > 4 ? `<span class="subvalue">+${addresses.length - 4} more in receipt</span>` : ''}</td></tr>`;
    }).join('') || empty(6, 'No matching confirmed records in the watched-address sample.');
    el('seller-more-txs').hidden = flows.length <= state.limit;
  }

  function renderHubSpends() {
    const trace = state.data.chain?.hubSpends;
    const rows = trace?.receipts || [];
    el('hub-coverage').textContent = trace ? `${rows.filter((r) => r.status === 'confirmed').length} first confirmed spends located for ${trace.outpointCount} observed hub outputs, including any activity today. The refresh checks at most six hub outputs.` : 'An exact outpoint trace is unavailable.';
    el('hub-spend-rows').innerHTML = rows.map((r) => `<tr><td>${receipt(r.txid, `${r.txid.slice(0, 10)}…:${r.vout}`)}<span class="subvalue">${btc(r.sats)} BTC into hub</span></td><td>${r.status === 'confirmed' ? `${receipt(r.spendTxid)}<span class="subvalue">${date(new Date(r.spendTime * 1000).toISOString())}</span><span class="subvalue">${r.singleInput ? 'Only this hub input' : 'Mixed inputs; output ownership unassigned'}</span>` : esc(r.status)}</td><td>${r.nonHubOutputs?.length ? r.nonHubOutputs.slice(0, 4).map((out) => `<div>${addressLink(out.address)} · ${btc(out.sats)} BTC</div>`).join('') + (r.nonHubOutputs.length > 4 ? `<div>+${r.nonHubOutputs.length - 4} in receipt</div>` : '') : r.status === 'confirmed' ? 'None' : '—'}</td><td>${known(r.returnedToHubSats) ? btc(r.returnedToHubSats) : '—'}</td></tr>`).join('') || empty(4, 'No first-hop records in this snapshot.');
  }

  function renderMara() {
    const m = state.data.mara;
    el('mara-letter').href = url(m?.letterUrl || state.data.case.mara.letterUrl);
    if (!known(m?.reportedHoldingsBtc)) {
      el('inventory-chart').innerHTML = chartEmpty('Primary disclosure extraction unavailable; no inventory figure is assumed.');
      el('inventory-bridge-note').textContent = '';
      el('mara-pace').innerHTML = chartEmpty('Company sales pace unavailable.');
      el('mara-fact-rows').innerHTML = empty(3, 'Company disclosures unavailable.');
      return;
    }
    const values = [m.reportedHoldingsBtc, m.postQuarterSoldBtc, m.disclosureOnlyBridgeBtc];
    const labels = [`Reported ${m.asOf}`, `Sold ${m.saleWindowStart} → ${m.saleWindowEnd}`, 'Arithmetic bridge / NOT live inventory'];
    const max = Math.max(...values, 1), colors = ['#97e5c5', '#d79c91', '#e8d3a6'];
    el('inventory-chart').innerHTML = `<svg viewBox="0 0 610 300" role="img" aria-label="Disclosure-only inventory arithmetic: ${values[0]} BTC reported, minus ${values[1]} sold after the quarter, equals ${values[2]} before unreported production and other changes"><text x="25" y="27" class="seller-svg-title">Do not add released collateral again: it was already owned</text>${values.map((value, i) => `<g><text x="25" y="${70 + i * 80}" class="seller-svg-small">${esc(labels[i])}</text><rect x="25" y="${82 + i * 80}" width="${value / max * 370}" height="20" fill="${colors[i]}" ${i === 2 ? 'fill-opacity=".25" stroke="#e8d3a6" stroke-dasharray="4 3"' : ''}/><text x="580" y="${100 + i * 80}" text-anchor="end" class="seller-svg-value">${count(value)} BTC</text></g>`).join('')}</svg>`;
    el('inventory-bridge-note').textContent = m.bridgeNote;
    const ratio = m.q3AverageSalesBtcPerDay > 0 ? ` Approximately ${(m.postQuarterAverageSalesBtcPerDay / m.q3AverageSalesBtcPerDay).toFixed(1)}× the Q3 calendar-day average.` : '';
    el('mara-pace').innerHTML = `<article class="pace-item"><span>Q3 / ${m.q3Days} DAYS</span><strong>${m.q3AverageSalesBtcPerDay.toFixed(1)} BTC/day</strong><p>${count(m.q3SoldBtc)} BTC sold during the third quarter.</p></article><article class="pace-item"><span>POST-QUARTER DISCLOSURE INTERVAL / UP TO ${m.postQuarterDaysInclusive} DAYS</span><strong>${m.postQuarterAverageSalesBtcPerDay.toFixed(1)} BTC/day</strong><p>${count(m.postQuarterSoldBtc)} BTC disclosed sold by ${esc(m.saleWindowEnd)}.${ratio} Actual daily execution dates are not reported.</p></article><article class="pace-item"><span>Q3 PRODUCTION / HISTORICAL CONTEXT</span><strong>${m.miningBtcPerDayQ3.toFixed(1)} BTC/day</strong><p>Mining can replenish inventory. This is the Q3 average, not a live production estimate.</p></article>`;
    const rows = [
      ['Reported BTC holdings', `${count(m.reportedHoldingsBtc)} BTC`, `As of ${m.asOf}; not current`],
      ['Post-quarter BTC sold', `${count(m.postQuarterSoldBtc)} BTC`, `${m.saleWindowStart} through disclosure ${m.saleWindowEnd}; not exclusively the latest 14 days`],
      ['Current company-wide BTC', 'Unknown', 'The watched addresses and subtraction bridge do not establish this'],
      ['Bitcoin-backed loans repaid', usd(m.repaidDebtUsd), 'Completed according to the November 9 disclosure'],
      ['BTC collateral returned after repayment', units(m.collateralReturnedBtc), 'Previously owned. Do not add it to the treasury arithmetic a second time.'],
      ['Share repurchase authorization', usd(m.buybackAuthorizationUsd), 'Optional program; not a committed spend or completed repurchase'],
      ['Additional notes priced', usd(m.additionalNotesPricedUsd), 'November 17 financing disclosure; not assumed closed or fully available as cash'],
      ['Expected acquisition closing', m.acquisitionExpectedClose || 'Not extracted', 'Forward-looking timing in the November 17 filing; subject to conditions'],
      ['Further BTC monetization', m.continuesMonetization ? 'Explicitly intended' : 'Not verified', 'Company-stated plan, not a daily sale schedule or fixed exhaustion date'],
    ];
    el('mara-fact-rows').innerHTML = rows.map((r) => `<tr><td>${esc(r[0])}</td><td>${esc(r[1])}</td><td>${esc(r[2])}</td></tr>`).join('');
  }

  function renderMarket() {
    const m = state.data.market;
    if (!m?.daily) {
      el('coinbase-tape').innerHTML = '';
      el('coinbase-market-chart').innerHTML = chartEmpty('Coinbase market data is unavailable. No customer-level selling volume is inferred.');
      renderEtf();
      return;
    }
    const tape = m.tape;
    const tapeTime = (s) => s && Number.isFinite(Date.parse(s)) ? new Date(s).toISOString().slice(11, 19) : '—';
    const cards = [
      ['LATEST COINBASE BTC-USD', price(m.lastUsd), `Observed ${date(m.observedAt)}`],
      ['VENUE-WIDE VOLUME / ROLLING 24H', `${count(m.volume24hBtc?.toFixed(2))} BTC`, 'All buyers and sellers; not a tracked entity’s volume'],
      ['RECENT SAMPLE / AGGRESSOR SELL SHARE', pct(tape?.aggressorSellShare), `${count(tape?.tradeCount)} public trades · ${day(tape?.windowStart)} ${tapeTime(tape?.windowStart)} to ${day(tape?.windowEnd)} ${tapeTime(tape?.windowEnd)} UTC. Maker buy = aggressor sell.`],
    ];
    el('coinbase-tape').innerHTML = cards.map(([label, value, note]) => `<article><span>${label}</span><strong>${value}</strong><p>${esc(note)}</p></article>`).join('');
    const rows = m.daily, width = 1050, height = 300, left = 40, right = 950, top = 45, bottom = 235;
    const valid = rows.filter((r) => known(r.closeUsd));
    const min = valid.length ? Math.min(...valid.map((r) => r.closeUsd)) : 0;
    const max = valid.length ? Math.max(...valid.map((r) => r.closeUsd)) : 1;
    const spread = Math.max(max - min, 1), maxVolume = Math.max(...rows.map((r) => r.volumeBtc || 0), 1);
    const slot = (right - left) / rows.length;
    let line = '', disconnected = true;
    rows.forEach((r, i) => {
      if (!known(r.closeUsd) || r.hourCount !== 24) { disconnected = true; return; }
      line += `${disconnected ? 'M' : 'L'}${left + i * slot + slot / 2},${top + (max - r.closeUsd) / spread * (bottom - top)} `;
      disconnected = false;
    });
    el('coinbase-market-chart').innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Coinbase BTC-USD daily closing prices on a cropped price axis and BTC volume bars on a separate volume scale"><text x="${left}" y="21" class="seller-svg-title">Line: daily close, cropped USD scale ${price(min)}–${price(max)}</text><text x="${right}" y="21" text-anchor="end" class="seller-svg-small">Bars: BTC volume · max ${count(maxVolume.toFixed(0))}</text>${rows.map((r, i) => {
      const h = (r.volumeBtc || 0) / maxVolume * 155, x = left + i * slot;
      return `<g><title>${esc(r.date)}: ${price(r.closeUsd)} last observed close; ${count(r.volumeBtc?.toFixed(2))} BTC observed volume; ${r.hourCount}/24 hourly bars</title><rect x="${x + 5}" y="${bottom - h}" width="${Math.max(4, slot - 10)}" height="${h}" fill="${r.hourCount === 24 ? '#527466' : '#e8d3a6'}" opacity=".42"/><text x="${x + slot / 2}" y="259" text-anchor="middle" class="seller-svg-small">${r.date.slice(5)}${r.hourCount === 24 ? '' : '*'}</text></g>`;
    }).join('')}<path d="${line}" stroke="#e8d3a6" stroke-width="2.2" fill="none"/><line x1="${left}" y1="${bottom}" x2="${right}" y2="${bottom}" stroke="#36513f"/><text x="${left}" y="286" class="seller-svg-small">${m.hourlyBars}/${m.expectedHourlyBars} hourly candles · gaps/partial days are not drawn as complete price observations</text></svg>`;
    renderEtf();
  }

  function renderEtf() {
    const e = state.data.etf;
    if (!e?.daily?.length) {
      el('etf-context').innerHTML = '<h3>ETF flow context / source unavailable</h3><p>The public ETF flow page could not be refreshed. No zero flows or ended-selling signal is assumed. ETF redemptions and custody/settlement are alternative sources of Coinbase-related movement; they do not identify a proprietary seller.</p>';
      return;
    }
    const complete = e.daily.filter((r) => r.completeFunds && known(r.totalUsdMillions));
    const latest = e.daily.at(-1);
    const dollarMillions = (n) => known(n) ? usd(Number(n) * 1e6) : 'Unavailable';
    el('etf-context').innerHTML = `<h3>US spot BTC ETF context / USD fund flows</h3><p>${e.status === 'retained' ? 'Last available observations; automated refresh unavailable. ' : ''}${complete.length} complete reporting days from ${esc(e.daily[0].date)} to ${esc(latest.date)}. Net flows on complete days: <strong>${dollarMillions(complete.length ? sum(complete, 'totalUsdMillions') : null)}</strong>. Latest listed day ${esc(latest.date)}: ${dollarMillions(latest.totalUsdMillions)} total, ${dollarMillions(latest.ibitUsdMillions)} IBIT${latest.completeFunds ? '.' : ' (partial reporting).'}</p><p>Fund flows measure subscriptions and redemptions, not Coinbase execution or BlackRock’s own treasury activity. <a href="${url(e.sourceUrl)}" target="_blank" rel="noopener noreferrer">Farside source ↗</a></p>`;
  }

  function renderSignals() {
    const c = state.data.chain, m = state.data.mara;
    const caseData = state.data.case;
    const signals = [
      ['DEBT REPAYMENT', 'One cash need may have passed', known(m?.repaidDebtUsd) ? `MARA used sale proceeds to repay ${usd(m.repaidDebtUsd)} of BTC-backed debt. The loan repayment removed that specific cash need.` : 'Check the primary disclosure for the amount and timing of loan repayment.', caseData.mara.letterUrl],
      ['FUTURE SALES', 'Look for a change in treasury policy', m?.continuesMonetization ? 'MARA says it intends to keep using BTC to raise cash for AI infrastructure, convertible-note puts, and potential buybacks.' : 'The case snapshot has no verified update on intended monetization.', caseData.mara.letterUrl],
      ['WATCHED ROUTE', 'Watch for fresh deposits and forwarding', `${c?.lastForwardAt ? `Last observed hub payment: ${date(c.lastForwardAt)}.` : 'No last payment time is available in this snapshot.'} Multiple quiet windows plus no replenishment would support a slowdown on this route. A new venue-linked receipt would be stronger evidence.`, 'https://mempool.space/address/' + caseData.watchedAddresses[0].address],
      ['TREASURY INVENTORY', 'Check the next dated holdings disclosure', 'A new holdings figure with production, sales, and pledged BTC would narrow the estimate of inventory available to sell.', m?.filingsIndexUrl || 'https://ir.mara.com/sec-filings/all-sec-filings'],
      ['ALTERNATIVE FINANCING', 'Check whether new financing closed', known(m?.additionalNotesPricedUsd) ? `${usd(m.additionalNotesPricedUsd)} of additional notes were priced${m.acquisitionExpectedClose ? ` for an expected ${m.acquisitionExpectedClose} closing` : ''}. Check the next filing for the closing and actual use of proceeds; financing could reduce the need for near-term BTC sales.` : 'Check the financing filing and subsequent updates for the closing and use of proceeds.', caseData.mara.financingUrl],
      ['BROADER MARKET', 'Compare ETF outflows and liquidations', 'ETF redemptions, custody movements, and liquidations are other explanations for selling pressure. Watch whether ETF outflows and liquidation pressure ease alongside the watched transfers.', 'index.html#liquidations'],
    ];
    el('end-signals').innerHTML = signals.map(([tag, title, body, link]) => `<article><span class="signal-tag">${tag}</span><h3>${title}</h3><p>${esc(body)}</p>${link.startsWith('https://') ? `<a href="${url(link)}" target="_blank" rel="noopener noreferrer">Underlying evidence ↗</a>` : `<a href="${esc(link)}">Open liquidation watch →</a>`}</article>`).join('');
    el('end-bottom-line').textContent = 'No reliable end date. A slowdown in this relay would matter to the case, but it would not show that the seller has run out of BTC. Look for dated company sales and holdings disclosures together with a verified Coinbase route.';
  }

  function renderSources() {
    const d = state.data, c = d.chain, m = d.mara;
    const sources = [
      ['PRIMARY COMPANY DISCLOSURE', 'MARA Q3 shareholder letter', 'Confirms post-quarter BTC sales and future monetization intent. Reporting as of September 30, published November 9; not a current on-chain balance.', m?.letterUrl || d.case.mara.letterUrl],
      ['PRIMARY REGULATORY FILING', 'MARA Q3 10-Q', 'Company inventory, borrowing/collateral context, and subsequent events. Coinbase is named as a lender; that does not establish execution venue for the disclosed sales.', m?.reportUrl || d.case.mara.reportUrl],
      ['PRIMARY FINANCING UPDATE', 'November 17 additional-notes pricing', 'Discloses the $185M offering and expected acquisition closing date, subject to conditions.', m?.financingUrl || d.case.mara.financingUrl],
      ['ON-CHAIN TRANSACTIONS / PUBLIC INDEXERS', 'Mempool.space + Blockstream', `Address balances and confirmed transactions. Observed ${date(c?.observedAt)}. Transaction amounts can be verified independently; off-chain beneficial ownership cannot.`, 'https://mempool.space/address/' + d.case.watchedAddresses[0].address],
      ['ATTRIBUTION LEAD / SECONDARY REPORT', 'Published MARA relay report', 'October 19 report links the relay route to MARA-labeled wallets. The historical report is the attribution lead; the current watched transactions are independently queried.', d.case.watchedAddresses[0].source],
      ['VENUE PRIMARY DATA', 'Coinbase Exchange public API', 'Anonymous public trades and BTC-USD candles. The documented trade side is maker side, reversed for aggressor classification. No customer name is exposed.', 'https://docs.cdp.coinbase.com/exchange/reference/exchangerestapi_getproducttrades'],
      ...(d.case.otherEvidence || []).map((r) => [r.sourceType.toUpperCase(), r.title, `${r.date}: ${r.finding}`, r.url]),
    ];
    el('seller-source-list').innerHTML = sources.map(([type, title, note, link]) => `<article><p class="eyebrow">${esc(type)}</p><h3>${esc(title)}</h3><p>${esc(note)}</p><a href="${url(link)}" target="_blank" rel="noopener noreferrer">Open source ↗</a></article>`).join('');
  }

  async function fetchCase(path) {
    const response = await fetch(path, { cache: 'no-cache', signal: AbortSignal.timeout(8000) });
    if (!response.ok) throw new Error(`Case HTTP ${response.status}`);
    const data = await response.json();
    if (data.schemaVersion !== 1 || !data.case || !Number.isFinite(Date.parse(data.generatedAt))) throw new Error('Unrecognized investigation data');
    return data;
  }

  async function load() {
    el('seller-reload').disabled = true;
    try {
      const paths = ['data/coinbase_seller.json'];
      // Scheduled commits can update main without rebuilding the branch-based Pages site.
      if (location.hostname === 'glitch46.github.io' && location.pathname.startsWith('/hyperliquid-cat-desk/')) {
        paths.push('https://raw.githubusercontent.com/glitch46/hyperliquid-cat-desk/main/data/coinbase_seller.json');
      }
      const results = await Promise.allSettled(paths.map(fetchCase));
      const snapshots = results.filter((result) => result.status === 'fulfilled').map((result) => result.value);
      if (!snapshots.length) throw results[0].reason;
      if (state.data) snapshots.push(state.data);
      state.data = snapshots.sort((a, b) => Date.parse(b.generatedAt) - Date.parse(a.generatedAt))[0];
      render();
      if (state.downloadUrl) URL.revokeObjectURL(state.downloadUrl);
      state.downloadUrl = URL.createObjectURL(new Blob([JSON.stringify(state.data, null, 2)], { type: 'application/json' }));
      el('seller-download').href = state.downloadUrl;
    } catch (error) {
      el('seller-notice').hidden = false;
      el('seller-notice').textContent = `Could not load the investigation: ${error.message}. Previous observations, if displayed, retain their original dates.`;
      if (!state.data) el('seller-freshness').textContent = 'CASE SNAPSHOT UNAVAILABLE';
    } finally { el('seller-reload').disabled = false; }
  }

  el('seller-reload').addEventListener('click', load);
  el('seller-tx-filter').addEventListener('change', () => { state.limit = 12; if (state.data) renderLedger(); });
  el('seller-more-txs').addEventListener('click', () => { state.limit += 12; renderLedger(); });
  setInterval(() => { if (document.visibilityState === 'visible' && !el('seller-reload').disabled) load(); }, 600_000);
  load();
})();
