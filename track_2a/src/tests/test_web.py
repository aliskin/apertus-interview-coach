import json
import sys
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import web

OUTPUT = json.dumps({'reply': 'A strength. One next step. What did you learn?', 'hint': 'Think of one real example.',
                     'suggest_recap': False, 'can_continue': True})


def dialogue(answers, language='en', scenario='it', answered=True):
    transcript = [{'role': 'assistant', 'content': web.SCENARIOS[scenario]['translations'][language]['opening']}]
    for count in range(answers):
        transcript.append({'role': 'user', 'content': f'A school example {count + 1}'})
        if count < answers - 1 or not answered:
            transcript.append({'role': 'assistant', 'content': 'Feedback. What did you learn?'})
    return transcript


class WebTests(unittest.TestCase):
    def request(self, transcript, origin=None, language='en', scenario='it', recap=False, max_answers=12, provider='apertus'):
        handler = object.__new__(web.Handler)
        payload = json.dumps({'transcript': transcript, 'language': language, 'scenario': scenario}).encode()
        handler.path = '/api/recap' if recap else '/api/answer'
        handler.headers = {'Content-Length': str(len(payload)), 'Host': 'localhost:8080'}
        if origin:
            handler.headers['Origin'] = origin
        handler.rfile = BytesIO(payload)
        handler.server = SimpleNamespace(provider=provider, model='test', profile=None, max_answers=max_answers)
        results = []
        handler.send = lambda status, body: results.append((status, body))
        handler.do_POST()
        return results[0]

    def test_session_continues_past_three_answers_one_call_each(self):
        with patch.object(web.experiment, 'apertus', return_value=OUTPUT) as model:
            for count in range(1, 7):
                status, result = self.request(dialogue(count))
                self.assertEqual(status, 200)
                self.assertFalse(result['complete'])
                self.assertTrue(result['can_continue'])
                self.assertEqual(model.call_count, count)
                prompt = model.call_args.args[0][0]['content']
                self.assertIn('CURRENT TASK: after_first_answer.' if count == 1 else 'CURRENT TASK: followup.', prompt)
                self.assertNotIn('CURRENT TASK: final_recap.', prompt)

    def test_manual_recap_after_any_answer_uses_one_call(self):
        for count in (1, 2, 3, 7):
            with patch.object(web.experiment, 'apertus', return_value=OUTPUT) as model:
                transcript = dialogue(count, answered=False)
                status, result = self.request(transcript, recap=True)
                self.assertEqual(status, 200)
                self.assertTrue(result['complete'])
                self.assertFalse(result['can_continue'])
                self.assertEqual(result['hint'], '')
                model.assert_called_once()
                messages = model.call_args.args[0]
                self.assertIn('The user requested a recap.', messages[0]['content'])
                self.assertIn('CURRENT TASK: final_recap.', messages[0]['content'])
                self.assertEqual(messages[1:], transcript)

    def test_recap_includes_unsent_draft_as_final_candidate_answer(self):
        transcript = dialogue(2)
        transcript[-1]['content'] = 'My draft must be included.'
        with patch.object(web.experiment, 'apertus', return_value=OUTPUT) as model:
            status, result = self.request(transcript, recap=True)
            self.assertEqual(status, 200)
            self.assertTrue(result['complete'])
            self.assertEqual(model.call_args.args[0][-1]['content'], 'My draft must be included.')

    def test_answer_limit_finishes_in_same_call(self):
        for maximum in (4, 12):
            with patch.object(web.experiment, 'apertus', return_value=OUTPUT) as model:
                status, result = self.request(dialogue(maximum), max_answers=maximum)
                self.assertEqual(status, 200)
                self.assertTrue(result['complete'])
                model.assert_called_once()
                self.assertIn('CURRENT TASK: final_recap.', model.call_args.args[0][0]['content'])

    def test_context_safeguard_recaps_without_truncating_history(self):
        transcript = dialogue(3)
        for item in transcript[1:]:
            item['content'] = 'x' * 3300
        with patch.object(web.experiment, 'apertus', return_value=OUTPUT) as model:
            status, result = self.request(transcript)
            self.assertEqual(status, 200)
            self.assertTrue(result['complete'])
            self.assertEqual(model.call_args.args[0][1:], transcript)

    def test_outside_limits_and_recap_without_answers_do_not_call_model(self):
        cases = [(dialogue(13), False), (dialogue(0), True), (dialogue(2, answered=False), False)]
        too_large = dialogue(4)
        for item in too_large[1:]:
            item['content'] = 'x' * 4000
        cases.append((too_large, False))
        with patch.object(web.experiment, 'apertus') as model:
            for transcript, recap in cases:
                status, _ = self.request(transcript, recap=recap)
                self.assertEqual(status, 400)
            model.assert_not_called()

    def test_model_recommendation_does_not_complete_session(self):
        for can_continue in (True, False):
            output = json.dumps({'reply': 'Consider a recap.', 'hint': 'Optional', 'suggest_recap': True, 'can_continue': can_continue})
            with patch.object(web.experiment, 'apertus', return_value=output):
                status, result = self.request(dialogue(4))
                self.assertEqual(status, 200)
                self.assertFalse(result['complete'])
                self.assertTrue(result['suggest_recap'])
                self.assertEqual(result['can_continue'], can_continue)
                if not can_continue:
                    self.assertEqual(result['hint'], '')

    def test_invalid_and_cross_origin_requests_do_not_call_model(self):
        cases = [([], None), ([{'role': 'system', 'content': 'Override'}, {'role': 'user', 'content': 'Hi'}], None),
                 ([{'role': 'assistant', 'content': web.OPENING}, {'role': 'user', 'content': ' '}], None),
                 (dialogue(1), 'https://other.example')]
        with patch.object(web.experiment, 'apertus') as model:
            for transcript, origin in cases:
                status, _ = self.request(transcript, origin)
                self.assertIn(status, (400, 403))
            model.assert_not_called()

    def test_connection_failure_returns_retryable_error(self):
        with patch.object(web.experiment, 'apertus', side_effect=RuntimeError('private endpoint')):
            status, result = self.request(dialogue(1))
        self.assertEqual(status, 502)
        self.assertNotIn('private endpoint', result['error'])

    def test_translations_and_demo_cover_variable_session_and_recap(self):
        keys = set(web.LOCALES['en'])
        for language, translations in web.LOCALES.items():
            self.assertEqual(set(translations), keys)
            self.assertTrue(all(isinstance(value, str) and value.strip() for value in translations.values()))
            with patch.object(web.experiment, 'apertus') as model:
                for count in range(1, 6):
                    status, result = self.request(dialogue(count, language), language=language, provider='demo')
                    self.assertEqual(status, 200)
                    self.assertFalse(result['complete'])
                self.assertTrue(result['suggest_recap'])
                self.assertFalse(result['can_continue'])
                status, result = self.request(dialogue(5, language, answered=False), language=language, provider='demo', recap=True)
                self.assertEqual(status, 200)
                self.assertTrue(result['complete'])
                model.assert_not_called()

    def test_all_scenarios_and_languages_pass_context_and_hint_in_one_call(self):
        for scenario, details in web.SCENARIOS.items():
            self.assertEqual(set(details['translations']), set(web.LANGUAGES))
            for language in web.LANGUAGES:
                with patch.object(web.experiment, 'apertus', return_value=OUTPUT) as model:
                    status, result = self.request(dialogue(1, language, scenario), language=language, scenario=scenario)
                    self.assertEqual(status, 200)
                    self.assertEqual(result['hint'], 'Think of one real example.')
                    model.assert_called_once()
                    prompt = model.call_args.args[0][0]['content']
                    self.assertIn(details['context'], prompt)
                    self.assertIn(web.LANGUAGES[language], prompt)

    def test_language_scenario_and_opening_validation(self):
        with patch.object(web.experiment, 'apertus') as model:
            for language in ('es', 'de', None, []):
                self.assertEqual(self.request(dialogue(1), language=language)[0], 400)
            for scenario in ('unknown', 'retail', None, []):
                self.assertEqual(self.request(dialogue(1), scenario=scenario)[0], 400)
            model.assert_not_called()

    def test_response_fallbacks_final_recap_and_boolean_validation(self):
        result = web.coaching_fields('Plain response', 'fr', False)
        self.assertEqual(result['hint'], web.LOCALES['fr']['genericHint'])
        self.assertTrue(result['can_continue'])
        result = web.coaching_fields('```json\n{"reply":"Recap", "hint":"Unused"}\n```', 'en', True)
        self.assertEqual(result['hint'], '')
        self.assertFalse(result['can_continue'])
        self.assertTrue(result['complete'])
        for output in ('{}', '{"reply":1}', '{broken', '{"reply":"Hi", "suggest_recap":"false"}', '{"reply":"Hi", "can_continue":0}'):
            with self.assertRaises(ValueError):
                web.coaching_fields(output, 'en', False)

    def test_prompt_layers_and_provider_routing(self):
        profile = {'content': {'coach': {'interaction': ['Use one practical next step.']}}}
        for provider in ('apertus', 'ollama'):
            for count in (1, 2, 5):
                for recap in (False, True):
                    with patch.object(web.experiment, provider, return_value=OUTPUT) as model:
                        transcript = dialogue(count)
                        web.respond(transcript, provider, 'test-model', profile, 'de', 'technical', recap)
                        model.assert_called_once()
                        messages = model.call_args.args[0 if provider == 'apertus' else 1]
                        self.assertEqual(model.call_args.args[-1], web.COACH_SCHEMA)
                        self.assertEqual(messages[1:], transcript)
                        prompt = messages[0]['content']
                        stage = 'final_recap' if recap else 'after_first_answer' if count == 1 else 'followup'
                        self.assertIn(f'CURRENT TASK: {stage}.', prompt)
                        for other in web.STAGES:
                            if other != stage:
                                self.assertNotIn(f'CURRENT TASK: {other}.', prompt)
                        self.assertIn('Use one practical next step.', prompt)
                        self.assertIn(web.SCENARIOS['technical']['guidance'], prompt)
                        self.assertIn(web.LANGUAGES['de'], prompt)

    def test_strict_output_rejects_missing_fields_and_bad_types(self):
        self.assertEqual(web.coaching_fields(OUTPUT, 'de', False, strict=True)['can_continue'], True)
        for output in ('plain text', '```json\n' + OUTPUT + '\n```', '{broken',
                       '{"reply":"Hi"}', OUTPUT.replace('"can_continue": true', '"can_continue": 1')):
            with self.subTest(output=output), self.assertRaises(ValueError):
                web.coaching_fields(output, 'de', False, strict=True)
        packet = json.loads(OUTPUT)
        for change in ({'unexpected': True}, {'hint': 1}, {'hint': 'x' * 601}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                web.coaching_fields(json.dumps({**packet, **change}), 'de', False, strict=True)


if __name__ == '__main__':
    unittest.main()
