"""Read-only eToro public-market and public-investor client. No account endpoints."""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE = 'https://public-api.etoro.com'
MARKET_FIELDS = ','.join((
    'instrumentId', 'displayname', 'internalSymbolFull', 'instrumentType',
    'instrumentTypeID', 'internalExchangeName', 'internalAssetClassName',
    'isDelisted', 'isCurrentlyTradable', 'isActiveInPlatform', 'isHiddenFromClient',
    'popularityUniques7Day', 'popularityUniques30Day', 'holdingPct',
    'buyHoldingPct', 'sellHoldingPct', 'traders7DayChange', 'currentRate',
    'dailyPriceChange',
))


class ApiError(RuntimeError):
    def __init__(self, path, status=None):
        self.status = status
        # Never propagate response bodies, headers, or credentials into logs/data.
        super().__init__(f'eToro {path.split("?")[0]}: HTTP {status}' if status else f'eToro {path}: request failed')


class Client:
    def __init__(self):
        self.api_key = os.environ.get('ETORO_API_KEY', '').strip()
        self.user_key = os.environ.get('ETORO_USER_KEY', '').strip()
        self.next_request = 0
        if not self.api_key or not self.user_key:
            raise RuntimeError('ETORO_API_KEY and ETORO_USER_KEY are required')

    def get(self, path, **params):
        allowed = ('/api/v1/market-data/', '/api/v2/market-data/',
                   '/api/v2/portfolios/rankings', '/api/v1/user-info/people/', '/api/v1/curated-lists')
        if not path.startswith(allowed) or '..' in path:
            raise ValueError('Only public-market/public-investor GET endpoints are allowed')
        query = urllib.parse.urlencode({key: str(value).lower() if isinstance(value, bool) else value
                                       for key, value in params.items() if value is not None})
        url = BASE + path + ('?' + query if query else '')
        for attempt in range(3):
            delay = self.next_request - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            self.next_request = time.monotonic() + 1.15
            req = urllib.request.Request(url, headers={
                'x-api-key': self.api_key, 'x-user-key': self.user_key,
                'x-request-id': str(uuid.uuid4()), 'Accept': 'application/json',
                'User-Agent': 'Cat-Desk-Public-Analytics/1.0',
            }, method='GET')
            try:
                with urllib.request.urlopen(req, timeout=35) as response:
                    return json.load(response)
            except urllib.error.HTTPError as exc:
                if exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                    retry = exc.headers.get('Retry-After', '15')
                    time.sleep(min(65, max(5, int(retry) if retry.isdigit() else 15)))
                    continue
                raise ApiError(path, exc.code) from None
            except (urllib.error.URLError, TimeoutError, ValueError):
                if attempt < 2:
                    time.sleep(3 * (attempt + 1))
                    continue
                raise ApiError(path) from None


def probe():
    client = Client()
    queries = [
        ('markets', '/api/v1/market-data/search', dict(fields=MARKET_FIELDS, pageSize=3, pageNumber=1, sort='-popularityUniques7Day')),
        ('rankings', '/api/v2/portfolios/rankings', dict(period='CurrMonth', pageSize=3, page=1, sort='-copiers')),
        ('users', '/api/v1/user-info/people/search', dict(period='CurrMonth', pageSize=3, page=1, sort='-copiers', isTestAccount=False, optIn=True)),
        ('lists', '/api/v1/curated-lists', {}),
    ]
    username = None
    for label, path, params in queries:
        try:
            data = client.get(path, **params)
            print(label, 'OK', 'top-level keys:', list(data) if isinstance(data, dict) else type(data).__name__, flush=True)
            rows = data.get('results', data.get('items', data.get('curatedLists', []))) if isinstance(data, dict) else []
            for row in rows[:3]:
                allow = {'instrumentId', 'displayname', 'internalSymbolFull', 'instrumentType',
                         'instrumentTypeID', 'popularityUniques7Day', 'holdingPct', 'buyHoldingPct',
                         'sellHoldingPct', 'username', 'userName', 'gain', 'riskScore', 'copiers',
                         'name', 'description', 'currentRate', 'trades', 'isTestAccount'}
                print(json.dumps({key: val for key, val in row.items() if key in allow}), flush=True)
            if label == 'rankings' and rows:
                username = rows[0].get('username')
            if label == 'lists':
                print('Available list names:', [row.get('name') for row in rows], flush=True)
        except (ApiError, RuntimeError) as exc:
            print(label, str(exc), flush=True)
    if username:
        path = '/api/v1/user-info/people/' + urllib.parse.quote(username, safe='') + '/portfolio/live'
        try:
            data = client.get(path)
            print('Public portfolio keys:', list(data), flush=True)
            rows = data.get('positions', [])
            for row in rows[:3]:
                allow = {'positionId', 'openTimestamp', 'instrumentId', 'isBuy', 'leverage',
                         'investmentPct', 'netProfit', 'openRate'}
                print(json.dumps({key: val for key, val in row.items() if key in allow}), flush=True)
            print('Position count:', len(rows), 'Copy groups:', len(data.get('socialTrades', [])), flush=True)
        except ApiError as exc:
            print(str(exc), flush=True)


if __name__ == '__main__':
    probe()
