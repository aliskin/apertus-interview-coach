"""Main questions belong to the controller, including imperative questions."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import interview_controller as c

class SpeakerCompositionTests(unittest.TestCase):
    def reply(self,language,ack,question_id='Q-02-01',support=False):
        s=c.Session(language,c.POSTINGS['P-01'],c.make_plan(['Q-01-01',question_id]),pipeline='legacy');s.start()
        answer='OK.'
        analysis=dict(observations=[],answer_status='answered',missing_information='',support_quote=answer if support else '',company_question_quote='',resolved_record_ids=[],conflict_record_ids=[])
        with patch.object(c.model_client,'apertus',side_effect=[json.dumps(analysis),json.dumps(dict(acknowledgement=ack,question=''))]) as model:
            result=s.answer(answer)
        self.assertEqual(model.call_count,2)
        self.assertEqual(s.transcript[-1]['actual_question'],c.question_text(s.plan[1],language))
        return result['reply']

    def test_reported_german_reproduction_preserves_reaction_and_one_question(self):
        reply=self.reply('de','Danke, das hilft mir, dich besser kennenzulernen. Jetzt erzähl uns etwas über dich.')
        self.assertEqual(reply,'Danke, das hilft mir, dich besser kennenzulernen. Erzähl uns etwas über dich.')

    def test_duplicate_bank_question_is_removed_in_every_language(self):
        for language in ('de','en','fr','it'):
            with self.subTest(language=language):
                question=c.question_text(c.QUESTIONS['Q-02-01'],language)
                reply=self.reply(language,'OK. '+question)
                self.assertEqual(reply,'OK. '+question)

    def test_case_punctuation_and_support_do_not_bypass_guard(self):
        for language in ('de','en','fr','it'):
            with self.subTest(language=language):
                question=c.question_text(c.QUESTIONS['Q-02-01'],language)
                embedded=question.rstrip('.?!').upper()+'!'
                self.assertEqual(self.reply(language,'OK. '+embedded,support=True),'OK. '+question)

    def test_contextual_reaction_without_question_is_preserved(self):
        for language in ('de','en','fr','it'):
            with self.subTest(language=language):
                question=c.question_text(c.QUESTIONS['Q-02-01'],language)
                self.assertEqual(self.reply(language,'OK. Danke für deinen Hinweis.'),'OK. Danke für deinen Hinweis. '+question)
