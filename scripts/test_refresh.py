"""Accounting and coverage checks for financial data; no network requests."""
import unittest
from unittest.mock import patch

import refresh


def fill(index, coin='xyz:GOLD', px='100', size='1', timestamp=None, direction='Open Long'):
    return {'tid': index, 'oid': index, 'time': timestamp if timestamp is not None else index,
            'coin': coin, 'px': px, 'sz': size, 'side': 'B', 'closedPnl': '2', 'dir': direction}


def xyz_metric(segment_id=8, gross=1000, long_value=300, category='pnl'):
    return {'segment': {'id': segment_id, 'name': 'Test cohort', 'category': category,
                        'criteria': {'minPnl': 1_000_000}},
            'totalPositionValue': gross, 'totalPositionValueLong': long_value,
            'positionCount': 12, 'timestamp': '2026-11-16T15:00:00Z'}


class InstrumentGroupTests(unittest.TestCase):
    def test_known_instrument_types(self):
        self.assertEqual(refresh.instrument_category('xyz:XYZ100'), 'indices')
        self.assertEqual(refresh.instrument_category('xyz:GOLD'), 'commodities')
        self.assertEqual(refresh.instrument_category('xyz:EUR'), 'fx')
        self.assertEqual(refresh.instrument_category('xyz:TLT'), 'etfs')

    def test_unknown_symbol_falls_back_to_equity_not_dropped(self):
        self.assertEqual(refresh.instrument_category('xyz:NEWCO'), 'equities')

    def test_group_reads_symbol_suffix_not_dex_prefix(self):
        self.assertEqual(refresh.instrument_category('km:GOLD'), 'commodities')
        self.assertEqual(refresh.instrument_category('xyz:NVDA'), 'equities')


class XyzCohortTests(unittest.TestCase):
    def test_per_pair_exposure_derives_short_and_signed_net(self):
        rows = refresh.normalize_xyz_cohorts('xyz:NVDA', {
            'coin': 'xyz:NVDA', 'cohortMetrics': [xyz_metric()]})
        self.assertEqual(rows[0]['short'], 700)
        self.assertEqual(rows[0]['net'], -400)
        self.assertEqual(rows[0]['longShare'], .3)
        self.assertEqual(rows[0]['positions'], 12)

    def test_overlapping_size_cohorts_do_not_enter_pair_totals(self):
        rows = refresh.normalize_xyz_cohorts('xyz:NVDA', {
            'coin': 'xyz:NVDA', 'cohortMetrics': [xyz_metric(7, category='size'), xyz_metric(8)]})
        self.assertEqual([row['id'] for row in rows], [8])
        self.assertEqual(sum(row['gross'] for row in rows), 1000)

    def test_missing_cohort_is_not_synthesized_as_zero(self):
        rows = refresh.normalize_xyz_cohorts('xyz:NVDA', {
            'coin': 'xyz:NVDA', 'cohortMetrics': [xyz_metric(8)]})
        self.assertEqual(len(rows), 1)
        self.assertNotIn(9, [row['id'] for row in rows])

    def test_explicit_zero_is_flat_with_undefined_direction(self):
        rows = refresh.normalize_xyz_cohorts('xyz:NVDA', {
            'coin': 'xyz:NVDA', 'cohortMetrics': [xyz_metric(gross=0, long_value=0)]})
        self.assertEqual(rows[0]['net'], 0)
        self.assertIsNone(rows[0]['longShare'])

    def test_null_exposure_is_rejected_instead_of_becoming_flat(self):
        with self.assertRaises(ValueError):
            refresh.normalize_xyz_cohorts('xyz:NVDA', {
                'coin': 'xyz:NVDA', 'cohortMetrics': [xyz_metric(long_value=None)]})

    def test_duplicate_cohorts_cannot_double_count_exposure(self):
        with self.assertRaises(ValueError):
            refresh.normalize_xyz_cohorts('xyz:NVDA', {
                'coin': 'xyz:NVDA', 'cohortMetrics': [xyz_metric(), xyz_metric()]})

    def test_invalid_long_exceeding_gross_is_rejected(self):
        with self.assertRaises(ValueError):
            refresh.normalize_xyz_cohorts('xyz:NVDA', {
                'coin': 'xyz:NVDA', 'cohortMetrics': [xyz_metric(long_value=1200)]})

    def test_wrong_pair_response_is_rejected(self):
        with self.assertRaises(ValueError):
            refresh.normalize_xyz_cohorts('xyz:NVDA', {'coin': 'xyz:SP500', 'cohortMetrics': []})

    def test_public_position_sample_deduplicates_without_inventing_membership(self):
        raw_position = {'id': 'same-position', 'address': '0xwallet', 'coin': 'xyz:NVDA',
                        'side': 'short', 'value': -500, 'profile': {'segments': [7, 8]}}

        def source(url):
            if url.endswith('positions.json'):
                return {'coin': 'xyz:NVDA', 'positions': [raw_position, raw_position]}
            return {'coin': 'xyz:NVDA', 'cohortMetrics': [xyz_metric()]}

        with patch.object(refresh, 'fetch', side_effect=source):
            data = refresh.get_xyz_dashboard({'fetchedAt': '2026-11-16T15:00:00Z',
                'items': [{'coin': 'xyz:NVDA', 'volume24h': 100_000_000}]})
        pair = data['items'][0]
        self.assertEqual(len(pair['positions']), 1)
        self.assertEqual(pair['positions'][0]['pnlCohortIds'], [8])
        self.assertFalse(pair['cohortCoverageComplete'])


class VolumeAndCoverageTests(unittest.TestCase):
    def test_expired_budget_is_not_an_empty_complete_wallet(self):
        with patch.object(refresh, 'SCREEN_DEADLINE', 1), patch.object(refresh, 'fetch') as network:
            with self.assertRaises(refresh.ScreeningBudgetReached):
                refresh.info('userFillsByTime', user='0xwallet', startTime=0)
        network.assert_not_called()

    def test_volume_is_notional_not_fill_count_and_excludes_spot(self):
        values = [fill(1, px='200', size='3'), fill(2, 'BTC', px='100', size='2'),
                  fill(3, '@107', px='100000', direction='Buy'),
                  fill(4, 'PURR/USDC', px='100000', direction='Buy')]
        result = refresh.summarize_fills(values)
        self.assertEqual(result['perpVolume'], 800)
        self.assertEqual(result['xyzVolume'], 600)
        self.assertEqual(result['xyzShare'], .75)
        self.assertEqual(result['xyzClosedPnl'], 2)

    def test_all_perp_venues_are_in_the_denominator(self):
        result = refresh.summarize_fills([fill(1), fill(2, 'hyna:BTC'), fill(3, 'cash:GOLD')])
        self.assertAlmostEqual(result['xyzShare'], 1 / 3)

    def test_no_volume_is_unknown_share_not_zero_or_majority(self):
        self.assertIsNone(refresh.summarize_fills([])['xyzShare'])

    def test_inclusive_pagination_deduplicates_boundary(self):
        first = [fill(i) for i in range(2000)]
        with patch.object(refresh, 'info', side_effect=[first, [fill(1999), fill(2000)]]) as api:
            result = refresh.get_fills('0xwallet', 0, 3000)
        self.assertTrue(result['complete'])
        self.assertEqual(result['fillCount'], 2001)
        self.assertEqual(result['xyzVolume'], 200100)
        self.assertEqual(api.call_args.kwargs['startTime'], 1999)

    def test_retention_cap_never_qualifies_as_complete(self):
        pages = [[fill(i) for i in range(k * 2000, (k + 1) * 2000)] for k in range(5)]
        with patch.object(refresh, 'info', side_effect=pages):
            result = refresh.get_fills('0xwallet', 0, 20_000)
        self.assertFalse(result['complete'])
        self.assertEqual(result['coverageReason'], '10,000-fill retention limit')
        self.assertEqual(result['xyzShare'], 1)

    def test_full_timestamp_page_cannot_skip_unseen_fills(self):
        page = [fill(i, timestamp=7) for i in range(2000)]
        with patch.object(refresh, 'info', side_effect=[page, page]):
            result = refresh.get_fills('0xwallet', 0, 100)
        self.assertFalse(result['complete'])
        self.assertEqual(result['coverageReason'], 'Saturated timestamp boundary')

    def test_page_budget_is_not_complete(self):
        page = [fill(i) for i in range(2000)]
        with patch.object(refresh, 'info', return_value=page):
            result = refresh.get_fills('0xwallet', 0, 10_000, max_pages=1)
        self.assertFalse(result['complete'])

    def test_fill_network_failure_is_not_an_empty_wallet(self):
        with patch.object(refresh, 'info', side_effect=RuntimeError('unavailable')):
            with self.assertRaises(RuntimeError):
                refresh.get_fills('0xwallet', 0, 100)

    def test_signed_position_size_sets_side_not_absolute_notional(self):
        result = refresh.position({'coin': 'xyz:GOLD', 'szi': '-3', 'positionValue': '900',
                                   'entryPx': '310', 'unrealizedPnl': '30'}, 'Hyperliquid')
        self.assertEqual(result['side'], 'short')
        self.assertEqual(result['value'], 900)
        self.assertEqual(result['mark'], 300)

    def test_allocation_uses_detail_denominator_not_separate_summary(self):
        row = {'segmentId': 8, 'segment': {'name': 'Test', 'category': 'pnl', 'criteria': {'minPnl': 0}},
               'positionValue': 1000, 'positionLongValue': 600, 'positionShortValue': 400,
               'countTraders': 10, 'countTradersInPosition': 8}
        detail = {'countTraders': 10, 'countTraders24HoursAgo': 9,
                  'openPerpsSummary': {'totalValue': 1200}, 'largestPositions': [],
                  'top10OpenPerps': [{'coin': 'BTC', 'totalValue': 300,
                                      'totalValueLong': 100, 'totalValueShort': 200}]}
        result = refresh.normalize_cohort(row, detail, '2026-01-01T00:00:00Z')
        self.assertEqual(result['gross'], 1000)
        self.assertEqual(result['allocationGross'], 1200)
        self.assertEqual(result['allocationCoverage'], .25)
        self.assertEqual(result['otherAllocation'], 900)
        self.assertEqual(result['walletChange24h'], 1)


if __name__ == '__main__':
    unittest.main()
