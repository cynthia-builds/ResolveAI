import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

import agent
import database
import llm_decision


VALID_DECISION = {
    'intent': 'refund',
    'route': 'CHECK_REFUND',
    'order_id': 'ORD-1017',
    'tool': ['get_order', 'check_refund_eligibility'],
    'action': 'NONE',
    'reason': 'REFUND_REQUEST',
    'escalated': False,
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


def api_response(decision=VALID_DECISION, status='completed'):
    return {
        'status': status,
        'output': [{
            'type': 'message',
            'content': [{
                'type': 'output_text',
                'text': json.dumps(decision),
            }],
        }],
    }


class LLMDecisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'test.db'
        database.initialize_database(self.db)
        patcher = patch(
            'refund_service.connect', lambda: database.connect(self.db))
        patcher.start()
        self.addCleanup(patcher.stop)

    @patch('llm_decision.load_api_key', return_value='test-key-not-real')
    @patch('llm_decision.urlopen')
    def test_real_provider_uses_responses_structured_output(self, mock_urlopen, _):
        mock_urlopen.return_value = FakeHTTPResponse(api_response())

        result = llm_decision.real_decision('Please refund ORD-1017')

        self.assertEqual(result, VALID_DECISION)
        request = mock_urlopen.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, 'https://api.openai.com/v1/responses')
        self.assertEqual(payload['model'], 'gpt-5.6-luna')
        self.assertFalse(payload['store'])
        self.assertEqual(payload['reasoning'], {'effort': 'none'})
        output_format = payload['text']['format']
        self.assertEqual(output_format['type'], 'json_schema')
        self.assertTrue(output_format['strict'])
        self.assertEqual(set(output_format['schema']['required']), agent.DECISION_KEYS)

    @patch('llm_decision.load_api_key', return_value='test-key-not-real')
    @patch('llm_decision.urlopen', side_effect=URLError('offline'))
    def test_api_failure_fails_closed_without_tools(self, _, __):
        result = agent.handle_message(
            'Refund ORD-1017', decision_provider=llm_decision.real_decision,
            confirmed_order_id='ORD-1017')

        self.assertEqual(result['reason'], 'INVALID_DECISION')
        self.assertEqual(result['route'], 'ESCALATE')
        self.assertEqual(result['tool'], [])
        self.assertEqual(result['action'], 'NONE')
        self.assertTrue(result['escalated'])

    @patch('llm_decision.load_api_key', return_value='test-key-not-real')
    @patch('llm_decision.urlopen')
    def test_incomplete_or_invalid_output_fails_closed(self, mock_urlopen, _):
        responses = [
            api_response(status='incomplete'),
            api_response({key: value for key, value in VALID_DECISION.items()
                          if key != 'action'}),
        ]
        for response in responses:
            with self.subTest(response=response):
                mock_urlopen.return_value = FakeHTTPResponse(response)
                result = agent.handle_message(
                    'Refund ORD-1017', decision_provider=llm_decision.real_decision,
                    confirmed_order_id='ORD-1017')
                self.assertEqual(result['reason'], 'INVALID_DECISION')
                self.assertNotIn('process_refund', result['tool'])

    def test_model_tool_and_reason_are_never_executor_results(self):
        model_proposal = {
            **VALID_DECISION,
            'tool': ['process_refund'],
            'reason': 'MODEL_SAYS_COMPLETED',
        }
        result = agent.handle_message(
            'Refund ORD-1017', decision_provider=lambda _: model_proposal)

        self.assertEqual(result['tool'], ['get_order', 'check_refund_eligibility'])
        self.assertEqual(result['reason'], 'CONFIRMATION_REQUIRED')
        self.assertEqual(result['action'], 'NONE')
        self.assertEqual(result['model_decision'], model_proposal)


if __name__ == '__main__':
    unittest.main()
