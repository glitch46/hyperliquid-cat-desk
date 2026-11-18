"""Financial distance, crypto-only scope, deduplication, and freshness boundaries."""
import unittest

import fast_refresh
import liquidations as l

ADDRESS = '0x' + '1' * 40
OTHER = '0x' + '2' * 40


def raw_position(**changes):
    row = {'coin': 'BTC', 'szi': '10', 'positionValue': '500000', 'liquidationPx': '49000',
           'entryPx': '51000', 'unrealizedPnl': '-10000', 'leverage': {'type': 'cross', 'value': 20}}
    return {**row, **changes}


def discovery(address=ADDRESS, **changes):
    return {'address': address, 'coin': 'BTC', 'side': 'long', 'value': 500_000,
            'mark': 50_000, 'liquidation': 49_000, **changes}


def cohort_source(positions):
    return {'sourceUpdatedAt': '2026-11-18T10:00:00Z', 'items': [
        {'id': 8, 'category': 'pnl', 'observedAt': '2026-11-18T10:01:00Z', 'largestPositions': positions}]}


class DistanceTests(unittest.TestCase):
    def test_long_requires_a_downward_move(self):
        self.assertAlmostEqual(l.distance('long', 100, 95), .05)

    def test_short_requires_an_upward_move(self):
        self.assertAlmostEqual(l.distance('short', 100, 105), .05)

    def test_a_crossed_estimate_is_not_hidden_by_absolute_value(self):
        self.assertLess(l.distance('long', 100, 101), 0)
        self.assertLess(l.distance('short', 100, 99), 0)

    def test_null_zero_negative_prices_do_not_mean_zero_risk(self):
        for mark, price in [(0, 100), (100, 0), (100, None), (None, 100), (-1, 1)]:
            self.assertIsNone(l.distance('long', mark, price))


class AccountPositionTests(unittest.TestCase):
    def test_distance_uses_the_mark_from_the_same_account_reply(self):
        row = l.normalize_position(ADDRESS, raw_position(), {'BTC'}, {}, '2026-11-18T10:00:00Z')
        self.assertEqual(row['mark'], 50_000)
        self.assertAlmostEqual(row['distance'], .02)
        self.assertEqual(row['value'], 500_000)

    def test_signed_size_sets_side_not_positive_absolute_notional(self):
        row = l.normalize_position(ADDRESS, raw_position(szi='-10', liquidationPx='51000'), {'BTC'}, {}, '2026-11-18T10:00:00Z')
        self.assertEqual(row['side'], 'short')
        self.assertAlmostEqual(row['distance'], .02)

    def test_missing_liquidation_price_is_excluded(self):
        for value in (None, '0', '-10', 'NaN', 'Infinity'):
            self.assertIsNone(l.normalize_position(ADDRESS, raw_position(liquidationPx=value), {'BTC'}, {}, 'now'))

    def test_zero_size_cannot_divide_or_create_an_open_position(self):
        self.assertIsNone(l.normalize_position(ADDRESS, raw_position(szi='0'), {'BTC'}, {}, 'now'))

    def test_small_or_untracked_positions_cannot_enter_rankings(self):
        self.assertIsNone(l.normalize_position(ADDRESS, raw_position(positionValue='99999'), {'BTC'}, {}, 'now'))
        self.assertIsNone(l.normalize_position(ADDRESS, raw_position(coin='xyz:NVDA'), {'BTC'}, {}, 'now'))

    def test_native_metadata_excludes_stocks_hip3_spot_and_gold_proxies(self):
        meta = {'universe': [{'name': name} for name in ['BTC', 'ETH', 'HYPE', 'xyz:NVDA', 'hyna:BTC', '@107', 'NVDA', 'PAXG', 'XAUT']]}
        self.assertEqual(l.crypto_symbols(meta), {'BTC', 'ETH', 'HYPE'})


class DiscoveryAndCoverageTests(unittest.TestCase):
    def test_overlapping_size_and_pnl_cohorts_do_not_duplicate_wallet_positions(self):
        data = cohort_source([discovery()])
        data['items'].append({'id': 7, 'category': 'size', 'largestPositions': [discovery()]})
        rows, _ = l.candidates(data, {'BTC'}, {'BTC': 50_000})
        self.assertEqual(len(rows), 1)
        self.assertEqual(l.select_wallets(rows, 60), [ADDRESS])

    def test_a_stale_discovery_mark_can_only_influence_selection_not_verified_values(self):
        rows, _ = l.candidates(cohort_source([discovery(mark=1)]), {'BTC'}, {'BTC': 50_000})
        self.assertAlmostEqual(rows[0]['candidateDistance'], .02)

    def test_tradfi_position_cannot_seed_a_crypto_wallet_query(self):
        rows, _ = l.candidates(cohort_source([discovery(coin='xyz:NVDA')]), {'BTC'}, {'BTC': 50_000})
        self.assertEqual(rows, [])

    def test_successful_empty_account_removes_the_old_position(self):
        class Client:
            calls = 0
            def get(self, kind, **params):
                self.calls += 1
                return [{'universe': [{'name': 'BTC'}]}, [{'markPx': '50000'}]] if kind == 'metaAndAssetCtxs' else {'assetPositions': []}
        old = {'positions': [discovery()]}
        result = l.collect(cohort_source([discovery()]), old, client=Client())
        self.assertEqual(result['positions'], [])
        self.assertEqual(result['coverage']['verifiedWallets'], 1)
        self.assertIn(ADDRESS, result['walletChecks'])

    def test_failed_account_is_unknown_not_an_empty_success(self):
        class Client:
            calls = 0
            def get(self, kind, **params):
                self.calls += 1
                if kind == 'metaAndAssetCtxs':
                    return [{'universe': [{'name': 'BTC'}]}, [{'markPx': '50000'}]]
                raise RuntimeError('unavailable')
        with self.assertRaises(RuntimeError):
            l.collect(cohort_source([discovery()]), client=Client())

    def test_successful_account_deduplicates_records_and_excludes_xyz(self):
        class Client:
            calls = 0
            def get(self, kind, **params):
                self.calls += 1
                if kind == 'metaAndAssetCtxs':
                    return [{'universe': [{'name': 'BTC'}]}, [{'markPx': '40000'}]]
                return {'time': 1_795_000_000_000, 'assetPositions': [
                    {'position': raw_position()}, {'position': raw_position()},
                    {'position': raw_position(coin='xyz:NVDA')}]}
        result = l.collect(cohort_source([discovery()]), client=Client())
        self.assertEqual(len(result['positions']), 1)
        self.assertAlmostEqual(result['positions'][0]['distance'], .02)
        self.assertEqual(result['positions'][0]['mark'], 50_000)


class FrequentSnapshotTests(unittest.TestCase):
    def test_quote_refresh_does_not_retimestamp_cohort_or_position_observations(self):
        old = {'fetchedAt': '2026-11-18T10:00:00Z', 'marketObservedAt': '2026-11-18T10:00:00Z',
               'items': [{'coin': 'xyz:NVDA', 'volumeRank': 1, 'mark': 100,
                          'fetchedAt': '2026-11-18T10:00:00Z', 'positions': [{'id': 'original'}]}]}
        markets = {'fetchedAt': '2026-11-18T10:15:00Z',
                   'items': [{'coin': 'xyz:NVDA', 'volume24h': 500, 'mark': 110}]}
        result = fast_refresh.refresh_xyz_quotes(old, markets)
        self.assertEqual(result['marketObservedAt'], markets['fetchedAt'])
        self.assertEqual(result['items'][0]['mark'], 110)
        self.assertEqual(result['items'][0]['fetchedAt'], old['fetchedAt'])
        self.assertEqual(result['items'][0]['positions'], [{'id': 'original'}])
        self.assertEqual(old['items'][0]['mark'], 100)

    def test_newer_full_snapshot_takes_precedence_over_cached_fast_section(self):
        fast = {'cohorts': {'fetchedAt': '2026-11-18T10:00:00Z', 'value': 'old'}}
        base = {'cohorts': {'fetchedAt': '2026-11-18T10:15:00Z', 'value': 'new'}}
        self.assertEqual(fast_refresh.newest(fast, base, 'cohorts')['value'], 'new')


if __name__ == '__main__':
    unittest.main()
