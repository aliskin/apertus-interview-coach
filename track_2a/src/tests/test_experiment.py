import argparse
import json
import io
from contextlib import redirect_stderr
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import experiment as app


class ExperimentTests(unittest.TestCase):
    def test_feedback_uses_fixed_matching_conversation(self):
        run = app.generate(argparse.Namespace(provider='sample', model='unused'))
        self.assertEqual(len(run['cases']), 4)
        for followup, feedback in zip(run['cases'][::2], run['cases'][1::2]):
            self.assertEqual(feedback['messages'][-2]['content'], followup['output'])
            self.assertEqual(len(followup['messages']), 3)
            self.assertEqual(len(feedback['messages']), 5)

    def test_invalid_judge_scores_rejected(self):
        for score in (True, 0, 6, '5'):
            with self.subTest(score=score), self.assertRaises(ValueError):
                app.validate_scores({'flow': {'score': score, 'reason': 'reason', 'evidence': 'quote'}}, {'flow': ''})
        with self.assertRaises(ValueError):
            app.validate_scores({}, {'flow': ''})

    @patch.dict('os.environ', {'LLM_API_KEY': 'test-secret', 'LLM_BASE_URL': 'https://example.test/v1', 'LLM_NAME': 'test-apertus'})
    @patch.object(app, 'post')
    def test_apertus_request_and_secret_not_saved(self, post):
        post.return_value = {'choices': [{'message': {'content': 'A response'}, 'finish_reason': 'stop'}]}
        run = app.generate(argparse.Namespace(provider='apertus', model=None))
        self.assertEqual(post.call_count, 4)
        self.assertEqual(post.call_args.args[1], '/chat/completions')
        self.assertEqual(post.call_args.args[2]['model'], 'test-apertus')
        self.assertNotIn('test-secret', json.dumps(run))

    @patch.dict('os.environ', {'LLM_API_KEY': 'x', 'LLM_BASE_URL': 'https://example.test/v1', 'LLM_NAME': 'test'})
    @patch.object(app, 'post', return_value={'choices': [{'finish_reason': 'length'}]})
    def test_truncated_generation_rejected(self, post):
        with self.assertRaisesRegex(ValueError, 'truncated'):
            app.generate(argparse.Namespace(provider='apertus', model=None))

    def test_remote_plaintext_key_rejected(self):
        with self.assertRaisesRegex(ValueError, 'HTTPS'):
            app.post('http://example.test/v1', '/chat/completions', {}, 'secret')

    def test_evaluation_omits_model_identity_and_averages_scores(self):
        run = app.generate(argparse.Namespace(provider='sample', model='unused'))
        run['model'] = 'MODEL_ID_SHOULD_NOT_REACH_JUDGE'

        def fake_judge(model, messages, schema):
            self.assertNotIn(run['model'], json.dumps(messages))
            return json.dumps({name: {'score': 3, 'reason': 'Some gaps',
                                     'evidence': 'Missing element'}
                               for name in schema['required']})

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'run.json'
            path.write_text(json.dumps(run))
            with patch.object(app, 'ollama', side_effect=fake_judge):
                report = app.evaluate(argparse.Namespace(input=path, model='judge', output=Path(folder) / 'judged.json'))
        self.assertEqual(report['mean_by_stage'], {'followup': 3, 'feedback': 3})
        self.assertEqual(len(report['results']), 4)

    def test_bad_responses_are_saved_and_later_cases_continue(self):
        run = app.generate(argparse.Namespace(provider='sample', model='unused'))
        calls = 0
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'run.json'
            output = Path(folder) / 'judged.json'
            source.write_text(json.dumps(run))

            def fake_judge(model, messages, schema):
                nonlocal calls
                # Every previous result must already be persisted.
                self.assertEqual(len(json.loads(output.read_text())['results']), calls)
                calls += 1
                if calls == 2:
                    return 'not JSON'
                if calls == 3:
                    raise RuntimeError('Server unavailable')
                scores = {name: {'score': 4, 'reason': 'Supported', 'evidence': 'Quote'}
                          for name in schema['required']}
                if calls == 1:
                    scores['adaptation']['evidence'] = '   '
                return json.dumps(scores)

            warnings = io.StringIO()
            with patch.object(app, 'ollama', side_effect=fake_judge), redirect_stderr(warnings):
                report = app.evaluate(argparse.Namespace(input=source, output=output, model='judge'))
            self.assertEqual(json.loads(output.read_text()), report)
            self.assertEqual(report['status'], 'completed_with_warnings')
            self.assertEqual(len(report['results']), 4)
            self.assertEqual(report['results'][0]['scores']['adaptation']['evidence'], '   ')
            self.assertEqual(report['results'][1]['raw_response'], 'not JSON')
            self.assertIsNone(report['results'][2]['raw_response'])
            self.assertEqual(report['results'][3]['mean'], 4)
            self.assertEqual(report['mean_by_stage'], {'followup': None, 'feedback': 4})
            self.assertIn('adaptation.evidence', warnings.getvalue())
            self.assertEqual(warnings.getvalue().count('Warning:'), 3)

    def test_interruption_preserves_previous_case_and_existing_output(self):
        run = app.generate(argparse.Namespace(provider='sample', model='unused'))
        scores = {name: {'score': 4, 'reason': 'Reason', 'evidence': 'Quote'}
                  for name in app.CRITERIA['followup']}
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'run.json'
            output = Path(folder) / 'judged.json'
            source.write_text(json.dumps(run))
            args = argparse.Namespace(input=source, output=output, model='judge')
            with patch.object(app, 'ollama', side_effect=[json.dumps(scores), KeyboardInterrupt]):
                with self.assertRaises(KeyboardInterrupt):
                    app.evaluate(args)
            saved = output.read_text()
            self.assertEqual(len(json.loads(saved)['results']), 1)
            self.assertEqual(json.loads(saved)['status'], 'in_progress')
            with patch.object(app, 'ollama') as judge:
                with self.assertRaises(FileExistsError):
                    app.evaluate(args)
                judge.assert_not_called()
            self.assertEqual(output.read_text(), saved)


if __name__ == '__main__':
    unittest.main()
