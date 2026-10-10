from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json
import unittest
from unittest.mock import patch
import interview_controller as c
class ControllerTests(unittest.TestCase):
 def session(self,ids):
  s=c.Session('de',c.POSTINGS['P-01'],c.make_plan(ids));s.start();return s
 def test_smalltalk_cannot_follow_up(self):
  s=self.session(['Q-01-01','Q-02-01']);packet={'acknowledgement':'Danke.','question':'Warum?','followup':True,'reason':'short'}
  with patch.object(c.model_client,'apertus',return_value=json.dumps(packet)):result=s.answer('Ja, danke.')
  self.assertEqual(s.model_calls,2);self.assertEqual(s.main_question_count,2)
  self.assertEqual(s.followup_count,0);self.assertIn('Erzähl',result['reply'])
  self.assertEqual(s.validation_warnings[-1]['action'],'bank_question_fallback')
 def test_one_followup_then_progress(self):
  s=self.session(['Q-03-01','Q-05-01']);packets=[dict(acknowledgement='',question='Was gefällt dir?',followup=True,reason='vague'),dict(acknowledgement='',question='Welche Stärke hast du?',followup=False,reason='advance')]
  with patch.object(c.model_client,'apertus',side_effect=[json.dumps(p) for p in packets]):s.answer('Weiss nicht.');s.answer('Die Technik.')
  self.assertEqual(s.followup_count,1);self.assertEqual(s.main_question_count,2);self.assertEqual(s.current_stage,'strengths_weaknesses')
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
  packet=dict(acknowledgement='Danke.',question='Was sind deine Stärken?',followup=False,reason='advance')
  with patch.object(c.model_client,'apertus',return_value=json.dumps(packet)) as request:
   s.answer('Ich mag Technik.')
  content=json.dumps(request.call_args.args[0])
  self.assertNotIn('simulation_persona',content)
  self.assertNotIn('success_criteria_for_coach',content)
  self.assertNotIn('adaptive_hooks',content)
 def test_main_question_is_code_owned(self):
  s=self.session(['Q-03-01','Q-05-01'])
  packet=dict(acknowledgement='Danke.',question='What is your bank account?',followup=False,reason='advance')
  with patch.object(c.model_client,'apertus',return_value=json.dumps(packet)):
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
  server=SimpleNamespace(provider='apertus',model='test',sessions={},session_lock=threading.Lock())
  def request(path,payload):
   h=object.__new__(web.Handler);h.path=path;h.server=server
   raw=json.dumps(payload).encode();h.headers={'Content-Length':str(len(raw)),'Host':'localhost'};h.rfile=BytesIO(raw)
   out=[];h.send=lambda status,body:out.append((status,body));h.do_POST();return out[0]
  with tempfile.TemporaryDirectory() as folder,patch.object(c,'ROOT',Path(folder)):
   status,opening=request('/api/session/start',{'language':'de','scenario':'it'});self.assertEqual(status,200)
   sid=opening['session_id'];payload=dict(language='de',scenario='it',session_id=sid,revision=0,answer='Ja, danke.')
   with patch.object(c.model_client,'apertus',side_effect=RuntimeError('offline')):
    self.assertEqual(request('/api/answer',payload)[0],502)
   self.assertEqual(server.sessions[sid].answers,0);self.assertEqual(server.sessions[sid].model_calls,1)
   packet=dict(acknowledgement='Danke.',question='',followup=False,reason='advance')
   with patch.object(c.model_client,'apertus',return_value=json.dumps(packet)):
    status,result=request('/api/answer',payload);self.assertEqual(status,200)
   self.assertEqual(result['state']['answers'],1);self.assertEqual(result['state']['model_calls'],2)
   self.assertEqual(request('/api/answer',payload)[0],400)
   saved=json.loads((Path(folder)/'data/sessions'/f'{sid}.json').read_text());self.assertEqual(saved['answers'],1);self.assertEqual(saved['model_calls'],2)

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

 def test_localized_interviewer_and_correction_messages(self):
  for language in ('de','fr','it'):
   s=c.Session(language,c.POSTINGS['P-01'],c.make_plan(['Q-03-01','Q-05-01']));s.start()
   p=dict(acknowledgement='',question='',followup=False,reason='')
   with patch.object(c.model_client,'apertus',side_effect=['{}',json.dumps(p)]) as model:
    s.answer(c.QUESTIONS['Q-03-01']['text'][language])
   messages=model.call_args.args[0]
   self.assertTrue(messages[0]['content'].startswith(c.task_prompt('interviewer',language)))
   self.assertIn(c.INSTRUCTIONS[language]['context'],messages[0]['content'])
   self.assertTrue(messages[-2]['content'].startswith(c.INSTRUCTIONS[language]['task']))
   self.assertEqual(messages[-1]['content'],c.INSTRUCTIONS[language]['correction'])
   self.assertNotIn('CONTROLLER TASK',json.dumps(messages))
   question=c.question_context(s.plan[0],language)
   self.assertEqual(question['text'],s.plan[0]['text'][language])
   self.assertNotIn('gsw_variants',question);self.assertNotIn('phase_title_de',question)

 def test_localized_feedback_messages_without_inference(self):
  for language in ('de','fr','it'):
   s=c.Session(language,c.POSTINGS['P-01'],c.make_plan(['Q-01-01']));s.start()
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
