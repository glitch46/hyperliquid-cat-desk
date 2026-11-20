import unittest
from unittest.mock import Mock

from coinbase_seller import DAY, SAT, flow, get_hub_spends, parse_etf, retain, summarize_incoming, tape_summary, trend


class ChainEvidenceTests(unittest.TestCase):
    def test_mixed_inputs_bound_payments_without_counting_change_as_a_deposit(self):
        tx = {'txid': 'payment', 'time': 1, 'blockHeight': 100, 'feeSats': 10,
              'inputs': [{'address': 'relay', 'sats': 600}, {'address': 'unrelated', 'sats': 300}],
              'outputs': [{'address': 'hub', 'sats': 500}, {'address': 'relay', 'sats': 390}]}
        row = flow(tx, {'relay'}, 'hub', set())
        self.assertEqual((row['hubFundingLowerSats'], row['hubFundingUpperSats']), (200, 500))
        self.assertEqual(row['netWatchsetDebitIncludingFeesSats'], 210)
        self.assertEqual(row['externalIncomingSats'], 0)
        self.assertIsNone(row['coinbaseFundingLowerSats'])

    def test_repeat_recipient_does_not_imply_repeat_sender(self):
        def credit(txid, inputs, amount):
            tx = {'txid': txid, 'time': 1, 'blockHeight': 100, 'feeSats': 0,
                  'inputs': [{'address': address, 'sats': sats} for address, sats in inputs],
                  'outputs': [{'address': 'relay', 'sats': amount}]}
            return flow(tx, {'relay', 'change'}, 'hub', set())

        rows = [credit('first', [('source-a', SAT)], SAT),
                credit('second', [('source-b', 2 * SAT), ('source-c', 3 * SAT)], 5 * SAT)]
        summary = summarize_incoming(rows, {'relay', 'change'}, 2, True)
        self.assertEqual(summary['addresses'][0]['receivedSats'], 6 * SAT)
        self.assertEqual(summary['addresses'][0]['largestTxid'], 'second')
        self.assertIsNone(summary['singleFunderAddress'])
        self.assertIsNone(summarize_incoming(rows, {'relay', 'change'}, 2, False))

    def test_weekly_direction_is_unknown_when_funding_ranges_overlap(self):
        rows = [{'time': 6 * DAY, 'hubFundingLowerSats': 100, 'hubFundingUpperSats': 300},
                {'time': 7 * DAY, 'hubFundingLowerSats': 200, 'hubFundingUpperSats': 200},
                {'time': 14 * DAY, 'hubFundingLowerSats': 500, 'hubFundingUpperSats': 500}]
        observed = trend(rows, 0, 14 * DAY, True)
        self.assertEqual(observed['direction'], 'indeterminate')
        self.assertIsNone(observed['changePct'])
        self.assertEqual(observed['latest7dSats'], 200)
        self.assertIsNone(trend(rows, 0, 14 * DAY, False)['latest7dSats'])

    def test_reused_funding_requires_the_same_output_not_just_the_same_address(self):
        txs = [
            {'txid': 'first', 'time': 1, 'blockHeight': 100, 'feeSats': 1,
             'inputs': [{'address': 'a', 'sats': 601}],
             'outputs': [{'address': 'relay', 'sats': 100, 'vout': 0}, {'address': 'b', 'sats': 500, 'vout': 1}]},
            {'txid': 'second', 'time': 2, 'blockHeight': 101, 'feeSats': 1,
             'inputs': [{'address': 'b', 'sats': 500, 'txid': 'first', 'vout': 0}],
             'outputs': [{'address': 'relay', 'sats': 499, 'vout': 0}]},
        ]
        def summary():
            return summarize_incoming([flow(tx, {'relay'}, 'hub', set()) for tx in txs], {'relay'}, 3, True)

        self.assertEqual(summary()['reusedFundingOutputs'], [])
        txs[1]['inputs'][0]['vout'] = 1
        self.assertEqual(summary()['reusedFundingOutputs'][0]['sats'], 500)
        self.assertIsNone(summary()['singleFunderAddress'])

    def test_hub_spend_must_consume_the_exact_observed_outpoint(self):
        flows = [{'txid': 'relay', 'hubFundingUpperSats': 100,
                  'destinations': [{'address': 'hub', 'sats': 100, 'vout': 0}]}]
        status = {'confirmed': True, 'block_height': 101, 'block_time': 42}
        outspends = [{'spent': True, 'status': status, 'txid': 'spend', 'vin': 0}]
        raw = {'txid': 'spend', 'status': status, 'fee': 1,
               'vin': [{'txid': 'relay', 'vout': 1, 'prevout': {'scriptpubkey_address': 'hub', 'value': 100}}],
               'vout': [{'scriptpubkey_address': 'elsewhere', 'value': 99}]}
        api = Mock()
        api.get.side_effect = [outspends, raw]
        self.assertEqual(get_hub_spends(api, flows, 'hub')['receipts'][0]['status'], 'unavailable')
        raw['vin'][0]['vout'] = 0
        api.get.side_effect = [outspends, raw]
        row = get_hub_spends(api, flows, 'hub')['receipts'][0]
        self.assertEqual(row['status'], 'confirmed')
        self.assertEqual(row['nonHubOutputs'][0]['sats'], 99)


class MarketEvidenceTests(unittest.TestCase):
    def test_tape_counts_each_anonymous_trade_once_and_reverses_maker_side(self):
        first = {'trade_id': 1, 'side': 'buy', 'size': '3', 'time': '2026-11-20T14:40:18Z'}
        second = {'trade_id': 2, 'side': 'sell', 'size': '1', 'time': '2026-11-20T14:40:19Z'}
        malformed = {'trade_id': 3, 'side': 'buy', 'size': 'N/A', 'time': second['time']}
        result = tape_summary([second, first, first, malformed])
        self.assertEqual(result['tradeCount'], 2)
        self.assertEqual(result['aggressorSellShare'], 0.75)

    def test_pending_etf_reporting_day_is_not_assumed_to_have_zero_flow(self):
        table = '''<table><tr><th>Date</th><th>IBIT</th><th>FBTC</th><th>Total</th></tr>
                  <tr><td>19 Nov 2026</td><td>(541.1)</td><td>0.0</td><td>(541.1)</td></tr>
                  <tr><td>20 Nov 2026</td><td>-</td><td>-</td><td>0.0</td></tr></table>'''
        rows = parse_etf(table, 1795046400, 1795219200)
        self.assertEqual([(row['date'], row['totalUsdMillions']) for row in rows], [('2026-11-19', -541.1)])

    def test_repeated_failure_cannot_turn_unavailable_data_into_an_observation(self):
        old = retain(None, 'offline')
        self.assertEqual(retain(old, 'still offline')['status'], 'unavailable')
        old = {'observedAt': '2026-11-19T00:00:00+00:00', 'daily': []}
        self.assertEqual(retain(old, 'offline')['observedAt'], old['observedAt'])


if __name__ == '__main__':
    unittest.main()
