"""Regressions for reproduced purpose drift, repetition and suppressed support."""
import json,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import interview_controller as c
import hybrid as h
import connected as k

class ConversationGuardTests(unittest.TestCase):
 def session(self,ids=('Q-03-01','Q-05-01')):
  s=c.Session('de',c.POSTINGS['P-01'],c.make_plan(list(ids)));s.conversation_policy='fixed';s.start();s.answers=2;return s
 def speaker(self,s,question):
  packet=dict(reaction='',question=question,evidence_quote='')
  with patch.object(c.model_client,'apertus',return_value=json.dumps(packet)):
   return k.speaker(s,'Technik interessiert mich.',s.plan[0],s.plan[1],dict(missing_information=''),'advance','Next planned purpose')
 def analysis(self,s,text,support):
  packet=dict(quotes=[text],status='sufficient',gap='',requests=[],support_quote=support,resolves=[],conflicts=[])
  with patch.object(c.model_client,'apertus',return_value=json.dumps(packet)):return h.analyse(s,text,s.plan[0])
 def test_identical_question_after_acknowledgement_is_rejected(self):
  s=self.session();s.transcript.append(dict(role='assistant',content='Das ist interessant. Was sind deine grössten Stärken?'))
  with self.assertRaisesRegex(ValueError,'already been asked'):self.speaker(s,'Was sind deine grössten Stärken?')
 def test_synonymous_reviewed_question_is_rejected(self):
  s=self.session();s.transcript.append(dict(role='assistant',content='Welche Stärken helfen dir dabei?',actual_question='Welche Stärken helfen dir dabei?'))
  with self.assertRaisesRegex(ValueError,'already been asked'):self.speaker(s,'Was sind deine grössten Stärken?')
 def test_unrelated_question_is_rejected(self):
  self.assertTrue(self.speaker(self.session(),'Was machst du am Wochenende?')[2])
 def test_career_goal_question_does_not_become_another_motivation_strategy(self):
  s=self.session(('Q-SIT-07','Q-08-07'))
  self.assertTrue(self.speaker(s,'Wie hilfst du dabei, dass die Arbeit motivierender wird?')[2])
 def test_closing_cannot_become_another_career_question(self):
  s=self.session(('Q-08-07','Q-10-01'))
  self.assertTrue(self.speaker(s,'Wie siehst du deine langfristigen Karriereziele?')[2])
 def test_reviewed_paraphrase_is_accepted(self):
  result=self.speaker(self.session(),'Welche Stärken helfen dir dabei?')
  self.assertFalse(result[2]);self.assertEqual(result[3],'Welche Stärken helfen dir dabei?')
 def test_valid_self_doubt_quote_is_not_discarded(self):
  text='Ich habe Angst, dass ich nicht gut genug bin.'
  self.assertEqual(self.analysis(self.session(),text,text)['support_quote'],text)
 def test_model_support_signal_outside_strong_pattern_is_preserved(self):
  text='Ich fühle mich völlig überfordert und brauche Unterstützung.'
  self.assertEqual(self.analysis(self.session(),text,text)['support_quote'],text)
 def test_clear_self_doubt_has_backup_when_model_misses_it(self):
  text='Ich habe Angst, dass ich nicht gut genug bin.'
  self.assertEqual(self.analysis(self.session(),text,'')['support_quote'],text)
 def test_plain_nervousness_does_not_trigger_heavy_support(self):
  text='Ich bin etwas nervös.'
  self.assertEqual(self.analysis(self.session(),text,text)['support_quote'],'')
 def test_benign_family_description_does_not_trigger_support(self):
  text='Ich helfe meinem kleinen Bruder bei den Hausaufgaben.'
  self.assertEqual(self.analysis(self.session(),text,text)['support_quote'],'')
 def test_client_answer_cannot_invent_support_quote(self):
  text='Technik interessiert mich.'
  result=self.analysis(self.session(),text,'Ich bin nicht gut genug.')
  self.assertEqual(result['support_quote'],'')

 def test_controller_skips_a_purpose_already_asked_and_answered(self):
  s=self.session(('Q-03-01','Q-05-01','Q-09-02'))
  s.transcript.extend([dict(role='assistant',content='Dazu noch: Welche Stärken helfen dir dabei?',actual_question='Welche Stärken helfen dir dabei?'),dict(role='user',content='Geduld.')])
  selected,reason,skipped=k.choose(s,'Geduld.',{})
  self.assertEqual(selected['id'],'Q-09-02');self.assertIn('Q-05-01',skipped)
 def test_literal_doubt_routes_to_support_without_speaker_call(self):
  s=self.session();s.answers=0;text='Ich habe Angst, dass ich nicht gut genug bin.'
  packet=dict(quotes=[text],status='sufficient',gap='',requests=[],support_quote=text,resolves=[],conflicts=[])
  with patch.object(c.model_client,'apertus',return_value=json.dumps(packet)) as model:result=s.answer(text)
  self.assertEqual(s.turn_decisions[-1]['action'],'support');self.assertIn('Berufsberatung',result['reply']);self.assertEqual(model.call_count,1)
 def test_bookkeeping_gap_is_rejected_before_a_clarification(self):
  s=self.session();text='Technik interessiert mich.'
  packet=dict(quotes=[text],status='gap',gap='record_id fehlt',requests=[],support_quote='',resolves=[],conflicts=[])
  with patch.object(c.model_client,'apertus',return_value=json.dumps(packet)):result=h.analyse(s,text,s.plan[0])
  self.assertEqual(result['missing_information'],'');self.assertIn('analysis_unavailable',[w['action'] for w in s.validation_warnings])
 def test_question_spans_recover_old_replies_with_acknowledgements(self):
  transcript=[dict(role='assistant',content='Interessant. Was sind deine grössten Stärken?')]
  self.assertTrue(c.question_repeated('Was sind deine grössten Stärken?',transcript,'de'))
  self.assertFalse(c.question_repeated('Welche Schwäche möchtest du verbessern?',transcript,'de'))

 def test_negated_self_doubt_does_not_route_to_support(self):
  text='Ich zweifle nicht an mir.'
  self.assertEqual(self.analysis(self.session(),text,text)['support_quote'],'')
 def test_negated_fear_does_not_route_to_support(self):
  text='Ich habe keine Angst, dass ich nicht gut genug bin.'
  self.assertEqual(self.analysis(self.session(),text,text)['support_quote'],'')
 def test_reaction_cannot_hide_an_unrelated_extra_question(self):
  s=self.session();packet=dict(reaction='Erzähl mir von deinen Hobbys.',question='Was sind deine grössten Stärken?',evidence_quote='Technik interessiert mich.')
  with patch.object(c.model_client,'apertus',return_value=json.dumps(packet)):
   reply,quote,failed,actual=k.speaker(s,'Technik interessiert mich.',s.plan[0],s.plan[1],dict(missing_information=''),'advance','Next purpose')
  self.assertTrue(failed);self.assertNotIn('Hobbys',reply)

 def test_fixed_clarification_cannot_steal_a_future_main_question(self):
  s=self.session();packet=dict(acknowledgement='',question='Welche Stärken helfen dir dabei?')
  with patch.object(c.model_client,'apertus',return_value=json.dumps(packet)):
   ack,question,action=h.speak(s,'Technik.',s.plan[0],s.plan[1],'clarify','Ein persönlicher Grund')
  self.assertEqual(action,'advance');self.assertEqual(question,'')

 def test_job_related_json_detail_is_not_confused_with_internal_bookkeeping(self):
  s=self.session();text='Ich kenne JSON.'
  packet=dict(quotes=[text],status='gap',gap='Ein konkretes Beispiel zur Arbeit mit JSON fehlt.',requests=[],support_quote='',resolves=[],conflicts=[])
  with patch.object(c.model_client,'apertus',return_value=json.dumps(packet)):result=h.analyse(s,text,s.plan[0])
  self.assertEqual(result['missing_information'],packet['gap'])
