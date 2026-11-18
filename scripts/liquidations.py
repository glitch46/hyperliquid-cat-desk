"""Bounded, public Hyperliquid account verification for the crypto liquidation watch."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import math
import re
import threading
import time
import urllib.error
import urllib.request

INFO = 'https://api.hyperliquid.xyz/info'
MIN_VALUE = 100_000
NON_CRYPTO = {'PAXG', 'XAUT', 'GOLD', 'SILVER', 'XYZ100', 'SP500', 'SPY', 'QQQ',
              'NVDA', 'AAPL', 'TSLA', 'MSFT', 'OIL', 'CL', 'BRENTOIL'}


def stamp(ms=None):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat() if ms else datetime.now(timezone.utc).isoformat()


def finite(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def crypto_symbols(meta):
    return {row['name'] for row in meta['universe'] if not row.get('isDelisted')
            and ':' not in row['name'] and '/' not in row['name']
            and not row['name'].startswith('@') and row['name'] not in NON_CRYPTO}


def distance(side, mark, liquidation):
    if side not in ('long', 'short') or mark is None or liquidation is None or mark <= 0 or liquidation <= 0:
        return None
    return (mark - liquidation) / mark if side == 'long' else (liquidation - mark) / mark


class BudgetReached(Exception):
    pass


class PublicInfo:
    def __init__(self, budget_seconds=180):
        self.deadline = time.monotonic() + budget_seconds
        self.lock = threading.Lock()
        self.next_request = 0
        self.calls = 0

    def get(self, kind, **params):
        if kind not in ('metaAndAssetCtxs', 'clearinghouseState'):
            raise ValueError('Unsupported public-read method')
        for attempt in range(2):
            with self.lock:
                now = time.monotonic()
                delay = max(0, self.next_request - now)
                self.next_request = max(now, self.next_request) + .3
            if time.monotonic() + delay >= self.deadline:
                raise BudgetReached()
            if delay:
                time.sleep(delay)
            with self.lock:
                self.calls += 1
            req = urllib.request.Request(INFO, data=json.dumps({'type': kind, **params}).encode(),
                headers={'Content-Type': 'application/json', 'User-Agent': 'Cat-Desk-Crypto-Watch/1.0'})
            try:
                with urllib.request.urlopen(req, timeout=15) as response:
                    return json.load(response)
            except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                if attempt == 0 and time.monotonic() + 20 < self.deadline:
                    time.sleep(15 if getattr(exc, 'code', None) == 429 else 2)
                    continue
                status = getattr(exc, 'code', None)
                raise RuntimeError(f'Hyperliquid public read HTTP {status}' if status else 'Hyperliquid public read failed') from None


def candidates(cohorts, coins, marks, previous=None):
    positions, metadata = {}, {}
    for cohort in cohorts.get('items', []):
        for row in cohort.get('largestPositions', []):
            address, coin = str(row.get('address', '')).lower(), row.get('coin')
            value = finite(row.get('value'))
            if coin not in coins or not re.fullmatch(r'0x[a-f0-9]{40}', address) or value is None or value < MIN_VALUE:
                continue
            record = dict(row, address=address, mark=marks.get(coin) or row.get('mark'))
            record['candidateDistance'] = distance(row.get('side'), finite(record['mark']), finite(row.get('liquidation')))
            positions[(address, coin)] = record
            info = metadata.setdefault(address, {'name': row.get('name'), 'cohortIds': [], 'cohortObservedAt': None})
            if not info['name'] and row.get('name'):
                info['name'] = row['name']
            if cohort.get('category') == 'pnl' and (cohort.get('observedAt') or '') >= (info['cohortObservedAt'] or ''):
                info.update({'cohortIds': [cohort['id']], 'cohortObservedAt': cohort.get('observedAt')})
    for row in (previous or {}).get('positions', []):
        address, coin = row.get('address'), row.get('coin')
        if coin not in coins or not re.fullmatch(r'0x[a-f0-9]{40}', address or ''):
            continue
        if (address, coin) in positions:
            continue
        record = dict(row)
        record['mark'] = marks.get(coin) or row.get('mark')
        record['candidateDistance'] = distance(row.get('side'), finite(record['mark']), finite(row.get('liquidation')))
        positions[(address, coin)] = record
        metadata.setdefault(address, {'name': row.get('name'), 'cohortIds': row.get('cohortIds') or [], 'cohortObservedAt': row.get('cohortObservedAt')})
    return list(positions.values()), metadata


def select_wallets(rows, limit=60):
    selected = []
    seen = set()

    def take(ordered, budget):
        added = 0
        for row in ordered:
            if added >= budget or len(selected) >= limit:
                break
            address = row['address']
            if address not in seen:
                seen.add(address)
                selected.append(address)
                added += 1

    near = [row for row in rows if row.get('candidateDistance') is not None and row['candidateDistance'] <= .2]
    largest_near = sorted([row for row in near if row['candidateDistance'] <= .1], key=lambda row: -row['value'])
    closest = sorted(near, key=lambda row: (row['candidateDistance'], -row['value']))
    largest = sorted(rows, key=lambda row: -row['value'])
    take(largest_near, max(1, int(limit * .65)))
    take(closest, max(1, int(limit * .2)))
    take(largest, limit)
    return selected


def normalize_position(address, raw, coins, metadata, checked_at, state_time=None):
    coin = raw.get('coin')
    size, value, liquidation = finite(raw.get('szi')), finite(raw.get('positionValue')), finite(raw.get('liquidationPx'))
    if coin not in coins or size is None or not size or value is None or value <= 0 or value < MIN_VALUE:
        return None
    if liquidation is None or liquidation <= 0:
        return None
    side = 'long' if size > 0 else 'short'
    mark = value / abs(size)
    gap = distance(side, mark, liquidation)
    leverage = raw.get('leverage') or {}
    return {'id': address + ':' + coin, 'address': address, 'name': metadata.get('name'),
            'coin': coin, 'side': side, 'size': abs(size), 'value': value, 'mark': mark,
            'entry': finite(raw.get('entryPx')), 'liquidation': liquidation,
            'distance': gap, 'atOrBeyondEstimate': gap <= 0,
            'unrealizedPnl': finite(raw.get('unrealizedPnl')), 'marginUsed': finite(raw.get('marginUsed')),
            'leverage': finite(leverage.get('value')), 'marginMode': leverage.get('type'),
            'cohortIds': metadata.get('cohortIds') or [], 'cohortObservedAt': metadata.get('cohortObservedAt'),
            'verifiedAt': checked_at, 'accountStateAt': stamp(state_time) if state_time else None}


def collect(cohorts, previous=None, wallet_limit=60, budget_seconds=180, client=None):
    started = time.monotonic()
    client = client or PublicInfo(budget_seconds)
    meta, contexts = client.get('metaAndAssetCtxs')
    coins = crypto_symbols(meta)
    marks = {row['name']: finite(ctx.get('markPx')) for row, ctx in zip(meta['universe'], contexts) if row['name'] in coins}
    rows, metadata = candidates(cohorts, coins, marks, previous)
    wallets = select_wallets(rows, wallet_limit)
    if not wallets:
        raise RuntimeError('No crypto discovery wallets available')
    positions, errors, wallet_checks = [], [], {}
    checked = deferred = positions_observed = missing_estimates = 0

    def verify(address):
        state = client.get('clearinghouseState', user=address, dex='')
        if not isinstance(state.get('assetPositions'), list):
            raise ValueError('Account state has no position array')
        now = stamp()
        output, count, missing = [], 0, 0
        seen = set()
        for item in state['assetPositions']:
            raw = item['position']
            if raw.get('coin') not in coins or not finite(raw.get('szi')):
                continue
            count += 1
            value = finite(raw.get('positionValue'))
            if value is not None and value >= MIN_VALUE and not (finite(raw.get('liquidationPx')) or 0) > 0:
                missing += 1
            row = normalize_position(address, raw, coins, metadata.get(address, {}), now, state.get('time'))
            if row and row['id'] not in seen:
                seen.add(row['id'])
                output.append(row)
        return output, count, missing

    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = {pool.submit(verify, address): address for address in wallets}
        for job in as_completed(jobs):
            address = jobs[job]
            try:
                records, count, missing = job.result()
                positions.extend(records)
                positions_observed += count
                missing_estimates += missing
                checked += 1
                wallet_checks[address] = records[0]['verifiedAt'] if records else stamp()
            except BudgetReached:
                deferred += 1
            except (RuntimeError, ValueError, KeyError, TypeError) as exc:
                errors.append({'address': address, 'reason': str(exc)})
    if checked == 0:
        raise RuntimeError('No crypto wallets could be verified; preserve the previous watch with its dates')
    positions.sort(key=lambda row: -row['value'])
    return {'schemaVersion': 1, 'generatedAt': stamp(), 'status': 'partial' if errors or deferred else 'ok',
            'scope': 'Native Hyperliquid crypto perps only; HIP-3/XYZ, spot, and metal-backed proxies excluded',
            'nativeCryptoSymbols': sorted(coins), 'minimumStoredNotional': MIN_VALUE,
            'discoverySource': 'https://dw3ji7n7thadj.cloudfront.net/aggregator/segments.json',
            'discoveryUpdatedAt': cohorts.get('sourceUpdatedAt'), 'verificationSource': INFO,
            'coverage': {'discoveredPositions': len(rows), 'candidateWallets': len(metadata),
                         'requestedWallets': len(wallets), 'verifiedWallets': checked,
                         'failedWallets': len(errors), 'deferredWallets': deferred,
                         'nativePositionsObserved': positions_observed, 'withoutPositiveLiquidationPrice': missing_estimates,
                         'retainedPositions': len(positions), 'publicInfoRequests': client.calls,
                         'elapsedSeconds': round(time.monotonic() - started, 2)},
            'positions': positions, 'walletChecks': wallet_checks, 'errors': errors,
            'method': 'Discovery uses cohort largest-position samples and prior watch rows. Wallets prioritize large nearby positions, '
                      'closest estimates, and largest notional. Only fresh successful native account reads enter this observation. '
                      'Distances use each position’s own mark (positionValue / abs(szi)) and reported liquidation price. '
                      'Long distance=(mark−liquidation)/mark; short distance=(liquidation−mark)/mark. '
                      'Liquidation prices are estimates, not fixed triggers or predicted executions. '
                      'This is a bounded verified sample, not the global largest/closest-position ranking.'}
