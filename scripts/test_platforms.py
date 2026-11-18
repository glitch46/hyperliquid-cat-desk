"""Source identity, units, sample accounting, and credential-boundary tests."""
import json
import unittest
import re
from urllib.parse import urlsplit
from unittest.mock import patch

import etoro
import platforms as p


class InstrumentIdentityTests(unittest.TestCase):
    def test_exact_symbol_required_even_if_search_ignores_filter(self):
        rows = [{'internalSymbolFull': 'NVDL', 'instrumentId': 1, 'displayname': 'Leveraged NVDA'}]
        self.assertIsNone(p.match_market(p.identity('xyz:NVDA'), rows))

    def test_ticker_reuse_cannot_match_unrelated_spcx_fund(self):
        rows = [{'internalSymbolFull': 'SPCX', 'instrumentId': 1, 'displayname': 'SPAC ETF'}]
        self.assertIsNone(p.match_market(p.identity('xyz:SPCX'), rows))
        scope = [{'coin': 'xyz:SPCX', 'identity': p.identity('xyz:SPCX')}]
        self.assertEqual(p.overlaps('SPCX', scope, name='SPAC ETF'), [])
        self.assertEqual(p.overlaps('SPCX', scope, name='SpaceX'), ['xyz:SPCX'])

    def test_ambiguous_symbols_are_not_selected_arbitrarily(self):
        rows = [{'internalSymbolFull': 'NVDA', 'instrumentId': value} for value in (1, 2)]
        self.assertIsNone(p.match_market(p.identity('xyz:NVDA'), rows))

    def test_qqq_is_not_an_exact_xyz100_overlap(self):
        scope = [{'coin': 'xyz:XYZ100', 'identity': p.identity('xyz:XYZ100')}]
        self.assertEqual(p.overlaps('QQQ', scope), [])
        self.assertEqual(p.overlaps('NSDQ100', scope), [])
        self.assertEqual(p.overlaps('NSDQ100', scope, allow_reference=True), ['xyz:XYZ100'])

    def test_unknown_synthetic_remains_unmapped(self):
        self.assertEqual(p.identity('xyz:SKHX')['kind'], 'unmapped')

    def test_twenty_pair_limit_does_not_expand_for_pinned_market(self):
        snapshot = {'xyz': {'items': [{'coin': f'xyz:S{i}', 'volumeRank': i} for i in range(1, 24)]}}
        self.assertEqual(len(p.universe(snapshot)), 20)
        self.assertEqual(p.universe(snapshot)[-1]['volumeRank'], 20)


class PortfolioAccountingTests(unittest.TestCase):
    def test_copy_and_direct_position_ids_are_not_counted_twice(self):
        position = {'positionId': 1, 'instrumentId': 100, 'isBuy': True, 'investmentPct': 2.5, 'netProfit': 18}
        result = p.portfolio_positions({'positions': [position], 'socialTrades': [{'positions': [position]}]}, {100: 'xyz:NVDA'})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['allocationPct'], 2.5)
        self.assertEqual(result[0]['positionReturnPct'], 18)
        self.assertNotIn('dollarValue', result[0])

    def test_unknown_side_or_allocation_is_not_assumed_zero_or_short(self):
        rows = [{'positionId': 1, 'instrumentId': 100, 'investmentPct': 1},
                {'positionId': 2, 'instrumentId': 100, 'isBuy': True},
                {'positionId': 3, 'instrumentId': 100, 'isBuy': False, 'investmentPct': -2}]
        self.assertEqual(p.portfolio_positions({'positions': rows}, {100: 'xyz:NVDA'}), [])

    def test_nested_copy_weights_are_not_assumed_account_percentages(self):
        position = {'positionId': 2, 'instrumentId': 100, 'isBuy': True, 'investmentPct': 80}
        raw = {'positions': [], 'socialTrades': [{'investmentPct': 5, 'positions': [position]}]}
        self.assertEqual(p.portfolio_positions(raw, {100: 'xyz:NVDA'}), [])

    def test_missing_instrument_id_does_not_match_unrelated_position(self):
        raw = {'positions': [{'positionId': 1, 'instrumentId': 999, 'isBuy': True, 'investmentPct': 5}]}
        self.assertEqual(p.portfolio_positions(raw, {100: 'xyz:NVDA'}), [])

    def test_allocations_weight_accounts_equally_not_by_dollar_wealth(self):
        traders = [
            {'username': 'one', 'bucket': 'gain', 'positions': [
                {'coin': 'xyz:NVDA', 'side': 'long', 'allocationPct': 10},
                {'coin': 'xyz:NVDA', 'side': 'long', 'allocationPct': 5}]},
            {'username': 'two', 'bucket': 'gain', 'positions': [
                {'coin': 'xyz:NVDA', 'side': 'short', 'allocationPct': 5}]},
            {'username': 'flat', 'bucket': 'gain', 'positions': []},
        ]
        row = next(c for c in p.summarize_etoro(traders, ['xyz:NVDA'])['xyz:NVDA']['cohorts'] if c['id'] == 'gain')
        self.assertEqual(row['holders'], 2)
        self.assertEqual(row['positions'], 3)
        self.assertEqual(row['longHolders'], 1)
        self.assertEqual(row['shortHolders'], 1)
        self.assertEqual(row['allocationLongShare'], .75)
        self.assertAlmostEqual(row['meanAllocationPct'], 20 / 3)

    def test_empty_sample_is_unknown_not_a_flat_platform(self):
        rows = p.summarize_etoro([], ['xyz:NVDA'])['xyz:NVDA']['cohorts']
        self.assertTrue(all(row['allocationLongShare'] is None for row in rows))
        self.assertTrue(all(row['meanAllocationPct'] is None for row in rows))

    def test_mtd_gain_fraction_is_not_mistaken_for_percent_points(self):
        self.assertEqual(p.bucket(.11), 'strong_gain')
        self.assertEqual(p.bucket(.011), 'gain')
        self.assertEqual(p.bucket(-.1), 'loss')
        self.assertEqual(p.bucket(-.101), 'large_loss')
        self.assertIsNone(p.bucket(None))

    def test_reported_holding_percentages_have_separate_basis(self):
        result = p.normalize_market({'instrumentId': 100, 'internalSymbolFull': 'NVDA',
                                     'buyHoldingPct': 98, 'sellHoldingPct': 2})
        self.assertEqual(result['reportedBuyShare'], .98)
        missing = p.normalize_market({'instrumentId': 100, 'internalSymbolFull': 'NVDA'})
        self.assertIsNone(missing['reportedBuyShare'])


class PublicSourceTests(unittest.TestCase):
    def test_robinhood_rank_is_not_fabricated_as_portfolio_weight(self):
        props = {'props': {'pageProps': {'lastUpdatedDate': 'November 2, 2026', 'top10': [
            {'ticker': 'NVDA', 'name': 'NVIDIA', 'rank': 1}]}}}
        source = '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(props) + '</script>'
        date, rows = p.parse_robinhood(source)
        self.assertTrue(date.startswith('2026-11-02'))
        self.assertEqual(rows[0]['rank'], 1)
        self.assertNotIn('weight', rows[0])

    def test_schwab_uses_labeled_table_not_mentions_in_commentary(self):
        source = '''<p>NVDA was bought last month.</p><table><tr><th>Top net buys</th><th>Top net sells</th></tr>
        <tr><td><b>Intel</b> (##INTC##)</td><td><b>Apple</b> (##AAPL##)</td></tr></table>'''
        rows = p.parse_schwab(source)
        self.assertEqual([row['symbol'] for row in rows], ['INTC', 'AAPL'])
        self.assertEqual(rows[1]['direction'], 'net_sell')
        self.assertEqual(rows[0]['rank'], 1)

    def test_changed_schwab_markup_fails_instead_of_publishing_empty_list(self):
        with self.assertRaises(ValueError):
            p.parse_schwab('<p>NVDA rose 2%.</p>')

    def test_retaining_data_preserves_actual_observation_time(self):
        old = {'observedAt': '2026-11-01T00:00:00Z', 'pairs': {'xyz:NVDA': {'rank': 1}}}
        result = p.retain(old, 'Robinhood', RuntimeError('HTTP 503'))
        self.assertEqual(result['observedAt'], old['observedAt'])
        self.assertEqual(result['status'], 'retained')
        self.assertIn('lastAttemptAt', result)

    def test_private_account_endpoints_cannot_be_requested(self):
        with patch.dict('os.environ', {'ETORO_API_KEY': 'fixture-app', 'ETORO_USER_KEY': 'fixture-user'}):
            client = etoro.Client()
        with self.assertRaises(ValueError):
            client.get('/api/v1/trading/info/real/pnl')


class NavigationTests(unittest.TestCase):
    def test_all_three_pages_have_the_same_navigation(self):
        navs = []
        for name in ('index.html', 'xyz.html', 'platforms.html'):
            text = (p.ROOT / name).read_text(encoding='utf-8')
            navs.append(re.search(r'<nav id="site-nav".*?</nav>', text, re.S).group(0))
        self.assertEqual(navs[0], navs[1])
        self.assertEqual(navs[0], navs[2])
        self.assertEqual(navs[0].count('href="platforms.html"'), 1)

    def test_all_shared_navigation_destinations_exist(self):
        text = (p.ROOT / 'index.html').read_text(encoding='utf-8')
        nav = re.search(r'<nav id="site-nav".*?</nav>', text, re.S).group(0)
        for href in re.findall(r'href="([^"]+)"', nav):
            link = urlsplit(href)
            path = p.ROOT / link.path
            self.assertTrue(path.exists(), href)
            if link.fragment:
                self.assertIn('id="' + link.fragment + '"', path.read_text(encoding='utf-8'), href)


if __name__ == '__main__':
    unittest.main()
