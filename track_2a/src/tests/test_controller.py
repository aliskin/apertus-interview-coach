from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json
import unittest
from unittest.mock import patch
import interview_controller as c
class ControllerTests(unittest.TestCase):
 def session(self,ids):
  s=c.Session('de',c.POSTINGS['P-01'],c.make_plan(ids),pipeline="legacy");s.start();return s
 def analysis(self,text,status='answered',missing=''):
  return dict(observations=[dict(statement=text,quote=text)],answer_status=status,missing_information=missing,support_quote='',company_question_quote='',resolved_record_ids=[],conflict_record_ids=[])
 def speaker(self,question=''):
  return dict(acknowledgement='Danke, das hilft mir, deine Antwort zu verstehen.',question=question)
 def test_smalltalk_cannot_follow_up(self):
  s=self.session(['Q-01-01','Q-02-01'])
  with patch.object(c.model_client,'apertus',side_effect=[json.dumps(self.analysis('Ja, danke.')),json.dumps(self.speaker('Warum?'))]) as model:result=s.answer('Ja, danke.')
  self.assertEqual(model.call_count,2);self.assertEqual(s.main_question_count,2);self.assertEqual(s.followup_count,0);self.assertIn('Erzähl',result['reply'])
 def test_one_followup_then_progress(self):
  s=self.session(['Q-03-01','Q-05-01']);packets=[self.analysis('Weiss nicht.','unanswered','Interesse am Beruf'),self.speaker('Was interessiert dich an diesem Beruf?'),self.analysis('Die Technik.'),self.speaker()]
  with patch.object(c.model_client,'apertus',side_effect=[json.dumps(p) for p in packets]):s.answer('Weiss nicht.');s.answer('Die Technik.')
  self.assertEqual(s.followup_count,1);self.assertEqual(s.main_question_count,2);self.assertEqual(s.current_stage,'strengths_weaknesses')
  self.assertEqual([r['task'] for r in s.requests],['analysis','speaker','analysis','speaker'])
 def test_conditions(self):
  self.assertEqual(c.make_plan(['Q-06-06']),[])
  self.assertEqual(len(c.make_plan(['Q-06-06'],{'school':{'stellwerk':'done'}})),1)
 def test_feedback_rejects_fake_quotes(self):
  s=self.session(['Q-01-01']);s.transcript.append({'role':'user','content':'Ja, danke.'});s.answers=1
  p=dict(summary='Gut.',closing='Übe weiter.',criteria=[dict(key=x['key'],score=3,evidence='Invented',explanation='Gut',next_step='') for x in c.RUBRIC['criteria']])
  with patch.object(c.model_client,'apertus',return_value=json.dumps(p)),self.assertRaisesRegex(ValueError,'absent'):s.finish()
 def test_early_recap_covers_all_criteria(self):
  s=self.session(['Q-01-01']);p=dict(summary='Danke.',closing='Das war eine Übung.',criteria=[dict(key=x['key'],score=None,evidence='',explanation='Nicht beobachtet.',next_step='') for x in c.RUBRIC['criteria']])
  with patch.object(c.model_client,'apertus',return_value=json.dumps(p)):s.answer('Ja.',recap=True)
  self.assertTrue(s.complete);self.assertEqual(s.current_stage,'feedback');self.assertEqual(len(s.feedback['criteria']),11)

 def test_dossier_does_not_include_simulator_persona(self):
  s=self.session(['Q-03-01','Q-05-01'])
  packet=self.speaker()
  with patch.object(c.model_client,'apertus',side_effect=[json.dumps(self.analysis('Ich mag Technik.')),json.dumps(packet)]) as request:
   s.answer('Ich mag Technik.')
  content=json.dumps(request.call_args.args[0])
  self.assertNotIn('simulation_persona',content)
  self.assertNotIn('success_criteria_for_coach',content)
  self.assertNotIn('adaptive_hooks',content)
 def test_main_question_is_code_owned(self):
  s=self.session(['Q-03-01','Q-05-01'])
  packet=self.speaker('What is your bank account?')
  with patch.object(c.model_client,'apertus',side_effect=[json.dumps(self.analysis('Ich mag Technik.')),json.dumps(packet)]):
   result=s.answer('Ich mag Technik.')
  self.assertIn(c.QUESTIONS['Q-05-01']['text']['de'],result['reply'])
  self.assertNotIn('bank account',result['reply'])

 def test_english_default_questions_are_translated(self):
  for key in c.ENGLISH_DEFAULTS:
   self.assertNotEqual(c.question_text(c.QUESTIONS[key],'en'),c.QUESTIONS[key]['text']['de'])

 def test_controlled_api_revision_persistence_and_retry_accounting(self):
  import web, tempfile, threading
  from types import SimpleNamespace
  from io import BytesIO
  server=SimpleNamespace(pipeline='legacy',provider='apertus',model='test',sessions={},session_lock=threading.Lock())
  def request(path,payload):
   h=object.__new__(web.Handler);h.path=path;h.server=server
   raw=json.dumps(payload).encode();h.headers={'Content-Length':str(len(raw)),'Host':'localhost'};h.rfile=BytesIO(raw)
   out=[];h.send=lambda status,body:out.append((status,body));h.do_POST();return out[0]
  with tempfile.TemporaryDirectory() as folder,patch.object(c,'ROOT',Path(folder)):
   status,opening=request('/api/session/start',{'language':'de','scenario':'it'});self.assertEqual(status,200)
   sid=opening['session_id']
   with patch.object(c.model_client,'apertus',side_effect=[json.dumps(self.analysis('Ja, danke.')),json.dumps(self.speaker())]):
    request('/api/answer',dict(language='de',scenario='it',session_id=sid,revision=0,answer='Ja, danke.'))
   payload=dict(language='de',scenario='it',session_id=sid,revision=1,answer='Ich mag Technik.')
   self.assertEqual(opening['speech']['language'],'de-CH');self.assertEqual(opening['speech']['kind'],'opening')
   with patch.object(c.model_client,'apertus',side_effect=RuntimeError('offline')):
    self.assertEqual(request('/api/answer',payload)[0],502)
   self.assertEqual(server.sessions[sid].answers,1);self.assertEqual(server.sessions[sid].model_calls,3)
   packet=self.speaker()
   with patch.object(c.model_client,'apertus',side_effect=[json.dumps(self.analysis('Ich mag Technik.')),json.dumps(packet)]):
    status,result=request('/api/answer',payload);self.assertEqual(status,200)
   self.assertEqual(result['state']['answers'],2);self.assertEqual(result['state']['model_calls'],5)
   self.assertEqual(result['speech']['session_id'],sid);self.assertNotEqual(result['speech']['turn_id'],opening['speech']['turn_id'])
   self.assertEqual(request('/api/answer',payload),(200,result))
   self.assertEqual(request('/api/answer',{**payload,'answer':'A different answer'})[0],400)
   saved=json.loads((Path(folder)/'data/sessions'/f'{sid}.json').read_text());self.assertEqual(saved['answers'],2);self.assertEqual(saved['model_calls'],5)

 def test_localized_guidance_covers_same_rubric_and_rules(self):
  keys=[x['key'] for x in c.RUBRIC['criteria']]
  rule_ids=[r['id'] for g in c.GUIDELINES['groups'] for r in g['rules']]
  for language in ('de','fr','it','en'):
   guidance=c.GUIDANCE[language]
   self.assertEqual([x['key'] for x in guidance['rubric']],keys)
   self.assertEqual([x['id'] for x in guidance['guidelines']],rule_ids)
   for original,translated in zip(c.RUBRIC['criteria'],guidance['rubric']):
    self.assertEqual([l['score'] for l in translated['levels']],[l['value'] for l in original['levels']])
    self.assertTrue(translated['meaning']);self.assertTrue(all(l['anchor'] for l in translated['levels']))
   self.assertTrue(all(r['text'] for r in guidance['guidelines']))

 def test_localized_analysis_and_speaker_messages(self):
  for language in ('de','fr','it'):
   s=c.Session(language,c.POSTINGS['P-01'],c.make_plan(['Q-03-01','Q-05-01']),pipeline='legacy');s.start()
   text='Technik.'
   with patch.object(c.model_client,'apertus',side_effect=[json.dumps(self.analysis(text)),json.dumps(self.speaker())]) as model:s.answer(text)
   self.assertTrue(model.call_args_list[0].args[0][0]['content'].startswith(c.task_prompt('analysis',language)))
   self.assertTrue(model.call_args_list[1].args[0][0]['content'].startswith(c.task_prompt('speaker',language)))
   question=c.question_context(s.plan[0],language)
   self.assertEqual(question['text'],s.plan[0]['text'][language]);self.assertNotIn('gsw_variants',question)

 def test_fake_analysis_evidence_cannot_trigger_followup(self):
  s=self.session(['Q-03-01','Q-05-01'])
  with patch.object(c.model_client,'apertus',return_value=json.dumps(self.analysis('Invented.','partial','Example'))):result=s.answer('Technik.')
  self.assertEqual(s.followup_count,0);self.assertEqual(s.answer_analyses,[]);self.assertIn('analysis_unavailable',[w['action'] for w in s.validation_warnings]);self.assertLess(s.model_calls,5)

 def test_short_sufficient_answer_advances_even_if_speaker_proposes_question(self):
  s=self.session(['Q-03-01','Q-05-01'])
  with patch.object(c.model_client,'apertus',side_effect=[json.dumps(self.analysis('Technik.')),json.dumps(self.speaker('Warum?'))]):s.answer('Technik.')
  self.assertEqual(s.followup_count,0);self.assertEqual(s.turn_decisions[-1]['action'],'advance')

 def test_retry_budget_reserves_early_recap(self):
  s=self.session(['Q-03-01','Q-05-01'])
  feedback=dict(summary='',closing='',criteria=[dict(key=x['key'],score=None,evidence='',explanation='',next_step='') for x in c.RUBRIC['criteria']])
  with patch.object(c.model_client,'apertus',side_effect=['{}',json.dumps(self.analysis('Technik.')),json.dumps(feedback)]):
   s.answer('Technik.');s.finish()
  self.assertLess(s.model_calls/s.answers,5);self.assertTrue(s.complete)

 def test_localized_feedback_messages_without_inference(self):
  for language in ('de','fr','it'):
   s=c.Session(language,c.POSTINGS['P-01'],c.make_plan(['Q-01-01']),pipeline='legacy');s.start()
   p=dict(summary='',closing='',criteria=[dict(key=x['key'],score=None,evidence='',explanation='',next_step='') for x in c.RUBRIC['criteria']])
   with patch.object(c.model_client,'apertus',return_value=json.dumps(p)) as model:
    s.answer(c.QUESTIONS['Q-01-01']['text'][language],recap=True)
   messages=model.call_args.args[0];instructions=c.INSTRUCTIONS[language]
   self.assertTrue(messages[0]['content'].startswith(c.task_prompt('feedback',language)))
   self.assertIn(json.dumps(c.GUIDANCE[language]['rubric'],ensure_ascii=False),messages[0]['content'])
   self.assertIn(json.dumps(c.GUIDANCE[language]['guidelines'],ensure_ascii=False),messages[0]['content'])
   self.assertTrue(messages[-1]['content'].startswith(instructions['quotes']))
   self.assertIn(instructions['keys'],messages[-1]['content'])
   self.assertNotIn('Use evidence ONLY',messages[-1]['content'])
   self.assertNotIn('Public rubric:',messages[0]['content'])

 def test_strong_self_doubt_in_introduction_gets_support(self):
  s=self.session(['Q-01-01','Q-02-01']);text='Ich bin zu schlecht für alles.'
  analysis=self.analysis(text);analysis['support_quote']=text
  packet={'acknowledgement':'Das klingt belastend. Sprich mit deiner Lehrperson. Hier können wir in deinem Tempo üben.','question':''}
  with patch.object(c.model_client,'apertus',side_effect=[json.dumps(analysis),json.dumps(packet)]):result=s.answer(text)
  self.assertEqual(s.turn_decisions[-1]['action'],'support_advance');self.assertIn('Lehrperson',result['reply']);self.assertEqual(s.followup_count,0)

 def test_company_request_during_phone_documents_is_answered(self):
  s=self.session(['Q-OTH-03','Q-10-01']);text='Welche Unterlagen brauchen Sie?'
  analysis=self.analysis(text,'partial','Unterlagen');analysis['company_question_quote']=text
  packet={'acknowledgement':'Schick deinen Lebenslauf und deine Zeugnisse.','question':''}
  with patch.object(c.model_client,'apertus',side_effect=[json.dumps(analysis),json.dumps(packet)]):result=s.answer(text)
  self.assertEqual(s.turn_decisions[-1]['action'],'answer_company');self.assertEqual(s.followup_count,0);self.assertIn('Zeugnisse',result['reply'])

 def test_followup_cannot_copy_future_main_question(self):
  s=self.session(['Q-03-01','Q-05-01']);text='Weiss nicht.'
  packets=[self.analysis(text,'partial','Interesse'),self.speaker(c.question_text(s.plan[1],'de'))]
  with patch.object(c.model_client,'apertus',side_effect=[json.dumps(p) for p in packets]):s.answer(text)
  self.assertEqual(s.followup_count,0);self.assertEqual(s.index,1);self.assertIn('speaker_bank_fallback',[w['action'] for w in s.validation_warnings])

 def test_evidence_gap_resolution_preserves_original_quote(self):
  s=self.session(['Q-03-01','Q-05-01']);first=self.analysis('Weiss nicht.','partial','Eine Tätigkeit');second=self.analysis('Ich habe Joghurts eingeräumt.');second['resolved_record_ids']=['answer-1']
  packets=[first,self.speaker('Was hast du am ersten Morgen gemacht?'),second,self.speaker()]
  with patch.object(c.model_client,'apertus',side_effect=[json.dumps(p) for p in packets]):s.answer('Weiss nicht.');s.answer('Ich habe Joghurts eingeräumt.')
  self.assertEqual(s.evidence_records[0]['evidence'][0]['quote'],'Weiss nicht.')
  self.assertEqual(s.evidence_records[0]['open_gap'],'');self.assertEqual(s.evidence_records[0]['clarified_by'],['answer-2']);self.assertEqual(s.evidence_records[0]['original_gap'],'Eine Tätigkeit')

 def test_possible_conflict_is_recorded_without_overwriting(self):
  s=self.session(['Q-03-01','Q-05-01','Q-05-03']);first=self.analysis('Ich arbeite lieber alleine.');second=self.analysis('Ich arbeite immer am liebsten im Team.');second['conflict_record_ids']=['answer-1']
  with patch.object(c.model_client,'apertus',side_effect=[json.dumps(p) for p in [first,self.speaker(),second,self.speaker()]]):s.answer('Ich arbeite lieber alleine.');s.answer('Ich arbeite immer am liebsten im Team.')
  self.assertEqual(s.evidence_records[0]['possible_conflict'],['answer-2']);self.assertEqual(s.evidence_records[0]['evidence'][0]['quote'],'Ich arbeite lieber alleine.')

 def test_memory_rejects_unknown_record_ids(self):
  s=self.session(['Q-03-01','Q-05-01']);packet=self.analysis('Technik.');packet['resolved_record_ids']=['invented']
  with patch.object(c.model_client,'apertus',return_value=json.dumps(packet)):s.answer('Technik.')
  self.assertEqual(s.answer_analyses,[]);self.assertEqual(s.evidence_records[0]['uncertainty'],'analysis_unavailable')

 def test_quoted_statement_is_not_a_company_request(self):
  s=self.session(['Q-01-01','Q-02-01']);text='Ja, ich bin gut angekommen.'
  analysis=self.analysis(text);analysis['company_question_quote']=text
  with patch.object(c.model_client,'apertus',side_effect=[json.dumps(analysis),json.dumps(self.speaker())]):s.answer(text)
  self.assertEqual(s.turn_decisions[-1]['action'],'advance');self.assertEqual(s.answer_analyses[-1]['company_question_quote'],'')
