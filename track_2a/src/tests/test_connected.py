import sys,unittest,copy,json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import interview_controller as c
import connected as k
import hybrid as h
class ConnectedTests(unittest.TestCase):
 def session(self,ids):
  s=c.Session('de',c.POSTINGS['P-01'],c.make_plan(ids));s.conversation_policy='connected';s.start();s.answers=2;return s
 def test_trial_topic_precedes_hobbies(self):
  s=self.session(['Q-01-04','Q-02-06','Q-06-08','Q-03-01'])
  q,reason,skipped=k.choose(s,'Ich war schon in Schnupperlehren.',{})
  self.assertEqual(q['id'],'Q-06-08');self.assertEqual(s.plan[1]['id'],'Q-06-08');self.assertEqual(set(q['id'] for q in s.plan),{'Q-01-04','Q-02-06','Q-06-08','Q-03-01'})
 def test_uncertain_coverage_does_not_remove_question(self):
  s=self.session(['Q-02-01','Q-03-01','Q-10-01']);a={'covered_questions':[dict(question_id='Q-03-01',quote='Ich habe den Beruf gewählt weil ich gern Menschen helfe.',confidence='uncertain')]}
  k.choose(s,'',a);self.assertIn('Q-03-01',[q['id'] for q in s.plan])
 def test_supported_complete_coverage_records_quote_and_skips(self):
  s=self.session(['Q-02-01','Q-03-01','Q-10-01']);quote='Ich habe den Beruf gewählt weil ich gern Menschen helfe.'
  q,_,skipped=k.choose(s,quote,{'covered_questions':[dict(question_id='Q-03-01',quote=quote,confidence='certain')]})
  self.assertEqual(skipped,['Q-03-01']);self.assertEqual(q['id'],'Q-10-01');self.assertEqual(s.question_status['Q-03-01']['quote'],quote)
 def test_speaker_rephrases_bank_question_without_appending_it(self):
  s=self.session(['Q-06-08','Q-03-01']);text='Mir hat die Arbeit im Laden gefallen.'
  packet={'reaction':'','question':'Wie hat deine bisherige Erfahrung deinen Berufswunsch beeinflusst?','evidence_quote':''}
  with patch.object(c.model_client,'apertus',return_value=json.dumps(packet)):
   reply,_,failed,actual=k.speaker(s,text,s.plan[0],s.plan[1],{'missing_information':''},'advance','Continue experience to motivation')
  self.assertFalse(failed);self.assertEqual(reply,packet['question']);self.assertNotIn(c.question_text(s.plan[1],'de'),reply)
 def test_invalid_evidence_falls_back_to_bank(self):
  s=self.session(['Q-06-08','Q-03-01']);packet={'reaction':'Das gefällt dir.','question':'Warum der Beruf?','evidence_quote':'nicht vorhanden'}
  with patch.object(c.model_client,'apertus',return_value=json.dumps(packet)):
   reply,_,failed,actual=k.speaker(s,'Ich war im Laden.',s.plan[0],s.plan[1],{'missing_information':''},'advance','test')
  self.assertTrue(failed);self.assertEqual(reply,c.question_text(s.plan[1],'de'))

 def test_connected_generation_stores_question_separately_from_reaction(self):
  s=c.Session('de',c.POSTINGS['P-01'],c.make_plan(['Q-03-01','Q-05-01']));s.start();s.conversation_policy='connected'
  a=dict(support_quote='',requests=[],missing_information='',covered_questions=[],related_question_id='')
  packet=dict(reaction='Du möchtest Autos reparieren.',question='Welche Stärken helfen dir dabei?',evidence_quote='Autos reparieren.')
  with patch('hybrid.analyse',return_value=a),patch.object(c.model_client,'apertus',return_value=json.dumps(packet)):
   k.answer(s,'Autos reparieren.')
  self.assertEqual(s.transcript[-1]['actual_question'],packet['question'])
  s.record_answer('Geduld.');self.assertEqual(s.transcript[-1]['actual_question'],packet['question'])
