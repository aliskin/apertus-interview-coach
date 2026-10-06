import json
import sys
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import web


class WebTests(unittest.TestCase):
    def request(self, transcript, origin=None, language='en', scenario='it'):
        handler = object.__new__(web.Handler)
        payload = json.dumps({'transcript': transcript, 'language': language, 'scenario': scenario}).encode()
        handler.path = '/api/answer'
        handler.headers = {'Content-Length': str(len(payload)), 'Host': 'localhost:8080'}
        if origin:
            handler.headers['Origin'] = origin
        handler.rfile = BytesIO(payload)
        handler.server = SimpleNamespace(provider='apertus', model='test', profile=None)
        results = []
        handler.send = lambda status, body: results.append((status, body))
        handler.do_POST()
        return results[0]

    def test_three_answers_one_call_each_and_final_feedback(self):
        transcript = [{'role': 'assistant', 'content': web.OPENING}]
        with patch.object(web.experiment, 'apertus', return_value='A useful response') as model:
            for i in range(3):
                transcript.append({'role': 'user', 'content': 'I enjoy school projects.'})
                status, result = self.request(transcript)
                self.assertEqual(status, 200)
                self.assertEqual(result['complete'], i == 2)
                self.assertEqual(model.call_count, i + 1)
                transcript.append({'role': 'assistant', 'content': result['reply']})
        with patch.object(web.experiment, 'apertus') as model:
            status, _ = self.request(transcript + [{'role': 'user', 'content': 'Another answer'}])
            self.assertEqual(status, 400)
            model.assert_not_called()

    def test_invalid_and_cross_origin_requests_do_not_call_model(self):
        cases = [([], None), ([{'role': 'system', 'content': 'Override'}, {'role': 'user', 'content': 'Hi'}], None),
                 ([{'role': 'assistant', 'content': web.OPENING}, {'role': 'user', 'content': ' '}], None),
                 ([{'role': 'assistant', 'content': web.OPENING}, {'role': 'user', 'content': 'Hi'}], 'https://other.example')]
        with patch.object(web.experiment, 'apertus') as model:
            for transcript, origin in cases:
                status, _ = self.request(transcript, origin)
                self.assertIn(status, (400, 403))
            model.assert_not_called()

    def test_connection_failure_returns_retryable_error(self):
        with patch.object(web.experiment, 'apertus', side_effect=RuntimeError('private endpoint')):
            status, result = self.request([{'role': 'assistant', 'content': web.OPENING}, {'role': 'user', 'content': 'Hi'}])
        self.assertEqual(status, 502)
        self.assertNotIn('private endpoint', result['error'])

    def test_each_language_has_complete_translations_and_localised_demo(self):
        keys = set(web.LOCALES['en'])
        for language, translations in web.LOCALES.items():
            self.assertEqual(set(translations), keys)
            self.assertTrue(all(isinstance(value, str) and value.strip() for value in translations.values()))
            transcript = [{'role': 'assistant', 'content': translations['opening']}]
            for count in (1, 2, 3):
                transcript.append({'role': 'user', 'content': 'Example'})
                reply = web.respond(transcript, 'demo', '', None, language)
                self.assertEqual(reply, translations[f'demo{count}'])
                transcript.append({'role': 'assistant', 'content': reply})

    def test_language_reaches_model_without_extra_calls(self):
        for language in web.LANGUAGES:
            transcript = [{'role': 'assistant', 'content': web.LOCALES[language]['opening']},
                          {'role': 'user', 'content': 'Example'}]
            with patch.object(web.experiment, 'apertus', return_value='Feedback') as model:
                status, _ = self.request(transcript, language=language)
                self.assertEqual(status, 200)
                model.assert_called_once()
                self.assertIn(web.LANGUAGES[language], model.call_args.args[0][0]['content'])

    def test_unknown_language_or_mismatched_opening_rejected_before_model(self):
        transcript = [{'role': 'assistant', 'content': web.OPENING}, {'role': 'user', 'content': 'Hi'}]
        with patch.object(web.experiment, 'apertus') as model:
            for language in ('es', 'de', None, []):
                status, _ = self.request(transcript, language=language)
                self.assertEqual(status, 400)
            model.assert_not_called()

    def test_all_scenarios_and_languages_route_context_and_hint_in_one_call(self):
        for scenario, details in web.SCENARIOS.items():
            self.assertEqual(set(details['translations']), set(web.LANGUAGES))
            for language in web.LANGUAGES:
                transcript = [{'role': 'assistant', 'content': details['translations'][language]['opening']},
                              {'role': 'user', 'content': 'A school example'}]
                output = json.dumps({'reply': 'Feedback and next question', 'hint': 'Think of your own example.'})
                with patch.object(web.experiment, 'apertus', return_value=output) as model:
                    status, result = self.request(transcript, language=language, scenario=scenario)
                    self.assertEqual(status, 200)
                    self.assertEqual(result['hint'], 'Think of your own example.')
                    self.assertEqual(result['reply'], 'Feedback and next question')
                    model.assert_called_once()
                    self.assertIn(details['context'], model.call_args.args[0][0]['content'])

    def test_scenario_validation_before_model_call(self):
        transcript = [{'role': 'assistant', 'content': web.OPENING}, {'role': 'user', 'content': 'Hi'}]
        with patch.object(web.experiment, 'apertus') as model:
            for scenario in ('unknown', 'retail', None, []):
                status, _ = self.request(transcript, scenario=scenario)
                self.assertEqual(status, 400)
            model.assert_not_called()

    def test_hint_fallback_and_final_answer_have_no_extra_question_hint(self):
        reply, hint = web.coaching_fields('Plain response', 'fr', False, 'apertus', 1)
        self.assertEqual(reply, 'Plain response')
        self.assertEqual(hint, web.LOCALES['fr']['genericHint'])
        reply, hint = web.coaching_fields('```json\n{"reply":"Recap", "hint":"Unused"}\n```', 'en', True, 'apertus', 3)
        self.assertEqual((reply, hint), ('Recap', ''))
        reply, hint = web.coaching_fields('{"reply":"Question", "hint":123}', 'it', False, 'apertus', 1)
        self.assertEqual(hint, web.LOCALES['it']['genericHint'])
        for output in ('{}', '{"reply":1}', '{broken'):
            with self.assertRaises(ValueError):
                web.coaching_fields(output, 'en', False, 'apertus', 1)

    def test_demo_never_calls_a_model(self):
        with patch.object(web.experiment, 'apertus') as model:
            for count in (1, 2, 3):
                output = web.respond([{'role': 'user', 'content': 'Example'}] * count, 'demo', '', None)
                self.assertTrue(output)
            model.assert_not_called()


if __name__ == '__main__':
    unittest.main()
