import sys,json,unittest,copy
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import interview_controller as c
import hybrid as h

class HybridTests(unittest.TestCase):
 def session(self,ids):
  s=c.Session('de',c.POSTINGS['P-01'],c.make_plan(ids));s.start();return s
 def analysis(self,text,status='sufficient',gap='',requests=None):
  return dict(quotes=[text],status=status,gap=gap,requests=requests or [],support_quote='',resolves=[],conflicts=[])
 def test_self_doubt_is_supported_even_if_model_misses_trigger(self):
  text='Ich glaube, ich bin nicht so schlau.';s=self.session(['Q-02-01','Q-03-01'])
  with patch.object(c.model_client,'apertus',return_value=json.dumps(self.analysis(text))):r=s.answer(text)
  self.assertEqual(s.turn_decisions[-1]['action'],'support');self.assertIn('Berufsberatung',r['reply']);self.assertNotIn('realistisch',r['reply']);self.assertEqual(s.model_calls,1)
 def test_nervousness_alone_is_not_distress(self):self.assertEqual(h.strong_doubt('Ich bin etwas nervös.'),'')
 def test_advance_rejects_extra_question_and_unsupported_praise(self):
  s=self.session(['Q-03-01','Q-05-01']);text='Ich mag Technik.'
  with patch.object(c.model_client,'apertus',side_effect=[json.dumps(self.analysis(text)),json.dumps(dict(acknowledgement='Das zeigt Teamfähigkeit. Wie lernst du?',question='')),json.dumps(dict(acknowledgement='Danke für die Erklärung.',question=''))]):r=s.answer(text)
  self.assertNotIn('Teamfähigkeit',r['reply']);self.assertNotIn('Wie lernst',r['reply']);self.assertEqual(s.model_calls,2)
 def test_company_selection_cannot_invent_posting_facts(self):
  s=self.session(['Q-OTH-03','Q-10-01']);text='Welche Unterlagen braucht ihr?'
  with patch.object(c.model_client,'apertus',side_effect=[json.dumps(self.analysis(text,requests=[text])),json.dumps({'answers':[{'request_quote':text,'fact_ids':['fake'],'unavailable':False}]}),json.dumps({'answers':[{'request_quote':text,'fact_ids':[],'unavailable':True}]})]):r=s.answer(text)
  self.assertIn('keine verlässliche Antwort',r['reply']);self.assertNotIn('fake',r['reply']);self.assertEqual(s.turn_decisions[-1]['action'],'answer_company')
 def test_hypothetical_evidence_and_unassessed_difficult_questions(self):
  s=self.session(['Q-SIT-02']);s.transcript.append({'role':'user','content':'Ich würde nachfragen.','question_id':'Q-SIT-02'});s.answers=1
  allowed=h.eligible_evidence(s);self.assertTrue(allowed['communication']);self.assertTrue(all(e['kind']=='hypothetical' for e in allowed['communication'].values()))
  s.transcript[-1]['question_id']='Q-OTH-03';self.assertFalse(h.eligible_evidence(s)['difficult_questions']);self.assertFalse(h.eligible_evidence(s)['demeanor'])
 def test_recap_displays_evidence_and_has_one_learning_target(self):
  s=self.session(['Q-03-01']);text='Ich mag Technik.';s.transcript.append({'role':'user','content':text,'question_id':'Q-03-01'});s.answers=1
  allowed=h.eligible_evidence(s);packet={'criteria':{k:dict(score=None,evidence_ids=[],explanation='Nicht ausreichend beurteilt.') for k in allowed}}
  key=next(k for k,v in allowed.items() if v);eid=next(iter(allowed[key]));packet['criteria'][key]=dict(score=2,evidence_ids=[eid],explanation='Das Interesse ist genannt, der Bezug zum Beruf bleibt offen.')
  learning=dict(explanation='Du kannst deinen Bezug zum Beruf ergänzen.',exercise='Schreibe eine Tätigkeit auf und erkläre in einem Satz, weshalb sie dich interessiert.',reflection='Welche Tätigkeit interessiert dich?',revision_prompt='Formuliere deine Antwort noch einmal.',encouragement='Du darfst in Ruhe weiterüben.')
  with patch.object(c.model_client,'apertus',side_effect=[json.dumps(packet),json.dumps(learning)]):r=s.finish()
  self.assertIn('„Ich mag Technik.“',r['reply']);self.assertEqual(s.requests[-2]['task'],'evaluator');self.assertEqual(s.requests[-1]['task'],'learning');self.assertEqual(len(s.practice_history),1);self.assertEqual(s.practice_history[0]['criterion'],key);self.assertTrue(r['can_revise']);self.assertLess(s.model_calls/s.answers,5)
 def test_learning_unavailable_is_transparent_not_fabricated(self):
  s=self.session(['Q-03-01']);s.answers=1;s.transcript.append({'role':'user','content':'Technik.','question_id':'Q-03-01'})
  packet={'criteria':{k['key']:dict(score=None,evidence_ids=[],explanation='Nicht beurteilt.') for k in c.RUBRIC['criteria']}}
  with patch.object(c.model_client,'apertus',side_effect=[json.dumps(packet),'{}','{}']):r=s.finish()
  self.assertIn('nicht verfügbar',r['reply']);self.assertFalse(r['can_revise'])
 def test_score_cannot_use_other_criterion_evidence(self):
  s=self.session(['Q-03-01']);s.answers=1;s.transcript.append({'role':'user','content':'Technik.','question_id':'Q-03-01'})
  packet={'criteria':{k['key']:dict(score=None,evidence_ids=[],explanation='Nicht beurteilt.') for k in c.RUBRIC['criteria']}};packet['criteria']['difficult_questions']=dict(score=4,evidence_ids=['candidate-1:quote-1'],explanation='Gut.')
  goodlearning=dict(explanation='Danke für die Übung.',exercise='',reflection='',revision_prompt='',encouragement='Übe in deinem Tempo.')
  with patch.object(c.model_client,'apertus',side_effect=[json.dumps(packet),json.dumps(packet),json.dumps(goodlearning)]):s.finish()
  self.assertTrue(all(x['score'] is None for x in s.feedback['criteria']));self.assertIn('evaluation_unavailable',[x['action'] for x in s.validation_warnings])
 def test_revision_keeps_assessment_and_counts_calls(self):
  s=self.session(['Q-03-01']);s.complete=True;s.answers=2;s.learning_target={'key':'motivation','evidence_records':[]};before=copy.deepcopy(s.feedback)
  with patch.object(c.model_client,'apertus',return_value=json.dumps({'reply':'Jetzt nennst du eine konkrete Tätigkeit. Übe weiter.'})):r=s.revise('Ich möchte technische Zeichnungen erstellen.')
  self.assertEqual(s.feedback,before);self.assertEqual(s.practice_answers,1);self.assertEqual(s.requests[-1]['task'],'revision');self.assertTrue(r['complete'])
 def test_api_revision_and_same_posting_learning_history(self):
  import web,tempfile,threading
  from types import SimpleNamespace
  prior=c.Session('de',c.POSTINGS['P-11'],c.make_plan(['Q-03-01']));prior.start();prior.complete=True;prior.answers=2;prior.learning_target={'key':'motivation','evidence_records':[]};prior.practice_history=[{'criterion':'motivation','exercise':'Nenne eine Tätigkeit.','optional':True}]
  identifier='a'*32;server=SimpleNamespace(provider='apertus',model='test',sessions={identifier:prior},session_lock=threading.Lock())
  def request(path,payload):
   handler=object.__new__(web.Handler);handler.path=path;handler.server=server;out=[];handler.send=lambda status,data:out.append((status,data));handler.controlled_request(payload,'de','it');return out[0]
  with tempfile.TemporaryDirectory() as folder,patch.object(c,'ROOT',Path(folder)):
   with patch.object(c.model_client,'apertus',return_value=json.dumps({'reply':'Du nennst jetzt eine konkrete Tätigkeit. Übe weiter.'})):
    code,data=request('/api/revise',{'session_id':identifier,'revision':2,'answer':'Ich möchte Webseiten erstellen.'})
   self.assertEqual(code,200);self.assertEqual(data['state']['practice_answers'],1);self.assertEqual(server.sessions[identifier].answers,2)
   code,new=request('/api/session/start',{'previous_session_id':identifier,'experience':'some_practice','difficulty':'easy'})
   self.assertEqual(code,200);self.assertEqual(new['state']['prior_learning_targets'][0]['exercise'],'Nenne eine Tätigkeit.')
   self.assertEqual(server.sessions[new['session_id']].difficulty,'easy');self.assertEqual(server.sessions[new['session_id']].experience,'some_practice')
 def test_smalltalk_only_recap_does_not_invent_a_learning_deficit(self):
  s=self.session(['Q-01-01']);s.answers=1;s.transcript.append({'role':'user','content':'Ja, danke.','question_id':'Q-01-01'})
  with patch.object(c.model_client,'apertus') as model:r=s.finish()
  model.assert_not_called();self.assertFalse(r['can_revise']);self.assertIsNone(s.learning_target);self.assertTrue(all(x['score'] is None for x in s.feedback['criteria']))
 def test_unassessed_text_cannot_smuggle_an_assessment(self):
  item=dict(key='demeanor',score=None,explanation='Du wirkst selbstsicher.')
  h.normalise_unassessed(item);self.assertNotIn('selbstsicher',item['explanation']);self.assertIn('nicht beurteilen',item['explanation'])
 def test_employer_promises_and_missing_punctuation_are_guarded(self):
  self.assertEqual(h.join_reply('Danke für die Erklärung','Warum dieser Beruf?'),'Danke für die Erklärung. Warum dieser Beruf?')
  self.assertNotIn('schicke',h.join_reply('Ich schicke dir die Liste gleich zu.','Warum dieser Beruf?'))
 def test_group_task_is_hypothetical_not_observed_teamwork(self):
  self.assertEqual(h.evidence_kind(c.QUESTIONS['Q-OTH-09'],'Zuerst würde ich Aufgaben verteilen.'),'hypothetical')
 def test_previous_support_is_not_referred_again(self):
  s=self.session(['Q-02-01','Q-03-01']);s.support_offered=True;text='Ich zweifle an mir.'
  with patch.object(c.model_client,'apertus',return_value=json.dumps(self.analysis(text))):r=s.answer(text)
  self.assertNotIn('Berufsberatung',r['reply']);self.assertIn('Zeit nehmen',r['reply'])
 def test_plan_and_configuration_bounds(self):
  with self.assertRaises(ValueError):c.Session('de',c.POSTINGS['P-01'],c.make_plan(['Q-03-01']),difficulty='invalid').start()
  s=self.session(['Q-03-01']);s.plan=s.plan*16
  with self.assertRaises(ValueError):s.start()

if __name__=='__main__':unittest.main()
