#!/usr/bin/env python3
"""Frequent public-data snapshots, independent of fill scans and authenticated brokers."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path

import liquidations
import refresh

ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None


def write_json(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, separators=(',', ':'), allow_nan=False) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def parse_time(value):
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
    except (AttributeError, ValueError):
        return 0


def newest(previous, base, section):
    options = [entry[section] for entry in (previous or {}, base or {}) if entry.get(section)]
    return max(options, key=lambda row: parse_time(row.get('fetchedAt'))) if options else None


def refresh_xyz_quotes(old, markets):
    result = {**old, 'marketObservedAt': markets['fetchedAt'],
              'totalXyzVolume24h': sum(row['volume24h'] for row in markets['items'])}
    quotes = {row['coin']: row for row in markets['items']}
    ranks = {row['coin']: index + 1 for index, row in enumerate(markets['items'])}
    result['items'] = [{**row, **quotes.get(row['coin'], {}), 'volumeRank': ranks.get(row['coin'], row['volumeRank'])}
                       for row in old['items']]
    result['items'].sort(key=lambda row: row['volumeRank'])
    # Cohort/position fetchedAt values remain unchanged when only quotes change.
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wallet-limit', type=int, default=60)
    parser.add_argument('--budget', type=int, default=180)
    args = parser.parse_args()
    if not 1 <= args.wallet_limit <= 100 or not 15 <= args.budget <= 300:
        parser.error('wallet-limit must be 1..100 and budget 15..300 seconds')
    directory = ROOT / 'data'
    base = read_json(directory / 'snapshot.json') or {}
    previous = read_json(directory / 'fast.json') or {}
    fast = {'schemaVersion': 1, 'generatedAt': refresh.stamp(), 'targetIntervalSeconds': 900, 'errors': []}
    cohorts = newest(previous, base, 'cohorts')
    changed = False
    try:
        status = refresh.fetch('https://dw3ji7n7thadj.cloudfront.net/aggregator/status.json')
        changed = not cohorts or status.get('lastUpdate') != cohorts.get('sourceUpdatedAt')
        if changed:
            print('Cohort feed changed: refreshing public cohort files', flush=True)
            cohorts = refresh.get_cohorts()
        else:
            print('Cohort feed unchanged: reusing dated cohort files', flush=True)
    except (RuntimeError, KeyError, ValueError) as exc:
        fast['errors'].append({'section': 'cohorts', 'reason': str(exc)})
    if cohorts:
        fast['cohorts'] = cohorts
    try:
        fast['markets'] = refresh.get_markets()
    except (RuntimeError, KeyError, ValueError) as exc:
        fast['errors'].append({'section': 'markets', 'reason': str(exc)})
        old = newest(previous, base, 'markets')
        if old:
            fast['markets'] = old
    old_xyz = newest(previous, base, 'xyz')
    try:
        markets = fast['markets']
        expected = {row['coin'] for row in markets['items'][:20]}
        existing = {row['coin'] for row in old_xyz['items']} if old_xyz else set()
        if changed or not expected.issubset(existing) or not old_xyz:
            print('Refreshing public per-pair XYZ cohort data', flush=True)
            fast['xyz'] = refresh.get_xyz_dashboard(markets)
        else:
            fast['xyz'] = refresh_xyz_quotes(old_xyz, markets)
    except (RuntimeError, KeyError, ValueError) as exc:
        fast['errors'].append({'section': 'xyz', 'reason': str(exc)})
        if old_xyz:
            fast['xyz'] = old_xyz
    if not fast.get('cohorts'):
        raise SystemExit('No cohort discovery data available; existing snapshots remain intact')
    old_watch = read_json(directory / 'liquidations.json')
    try:
        print(f'Verifying up to {args.wallet_limit} native crypto wallets; no fill-history requests', flush=True)
        watch = liquidations.collect(fast['cohorts'], old_watch, args.wallet_limit, args.budget)
        write_json(directory / 'liquidations.json', watch)
        print('Liquidation coverage:', json.dumps(watch['coverage']), flush=True)
    except (RuntimeError, ValueError, KeyError, liquidations.BudgetReached) as exc:
        fast['errors'].append({'section': 'liquidations', 'reason': str(exc)})
        if old_watch:
            write_json(directory / 'liquidations.json', {**old_watch, 'status': 'retained',
                'lastAttemptAt': refresh.stamp(), 'refreshError': str(exc)})
        print(f'Liquidation verification failed: {exc}', flush=True)
    fast['generatedAt'] = refresh.stamp()
    write_json(directory / 'fast.json', fast)
    print('Published frequent public snapshots; authenticated broker collectors were not called', flush=True)
    if fast['errors']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
