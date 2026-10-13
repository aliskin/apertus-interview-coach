import copy,json,sys,tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import interview_controller as c
import hybrid as h
import web

class QuestionTrackingTests(unittest.TestCase):
 def session(self,language='de'):
  s=c.Session(language,c.POSTINGS['P-01'],c.make_plan(['Q-03-01','Q-05-01']));s.start();return s
 def test_clarification_wording_is_stored_and_supplied_to_analysis_and_recap(self):
  s=self.session();actual='Welche Tätigkeit interessiert dich besonders?'
  s.transcript.append({'role':'assistant','content':'Wir bleiben kurz dabei. '+actual,'actual_question':actual,'question_id':'Q-03-01'})
  s.record_answer('Autos reparieren.')
  packet=dict(quotes=['Autos reparieren.'],status='sufficient',gap='',requests=[],support_quote='',resolves=[],conflicts=[])
  with patch.object(c.model_client,'apertus',return_value=json.dumps(packet)) as model:h.analyse(s,'Autos reparieren.',s.plan[0])
  data=json.loads(model.call_args.args[0][-1]['content'])
  self.assertEqual(data['question']['text'],actual)
  self.assertEqual(data['question']['planned_text'],'Warum hast du dich für diesen Beruf entschieden?')
  self.assertEqual(s.transcript[-1]['actual_question'],actual)
  self.assertEqual(h.full_answers(s)[0]['question']['text'],actual)
  self.assertEqual(next(iter(h.eligible_evidence(s)['motivation'].values()))['actual_question'],actual)
 def test_old_sessions_recover_actual_coach_reply_instead_of_bank_text(self):
  s=self.session();s.transcript.extend([dict(role='assistant',content='Welche Tätigkeit interessiert dich?'),dict(role='user',content='Reparaturen.',question_id='Q-03-01')])
  row=h.full_answers(s)[0]['question'];self.assertEqual(row['text'],'Welche Tätigkeit interessiert dich?');self.assertEqual(row['wording_source'],'previous_coach_reply')
 def test_serialization_preserves_wording(self):
  s=self.session();s.record_answer('Technik.');saved=json.loads(json.dumps(c.asdict(s)));restored=c.Session(**saved)
  self.assertEqual(h.full_answers(restored),h.full_answers(s))

 def test_legacy_analysis_uses_actual_clarification(self):
  s=self.session();s.pipeline='legacy';actual='Welche Tätigkeit interessiert dich?'
  s.transcript.append(dict(role='assistant',content=actual,actual_question=actual));s.record_answer('Reparaturen.')
  packet=dict(observations=[dict(statement='Reparaturen.',quote='Reparaturen.')],answer_status='answered',missing_information='',support_quote='',company_question_quote='',resolved_record_ids=[],conflict_record_ids=[])
  with patch.object(c.model_client,'apertus',return_value=json.dumps(packet)) as model:s.analyse_answer('Reparaturen.',s.plan[0])
  self.assertEqual(json.loads(model.call_args.args[0][1]['content'])['current_question']['text'],actual)
