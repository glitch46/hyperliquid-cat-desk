#!/usr/bin/env python3
"""Build a public, timestamped Hyperliquid snapshot. Python standard library only."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
AGGREGATOR = 'https://dw3ji7n7thadj.cloudfront.net/aggregator'
INFO = 'https://api.hyperliquid.xyz/info'
LEADERBOARD = 'https://stats-data.hyperliquid.xyz/Mainnet/leaderboard'
VENICE_NETWORKS = 'https://api.venice.ai/api/v1/crypto/rpc/networks'
DAY = 86_400_000
RATE_LOCK = threading.Lock()
NEXT_REQUEST = 0.0
SCREEN_DEADLINE = None


class ScreeningBudgetReached(Exception):
    pass


def reserve_weight(weight, wait=True):
    """Keep this collector below the shared 1,200-weight/minute API budget."""
    global NEXT_REQUEST
    with RATE_LOCK:
        now = time.monotonic()
        delay = max(0, NEXT_REQUEST - now)
        NEXT_REQUEST = max(now, NEXT_REQUEST) + weight / 15
    if wait and delay:
        time.sleep(delay)


def stamp(ms=None):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat() if ms is not None else datetime.now(timezone.utc).isoformat()


def number(value):
    result = float(value or 0)
    if not math.isfinite(result):
        raise ValueError('Non-finite source number')
    return result


def fetch(url, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    for attempt in range(4):
        request = urllib.request.Request(url, data=data, headers={
            'User-Agent': 'Hyperliquid-Cat-Desk/1.0', 'Content-Type': 'application/json',
        })
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == 3:
                code = f' HTTP {exc.code}' if isinstance(exc, urllib.error.HTTPError) else ''
                raise RuntimeError(f'{url}: {type(exc).__name__}{code}') from exc
            time.sleep((attempt + 1) * (20 if isinstance(exc, urllib.error.HTTPError) and exc.code == 429 else 2))


def info(kind, **params):
    if kind == 'userFillsByTime' and SCREEN_DEADLINE and time.monotonic() >= SCREEN_DEADLINE:
        raise ScreeningBudgetReached()
    reserve_weight(2 if kind == 'clearinghouseState' else 20)
    if kind == 'userFillsByTime' and SCREEN_DEADLINE and time.monotonic() >= SCREEN_DEADLINE:
        raise ScreeningBudgetReached()
    result = fetch(INFO, {'type': kind, **params})
    if kind == 'userFillsByTime':
        reserve_weight(math.ceil(len(result) / 20), wait=False)
    return result


def position(raw, source='HyperTracker'):
    if source == 'HyperTracker':
        profile = raw.get('profile') or {}
        return {
            'address': raw['address'], 'name': (profile.get('showName') or {}).get('text'),
            'coin': raw['coin'], 'dex': raw.get('dex', 'main'), 'side': raw['side'],
            'value': abs(number(raw['value'])), 'size': abs(number(raw.get('size'))),
            'entry': number(raw.get('entryPrice')), 'mark': number(raw.get('markPrice')),
            'unrealizedPnl': number(raw.get('unrealizedPnl')),
            'liquidation': raw.get('liquidationPrice'),
            'leverage': raw.get('isolatedLeverage') or raw.get('crossLeverage'),
            'source': source,
        }
    size = number(raw['szi'])
    value = abs(number(raw['positionValue']))
    return {
        'coin': raw['coin'], 'side': 'long' if size > 0 else 'short',
        'value': value, 'size': abs(size), 'entry': number(raw.get('entryPx')),
        'mark': value / abs(size) if size else None,
        'unrealizedPnl': number(raw.get('unrealizedPnl')),
        'liquidation': raw.get('liquidationPx'),
        'leverage': (raw.get('leverage') or {}).get('value'), 'source': source,
    }


def normalize_cohort(row, detail, observed_at):
    segment = row['segment']
    total = number(row['positionValue'])
    markets = [{
        'coin': item['coin'], 'value': number(item['totalValue']),
        'long': number(item['totalValueLong']), 'short': number(item['totalValueShort']),
        'positions': item.get('count'),
    } for item in detail['top10OpenPerps']]
    covered = sum(item['value'] for item in markets)
    summary = detail['openPerpsSummary']
    history = detail.get('historyPositionsData') or {}
    columns = history.get('columns', [])
    series = []
    if 'timestamp' in columns and 'totalOpenPositionValue' in columns:
        for point in history.get('data', []):
            record = dict(zip(columns, point))
            series.append({'time': record['timestamp'], 'value': record['totalOpenPositionValue'],
                           'long': record.get('totalLongOpenPositionValue')})
    # The detail file is a separate observation. Use its own denominator so
    # truncated top-ten allocations always reconcile to this detail snapshot.
    allocation_total = number(summary['totalValue'])
    return {
        'id': row['segmentId'], 'name': segment['name'], 'category': segment['category'],
        'criteria': segment['criteria'], 'wallets': row['countTraders'],
        'walletChange24h': detail['countTraders'] - detail['countTraders24HoursAgo']
        if detail.get('countTraders24HoursAgo') is not None else None,
        'activeWallets': row['countTradersInPosition'], 'gross': total,
        'long': number(row['positionLongValue']), 'short': number(row['positionShortValue']),
        'equity': number(row.get('perpMarginEquity', row.get('perpEquity'))),
        'activeEquity': number(row.get('activePerpMarginEquity', row.get('activePerpEquity'))),
        'openProfitableWallets': summary.get('countTradersInProfit'),
        'detailActiveWallets': summary.get('countTradersInPosition'),
        'allocationGross': allocation_total, 'markets': markets,
        'otherAllocation': max(0, allocation_total - covered),
        'allocationCoverage': covered / allocation_total if allocation_total else 0,
        'largestPositions': [position(item) for item in detail['largestPositions']],
        'history': series, 'observedAt': observed_at,
    }


def get_cohorts():
    status = fetch(f'{AGGREGATOR}/status.json')
    source = fetch(f'{AGGREGATOR}/segments.json')
    rows = source['segments']
    details = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(fetch, f'{AGGREGATOR}/segment_{row["segmentId"]}.json'): row for row in rows}
        for job in as_completed(jobs):
            row = jobs[job]
            details[row['segmentId']] = (job.result(), stamp())
    cohorts = [normalize_cohort(row, *details[row['segmentId']]) for row in rows]
    cohorts.sort(key=lambda row: row['id'])
    return {'fetchedAt': stamp(), 'sourceUpdatedAt': status.get('lastUpdate'),
            'nextSourceUpdate': status.get('nextUpdate'), 'items': cohorts}


def fill_key(fill):
    return (fill.get('coin'), fill.get('tid'), fill.get('oid'), fill.get('time'),
            fill.get('px'), fill.get('sz'), fill.get('side'))


def is_perp(fill):
    return not fill['coin'].startswith('@') and '/' not in fill['coin'] and fill.get('dir') not in ('Buy', 'Sell')


def summarize_fills(fills):
    perps = [fill for fill in fills if is_perp(fill)]
    total = sum(number(fill['px']) * abs(number(fill['sz'])) for fill in perps)
    xyz = [fill for fill in perps if fill['coin'].startswith('xyz:')]
    xyz_volume = sum(number(fill['px']) * abs(number(fill['sz'])) for fill in xyz)
    return {'perpVolume': total, 'xyzVolume': xyz_volume,
            'xyzShare': xyz_volume / total if total else None,
            'xyzClosedPnl': sum(number(fill.get('closedPnl')) for fill in xyz),
            'perpFillCount': len(perps), 'fillCount': len(fills)}


def get_fills(address, start, end, max_pages=7):
    cursor = start
    found = {}
    complete = False
    reason = 'Page budget reached'
    for _ in range(max_pages):
        batch = info('userFillsByTime', user=address, startTime=cursor, endTime=end, aggregateByTime=False)
        if not isinstance(batch, list):
            raise ValueError('Unexpected fills response')
        previous = len(found)
        for fill in batch:
            if start <= int(fill['time']) <= end:
                found[fill_key(fill)] = fill
        # API retains only the latest 10,000 fills across spot and all perps.
        if len(found) >= 10_000:
            reason = '10,000-fill retention limit'
            break
        if len(batch) < 2000:
            complete = True
            reason = 'Full requested window returned'
            break
        next_cursor = max(int(fill['time']) for fill in batch)
        # Repeat the inclusive boundary and deduplicate to avoid losing fills
        # sharing a timestamp. Saturated boundaries stay explicitly incomplete.
        if next_cursor <= cursor or len(found) == previous:
            reason = 'Saturated timestamp boundary'
            break
        cursor = next_cursor
    fills = list(found.values())
    return {**summarize_fills(fills), 'complete': complete, 'coverageReason': reason,
            'oldestFillAt': stamp(min(int(f['time']) for f in fills)) if fills else None,
            'venues': sorted({f['coin'].split(':')[0] if ':' in f['coin'] else '' for f in fills if is_perp(f)})}


def performance(row):
    return dict(row.get('windowPerformances', [])).get('month', {})


def get_traders(cohorts, limit, top_count, budget_seconds=480):
    global SCREEN_DEADLINE
    rows = fetch(LEADERBOARD)['leaderboardRows']
    leaderboard_at = stamp()
    rows.sort(key=lambda row: number(performance(row).get('pnl')), reverse=True)
    profitable = [row for row in rows if number(performance(row).get('pnl')) > 0]
    by_address = {row['ethAddress'].lower(): row for row in profitable}
    candidates = {row['ethAddress'].lower(): row for row in profitable[:limit]}
    # Expand discovery with publicly visible large xyz positions, including
    # wallets outside the top-N account-PnL candidate pool.
    for cohort in cohorts['items']:
        for item in cohort['largestPositions']:
            address = item['address'].lower()
            if item['coin'].startswith('xyz:') and address in by_address:
                candidates[address] = by_address[address]
    end = int(time.time() * 1000)
    start = end - 30 * DAY
    checked, eligible, partial, errors, deferred = [], [], [], [], []
    checkpoint = ROOT / '.cache' / 'screening.json'
    if checkpoint.exists():
        cached = json.loads(checkpoint.read_text(encoding='utf-8'))
        if (end - cached.get('end', 0) < 120 * 60_000
                and cached.get('limit') == limit):
            start, end = cached['start'], cached['end']
            checked = cached['checked']
            candidates = cached['candidates']
            leaderboard_at = cached['leaderboardAt']
            print(f'  Resuming {len(checked)} checkpointed wallet checks', flush=True)

    def save_checkpoint():
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_text(json.dumps({'start': start, 'end': end, 'limit': limit,
            'checked': checked, 'candidates': candidates, 'leaderboardAt': leaderboard_at}), encoding='utf-8')

    def inspect(row):
        fills = get_fills(row['ethAddress'], start, end)
        perf = performance(row)
        return {'address': row['ethAddress'], 'name': row.get('displayName'),
                'pnl30d': number(perf.get('pnl')), 'roi30d': number(perf.get('roi')),
                'leaderboardVolume30d': number(perf.get('vlm')),
                'accountValue': number(row.get('accountValue')), **fills}

    # Prioritize known large xyz-position holders inside this bounded screen.
    xyz_holders = {item['address'].lower() for cohort in cohorts['items'] for item in cohort['largestPositions']
                   if item['coin'].startswith('xyz:')}
    candidates = dict(sorted(candidates.items(), key=lambda item: (
        item[0] not in xyz_holders, -number(performance(item[1]).get('pnl')))))
    SCREEN_DEADLINE = time.monotonic() + budget_seconds
    with ThreadPoolExecutor(max_workers=3) as pool:
        done_addresses = {row['address'].lower() for row in checked}
        jobs = {pool.submit(inspect, row): address for address, row in candidates.items() if address not in done_addresses}
        for index, job in enumerate(as_completed(jobs), 1):
            address = jobs[job]
            try:
                trader = job.result()
                checked.append(trader)
            except ScreeningBudgetReached:
                deferred.append(address)
            except Exception as exc:
                errors.append({'address': address, 'reason': str(exc)})
            if index % 20 == 0:
                save_checkpoint()
                count = sum(t['complete'] and (t['xyzShare'] or 0) > 0.5 for t in checked)
                print(f'  Fills: {len(checked)}/{len(candidates)} checked; {count} verified xyz-majority', flush=True)
    save_checkpoint()
    SCREEN_DEADLINE = None
    partial = [row for row in checked if not row['complete']]
    eligible = [row for row in checked if row['complete'] and (row['xyzShare'] or 0) > 0.5]
    eligible.sort(key=lambda row: row['pnl30d'], reverse=True)
    dexes = info('perpDexs')
    venues = [''] + [dex['name'] for dex in dexes if dex and dex.get('name')]
    venues = list(dict.fromkeys(venues))
    selected = eligible[:top_count]
    for trader in selected:
        trader.update({'positions': [], 'positionVenues': [], 'positionErrors': [], 'positionTimes': []})
    print(f'  Checking {len(venues)} perp venues for {len(selected)} selected wallets...', flush=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = {pool.submit(info, 'clearinghouseState', user=trader['address'], dex=venue): (trader, venue)
                for trader in selected for venue in venues}
        for job in as_completed(jobs):
            trader, venue = jobs[job]
            try:
                state = job.result()
                for wrapped in state['assetPositions']:
                    item = wrapped['position']
                    if number(item['szi']):
                        trader['positions'].append({**position(item, 'Hyperliquid'), 'dex': venue or 'main'})
                trader['positionVenues'].append(venue or 'main')
                if state.get('time'):
                    trader['positionTimes'].append(state['time'])
            except Exception as exc:
                trader['positionErrors'].append({'venue': venue or 'main', 'reason': str(exc)})
    for trader in selected:
        trader['positions'].sort(key=lambda row: row['value'], reverse=True)
        trader['positionsObservedAt'] = stamp()
    partial.sort(key=lambda row: row['pnl30d'], reverse=True)
    return {'fetchedAt': stamp(), 'leaderboardObservedAt': leaderboard_at,
            'windowStart': stamp(start), 'windowEnd': stamp(end),
            'leaderboardWallets': len(rows), 'candidateLimit': limit,
            'candidates': len(candidates), 'checked': len(checked),
            'completeWindows': sum(row['complete'] for row in checked),
            'incompleteWindows': len(partial), 'eligibleCount': len(eligible),
            'errors': errors, 'deferred': len(deferred), 'screenBudgetSeconds': budget_seconds,
            'venues': [v or 'main' for v in venues],
            'items': selected, 'incompleteCandidates': partial[:10]}


INDEX_SYMBOLS = {'XYZ100', 'SP500', 'JP225', 'KR200', 'NIFTY', 'IBOV', 'VIX'}
FUND_SYMBOLS = {'MAGS', 'SMH', 'SOXL', 'TLT', 'XBI', 'XLE', 'EWJ', 'EWT', 'EWY', 'EWZ', 'URNM', 'KSTR', 'KORU'}
COMMODITY_SYMBOLS = {'GOLD', 'SILVER', 'COPPER', 'PLATINUM', 'PALLADIUM', 'ALUMINIUM',
                     'URANIUM', 'CL', 'BRENTOIL', 'NATGAS', 'WHEAT', 'CORN', 'TTF'}
FX_SYMBOLS = {'EUR', 'GBP', 'JPY', 'KRW', 'DXY'}


def instrument_category(coin):
    """Navigation grouping for TradFi markets, curated from the venue symbol list.

    Anything not explicitly an index, commodity, FX pair or fund is treated as a
    single-name equity. This is a browsing aid, not an exchange classification.
    """
    name = coin.split(':')[-1]
    if name in INDEX_SYMBOLS:
        return 'indices'
    if name in COMMODITY_SYMBOLS:
        return 'commodities'
    if name in FX_SYMBOLS:
        return 'fx'
    if name in FUND_SYMBOLS:
        return 'etfs'
    return 'equities'


def get_markets():
    meta, contexts = info('metaAndAssetCtxs', dex='xyz')
    markets = []
    for asset, ctx in zip(meta['universe'], contexts):
        if asset.get('isDelisted'):
            continue
        mark = number(ctx.get('markPx'))
        previous = number(ctx.get('prevDayPx'))
        markets.append({'coin': asset['name'], 'group': instrument_category(asset['name']), 'mark': mark,
                        'volume24h': number(ctx.get('dayNtlVlm')),
                        'openInterest': number(ctx.get('openInterest')) * mark,
                        'fundingHourly': number(ctx.get('funding')),
                        'change24h': mark / previous - 1 if previous else None})
    markets.sort(key=lambda item: item['volume24h'], reverse=True)
    return {'fetchedAt': stamp(), 'items': markets}


def normalize_xyz_cohorts(coin, data):
    """Use the full per-asset cohort feed, never a cohort's top-ten subset."""
    if data.get('coin') != coin:
        raise ValueError('Per-market cohort response has a different symbol')
    rows, seen = [], set()
    for raw in data['cohortMetrics']:
        segment = raw['segment']
        if segment['category'] != 'pnl':
            continue
        segment_id = int(segment['id'])
        if segment_id not in range(8, 16) or segment_id in seen:
            raise ValueError('Unexpected or duplicate PnL cohort')
        seen.add(segment_id)
        for field in ('totalPositionValue', 'totalPositionValueLong'):
            if raw.get(field) is None:
                raise ValueError(f'Missing {field}; unavailable exposure is not zero')
        gross = number(raw['totalPositionValue'])
        long_value = number(raw['totalPositionValueLong'])
        if gross < 0 or long_value < 0 or long_value > gross + .001:
            raise ValueError('Invalid gross/long exposure in cohort feed')
        long_value = min(long_value, gross)
        rows.append({'id': segment_id, 'name': segment['name'], 'criteria': segment['criteria'],
                     'gross': gross, 'long': long_value, 'short': gross - long_value,
                     'net': 2 * long_value - gross,
                     'longShare': long_value / gross if gross else None,
                     'positions': raw.get('positionCount'), 'sourceUpdatedAt': raw.get('timestamp')})
    rows.sort(key=lambda row: row['id'])
    return rows


def get_xyz_dashboard(markets, limit=20):
    ranked = [row for row in markets['items'] if row['coin'].startswith('xyz:')]
    ranked.sort(key=lambda row: row['volume24h'], reverse=True)
    chosen = ranked[:limit]
    # Keep the requested equity/index reference markets available if the tape
    # rotates them outside the top twenty. Their actual volume rank is retained.
    for row in ranked:
        if row['coin'] in ('xyz:NVDA', 'xyz:XYZ100', 'xyz:SP500') and row not in chosen:
            chosen.append(row)
    ranks = {row['coin']: index + 1 for index, row in enumerate(ranked)}

    def collect(market):
        coin = market['coin']
        base = f'{AGGREGATOR}/assets/{quote(coin, safe="")}'
        cohort_url = f'{base}/coin-position-breakdown-by-cohort.json'
        positions_url = f'{base}/positions.json'
        result = {**market, 'volumeRank': ranks[coin], 'cohorts': [], 'positions': [],
                  'cohortSourceUrl': cohort_url, 'positionSourceUrl': positions_url,
                  'errors': [], 'positionsAvailable': False}
        try:
            result['cohorts'] = normalize_xyz_cohorts(coin, fetch(cohort_url))
        except Exception as exc:
            result['errors'].append({'section': 'cohorts', 'reason': str(exc)})
        result['cohortCoverageComplete'] = {row['id'] for row in result['cohorts']} == set(range(8, 16))
        try:
            raw = fetch(positions_url)
            if raw.get('coin') != coin:
                raise ValueError('Position sample has a different symbol')
            seen = set()
            for item in raw['positions']:
                key = item.get('id') or (item.get('address'), item.get('coin'), item.get('side'))
                if item.get('coin') != coin or item.get('closeTime') or key in seen:
                    continue
                seen.add(key)
                result['positions'].append({**position(item),
                    'pnlCohortIds': [segment for segment in (item.get('profile') or {}).get('segments', [])
                                     if segment in range(8, 16)]})
            result['positions'].sort(key=lambda row: row['value'], reverse=True)
            result['positionsAvailable'] = True
        except Exception as exc:
            result['errors'].append({'section': 'positions', 'reason': str(exc)})
        result['fetchedAt'] = stamp()
        return result

    items = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for item in pool.map(collect, chosen):
            items.append(item)
    if not any(item['cohorts'] for item in items):
        raise RuntimeError('No per-market PnL cohort data returned')
    items.sort(key=lambda row: row['volumeRank'])
    return {'fetchedAt': stamp(), 'marketObservedAt': markets['fetchedAt'], 'rankingWindow': '24h',
            'topPairLimit': limit, 'xyzMarketCount': len(ranked),
            'totalXyzVolume24h': sum(row['volume24h'] for row in ranked),
            'items': items}


def venice_status():
    networks = fetch(VENICE_NETWORKS)['networks']
    supported = [network for network in networks if 'hyperliquid' in network.lower() or 'hyperevm' in network.lower()]
    return {'checkedAt': stamp(), 'networksUrl': VENICE_NETWORKS,
            'hyperliquidNetworks': supported,
            'status': 'Hyperliquid/HyperEVM absent from live network list' if not supported
            else 'HyperEVM RPC available; trader positions still use the HyperCore Info API'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trader-limit', type=int, default=120)
    parser.add_argument('--top-traders', type=int, default=10)
    parser.add_argument('--cohorts-only', action='store_true')
    parser.add_argument('--screen-budget', type=int, default=480,
                        help='Maximum seconds spent screening new wallet fill histories (default 480)')
    args = parser.parse_args()
    if args.trader_limit < 1 or args.top_traders < 1 or args.screen_budget < 1:
        parser.error('Trader limits and screening budget must be positive')
    target = ROOT / 'data' / 'snapshot.json'
    previous = json.loads(target.read_text(encoding='utf-8')) if target.exists() else {}
    snapshot = {'schemaVersion': 1, 'generatedAt': stamp(), 'errors': []}
    print('Refreshing HyperTracker cohorts...', flush=True)
    # Keep independent last-good sections with their original observation times.
    for key, operation in [('cohorts', get_cohorts), ('markets', get_markets), ('venice', venice_status)]:
        try:
            snapshot[key] = operation()
        except Exception as exc:
            snapshot['errors'].append({'section': key, 'reason': str(exc)})
            if key in previous:
                snapshot[key] = previous[key]
            print(f'{key}: {exc}', flush=True)
    if 'cohorts' not in snapshot:
        raise SystemExit('No cohort data available; snapshot not published')
    print('Refreshing busiest xyz pairs and all PnL cohorts...', flush=True)
    try:
        snapshot['xyz'] = get_xyz_dashboard(snapshot['markets'])
    except Exception as exc:
        snapshot['errors'].append({'section': 'xyz', 'reason': str(exc)})
        if 'xyz' in previous:
            snapshot['xyz'] = previous['xyz']
        print(f'xyz: {exc}', flush=True)
    # Publish usable cohort data before the longer wallet screen begins.
    target.parent.mkdir(parents=True, exist_ok=True)
    if 'traders' in previous:
        snapshot['traders'] = previous['traders']
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(snapshot, separators=(',', ':'), allow_nan=False) + '\n', encoding='utf-8')
    os.replace(temporary, target)
    if args.cohorts_only:
        if 'traders' in previous:
            snapshot['traders'] = previous['traders']
    else:
        print('Checking profitable traders and 30-day xyz volume...', flush=True)
        try:
            snapshot['traders'] = get_traders(snapshot['cohorts'], args.trader_limit, args.top_traders, args.screen_budget)
        except Exception as exc:
            snapshot['errors'].append({'section': 'traders', 'reason': str(exc)})
            if 'traders' in previous:
                snapshot['traders'] = previous['traders']
            print(f'traders: {exc}', flush=True)
    snapshot['generatedAt'] = stamp()
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(snapshot, separators=(',', ':'), allow_nan=False) + '\n', encoding='utf-8')
    os.replace(temporary, target)
    print(f'Published {target} ({target.stat().st_size:,} bytes)', flush=True)
    if snapshot['errors']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
