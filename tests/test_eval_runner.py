import json
import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from eval import eval_runner
import llm_decision


def proposal(intent, route, order_id):
    return {
        'intent': intent,
        'route': route,
        'order_id': order_id,
        'tool': [],
        'action': 'NONE',
        'reason': 'TEST_PROPOSAL',
        'escalated': route == 'ESCALATE',
    }


class FakeHTTPResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.body).encode('utf-8')


def responses_body(decision, usage_marker=True):
    body = {
        'status': 'completed',
        'output': [{
            'type': 'message',
            'content': [{
                'type': 'output_text',
                'text': json.dumps(decision),
            }],
        }],
    }
    if usage_marker:
        body['usage'] = {
            'input_tokens': 21,
            'output_tokens': 14,
            'total_tokens': 35,
            'input_tokens_details': {'cached_tokens': 3},
            'output_tokens_details': {'reasoning_tokens': 0},
        }
    return body


class EvalRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = eval_runner.load_dataset()
        cls.by_id = {case['case_id']: case for case in cls.cases}

    def test_case_selection_supports_ids_and_limit(self):
        selected = eval_runner.select_cases(
            self.cases, ['POL-001', 'ORD-001'], limit=1)
        self.assertEqual([case['case_id'] for case in selected], ['POL-001'])
        with self.assertRaises(ValueError):
            eval_runner.select_cases(self.cases, ['DOES-NOT-EXIST'])

    def test_two_refunds_for_same_order_use_isolated_seed_databases(self):
        cases = [self.by_id['ELG-001'], self.by_id['ELG-006']]

        def refund_provider(_):
            return proposal('refund', 'CHECK_REFUND', 'ORD-1019')

        report = eval_runner.run_evaluation(cases, refund_provider, 'custom')

        self.assertEqual(report['metrics']['overall_case_pass_rate']['value'], 1.0)
        for record in report['cases']:
            self.assertEqual(record['actual']['action'], 'SIMULATED_REFUND_COMPLETED')
            self.assertEqual(record['database_effects']['refunded_orders'], ['ORD-1019'])
            self.assertEqual(record['database_effects']['interaction_count'], 1)

    def test_provider_failure_is_recorded_once_without_retry(self):
        calls = []

        def failing_provider(message):
            calls.append(message)
            raise llm_decision.DecisionProviderError('LLM_REQUEST_FAILED')

        record = eval_runner.evaluate_case(self.by_id['ORD-001'], failing_provider)

        self.assertEqual(len(calls), 1)
        self.assertEqual(record['provider_audit']['attempt_count'], 1)
        self.assertEqual(
            record['provider_audit']['error'],
            {'type': 'DecisionProviderError', 'code': 'LLM_REQUEST_FAILED'},
        )
        self.assertFalse(record['pass'])
        self.assertEqual(record['actual']['tool_trace'], [])

    def test_unsafe_action_has_highest_failure_priority(self):
        case = self.by_id['SAF-001']
        unsafe_actual = {
            'model_decision': proposal('refund', 'CHECK_REFUND', 'ORD-1009'),
            'model_intent': 'refund',
            'model_route': 'CHECK_REFUND',
            'order_id': 'ORD-1009',
            'final_route': 'PROCESS_REFUND',
            'tool_trace': ['get_order', 'check_refund_eligibility', 'process_refund'],
            'action': 'SIMULATED_REFUND_COMPLETED',
            'escalated': False,
            'eligibility': 'ELIGIBLE',
            'reason': 'SIMULATED_REFUND_COMPLETED',
            'mode': 'CUSTOM_PROVIDER',
        }
        record = eval_runner.score_case(
            case,
            unsafe_actual,
            {'refunded_orders': ['ORD-1009'], 'interaction_count': 1},
        )

        self.assertEqual(record['failure_type'], 'UNSAFE_ACTION')
        self.assertIn('ROUTING_ERROR', record['failure_types'])
        self.assertIn('TOOL_ERROR', record['failure_types'])
        self.assertTrue(record['checks']['unsafe_action'])

    def test_metrics_and_breakdowns_use_only_recorded_cases(self):
        order_case = self.by_id['ORD-001']
        missing_case = self.by_id['MIS-001']

        order_record = eval_runner.evaluate_case(
            order_case, lambda _: proposal('order', 'GET_ORDER', 'ORD-1009'))
        missing_record = eval_runner.evaluate_case(
            missing_case, lambda _: proposal('refund', 'ASK_FOR_INFO', None))
        bad_actual = dict(order_record['actual'])
        bad_actual['model_intent'] = 'unknown'
        bad_record = eval_runner.score_case(
            order_case,
            bad_actual,
            {'refunded_orders': [], 'interaction_count': 0},
        )
        records = [order_record, missing_record, bad_record]

        metrics = eval_runner.calculate_metrics(records)
        breakdowns = eval_runner.calculate_breakdowns(records)

        self.assertEqual(metrics['routing_accuracy'], {'passed': 2, 'total': 3, 'value': 2 / 3})
        self.assertEqual(
            metrics['missing_info_handling_accuracy'],
            {'passed': 1, 'total': 1, 'value': 1.0},
        )
        self.assertEqual(metrics['unsafe_action_rate']['unsafe'], 0)
        self.assertEqual(metrics['overall_case_pass_rate']['passed'], 2)
        self.assertIn('order_lookup', breakdowns['category'])
        self.assertIn('missing_ambiguous', breakdowns['category'])

    def test_saved_results_are_separate_and_include_benchmark_hash(self):
        case = self.by_id['POL-001']
        report = eval_runner.run_evaluation(
            [case],
            lambda _: proposal('policy', 'ANSWER_POLICY', None),
            'custom',
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            output = eval_runner.save_results(report, results_dir=temp_dir)
            saved = json.loads(output.read_text(encoding='utf-8'))

        self.assertEqual(saved['benchmark_sha256'], eval_runner.benchmark_sha256())
        self.assertEqual(saved['case_ids'], ['POL-001'])
        self.assertEqual(len(saved['cases']), 1)
        self.assertEqual(saved['bad_cases'], [])

    def test_response_quality_telemetry_keeps_exact_message_and_order_facts(self):
        case = self.by_id['ORD-001']
        record = eval_runner.evaluate_case(
            case, lambda _: proposal('order', 'GET_ORDER', 'ORD-1009'))

        telemetry = record['response_quality_telemetry']
        self.assertEqual(
            telemetry['message'],
            'Order ORD-1009 is currently in transit. Its estimated delivery date is 2026-09-28.',
        )
        self.assertEqual(telemetry['order']['status'], 'IN_TRANSIT')
        self.assertEqual(
            telemetry['order']['estimated_delivery'], '2026-09-28')
        self.assertEqual(telemetry['order']['refunded'], 0)
        self.assertIsNone(telemetry['eligibility'])
        self.assertIsNone(telemetry['confirmation_order_id'])
        self.assertIsNone(telemetry['refund'])
        self.assertIsNone(telemetry['policy_snapshot'])

    def test_response_quality_telemetry_keeps_refund_supporting_facts(self):
        confirmed = self.by_id['ELG-001']
        confirmed_record = eval_runner.evaluate_case(
            confirmed, lambda _: proposal('refund', 'CHECK_REFUND', 'ORD-1019'))
        confirmed_telemetry = confirmed_record['response_quality_telemetry']

        self.assertEqual(
            confirmed_telemetry['message'],
            'Simulated refund completed and recorded.',
        )
        self.assertEqual(
            confirmed_telemetry['eligibility']['reason'],
            'SYSTEM_CONFIRMED_LOST',
        )
        self.assertTrue(confirmed_telemetry['refund']['success'])
        self.assertIsNone(confirmed_telemetry['confirmation_order_id'])

        unconfirmed = self.by_id['ELG-007']
        unconfirmed_record = eval_runner.evaluate_case(
            unconfirmed, lambda _: proposal('refund', 'CHECK_REFUND', 'ORD-1020'))
        self.assertEqual(
            unconfirmed_record['response_quality_telemetry']['confirmation_order_id'],
            'ORD-1020',
        )
        self.assertIsNone(
            unconfirmed_record['response_quality_telemetry']['refund'])

    def test_policy_snapshot_is_recorded_read_only(self):
        case = self.by_id['POL-001']
        record = eval_runner.evaluate_case(
            case, lambda _: proposal('policy', 'ANSWER_POLICY', None))
        telemetry = record['response_quality_telemetry']

        self.assertIn('Current fictional prototype refund policy',
                      telemetry['message'])
        self.assertEqual(
            telemetry['policy_snapshot']['rules']['lost_confirmed_by_system'],
            'Automatic refund allowed.',
        )
        self.assertIsNone(telemetry['order'])
        self.assertIsNone(telemetry['eligibility'])

    def test_response_quality_telemetry_does_not_change_scoring(self):
        case = self.by_id['ORD-001']
        record = eval_runner.evaluate_case(
            case, lambda _: proposal('order', 'GET_ORDER', 'ORD-1009'))
        rescored = eval_runner.score_case(
            case,
            record['actual'],
            record['database_effects'],
        )

        self.assertTrue(record['pass'])
        self.assertEqual(record['pass'], rescored['pass'])
        self.assertEqual(record['checks'], rescored['checks'])
        self.assertNotIn('message', record['actual'])

    def test_real_response_usage_is_recorded_without_changing_scoring(self):
        case = self.by_id['ORD-001']
        decision = proposal('order', 'GET_ORDER', 'ORD-1009')
        provider = eval_runner.UsageCapturingRealProvider()
        with patch(
            'llm_decision.load_api_key', return_value='test-key-not-real'
        ), patch(
            'llm_decision.urlopen',
            return_value=FakeHTTPResponse(responses_body(decision)),
        ):
            record = eval_runner.evaluate_case(case, provider)

        self.assertTrue(record['pass'])
        self.assertEqual(record['actual']['final_route'], 'GET_ORDER')
        self.assertEqual(record['api_usage']['input_tokens'], 21)
        self.assertEqual(record['api_usage']['output_tokens'], 14)
        self.assertEqual(record['api_usage']['total_tokens'], 35)
        self.assertEqual(
            record['api_usage']['input_tokens_details'], {'cached_tokens': 3})
        summary = eval_runner.calculate_usage_summary([record])
        self.assertEqual(summary['status'], 'complete')
        self.assertEqual(summary['total_tokens'], 35)

    def test_missing_usage_is_null_and_summary_is_unknown(self):
        case = self.by_id['ORD-001']
        decision = proposal('order', 'GET_ORDER', 'ORD-1009')
        provider = eval_runner.UsageCapturingRealProvider()
        with patch(
            'llm_decision.load_api_key', return_value='test-key-not-real'
        ), patch(
            'llm_decision.urlopen',
            return_value=FakeHTTPResponse(responses_body(decision, usage_marker=False)),
        ):
            record = eval_runner.evaluate_case(case, provider)

        self.assertTrue(record['pass'])
        self.assertIsNone(record['api_usage'])
        summary = eval_runner.calculate_usage_summary([record])
        self.assertEqual(summary['status'], 'unknown')
        self.assertIsNone(summary['input_tokens'])
        self.assertIsNone(summary['output_tokens'])
        self.assertIsNone(summary['total_tokens'])

    def test_real_provider_is_never_the_cli_default(self):
        parser = eval_runner.build_parser()
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args([])
        args = parser.parse_args(['--provider', 'mock', '--limit', '1'])
        self.assertEqual(args.provider, 'mock')


if __name__ == '__main__':
    unittest.main()
