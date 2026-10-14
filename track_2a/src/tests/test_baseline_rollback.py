"""Default v8 conversation with v10 German recap; later policies stay explicit."""
import json, sys, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import interview_controller as c
import hybrid

class BaselineRollbackTests(unittest.TestCase):
    def session(self, policy=None):
        s = c.Session('de', c.POSTINGS['P-01'], c.make_plan(['Q-01-01', 'Q-03-01']))
        if policy: s.conversation_policy = policy
        s.start()
        return s

    def test_default_neutral_openings_use_analysis_and_fixed_transition(self):
        examples = [
            'Mir geht’s gut, danke. Ich bin Dario, 16 Jahre alt aus Luzern.',
            'Ich freue mich, über die Lehre als Mediamatiker zu sprechen.',
            'Ich interessiere mich für moderne Werkstattausrüstung.',
            'Ich bin sehr motiviert, die Lehre im Sportgeschäft zu beginnen.',
            'Mir geht’s gut, danke. Ich bin bereit, ehrlich zu erzählen.',
        ]
        for answer in examples:
            with self.subTest(answer=answer):
                s = self.session()
                analysis = dict(observations=[dict(statement=answer, quote=answer)],
                    answer_status='answered', missing_information='', support_quote='',
                    company_question_quote='', resolved_record_ids=[], conflict_record_ids=[])
                speaker = dict(acknowledgement='Schön, dass du heute mitmachst.', question='')
                with patch.object(c.model_client, 'apertus', side_effect=[json.dumps(analysis), json.dumps(speaker)]) as model, patch.object(hybrid, 'answer') as later:
                    reply = s.answer(answer)['reply']
                later.assert_not_called()
                self.assertEqual(model.call_count, 1)
                self.assertEqual(s.turn_decisions[-1]['action'], 'advance')
                self.assertNotIn('Absagen', reply)
                self.assertIn('Danke. Jetzt geht es um deine Berufswahl.', reply)
                self.assertEqual(s.transcript[-1]['actual_question'], 'Warum hast du dich für diesen Beruf entschieden?')
                self.assertEqual(s.evidence_records[0]['evidence'][0]['quote'], answer)

    def test_default_recap_uses_verified_v10_path(self):
        s = self.session(); s.record_answer('Gut, danke.')
        with patch.object(hybrid, 'finish', return_value={'complete': True}) as finish:
            self.assertTrue(s.finish()['complete'])
        finish.assert_called_once_with(s)

    def test_later_interview_policies_are_opt_in(self):
        for policy in ['fixed', 'connected']:
            s = self.session(policy)
            with patch.object(hybrid, 'answer', return_value={'reply': 'experimental'}) as later:
                self.assertEqual(s.answer('Gut.')['reply'], 'experimental')
            later.assert_called_once_with(s, 'Gut.', False)

if __name__ == '__main__': unittest.main()
