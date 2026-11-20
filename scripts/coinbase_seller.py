#!/usr/bin/env python3
"""Bitcoin seller investigation: integer-satoshi flows, public filings, venue context."""
import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import html
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SAT = 100_000_000
DAY = 86_400
MEMPOOL = 'https://mempool.space/api'
BLOCKSTREAM = 'https://blockstream.info/api'
COINBASE = 'https://api.exchange.coinbase.com'
FARSIDE = 'https://farside.co.uk/btc/'


def stamp(ts=None):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts is not None else datetime.now(timezone.utc).isoformat()


def window(now=None):
    now = now or datetime.now(timezone.utc)
    end = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int((end - timedelta(days=14)).timestamp()), int(end.timestamp())


def finite(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


class PublicData:
    def __init__(self, max_requests=80):
        self.calls = 0
        self.maximum = max_requests
        self.last = 0

    def get(self, url, json_data=True):
        allowed = {'mempool.space', 'blockstream.info', 'api.exchange.coinbase.com', 'farside.co.uk', 'ir.mara.com'}
        if urllib.parse.urlsplit(url).hostname not in allowed:
            raise ValueError('Unapproved public data source')
        for attempt in range(2):
            if self.calls >= self.maximum:
                raise RuntimeError('Public request budget reached')
            time.sleep(max(0, .4 - (time.monotonic() - self.last)))
            self.last = time.monotonic()
            self.calls += 1
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json,text/html'})
            try:
                with urllib.request.urlopen(req, timeout=25) as response:
                    text = response.read().decode('utf-8')
                    return json.loads(text) if json_data else text
            except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                code = getattr(exc, 'code', None)
                if attempt == 0 and code not in (400, 401, 403, 404):
                    time.sleep(5 if code == 429 else 2)
                    continue
                raise RuntimeError(f'{urllib.parse.urlsplit(url).hostname}: HTTP {code}' if code else 'Public source request failed') from None


def sats(value):
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError('Bitcoin amounts must be non-negative integer satoshis')
    return value


def address_balance(raw):
    chain, pending = raw['chain_stats'], raw['mempool_stats']
    funded, spent = sats(chain['funded_txo_sum']), sats(chain['spent_txo_sum'])
    if spent > funded:
        raise ValueError('Address spent total exceeds funded total')
    return {'confirmedSats': funded - spent, 'pendingDeltaSats': sats(pending['funded_txo_sum']) - sats(pending['spent_txo_sum']),
            'confirmedTxCount': int(chain['tx_count']), 'pendingTxCount': int(pending['tx_count']),
            'lifetimeReceivedSats': funded, 'lifetimeSpentSats': spent}


def normalize_tx(raw):
    status = raw['status']
    if not status.get('confirmed'):
        return None
    inputs = [{'address': (item.get('prevout') or {}).get('scriptpubkey_address'),
               'sats': sats((item.get('prevout') or {}).get('value', 0)),
               'txid': item.get('txid'), 'vout': item.get('vout')} for item in raw['vin']]
    outputs = [{'address': item.get('scriptpubkey_address'), 'sats': sats(item['value']), 'vout': i}
               for i, item in enumerate(raw['vout'])]
    fee = sats(raw['fee'])
    if not any(item.get('is_coinbase') for item in raw['vin']) and sum(row['sats'] for row in inputs) - sum(row['sats'] for row in outputs) != fee:
        raise ValueError('Transaction inputs/outputs do not reconcile to the fee')
    return {'txid': raw['txid'], 'time': int(status['block_time']), 'blockHeight': int(status['block_height']),
            'blockHash': status.get('block_hash'), 'inputs': inputs, 'outputs': outputs, 'feeSats': fee}


def funding_bounds(sender_input, other_input, recipient_output):
    return max(0, recipient_output - other_input), min(sender_input, recipient_output)


def flow(tx, known, hub, coinbase_targets):
    source = sum(row['sats'] for row in tx['inputs'] if row['address'] in known)
    other = sum(row['sats'] for row in tx['inputs'] if row['address'] not in known)
    back = sum(row['sats'] for row in tx['outputs'] if row['address'] in known)
    forwarded = sum(row['sats'] for row in tx['outputs'] if row['address'] == hub)
    cb = sum(row['sats'] for row in tx['outputs'] if row['address'] in coinbase_targets)
    low, high = funding_bounds(source, other, forwarded) if source else (0, 0)
    cb_low, cb_high = funding_bounds(source, other, cb) if source and coinbase_targets else (None, None)
    return {'txid': tx['txid'], 'time': tx['time'], 'blockHeight': tx['blockHeight'],
            'knownInputSats': source, 'otherInputSats': other, 'returnedToWatchsetSats': back,
            'netWatchsetDebitIncludingFeesSats': source - back,
            'externalIncomingSats': back if source == 0 else 0,
            'hubOutputSats': forwarded if source else 0, 'hubFundingLowerSats': low, 'hubFundingUpperSats': high,
            'coinbaseFundingLowerSats': cb_low, 'coinbaseFundingUpperSats': cb_high,
            'feeSats': tx['feeSats'], 'mixedInputs': bool(source and other),
            'inputs': tx['inputs'],
            'destinations': [row for row in tx['outputs'] if row['address'] not in known],
            'watchsetOutputs': [row for row in tx['outputs'] if row['address'] in known],
            'sourceUrl': MEMPOOL.replace('/api', '') + '/tx/' + tx['txid']}


def summarize_incoming(flows, known, end, complete):
    if not complete:
        return None
    receipts = [row for row in flows if row['time'] < end and row['externalIncomingSats'] > 0]
    addresses = []
    for address in sorted(known):
        credits = [(out['sats'], row) for row in receipts for out in row['watchsetOutputs'] if out['address'] == address]
        totals = {}
        for amount, row in credits:
            totals[row['txid']] = totals.get(row['txid'], 0) + amount
        biggest = max(totals, key=totals.get) if totals else None
        addresses.append({'address': address, 'receivedSats': sum(totals.values()), 'txCount': len(totals),
                          'largestSats': totals[biggest] if biggest else None, 'largestTxid': biggest})
    input_sets = [{item['address'] for item in row['inputs'] if item['address']} for row in receipts]
    single_funder = next(iter(input_sets[0])) if input_sets and len(input_sets[0]) == 1 and all(
        inputs == input_sets[0] and all(item['address'] for item in row['inputs']) for inputs, row in zip(input_sets, receipts)) else None
    external_outputs = {(row['txid'], out['vout']): out for row in receipts for out in row['destinations'] if 'vout' in out}
    reused = []
    for row in receipts:
        for item in row['inputs']:
            outpoint = (item.get('txid'), item.get('vout'))
            out = external_outputs.get(outpoint)
            if out and out['sats'] == item['sats'] and out['address'] == item['address']:
                reused.append({'earlierTxid': outpoint[0], 'vout': outpoint[1], 'laterTxid': row['txid'],
                               'address': out['address'], 'sats': out['sats']})
    return {'addresses': sorted(addresses, key=lambda row: -row['receivedSats']), 'singleFunderAddress': single_funder,
            'txCount': len(receipts), 'reusedFundingOutputs': reused}


def get_hub_spends(client, flows, hub, limit=6):
    """Follow exact hub outpoints to their first confirmed spend; do not infer wallet clusters."""
    outputs = [(row, out) for row in flows if row['hubFundingUpperSats'] > 0
               for out in row['destinations'] if out['address'] == hub and out['sats'] > 0]
    results, outspends = [], {}
    for row, out in outputs[:limit]:
        txid = row['txid']
        result = {'txid': txid, 'vout': out['vout'], 'sats': out['sats'], 'status': 'unavailable'}
        try:
            if txid not in outspends:
                outspends[txid] = client.get(f'{MEMPOOL}/tx/{txid}/outspends')
            spend = outspends[txid][out['vout']]
            if spend['spent'] and spend['status'].get('confirmed'):
                raw = client.get(MEMPOOL + '/tx/' + spend['txid'])
                tx = normalize_tx(raw)
                expected = {'txid': txid, 'vout': out['vout'], 'address': hub, 'sats': out['sats']}
                if not tx or tx['txid'] != spend['txid'] or tx['inputs'][spend['vin']] != expected:
                    raise ValueError('Spending input did not match the requested outpoint')
                result.update(status='confirmed', spendTxid=tx['txid'], spendTime=tx['time'],
                              singleInput=len(tx['inputs']) == 1,
                              nonHubOutputs=[item for item in tx['outputs'] if item['address'] != hub],
                              returnedToHubSats=sum(item['sats'] for item in tx['outputs'] if item['address'] == hub))
            else:
                result['status'] = 'pending' if spend['spent'] else 'unspent'
        except (RuntimeError, ValueError, KeyError, IndexError, TypeError):
            pass
        results.append(result)
    return {'outpointCount': len(outputs), 'receipts': results}


def read_history(client, address, start, pages=8):
    records = {}
    cursor = None
    complete = False
    oldest = None
    for _ in range(pages):
        url = MEMPOOL + '/address/' + address + '/txs/chain' + ('/' + cursor if cursor else '')
        batch = client.get(url)
        if not isinstance(batch, list):
            raise ValueError('Unexpected Bitcoin history response')
        for raw in batch:
            row = normalize_tx(raw)
            if row:
                records[row['txid']] = row
                oldest = min(oldest, row['time']) if oldest is not None else row['time']
        if len(batch) < 25 or (oldest is not None and oldest < start):
            complete = True
            break
        next_cursor = batch[-1]['txid']
        if next_cursor == cursor:
            break
        cursor = next_cursor
    return list(records.values()), {'completeWindow': complete, 'transactionsRead': len(records), 'oldestReadAt': stamp(oldest) if oldest else None}


def trend(flows, start, end, complete):
    if not complete:
        return {'status': 'incomplete', 'previous7dSats': None, 'latest7dSats': None, 'changePct': None}
    middle = end - 7 * DAY
    def totals(lo, hi):
        rows = [row for row in flows if lo <= row['time'] < hi]
        return tuple(sum(row[key] for row in rows) for key in ('hubFundingLowerSats', 'hubFundingUpperSats'))
    previous, previous_upper = totals(start, middle)
    latest, latest_upper = totals(middle, end)
    exact = previous == previous_upper and latest == latest_upper
    direction = ('higher' if latest > previous_upper else 'lower' if latest_upper < previous else
                 'unchanged' if exact else 'indeterminate')
    return {'status': 'exact_watchset_flow' if exact else 'funding_lower_bounds', 'previous7dSats': previous,
            'latest7dSats': latest, 'previous7dUpperSats': previous_upper, 'latest7dUpperSats': latest_upper,
            'changePct': (latest / previous - 1) * 100 if exact and previous else None, 'direction': direction,
            'meaning': 'Watched-address funding toward the configured hub, not entity-wide selling or verified Coinbase deposits.'}


def get_chain(client, case, start, end):
    now = int(time.time())
    known = {row['address'] for row in case['watchedAddresses']}
    for address in known | {case['hubAddress']}:
        if not re.fullmatch(r'(?:bc1[a-z0-9]{25,87}|[13][A-Za-z0-9]{25,40})', address):
            raise ValueError('Invalid configured Bitcoin address')
    tip = int(client.get(MEMPOOL + '/blocks/tip/height', json_data=False))
    addresses, records = [], {}
    for item in case['watchedAddresses']:
        raw = client.get(MEMPOOL + '/address/' + item['address'])
        balance = address_balance(raw)
        try:
            check = address_balance(client.get(BLOCKSTREAM + '/address/' + item['address']))
            agreement = check['confirmedSats'] == balance['confirmedSats'] and check['confirmedTxCount'] == balance['confirmedTxCount']
        except RuntimeError:
            agreement = None
        history, coverage = read_history(client, item['address'], min(start, now - 2 * DAY))
        addresses.append({**item, **balance, **coverage, 'observedAt': stamp(), 'crossProviderAgreement': agreement,
                          'sourceUrl': 'https://mempool.space/address/' + item['address']})
        for tx in history:
            records[tx['txid']] = tx
    proof = normalize_tx(client.get(MEMPOOL + '/tx/' + case['coinputProofTxid']))
    coinput = known.issubset({row['address'] for row in proof['inputs']}) if proof else False
    targets = {row['address'] for row in case.get('coinbaseTargets', [])
               if row.get('verified') is True and row.get('source') and row.get('checkedAt')}
    if coinput:
        records[proof['txid']] = proof
    flows = [flow(tx, known, case['hubAddress'], targets) for tx in records.values() if tx['time'] >= start]
    flows.sort(key=lambda row: row['time'], reverse=True)
    complete = all(row['completeWindow'] for row in addresses)
    daily = []
    for timestamp in range(start, end, DAY):
        rows = [row for row in flows if timestamp <= row['time'] < timestamp + DAY]
        daily.append({'date': stamp(timestamp)[:10], 'incomingSats': sum(row['externalIncomingSats'] for row in rows) if complete else None,
                      'forwardedLowerSats': sum(row['hubFundingLowerSats'] for row in rows) if complete else None,
                      'forwardedUpperSats': sum(row['hubFundingUpperSats'] for row in rows) if complete else None,
                      'confirmedTxCount': len(rows) if complete else None})
    forwards = [row for row in flows if row['hubFundingUpperSats'] > 0]
    last = max((row['time'] for row in forwards), default=None)
    hub_stats = address_balance(client.get(MEMPOOL + '/address/' + case['hubAddress']))
    last_48h = [row for row in flows if now - 2 * DAY <= row['time'] <= now]
    return {'status': 'ok' if complete else 'partial', 'observedAt': stamp(), 'tipHeight': tip,
            'windowStart': stamp(start), 'windowEndExclusive': stamp(end), 'completeWindow': complete,
            'addresses': addresses, 'confirmedWatchsetBalanceSats': sum(row['confirmedSats'] for row in addresses),
            'pendingWatchsetDeltaSats': sum(row['pendingDeltaSats'] for row in addresses),
            'currentEntityHoldingsSats': None, 'coinbaseSpecificDepositsSats': None if not targets or not complete else sum((row['coinbaseFundingLowerSats'] or 0) for row in flows if row['time'] < end),
            'coinbaseSpecificDepositsUpperSats': None if not targets or not complete else sum((row['coinbaseFundingUpperSats'] or 0) for row in flows if row['time'] < end),
            'coinbaseTargetCount': len(targets), 'coinputProof': {'txid': case['coinputProofTxid'], 'addressesCoSpent': coinput,
                'sourceUrl': 'https://mempool.space/tx/' + case['coinputProofTxid'], 'meaning': 'Co-spend relationship, not beneficial ownership verification.'},
            'hub': {'address': case['hubAddress'], 'label': case['hubLabel'], 'note': case['hubNote'],
                    'confirmedSats': hub_stats['confirmedSats'], 'includedInWatchsetBalance': False},
            'flows': flows, 'daily': daily, 'trend': trend(flows, start, end, complete),
            'incoming': summarize_incoming(flows, known, end, complete),
            'lastForwardAt': stamp(last) if last else None,
            'hoursSinceLastForward': (now - last) / 3600 if last else None,
            'forwardedLast48hLowerSats': sum(row['hubFundingLowerSats'] for row in last_48h) if complete else None,
            'forwardedLast48hUpperSats': sum(row['hubFundingUpperSats'] for row in last_48h) if complete else None,
            'attribution': {'maraAssociation': 'reported_by_secondary_source', 'watchsetLink': 'confirmed_coinput_relationship' if coinput else 'unverified',
                            'maraBeneficialOwnershipVerified': False, 'coinbaseRoutingVerified': bool(targets), 'singleEntityMarketDominanceVerified': False}}


def text_only(source):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', source)))


def get_mara(client, case):
    config = case['mara']
    text = text_only(client.get(config['letterUrl'], json_data=False))
    if '2026' not in text or 'September 30' not in text:
        raise ValueError('Pinned MARA reporting period did not match')

    def extract(pattern):
        match = re.search(pattern, text, re.I)
        if not match:
            raise ValueError('Required MARA disclosure field could not be verified')
        return int(match.group(1).replace(',', ''))

    holdings = extract(r'held\s+(?:a total of\s+)?([\d,]+)\s+bitcoin')
    sold = extract(r'(?:After|Subsequent\s+to)\s+quarter\s*[-–−]?\s*end.{0,100}?sold\s+([\d,]+)\s+bitcoin')
    mined = extract(r'(?:mined|produced)\s+([\d,]+)\s+BTC')
    quarterly_sales = extract(r'(?:We\s+)?sold\s+([\d,]+)\s+BTC')
    collateral_returned = extract(r'return of\s+([\d,]+)\s+bitcoin previously pledged')
    quarterly_days = (datetime.fromisoformat(config['quarterEnd']) - datetime.fromisoformat(config['quarterStart'])).days + 1
    post_days = (datetime.fromisoformat(config['postQuarterEnd']) - datetime.fromisoformat(config['postQuarterStart'])).days + 1
    intent = 'continue using bitcoin to build cash' in text.lower() or 'continue to monetize bitcoin' in text.lower()
    debt = re.search(r'repaid\s+\$\s*([\d,.]+)\s*(?:million|M\b)\s+of\s+(?:BTC|Bitcoin)[-–\s]backed debt', text, re.I)
    if not debt:
        raise ValueError('MARA debt repayment disclosure could not be matched')
    financing = text_only(client.get(config['financingUrl'], json_data=False))
    debt_offer = bool(re.search(r'\$\s*185\s*million', financing, re.I))
    return {'status': 'ok', 'observedAt': stamp(), 'asOf': config['quarterEnd'], 'publishedAt': config['publicationDate'],
            'letterUrl': config['letterUrl'], 'reportUrl': config['reportUrl'], 'financingUrl': config['financingUrl'],
            'reportedHoldingsBtc': holdings, 'postQuarterSoldBtc': sold,
            'saleWindowStart': config['postQuarterStart'], 'saleWindowEnd': config['postQuarterEnd'],
            'disclosureOnlyBridgeBtc': holdings - sold, 'currentHoldingsBtc': None,
            'bridgeNote': 'Arithmetic only: quarter-end holdings minus disclosed post-quarter sales. Excludes subsequent mining, other purchases/sales, custody changes, and later disclosures; not a current balance. Collateral released is not newly acquired BTC.',
            'q3MinedBtc': mined, 'q3SoldBtc': quarterly_sales, 'q3Days': quarterly_days, 'postQuarterDaysInclusive': post_days,
            'q3AverageSalesBtcPerDay': quarterly_sales / quarterly_days,
            'postQuarterAverageSalesBtcPerDay': sold / post_days,
            'miningBtcPerDayQ3': mined / quarterly_days,
             'continuesMonetization': intent, 'repaidDebtUsd': int(Decimal(debt[1].replace(',', '')) * 1_000_000),
             'collateralReturnedBtc': collateral_returned,
            'buybackAuthorizationUsd': 500_000_000 if re.search(r'\$\s*500(?:\.0)?\s*(?:million|M\b)', text, re.I) else None,
            'additionalNotesPricedUsd': 185_000_000 if debt_offer else None,
            'acquisitionExpectedClose': '2026-11-27' if 'November 27, 2026' in financing else None,
             'filingsIndexUrl': 'https://ir.mara.com/sec-filings/all-sec-filings',
            'venueExecutionVerified': False,
            'finding': 'MARA is a confirmed disclosed BTC seller and explicitly plans further monetization. The filing does not identify a Coinbase execution account, prove sole-seller dominance, or provide today’s BTC inventory.'}


class Tables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables, self.table, self.row, self.cell = [], None, None, None

    def handle_starttag(self, tag, attrs):
        if tag == 'table' and self.table is None:
            self.table = []
        elif self.table is not None and tag == 'tr':
            self.row = []
        elif self.row is not None and tag in ('td', 'th'):
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split()))
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            self.table.append(self.row)
            self.row = None
        elif tag == 'table' and self.table is not None:
            self.tables.append(self.table)
            self.table = None


def parse_flow_number(value):
    text = value.strip().replace(',', '').replace('$', '')
    if text in ('', '-', '—', '–'):
        return None
    negative = text.startswith('(') and text.endswith(')')
    result = finite(text.strip('()'))
    return -result if negative and result is not None else result


def parse_etf(source, start, end):
    parser = Tables()
    parser.feed(source)
    for table in parser.tables:
        headers = next((row for row in table if 'IBIT' in row and any(cell.lower() == 'total' for cell in row)), None)
        if not headers:
            continue
        ibit_index = headers.index('IBIT')
        total_index = next(i for i, cell in enumerate(headers) if cell.lower() == 'total')
        days = []
        for row in table:
            if not row:
                continue
            try:
                date = datetime.strptime(row[0], '%d %b %Y').replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if not start <= date.timestamp() < end or max(ibit_index, total_index) >= len(row):
                continue
            fund_values = [parse_flow_number(v) for v in row[1:total_index]]
            # A pending day can display total 0.0 while every fund is '-'.
            if not fund_values or all(value is None for value in fund_values):
                continue
            days.append({'date': date.date().isoformat(), 'ibitUsdMillions': parse_flow_number(row[ibit_index]),
                         'totalUsdMillions': parse_flow_number(row[total_index]),
                         'completeFunds': all(value is not None for value in fund_values)})
        if days:
            return sorted(days, key=lambda row: row['date'])
    raise ValueError('Dated ETF flow table could not be parsed')


def get_etf(client, start, end):
    last_error = None
    for url in (FARSIDE, 'https://farside.co.uk/bitcoin-etf-flow-all-data/'):
        try:
            rows = parse_etf(client.get(url, json_data=False), start, end)
            return {'status': 'ok', 'observedAt': stamp(), 'sourceUrl': url, 'daily': rows,
                    'method': 'USD millions of fund net flows, not BTC trades, Coinbase-specific flows, or BlackRock proprietary selling.'}
        except (RuntimeError, ValueError) as exc:
            last_error = exc
    raise RuntimeError(str(last_error))


def normalize_candles(batches, start, end):
    rows = {}
    for batch in batches:
        if not isinstance(batch, list):
            raise ValueError('Unexpected Coinbase candle response')
        for raw in batch:
            ts = int(raw[0])
            if start <= ts < end:
                close, volume = finite(raw[4]), finite(raw[5])
                if ts % 3600 or close is None or volume is None or close <= 0 or volume < 0:
                    continue
                rows[ts] = {'time': ts, 'closeUsd': close, 'volumeBtc': volume}
    return [rows[key] for key in sorted(rows)]


def tape_summary(raw):
    trades = {}
    for row in raw:
        if row.get('side') not in ('buy', 'sell') or row.get('trade_id') is None:
            continue
        try:
            amount = Decimal(str(row.get('size')))
        except InvalidOperation:
            continue
        if not amount.is_finite() or amount <= 0:
            continue
        if isinstance(row.get('time'), str) and row['time']:
            trades[row['trade_id']] = (row, amount)
    if not trades:
        raise ValueError('No valid public Coinbase trades')
    rows = list(trades.values())
    selling = sum((amount for row, amount in rows if row['side'] == 'buy'), Decimal(0))
    buying = sum((amount for row, amount in rows if row['side'] == 'sell'), Decimal(0))
    return {'tradeCount': len(rows), 'windowStart': min((row['time'] for row, _ in rows), key=datetime.fromisoformat),
             'windowEnd': max((row['time'] for row, _ in rows), key=datetime.fromisoformat), 'aggressorSellBtc': float(selling),
            'aggressorBuyBtc': float(buying), 'aggressorSellShare': float(selling / (selling + buying)),
            'meaning': 'Recent public trade sample only. Coinbase side is MAKER side: maker buy means aggressor sell. No customer identity is exposed; this is not 14-day CVD.'}


def get_market(client, start, end):
    stats = client.get(COINBASE + '/products/BTC-USD/stats')
    middle = start + 7 * DAY
    batches = []
    for lo, hi in ((start, middle), (middle, end)):
        query = urllib.parse.urlencode({'start': stamp(lo), 'end': stamp(hi), 'granularity': 3600})
        batches.append(client.get(COINBASE + '/products/BTC-USD/candles?' + query))
    hours = normalize_candles(batches, start, end)
    tape = tape_summary(client.get(COINBASE + '/products/BTC-USD/trades?limit=1000'))
    daily = []
    for ts in range(start, end, DAY):
        selected = [row for row in hours if ts <= row['time'] < ts + DAY]
        daily.append({'date': stamp(ts)[:10], 'volumeBtc': sum(row['volumeBtc'] for row in selected) if selected else None,
                      'closeUsd': selected[-1]['closeUsd'] if selected else None, 'hourCount': len(selected)})
    return {'status': 'ok' if len(hours) == 336 else 'partial', 'observedAt': stamp(), 'sourceUrl': COINBASE,
            'lastUsd': finite(stats.get('last')), 'volume24hBtc': finite(stats.get('volume')), 'daily': daily,
            'hourlyBars': len(hours), 'expectedHourlyBars': 336, 'tape': tape,
            'method': 'Coinbase BTC-USD candles measure venue-wide executed BTC volume, not sales by a specific entity. Public fills are anonymous.'}


def retain(old, error):
    return {**old, 'status': 'retained', 'lastAttemptAt': stamp(), 'refreshError': str(error)} if (old or {}).get('observedAt') else {
        'status': 'unavailable', 'observedAt': None, 'lastAttemptAt': stamp(), 'refreshError': str(error)}


def write_json(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, separators=(',', ':'), allow_nan=False) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-requests', type=int, default=80)
    args = parser.parse_args()
    case = json.loads((ROOT / 'data' / 'seller_case.json').read_text(encoding='utf-8'))
    output_path = ROOT / 'data' / 'coinbase_seller.json'
    previous = json.loads(output_path.read_text(encoding='utf-8')) if output_path.exists() else {}
    client = PublicData(args.max_requests)
    start, end = window()
    data = {'schemaVersion': 1, 'title': case['title'], 'generatedAt': stamp(),
             'case': {key: value for key, value in case.items() if key != 'etfBaseline'},
            'windowStart': stamp(start), 'windowEndExclusive': stamp(end), 'errors': [],
            'conclusion': 'MARA is a disclosed BTC seller. The public evidence does not establish a single Coinbase seller, prove this watchset belongs beneficially to MARA, or identify Coinbase-specific sales. An empty relay is not treasury exhaustion.'}
    operations = [('mara', lambda: get_mara(client, case)), ('market', lambda: get_market(client, start, end)),
                  ('chain', lambda: get_chain(client, case, start, end)),
                  ('etf', lambda: get_etf(client, start, end))]
    for section, operation in operations:
        print('Refreshing seller investigation:', section, flush=True)
        try:
            data[section] = operation()
        except (RuntimeError, ValueError, KeyError, TypeError, IndexError) as exc:
            old = previous.get(section)
            if section == 'etf' and not (old or {}).get('daily'):
                old = case.get('etfBaseline')
            data[section] = retain(old, exc)
            data['errors'].append({'section': section, 'reason': str(exc)})
            print(section + ': ' + str(exc), flush=True)
    if data['chain']['status'] in ('ok', 'partial'):
        data['chain']['hubSpends'] = get_hub_spends(client, data['chain']['flows'], case['hubAddress'])
    data['generatedAt'] = stamp()
    data['requestCount'] = client.calls
    write_json(output_path, data)
    if data.get('chain', {}).get('daily'):
        print('Watchset:', json.dumps({'confirmedBalanceBtc': data['chain']['confirmedWatchsetBalanceSats'] / SAT,
            'hubForwardedBtc': sum(row['forwardedLowerSats'] or 0 for row in data['chain']['daily']) / SAT,
            'trend': data['chain']['trend'], 'idleHours': data['chain']['hoursSinceLastForward']}), flush=True)
    print('Published seller investigation using', client.calls, 'public requests; no paid API or broker credentials', flush=True)
    # ETF context is optional; primary chain, company, and venue failures are not.
    if any(error['section'] != 'etf' for error in data['errors']):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
