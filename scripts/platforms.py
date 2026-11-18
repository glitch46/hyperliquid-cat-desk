#!/usr/bin/env python3
"""Daily public broker comparison for exactly the twenty highest-volume XYZ pairs."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import html
import json
import math
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from etoro import ApiError, Client, MARKET_FIELDS

ROOT = Path(__file__).resolve().parents[1]
ROBINHOOD = 'https://robinhood.com/us/en/investor-index/'
SCHWAB = 'https://www.schwab.com/investment-research/stax/view-schwab-trading-activity-index'
SCHWAB_API = 'https://stax-xapi.schwab.com/public'
ETORO_DOCS = 'https://api-portal.etoro.com/'
PERIOD = 'CurrMonth'
# Only explicit identities are eligible for cross-source overlaps. Unsupported
# synthetics (e.g. SKHX/DRAM) are not guessed from a similar-looking ticker.
EQUITIES = set(('NVDA AAPL MSFT GOOGL GOOG AMD MU INTC TSLA CRCL NBIS SNDK SOXL HOOD COIN '
                'ORCL PLTR AMZN META MRVL AVGO IREN COST LITE GEV SMH KORU EWY EWZ TLT '
                'NFLX MSTR QCOM ARM BABA DELL CRWD CRWV RDDT RKLB IBM NOW NET LLY BX '
                'ACN AMAT ASML CVX GME HIMS MRNA SNAP TTWO TWST UMC USAR WDC ZM NU').split())
REFERENCES = {
    'XYZ100': ('NSDQ100', 'Index reference; XYZ100 is a different perpetual contract.'),
    'SP500': ('SPX500', 'S&P 500 index reference; different contract, not SPY.'),
    'GOLD': ('GOLD', 'Gold reference instrument; not the XYZ perpetual contract.'),
    'SILVER': ('SILVER', 'Silver reference instrument; not the XYZ perpetual contract.'),
    'COPPER': ('COPPER', 'Copper reference instrument; contract specifications differ.'),
    'PLATINUM': ('PLATINUM', 'Platinum reference instrument; contract specifications differ.'),
    'PALLADIUM': ('PALLADIUM', 'Palladium reference instrument; contract specifications differ.'),
    'CL': ('OIL', 'Oil reference only; not an identity match to the CL perpetual.'),
}
BUCKETS = (
    ('strong_gain', 'MTD return ≥ 10%'), ('gain', 'MTD return 0% to < 10%'),
    ('loss', 'MTD return −10% to < 0%'), ('large_loss', 'MTD return < −10%'),
)


def stamp():
    return datetime.now(timezone.utc).isoformat()


def finite(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError):
        return None


def fetch(url, headers=None):
    for attempt in range(3):
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json,text/html', **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=35) as response:
                return response.read().decode('utf-8')
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == 2:
                status = getattr(exc, 'code', None)
                raise RuntimeError(f'Public source HTTP {status}' if status else 'Public source request failed') from None
            time.sleep(2 * (attempt + 1))


def public_json(url, headers=None):
    return json.loads(fetch(url, headers))


def identity(coin):
    ticker = coin.split(':', 1)[-1]
    if ticker in EQUITIES:
        return {'symbol': ticker, 'kind': 'same_underlying',
                'note': 'Same equity/fund underlying; stock/fund and XYZ perp are distinct instruments.'}
    if ticker in REFERENCES:
        symbol, note = REFERENCES[ticker]
        return {'symbol': symbol, 'kind': 'reference', 'note': note}
    # SPCX needs a name check: ticker reuse must not match an unrelated fund.
    if ticker == 'SPCX':
        return {'symbol': ticker, 'kind': 'same_underlying', 'nameMustContain': 'spacex',
                'note': 'Requires a SpaceX name match; ticker text alone is insufficient.'}
    return {'symbol': None, 'kind': 'unmapped', 'note': 'No verified instrument identity configured.'}


def universe(snapshot):
    items = sorted(snapshot['xyz']['items'], key=lambda row: row['volumeRank'])[:20]
    return [{'coin': row['coin'], 'symbol': row['coin'].split(':', 1)[-1],
             'volumeRank': row['volumeRank'], 'identity': identity(row['coin'])} for row in items]


def overlaps(symbol, scope, allow_reference=False, name=None):
    return [row['coin'] for row in scope if row['identity']['symbol'] == symbol
            and (allow_reference or row['identity']['kind'] == 'same_underlying')
            and (not row['identity'].get('nameMustContain')
                 or row['identity']['nameMustContain'].lower() in (name or '').lower())]


def get_hyperliquid(snapshot, scope):
    selected = {row['coin'] for row in scope}
    pairs = {}
    for pair in snapshot['xyz']['items']:
        if pair['coin'] in selected:
            pairs[pair['coin']] = {key: pair.get(key) for key in ('coin', 'mark', 'volume24h', 'openInterest', 'cohorts', 'positions', 'fetchedAt')}
    leaders = [{'rank': index + 1, 'symbol': row['coin'].split(':', 1)[-1],
                'name': row['coin'], 'value': row['volume24h'], 'unit': 'USD executed notional',
                'overlaps': [row['coin']] if row['coin'] in selected else []}
               for index, row in enumerate(sorted(snapshot['markets']['items'], key=lambda row: -row['volume24h'])[:30])]
    return {'name': 'Hyperliquid / XYZ', 'status': 'ok', 'observedAt': snapshot['xyz']['marketObservedAt'],
            'sourceUrl': 'https://api.hyperliquid.xyz/info', 'period': 'Rolling 24h market volume; current positions',
            'activityLabel': 'XYZ executed volume / rolling 24h', 'activityKind': 'executed_volume',
            'note': 'Full reported PnL cohort books; wallet rows are public position samples.',
            'pairs': pairs, 'leaders': leaders}


def parse_robinhood(text):
    found = re.search(r'<script\b[^>]*\bid=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', text, re.S)
    if not found:
        raise ValueError('Robinhood published index payload was not found')
    props = json.loads(found.group(1))['props']['pageProps']
    rows = props.get('top10', [])
    if not rows or not props.get('lastUpdatedDate'):
        raise ValueError('Robinhood top investments or publication date missing')
    published = datetime.strptime(props['lastUpdatedDate'], '%B %d, %Y').replace(tzinfo=timezone.utc).isoformat()
    return published, [{'symbol': row['ticker'], 'name': row['name'], 'rank': int(row['rank'])} for row in rows]


def get_robinhood(scope):
    published, rows = parse_robinhood(fetch(ROBINHOOD))
    pairs = {}
    for row in rows:
        row.update({'value': row['rank'], 'unit': 'Published index rank', 'overlaps': overlaps(row['symbol'], scope, name=row['name'])})
        for coin in row['overlaps']:
            pairs[coin] = {'rank': row['rank'], 'symbol': row['symbol'], 'name': row['name']}
    return {'name': 'Robinhood', 'status': 'ok', 'observedAt': published, 'collectedAt': stamp(),
            'sourceUrl': ROBINHOOD, 'period': 'Monthly Investor Index publication',
            'activityLabel': 'Investor Index top investments / monthly', 'activityKind': 'holdings_rank',
            'note': 'Published top ten of a conviction-weighted index, not trade volume or dollar holdings. '
                    'ETFs/options/crypto excluded. Absence from ten names is not zero ownership. '
                    'Robinhood Social has no validated external feed connected here.',
            'pairs': pairs, 'leaders': sorted(rows, key=lambda row: row['rank'])}


def parse_schwab(summary):
    for table in re.findall(r'<table\b[^>]*>(.*?)</table>', summary, re.S | re.I):
        if not (re.search(r'top\s+net\s+buys', table, re.I) and re.search(r'top\s+net\s+sells', table, re.I)):
            continue
        leaders = []
        rank = 0
        for tr in re.findall(r'<tr\b[^>]*>(.*?)</tr>', table, re.S | re.I):
            cells = re.findall(r'<td\b[^>]*>(.*?)</td>', tr, re.S | re.I)
            if len(cells) < 2:
                continue
            rank += 1
            for column, cell in enumerate(cells[:2]):
                match = re.search(r'##([A-Z0-9.\-]+)##', cell)
                if not match:
                    raise ValueError('Schwab table ticker markup changed')
                symbol = match.group(1)
                name = html.unescape(re.sub(r'<[^>]+>', '', cell)).split('(##')[0].strip()
                leaders.append({'symbol': symbol, 'name': name, 'rank': rank,
                                'direction': 'net_buy' if column == 0 else 'net_sell'})
        if leaders:
            return leaders
    raise ValueError('Schwab top net-buy/net-sell table was not found')


def get_schwab(scope):
    # The same public client headers used by Schwab's embedded STAX page.
    headers = {'Schwab-Client-CorrelId': str(uuid.uuid4()), 'Schwab-Client-AppId': 'AD00007961',
               'Schwab-Client-Channel': 'IO', 'Schwab-Resource-Version': '1.0'}
    chart = public_json(SCHWAB_API + '/chart-data', headers)
    summaries = [row for row in chart if row.get('hasSummary')]
    latest = max(summaries, key=lambda row: datetime.strptime(row['date'], '%m/%d/%Y'))
    date = datetime.strptime(latest['date'], '%m/%d/%Y').replace(tzinfo=timezone.utc)
    detail_url = SCHWAB_API + '/stax-data/' + date.strftime('%m%d%Y')
    detail = public_json(detail_url, headers)
    rows = parse_schwab(detail['summary'])
    pairs = {}
    for row in rows:
        row.update({'value': row['rank'], 'unit': 'Rank within net-buy/net-sell list',
                    'overlaps': overlaps(row['symbol'], scope, name=row['name'])})
        for coin in row['overlaps']:
            pairs[coin] = {key: row[key] for key in ('symbol', 'rank', 'direction')}
    return {'name': 'Schwab', 'status': 'ok', 'observedAt': date.isoformat(), 'collectedAt': stamp(),
            'sourceUrl': SCHWAB, 'dataUrl': detail_url, 'period': date.strftime('%B %Y') + ' STAX reporting period',
            'activityLabel': 'Top net buys / net sells · monthly', 'activityKind': 'net_flow_rank',
            'score': finite(detail.get('staxScore')), 'scoreChange': finite(detail.get('staxScoreChange')),
            'note': 'Reported top-five net buys and top-five net sells. Not an exhaustive holdings book, '
                    'not execution-volume rankings; no direction is inferred for unlisted names.',
            'pairs': pairs, 'leaders': rows}


def normalize_market(raw):
    symbol = raw.get('internalSymbolFull')
    identifier = raw.get('instrumentId')
    if not symbol or identifier is None:
        raise ValueError('eToro instrument has no verified symbol/ID')
    buy, sell = finite(raw.get('buyHoldingPct')), finite(raw.get('sellHoldingPct'))
    # Native fields are 0..100 percentages. Never infer zero from missing data.
    share = buy / (buy + sell) if (buy is not None and sell is not None and 0 <= buy <= 100
                                                  and 0 <= sell <= 100 and buy + sell > 0) else None
    return {'symbol': symbol, 'instrumentId': identifier, 'name': raw.get('displayname') or symbol,
            'buyHoldingPct': buy, 'sellHoldingPct': sell, 'reportedBuyShare': share,
            'viewers7d': finite(raw.get('popularityUniques7Day')),
            'traders7dChange': finite(raw.get('traders7DayChange')),
            'mark': finite(raw.get('currentRate')), 'type': raw.get('instrumentType') or raw.get('internalAssetClassName'),
            'isDelisted': raw.get('isDelisted'), 'isHidden': raw.get('isHiddenFromClient')}


def match_market(mapping, rows):
    if not mapping.get('symbol'):
        return None
    found = [row for row in rows if row.get('internalSymbolFull') == mapping['symbol']]
    if mapping.get('nameMustContain'):
        found = [row for row in found if mapping['nameMustContain'].lower() in row.get('displayname', '').lower()]
    # Reject ambiguous symbols; never take the first unrelated partial match.
    return normalize_market(found[0]) if len(found) == 1 else None


def bucket(gain):
    if gain is None:
        return None
    return 'strong_gain' if gain >= .1 else 'gain' if gain >= 0 else 'loss' if gain >= -.1 else 'large_loss'


def portfolio_positions(raw, instrument_coins):
    found = []
    seen = set()
    positions = list(raw.get('positions') or [])
    # Nested copy portfolios have an unspecified allocation denominator. Do not
    # add their percentages to direct-account percentages or infer dollar values.
    for position in positions:
        position_id = position.get('positionId')
        if position_id is None:
            # Without an identity a copied/direct row cannot be deduplicated safely.
            continue
        if position_id in seen:
            continue
        seen.add(position_id)
        coin = instrument_coins.get(position.get('instrumentId'))
        allocation = finite(position.get('investmentPct'))
        if not coin or allocation is None or allocation < 0 or not isinstance(position.get('isBuy'), bool):
            continue
        found.append({'id': position_id, 'coin': coin,
                      'side': 'long' if position['isBuy'] else 'short',
                      'allocationPct': allocation, 'entry': finite(position.get('openRate')),
                      'leverage': finite(position.get('leverage')),
                      'positionReturnPct': finite(position.get('netProfit')),
                      'openedAt': position.get('openTimestamp')})
    return sorted(found, key=lambda row: -row['allocationPct'])


def summarize_etoro(traders, coins):
    pairs = {}
    for coin in coins:
        rows = []
        for key, label in BUCKETS:
            members = [trader for trader in traders if trader['bucket'] == key]
            holders, long_users, short_users = set(), set(), set()
            long_allocation = short_allocation = 0
            position_count = 0
            for trader in members:
                for position in trader['positions']:
                    if position['coin'] != coin:
                        continue
                    holders.add(trader['username'].lower())
                    position_count += 1
                    if position['side'] == 'long':
                        long_users.add(trader['username'].lower())
                        long_allocation += position['allocationPct']
                    else:
                        short_users.add(trader['username'].lower())
                        short_allocation += position['allocationPct']
            combined = long_allocation + short_allocation
            rows.append({'id': key, 'label': label, 'sampledPortfolios': len(members), 'holders': len(holders),
                         'longHolders': len(long_users), 'shortHolders': len(short_users),
                         'positions': position_count, 'longAllocationPoints': long_allocation,
                         'shortAllocationPoints': short_allocation,
                         'allocationLongShare': long_allocation / combined if combined else None,
                         'meanAllocationPct': combined / len(members) if members else None})
        pairs[coin] = {'cohorts': rows}
    return pairs


def get_etoro(scope, sample_limit=60):
    client = Client()
    errors, matched, mappings = [], {}, {}
    for row in scope:
        coin, mapping = row['coin'], row['identity']
        mappings[coin] = {**mapping, 'matched': False}
        if mapping['symbol'] is None:
            continue
        try:
            data = client.get('/api/v1/market-data/search', fields=MARKET_FIELDS,
                              internalSymbolFull=mapping['symbol'], pageSize=100, pageNumber=1)
            instrument = match_market(mapping, data.get('items', []))
            if instrument:
                matched[coin] = instrument
                mappings[coin].update({'matched': True, 'instrumentId': instrument['instrumentId'], 'name': instrument['name']})
        except ApiError as exc:
            if exc.status in (401, 403):
                raise
            errors.append({'stage': 'mapping', 'coin': coin, 'reason': str(exc)})

    attention = client.get('/api/v1/market-data/search', fields=MARKET_FIELDS, pageSize=100,
                           pageNumber=1, sort='-popularityUniques7Day')
    leaders, seen_instruments = [], set()
    for raw in attention.get('items', []):
        instrument = normalize_market(raw)
        if instrument['instrumentId'] in seen_instruments or instrument['isDelisted'] or instrument['isHidden']:
            continue
        seen_instruments.add(instrument['instrumentId'])
        if instrument['viewers7d'] is None:
            continue
        leaders.append({'symbol': instrument['symbol'], 'name': instrument['name'],
                        'instrumentId': instrument['instrumentId'], 'value': instrument['viewers7d'],
                        'unit': 'Unique viewers / 7d', 'overlaps': overlaps(instrument['symbol'], scope, name=instrument['name'])})
    leaders.sort(key=lambda row: -row['value'])
    for index, row in enumerate(leaders):
        row['rank'] = index + 1

    # Sample multiple discovery orders, not only recent winners. All performance
    # numbers below use v2's documented fractional gain and current-month period.
    candidates = {}
    ranking_errors = []
    per_order = max(10, sample_limit // 4)
    for order in ('-copiers', '-gain', 'gain', '-trades'):
        try:
            data = client.get('/api/v2/portfolios/rankings', period=PERIOD, sort=order, pageSize=per_order, page=1)
            for row in data.get('results', []):
                username = row.get('username')
                if username and row.get('type', 'trader') == 'trader' and finite(row.get('gain')) is not None:
                    candidates.setdefault(username.lower(), row)
        except ApiError as exc:
            ranking_errors.append({'stage': 'rankings', 'reason': str(exc)})
    errors.extend(ranking_errors)
    instrument_coins = {row['instrumentId']: coin for coin, row in matched.items()}
    traders = []
    failures = 0
    for raw in list(candidates.values())[:sample_limit]:
        username = raw['username']
        if not re.fullmatch(r'[A-Za-z0-9_.\-]{1,100}', username):
            continue
        try:
            data = client.get('/api/v1/user-info/people/' + urllib.parse.quote(username, safe='') + '/portfolio/live')
            if not isinstance(data.get('positions'), list):
                raise ValueError('Public portfolio response missing positions')
            gain = finite(raw['gain'])
            traders.append({'username': username, 'gain': gain, 'period': PERIOD, 'bucket': bucket(gain),
                            'copiers': finite(raw.get('copiers')), 'riskScore': finite(raw.get('riskScore')),
                            'trades': finite(raw.get('trades')), 'observedAt': stamp(),
                            'copyGroupsExcluded': len(data.get('socialTrades') or []),
                            'profileUrl': 'https://www.etoro.com/people/' + urllib.parse.quote(username, safe=''),
                            'positions': portfolio_positions(data, instrument_coins)})
        except (ApiError, ValueError):
            failures += 1
        if (len(traders) + failures) % 10 == 0:
            print(f'eToro: {len(traders)} public portfolios read; {failures} unavailable', flush=True)
    pairs = summarize_etoro(traders, [row['coin'] for row in scope])
    for coin, row in pairs.items():
        row['mapping'] = mappings[coin]
        row['market'] = matched.get(coin)
    if not matched:
        raise RuntimeError('eToro credentials worked but no tracked instrument identities could be validated')
    return {'name': 'eToro', 'status': 'partial' if errors or failures else 'ok', 'observedAt': stamp(),
            'sourceUrl': ETORO_DOCS, 'period': 'Current calendar month to latest ranking refresh (MTD)',
            'activityLabel': 'Instrument attention / unique viewers in 7d', 'activityKind': 'instrument_viewers',
            'note': 'Public investors are a bounded discovery sample, not all eToro customers. '
                    'Performance cohorts use MTD percentage return, not Hyperliquid lifetime dollar PnL. '
                    'Direct-position allocation points weight portfolio percentages equally across accounts, not account dollars. '
                    'Nested copy portfolios are not expanded because their allocation denominator is unspecified. '
                    'Reported buy/sell holdings fields have no documented dollar-notional denominator.',
            'sample': {'candidates': len(candidates), 'checked': len(traders), 'failed': failures,
                       'holdingTrackedPairs': sum(bool(row['positions']) for row in traders),
                       'requestedLimit': sample_limit, 'discovery': ['Most copied', 'Highest MTD gain', 'Lowest MTD gain', 'Most trades']},
            'errors': errors, 'pairs': pairs, 'traders': traders, 'leaders': leaders[:30],
            'activitySearchTotal': attention.get('totalItems'), 'matchedPairs': len(matched)}


def retain(old, name, error):
    if old and old.get('observedAt'):
        return {**old, 'status': 'retained', 'lastAttemptAt': stamp(), 'refreshError': str(error)}
    return {'name': name, 'status': 'unavailable', 'observedAt': None, 'lastAttemptAt': stamp(),
            'refreshError': str(error), 'pairs': {}, 'leaders': []}


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, separators=(',', ':'), allow_nan=False) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def daily_record(data):
    result = {'date': data['generatedAt'][:10], 'collectedAt': data['generatedAt'], 'pairs': {}}
    for item in data['universe']:
        coin = item['coin']
        hl = data['platforms']['hyperliquid']['pairs'].get(coin, {})
        printer = next((row for row in hl.get('cohorts', []) if row['id'] == 8), {})
        ep = data['platforms'].get('etoro', {}).get('pairs', {}).get(coin, {})
        rh = data['platforms'].get('robinhood', {}).get('pairs', {}).get(coin, {})
        sc = data['platforms'].get('schwab', {}).get('pairs', {}).get(coin, {})
        result['pairs'][coin] = {'hyperliquidMoneyPrinterLongShare': printer.get('longShare'),
                                'hyperliquidObservedAt': data['platforms']['hyperliquid'].get('observedAt'),
                                'etoroReportedBuyShare': (ep.get('market') or {}).get('reportedBuyShare'),
                                'etoroObservedAt': data['platforms'].get('etoro', {}).get('observedAt'),
                                'robinhoodRank': rh.get('rank'), 'schwabDirection': sc.get('direction')}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public-only', action='store_true', help='Refresh public sources; retain authenticated eToro data')
    parser.add_argument('--sample-limit', type=int, default=60)
    args = parser.parse_args()
    if not 4 <= args.sample_limit <= 200:
        parser.error('sample-limit must be 4..200')
    data_dir = ROOT / 'data'
    snapshot = json.loads((data_dir / 'snapshot.json').read_text(encoding='utf-8'))
    path = data_dir / 'platforms.json'
    previous = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    scope = universe(snapshot)
    output = {'schemaVersion': 1, 'generatedAt': stamp(), 'universeObservedAt': snapshot['xyz']['marketObservedAt'],
              'universe': scope, 'platforms': {}, 'errors': []}
    output['platforms']['hyperliquid'] = get_hyperliquid(snapshot, scope)
    for key, operation in [('robinhood', lambda: get_robinhood(scope)), ('schwab', lambda: get_schwab(scope)),
                           ('etoro', lambda: get_etoro(scope, args.sample_limit))]:
        old = previous.get('platforms', {}).get(key)
        if key == 'etoro' and args.public_only:
            output['platforms'][key] = old or retain(None, 'eToro', 'Authenticated collection runs in GitHub Actions')
            continue
        try:
            print(f'Refreshing {key} public analytics...', flush=True)
            output['platforms'][key] = operation()
            print(f'{key}: {output["platforms"][key]["status"]}', flush=True)
        except (RuntimeError, ValueError, KeyError, TypeError) as exc:
            output['platforms'][key] = retain(old, key, exc)
            output['errors'].append({'platform': key, 'reason': str(exc)})
            print(f'{key}: {exc}', flush=True)
    output['platforms']['ibkr'] = {'name': 'IBKR', 'status': 'not_connected', 'observedAt': None,
        'sourceUrl': 'https://www.ibkrguides.com/traderworkstation/market-scanner-types.htm',
        'period': None, 'pairs': {}, 'leaders': [],
        'note': 'No IBKR account/scanner feed connected. Official scanners rank market-wide activity, '
                'not IBKR-only customer volume. Broker-wide customer positions are not publicly exposed by the documented account APIs.'}
    output['generatedAt'] = stamp()
    write_json(path, output)
    history_path = data_dir / 'platforms_history.json'
    history = json.loads(history_path.read_text(encoding='utf-8')) if history_path.exists() else {'schemaVersion': 1, 'days': []}
    record = daily_record(output)
    history['days'] = sorted([day for day in history['days'] if day['date'] != record['date']] + [record], key=lambda row: row['date'])[-90:]
    write_json(history_path, history)
    print(f'Published {len(scope)}-pair platform comparison; {len(history["days"])} daily records', flush=True)
    if output['errors']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
