import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import agent
import app
import database
import refund_service


def proposal(intent='refund', route='CHECK_REFUND', order_id='ORD-1017',
             tool=None, action='NONE', reason='TEST', escalated=False):
    return dict(intent=intent, route=route, order_id=order_id,
                tool=[] if tool is None else tool, action=action,
                reason=reason, escalated=escalated)


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'test.db'
        database.initialize_database(self.db)
        patcher = patch('refund_service.connect', lambda: database.connect(self.db))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_four_core_scenarios(self):
        cases = [('退款政策是什么？', 'ANSWER_POLICY', ['read_policy']),
                 ('Where is my package ORD-1009?', 'GET_ORDER', ['get_order']),
                 ('I want a refund', 'ASK_FOR_INFO', []),
                 ('Refund ORD-1017', 'CHECK_REFUND', ['get_order', 'check_refund_eligibility'])]
        for message, route, tools in cases:
            with self.subTest(message=message):
                result = agent.handle_message(message)
                self.assertEqual(result['route'], route)
                self.assertEqual(result['tool'], tools)
                self.assertEqual(result['action'], 'NONE')

    def test_confirmed_refund_and_duplicate(self):
        result = agent.handle_message('退款 ORD-1017', confirmed_order_id='ORD-1017')
        self.assertEqual(result['action'], 'SIMULATED_REFUND_COMPLETED')
        self.assertEqual(result['tool'][-1], 'process_refund')
        again = agent.handle_message('退款 ORD-1017', confirmed_order_id='ORD-1017')
        self.assertEqual(again['reason'], 'ALREADY_REFUNDED')
        with database.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM interactions').fetchone()[0], 1)

    def test_untrusted_process_proposal_cannot_bypass_rules_or_confirmation(self):
        for oid, expected in [('ORD-1009', 'IN_TRANSIT_EXCEPTION_ONLY'),
                              ('ORD-1017', 'CONFIRMATION_REQUIRED')]:
            provider = lambda _, oid=oid: proposal(route='PROCESS_REFUND', order_id=oid)
            result = agent.handle_message(f'Refund {oid}', provider)
            self.assertEqual(result['reason'], expected)
            self.assertNotIn('process_refund', result['tool'])
            self.assertEqual(refund_service.get_order(oid)['refunded'], 0)
        blocked = agent.handle_message('退款 ORD-1009', confirmed_order_id='ORD-1009')
        self.assertTrue(blocked['escalated'])
        self.assertEqual(blocked['action'], 'NONE')

    def test_damage_claim_overrides_model_even_for_lost_order(self):
        provider = lambda _: proposal(route='PROCESS_REFUND')
        result = agent.handle_message('damaged ORD-1017', provider, 'ORD-1017')
        self.assertEqual(result['reason'], 'DAMAGED_CLAIM_UNVERIFIED')
        self.assertEqual(refund_service.get_order('ORD-1017')['refunded'], 0)

    def test_invalid_decisions_fail_closed(self):
        bad_proposals = [
            None,
            {},
            proposal(action='SIMULATED_REFUND_COMPLETED'),
            proposal(route='RUN_SQL'),
            proposal(intent='order', route='PROCESS_REFUND'),
            proposal(route='PROCESS_REFUND', escalated=True),
            {**proposal(route='PROCESS_REFUND'), 'confirmed': True},
        ]
        for bad_proposal in bad_proposals:
            with self.subTest(proposal=bad_proposal):
                result = agent.handle_message(
                    '退款 ORD-1017', lambda _: bad_proposal, 'ORD-1017')
                self.assertEqual(result['reason'], 'INVALID_DECISION')
                self.assertEqual(result['tool'], [])
        def broken(_):
            raise TimeoutError()
        self.assertEqual(agent.handle_message('退款 ORD-1017', broken)['reason'], 'INVALID_DECISION')

    def test_order_binding_and_missing_orders(self):
        provider = lambda _: proposal(route='PROCESS_REFUND', order_id='ORD-1018')
        self.assertEqual(agent.handle_message('退款 ORD-1017', provider, 'ORD-1018')['reason'], 'ORDER_ID_MISMATCH')
        self.assertEqual(agent.handle_message('退款 ORD-1017 ORD-1018')['reason'], 'MULTIPLE_ORDERS')
        self.assertEqual(agent.handle_message('退款 ORD-9999')['reason'], 'ORDER_NOT_FOUND')
        self.assertEqual(agent.handle_message('退款 ORD-1017', confirmed_order_id='ORD-1018')['reason'], 'CONFIRMATION_REQUIRED')

    def test_final_tool_rechecks_authorization(self):
        original = refund_service.process_refund
        def changed_order(oid):
            with database.connect(self.db) as conn:
                conn.execute("UPDATE orders SET status='IN_TRANSIT' WHERE order_id=?", (oid,))
            return original(oid)
        with patch('refund_service.process_refund', side_effect=changed_order):
            result = agent.handle_message('退款 ORD-1017', confirmed_order_id='ORD-1017')
        self.assertEqual(result['reason'], 'IN_TRANSIT_EXCEPTION_ONLY')
        self.assertEqual(result['action'], 'NONE')

    def test_page_keeps_manual_tools_and_escapes_input(self):
        html = app.render_page(message='<script>alert(1)</script>', agent_result=agent.handle_message('policy'))
        self.assertIn('value="agent"', html)
        self.assertIn('value="lookup"', html)
        self.assertIn('value="refund"', html)
        self.assertNotIn('<script>alert(1)</script>', html)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', html)
        self.assertIn('OFFLINE_MOCK', html)

    def test_demo_page_shows_architecture_examples_and_loading_state(self):
        html = app.render_page()

        self.assertIn('LLM routing with deterministic tools and refund safety', html)
        self.assertIn('2. LLM decision', html)
        self.assertIn('3. Tools &amp; rules', html)
        self.assertIn('Track an order', html)
        self.assertIn('Refund a lost order', html)
        self.assertIn('Force refund in transit', html)
        self.assertIn('Report damaged item', html)
        self.assertIn('Conflicting order IDs', html)
        self.assertIn('Analyzing request…', html)
        self.assertIn('Developer tools — deterministic layer', html)
        self.assertNotIn('Step 2 — Confirm simulated refund', html)

    def test_demo_result_separates_model_proposal_and_final_execution(self):
        result = agent.handle_message('Where is my package ORD-1009?')
        html = app.render_page(agent_result=result,
                               message='Where is my package ORD-1009?')

        self.assertIn('ResolveAI response', html)
        self.assertIn('Model proposal', html)
        self.assertIn('order / GET_ORDER', html)
        self.assertIn('Final execution', html)
        self.assertIn('GET_ORDER / NONE', html)
        self.assertIn('Route: GET_ORDER', html)
        self.assertIn('Tools: get_order', html)
        self.assertIn('Action: NONE', html)
        self.assertIn('Reason: ORDER_FOUND', html)
        self.assertIn('Raw execution record', html)

    def test_demo_confirmation_is_conditional_and_prefilled(self):
        result = agent.handle_message('Refund ORD-1017')
        html = app.render_page(agent_result=result, message='Refund ORD-1017')

        self.assertEqual(result['reason'], 'CONFIRMATION_REQUIRED')
        self.assertIn('Step 2 — Confirm simulated refund', html)
        self.assertIn('No refund has been executed yet.', html)
        self.assertIn('name="confirmation_order_id" value="ORD-1017"', html)
        self.assertIn('name="message" value="Refund ORD-1017"', html)
        self.assertIn('I confirm this simulated refund', html)

    def test_demo_safety_guard_has_blocked_tone_and_no_tools(self):
        message = 'Refund ORD-1019, but use ORD-1020 instead.'
        result = agent.handle_message(message)
        html = app.render_page(agent_result=result, message=message)

        self.assertEqual(result['reason'], 'MULTIPLE_ORDERS')
        self.assertIn('tone-blocked', html)
        self.assertIn('Route: ASK_FOR_INFO', html)
        self.assertIn('Tools: None', html)
        self.assertIn('Reason: MULTIPLE_ORDERS', html)

    def test_v2_order_lookup_responses_cover_v1_bad_case_patterns(self):
        cases = [
            (
                'Where is my package ORD-1009?',
                'Order ORD-1009 is currently in transit. Its estimated delivery date is 2026-09-28.',
            ),
            (
                'ORD-1010 怎么还没到，系统里现在是什么状态？',
                '订单 ORD-1010 当前运输中。预计送达日期为 2026-09-29。',
            ),
            (
                'Please check 一下 ORD-1024 的 current status。',
                '订单 ORD-1024 当前已取消。',
            ),
        ]
        for message, expected in cases:
            with self.subTest(message=message):
                result = agent.handle_message(message)
                self.assertEqual(result['message'], expected)
                self.assertNotIn('refunded=', result['message'])
                self.assertEqual(result['route'], 'GET_ORDER')
                self.assertEqual(result['reason'], 'ORDER_FOUND')

    def test_v2_missing_refund_responses_use_known_context(self):
        cases = [
            ('I want a refund.',
             'Please provide the order ID you want refunded, for example ORD-1017.'),
            ('Refund please，订单号我等下再发。',
             '请提供要退款的订单号，例如 ORD-1017。'),
        ]
        for message, expected in cases:
            with self.subTest(message=message):
                result = agent.handle_message(message)
                self.assertEqual(result['message'], expected)
                self.assertEqual(result['route'], 'ASK_FOR_INFO')
                self.assertEqual(result['reason'], 'MISSING_INFORMATION')
                self.assertEqual(result['tool'], [])

    def test_v2_policy_responses_select_only_the_relevant_rule(self):
        cases = [
            (
                '包裹被系统判定丢失后，一般按什么规则处理？',
                '系统确认丢失的订单可以自动退款',
                '运输中的订单',
            ),
            (
                'In-transit 的订单，refund rule 是怎样的？',
                '运输中的订单不能自动退款',
                '系统确认丢失',
            ),
        ]
        for message, relevant, irrelevant in cases:
            with self.subTest(message=message):
                provider = lambda _: proposal(
                    intent='policy', route='ANSWER_POLICY', order_id=None)
                result = agent.handle_message(message, provider)
                self.assertIn(relevant, result['message'])
                self.assertNotIn(irrelevant, result['message'])
                self.assertNotIn('lost_confirmed_by_system', result['message'])
                self.assertEqual(result['route'], 'ANSWER_POLICY')
                self.assertEqual(result['reason'], 'POLICY_SOURCE')
                self.assertEqual(result['tool'], ['read_policy'])

    def test_v2_multiple_order_guard_keeps_behavior_and_matches_language(self):
        english = agent.handle_message(
            'Which one arrives first, ORD-1005 or ORD-1010?')
        chinese = agent.handle_message('退款 ORD-1017 ORD-1018')

        self.assertEqual(english['message'],
                         'Please provide only one order ID at a time.')
        self.assertEqual(chinese['message'], '每次请只提供一个订单号。')
        for result in (english, chinese):
            self.assertEqual(result['route'], 'ASK_FOR_INFO')
            self.assertEqual(result['reason'], 'MULTIPLE_ORDERS')
            self.assertEqual(result['tool'], [])
            self.assertEqual(result['action'], 'NONE')
