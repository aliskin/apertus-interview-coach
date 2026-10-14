import sys,json,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import interview_controller as c
import hybrid as h

def evaluator_packet(packet):
 if 'criteria' not in packet:return packet
 rows=json.loads(json.dumps(packet['criteria']));proposals=[]
 for key,row in rows.items():
  improvement=row.pop('improvement',h.no_improvement())
  if improvement['usefulness']=='useful':proposals.append(dict(criterion_key=key,**improvement))
 return {'criteria':rows,'improvements':proposals}

class VerifiedLearningTests(unittest.TestCase):
 def session(self):
  s=c.Session('de',c.POSTINGS['P-01'],c.make_plan(['Q-03-01','Q-05-01']));s.start();s.answers=2
  s.transcript += [{'role':'user','question_id':'Q-03-01','content':'Ich mag praktische Arbeit.'},{'role':'assistant','content':'Welche Stärke?'},{'role':'user','question_id':'Q-05-01','content':'Ich helfe gern und möchte Bauteile zeichnen.'}]
  return s
 def criterion(self,s):
  allowed=h.eligible_evidence(s)['motivation'];eid=next(iter(allowed));return {'key':'motivation','score':2,'explanation':'Interesse genannt.','evidence':'Ich mag praktische Arbeit.','evidence_records':[dict(evidence_id=eid,**allowed[eid])],'improvement':dict(usefulness='useful',missing_detail='Konkrete Tätigkeit',why_needed='Berufsinteresse konkret erklären.',already_supplied=False,expected_outcome='Eine Tätigkeit nennen.',question_id='Q-03-01')}
 def test_later_answer_is_available_to_verifier_and_contradiction_drops_target(self):
  s=self.session();row=self.criterion(s);global_ids={k:v for group in h.eligible_evidence(s).values() for k,v in group.items()};eid=next(k for k,v in global_ids.items() if 'zeichnen' in v['quote'])
  with patch.object(c.model_client,'apertus',return_value=json.dumps({'checks':{'gap:motivation':{'decision':'contradicted','reason':'Die Tätigkeit steht in der späteren Antwort.','evidence_ids':[eid]}}})) as model:
   proposals,checks,target=h.verify_improvements(s,[row])
  payload=json.loads(model.call_args.args[0][1]['content']);self.assertEqual(len(payload['answers']),2);self.assertIn('zeichnen',payload['answers'][1]['answer']);self.assertIsNone(target);self.assertIsNone(row['score']);self.assertIn('nicht bestätigt',row['explanation']);self.assertEqual(checks['gap:motivation']['evidence_records'][0]['quote'],global_ids[eid]['quote'])
 def test_uncertain_gap_is_not_a_learning_target(self):
  s=self.session();row=self.criterion(s)
  with patch.object(c.model_client,'apertus',return_value=json.dumps({'checks':{'gap:motivation':{'decision':'uncertain','reason':'Die Frage verlangt das nicht eindeutig.','evidence_ids':[]}}})):_,_,target=h.verify_improvements(s,[row])
  self.assertIsNone(target);self.assertIsNone(row['score'])
 def test_unknown_verifier_quote_fails_closed(self):
  s=self.session();row=self.criterion(s)
  with patch.object(c.model_client,'apertus',return_value=json.dumps({'checks':{'gap:motivation':{'decision':'supported','reason':'Eine Tätigkeit fehlt.','evidence_ids':['invented']}}})):_,checks,target=h.verify_improvements(s,[row])
  self.assertIsNone(target);self.assertEqual(checks['gap:motivation']['decision'],'uncertain');self.assertIn('verification_unavailable',[w['action'] for w in s.validation_warnings])
 def test_existing_detail_cannot_be_declared_a_useful_gap(self):
  s=self.session();p=self.criterion(s)['improvement'];p['already_supplied']=True
  with self.assertRaises(ValueError):h.validate_improvement(p,h.eligible_evidence(s)['motivation'],2)
 def test_learning_cannot_switch_target_id(self):
  s=self.session();packet=dict(target_id='gap:preparation',explanation='Vorbereitung.',exercise='Lies eine Aufgabe.',reflection='Was lernst du?',revision_prompt='Schreibe neu.',encouragement='Übe weiter.')
  with patch.object(c.model_client,'apertus',return_value=json.dumps(evaluator_packet(packet))):result=h.learn(s,dict(target_id='gap:motivation',key='motivation'))
  self.assertFalse(result['exercise']);self.assertIn('learning_unavailable',[w['action'] for w in s.validation_warnings])
 def test_no_gap_offers_choices_without_a_mandatory_learner_call(self):
  s=self.session();allowed=h.eligible_evidence(s);packet={'criteria':{k:dict(score=None,evidence_ids=[],explanation='Nicht beurteilt.',improvement=h.no_improvement()) for k in allowed}};packet['criteria']['motivation']=dict(score=3,evidence_ids=[next(iter(allowed['motivation']))],explanation='Du nennst ein Interesse.',improvement=h.no_improvement())
  with patch.object(c.model_client,'apertus',return_value=json.dumps(evaluator_packet(packet))) as model:r=s.finish()
  self.assertEqual(model.call_count,1);self.assertIsNone(s.learning_target);self.assertFalse(r['can_revise']);self.assertEqual(r['optional_practice_choices'][0]['target_id'],'optional:motivation');self.assertFalse(s.feedback['learning']['exercise'])
 def test_optional_target_requires_explicit_valid_choice_and_preserves_scores(self):
  s=self.session();row=self.criterion(s);s.complete=True;s.feedback={'criteria':[row],'optional_practice_choices':[{'target_id':'optional:motivation','key':'motivation','label':'Motivation'}]}
  with self.assertRaises(ValueError):h.choose_practice(s,'optional:fake')
  packet=dict(target_id='optional:motivation',explanation='Freiwillig üben.',exercise='Erkläre eine Tätigkeit in einem Satz.',reflection='Welche Tätigkeit interessiert dich?',revision_prompt='Formuliere neu.',encouragement='Übe in deinem Tempo.')
  with patch.object(c.model_client,'apertus',return_value=json.dumps(evaluator_packet(packet))) as model:r=h.choose_practice(s,'optional:motivation')
  self.assertTrue(r['can_revise']);self.assertEqual(row['score'],2);self.assertTrue(s.practice_history[-1]['optional']);data=json.loads(model.call_args.args[0][1]['content']);self.assertTrue(data['optional_practice']);self.assertEqual(data['target']['missing_detail'],'')
 def test_low_score_without_specific_gap_is_withheld(self):
  s=self.session();allowed=h.eligible_evidence(s)
  packet={'criteria':{key:dict(score=None,evidence_ids=[],explanation='Nicht beurteilt.',improvement=h.no_improvement()) for key in allowed}}
  packet['criteria']['motivation']=dict(score=2,evidence_ids=[next(iter(allowed['motivation']))],explanation='Kein langer Karriereplan.',improvement=h.no_improvement())
  with patch.object(c.model_client,'apertus',return_value=json.dumps(evaluator_packet(packet))):s.finish()
  row=next(x for x in s.feedback['criteria'] if x['key']=='motivation');self.assertIsNone(row['score']);self.assertNotIn('Karriereplan',row['explanation']);self.assertIsNone(s.learning_target)
 def test_optional_practice_api_persists_the_chosen_target(self):
  import web,tempfile,threading
  from types import SimpleNamespace
  s=self.session();s.complete=True;row=self.criterion(s);s.feedback={'criteria':[row],'optional_practice_choices':[{'target_id':'optional:motivation','key':'motivation','label':'Motivation'}]}
  sid='b'*32;server=SimpleNamespace(provider='apertus',model='test',sessions={sid:s},session_lock=threading.Lock())
  handler=object.__new__(web.Handler);handler.path='/api/practice/select';handler.server=server;responses=[];handler.send=lambda code,data:responses.append((code,data))
  packet=dict(target_id='optional:motivation',explanation='Freiwillig üben.',exercise='Erkläre eine Tätigkeit.',reflection='Welche Tätigkeit interessiert dich?',revision_prompt='Formuliere neu.',encouragement='Übe in deinem Tempo.')
  with tempfile.TemporaryDirectory() as folder,patch.object(c,'ROOT',Path(folder)),patch.object(c.model_client,'apertus',return_value=json.dumps(packet)):
   handler.controlled_request({'session_id':sid,'revision':s.answers,'target_id':'optional:motivation'},'de','it')
   saved=json.loads((Path(folder)/'data/sessions'/f'{sid}.json').read_text())
  self.assertEqual(responses[0][0],200);self.assertTrue(responses[0][1]['can_revise']);self.assertEqual(saved['learning_target']['target_id'],'optional:motivation');self.assertTrue(saved['practice_history'][-1]['optional']);self.assertEqual(saved['answers'],2);self.assertEqual(saved['practice_events'],1);self.assertEqual(responses[0][1]['state']['revision'],3);self.assertNotEqual(responses[0][1]['speech']['turn_id'],__import__('voice').speech_output('Previous recap','de',sid,2,'feedback')['turn_id'])
 def test_empty_evidence_groups_are_unassessed_without_model_calls(self):
  s=self.session();s.answers=3;empty={x['key']:{} for x in c.RUBRIC['criteria']}
  with patch.object(h,'eligible_evidence',return_value=empty),patch.object(c.model_client,'apertus') as model:r=s.finish()
  model.assert_not_called();self.assertTrue(all(x['score'] is None for x in s.feedback['criteria']));self.assertFalse(r['can_revise'])
 def test_dates_and_abbreviations_remain_whole_in_evidence(self):
  text='Ich wohne in St. Gallen. Die Woche vom 10. bis 13. August passt.';quotes=h.parts(text)
  self.assertIn('Ich wohne in St. Gallen.',quotes);self.assertIn('Die Woche vom 10. bis 13. August passt.',quotes)

if __name__=='__main__':unittest.main()
