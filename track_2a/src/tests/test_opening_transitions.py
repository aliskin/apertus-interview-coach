"""Ordinary openings are deterministic; concerns and questions still use Apertus."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import interview_controller as c

class OpeningTransitionTests(unittest.TestCase):
    def session(self,language):
        s=c.Session(language,c.POSTINGS['P-01'],c.make_plan(['Q-01-01','Q-02-01','Q-03-01']));s.start();return s

    def analysis(self,text,**overrides):
        return dict(observations=[dict(statement=text,quote=text)],answer_status='answered',missing_information='',support_quote='',company_question_quote='',resolved_record_ids=[],conflict_record_ids=[],**overrides)

    def test_greeting_and_introduction_use_one_analysis_call_each(self):
        for language in ('de','fr','it'):
            with self.subTest(language=language):
                s=self.session(language)
                answers={'de':['Hi! Es geht mir gut, danke','Ich bin Alisa und 15 Jahre alt. Ich gehe in die Sek A.'],'fr':['Bonjour ! Je vais bien, merci.','Je suis Alisa et j’ai 15 ans. Je suis à l’école secondaire.'],'it':['Ciao! Sto bene, grazie.','Sono Alisa e ho 15 anni. Frequento la scuola secondaria.']}
                for text,expected_id in zip(answers[language],['Q-02-01','Q-03-01']):
                    with patch.object(c.model_client,'apertus',return_value=json.dumps(self.analysis(text))) as model:
                        result=s.answer(text)
                    self.assertEqual(model.call_count,1)
                    question=c.question_text(c.QUESTIONS[expected_id],language)
                    self.assertTrue(result['reply'].endswith(question))
                    self.assertEqual(result['reply'].count(question),1)
                    self.assertEqual(s.transcript[-1]['actual_question'],question)
                    self.assertEqual(s.turn_decisions[-1]['action'],'advance')
                self.assertEqual(s.answers,2);self.assertEqual(s.model_calls,2)

    def test_support_and_company_requests_keep_the_speaker(self):
        for language in ('de','fr','it'):
            for signal,action in [('support_quote','support_advance'),('company_question_quote','answer_company')]:
                with self.subTest(language=language,signal=signal):
                    s=self.session(language);text='A concern.' if signal=='support_quote' else 'What are the working hours?';analysis=self.analysis(text);analysis[signal]=text
                    with patch.object(c.model_client,'apertus',side_effect=[json.dumps(analysis),json.dumps(dict(acknowledgement='A contextual reply.',question=''))]) as model:
                        result=s.answer(text)
                    self.assertEqual(model.call_count,2);self.assertIn('A contextual reply.',result['reply'])
                    self.assertEqual(s.turn_decisions[-1]['action'],action)

    def test_incomplete_introduction_can_still_receive_clarification(self):
        for language in ('de','fr','it'):
            s=self.session(language);s.index=1;s.set_question(s.plan[1]);text='Not sure.'
            analysis=self.analysis(text);analysis.update(answer_status='partial',missing_information='A school detail')
            with patch.object(c.model_client,'apertus',side_effect=[json.dumps(analysis),json.dumps(dict(acknowledgement='',question='Which school do you attend?'))]) as model:
                s.answer(text)
            self.assertEqual(model.call_count,2);self.assertEqual(s.turn_decisions[-1]['action'],'follow_up')

    def test_generic_advance_demonstration_is_not_injected(self):
        for language in ('de','fr','it','en'):
            example=json.loads((c.PROMPTS/f'examples.{language}.json').read_text())['speaker'][1]['output']['acknowledgement']
            prompt=c.task_prompt('speaker',language,dict(action='advance',current_question={'id':'Q-03-01'}))
            self.assertNotIn(example,prompt)
