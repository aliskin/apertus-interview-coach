import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model_client as app

class ModelClientTests(unittest.TestCase):
    @patch.dict('os.environ', {'LLM_API_KEY': 'test-secret', 'LLM_BASE_URL': 'https://example.test/v1', 'LLM_NAME': 'test-apertus'})
    @patch.object(app, 'post')
    def test_apertus_schema_is_enforced_in_request_without_fallback(self, post):
        import web
        packet = {'reply': 'Quoted "example"\nSecond line: café, Grüße, città.', 'hint': '',
                  'suggest_recap': True, 'can_continue': False}
        post.return_value = {'choices': [{'message': {'content': json.dumps(packet)}, 'finish_reason': 'stop'}]}
        output = app.apertus([{'role': 'user', 'content': 'Test'}], web.COACH_SCHEMA)
        self.assertEqual(json.loads(output), packet)
        requested = post.call_args.args[2]['response_format']
        self.assertEqual(requested, {'type': 'json_schema', 'json_schema': {
            'name': 'coach_response', 'strict': True, 'schema': web.COACH_SCHEMA}})
        post.reset_mock()
        post.side_effect = RuntimeError('API returned HTTP 400')
        with self.assertRaises(RuntimeError):
            app.apertus([], web.COACH_SCHEMA)
        post.assert_called_once()

    def test_remote_plaintext_key_rejected(self):
        with self.assertRaisesRegex(ValueError, 'HTTPS'):
            app.post('http://example.test/v1', '/chat/completions', {}, 'secret')

