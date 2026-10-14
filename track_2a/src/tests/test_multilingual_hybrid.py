"""All production languages share evidenced recap, verification and practice."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import interview_controller as c
import hybrid as h

LANGUAGES=('en','de','fr','it')
ANSWERS={'en':'I like practical work.','de':'Ich mag praktische Arbeit.','fr':'J’aime le travail pratique.','it':'Mi piace il lavoro pratico.'}
class MultilingualHybridTests(unittest.TestCase):
 def session(self,language):
  s=c.Session(language,c.POSTINGS['P-01'],c.make_plan(['Q-03-01','Q-05-01']));s.start();s.record_answer(ANSWERS[language]);return s
 def test_default_routes_all_languages_to_same_recap_and_revision(self):
  for language in LANGUAGES:
   with self.subTest(language=language):
    s=self.session(language)
    with patch.object(h,'finish',return_value={'complete':True}) as finish:s.finish()
    finish.assert_called_once_with(s)
    with patch.object(h,'revise',return_value={'reply':'ok'}) as revise:s.revise('new answer')
    revise.assert_called_once_with(s,'new answer')
 def test_all_active_prompt_tasks_and_fixed_text_are_localised(self):
  for language in LANGUAGES:
   for task in ('evaluator','verify','learning','revision'):
    self.assertEqual(h.messages(task,{},language)[0]['content'],(c.PROMPTS/f'hybrid_{task}.{language}.txt').read_text())
   self.assertEqual(set(h.TEXT[language]),set(h.TEXT['de']))
   if language!='de':self.assertTrue(all(value!=h.TEXT['de'][key] for key,value in h.TEXT[language].items()))
 def test_recap_uses_local_rubric_actual_question_and_offers_explicit_practice(self):
  for language in LANGUAGES:
   with self.subTest(language=language):
    s=self.session(language);allowed=h.eligible_evidence(s)
    packet={'criteria':{k:dict(score=None,evidence_ids=[],explanation='Not observed.') for k in allowed},'improvements':[]}
    packet['criteria']['motivation']=dict(score=3,evidence_ids=[next(iter(allowed['motivation']))],explanation=ANSWERS[language])
    with patch.object(c.model_client,'apertus',return_value=json.dumps(packet)) as model:result=s.finish()
    payload=json.loads(model.call_args.args[0][1]['content'])
    self.assertEqual(payload['rubric'],c.GUIDANCE[language]['rubric'])
    self.assertEqual(payload['answers'][0]['question']['text'],c.question_text(s.plan[0],language))
    self.assertEqual(result['optional_practice_choices'][0]['label'],next(x['label'][language] for x in c.RUBRIC['criteria'] if x['key']=='motivation'))
    self.assertIn(h.local_text(language,'Was schon gelingt: '),result['reply'])
    self.assertFalse(result['can_revise']);self.assertLess(s.model_calls,5*s.answers)
 def test_gap_verification_learning_and_revision_use_same_language_and_evidence(self):
  for language in LANGUAGES:
   with self.subTest(language=language):
    s=self.session(language);allowed=h.eligible_evidence(s)['motivation'];eid=next(iter(allowed))
    row=dict(key='motivation',score=2,explanation='Gap.',evidence=ANSWERS[language],evidence_records=[dict(evidence_id=eid,**allowed[eid])],improvement=dict(usefulness='useful',missing_detail='Task',why_needed='Explain the choice.',already_supplied=False,expected_outcome='Name one task.',question_id='Q-03-01'))
    packet={'checks':{'gap:motivation':dict(decision='supported',reason='A task is missing.',evidence_ids=[eid])}}
    with patch.object(c.model_client,'apertus',return_value=json.dumps(packet)) as model:_,_,target=h.verify_improvements(s,[row])
    self.assertEqual(model.call_args.args[0][0]['content'],h.prompt('verify',language));self.assertEqual(target['label'],next(x['label'][language] for x in c.RUBRIC['criteria'] if x['key']=='motivation'))
    s.complete=True;s.learning_target=target
    with patch.object(c.model_client,'apertus',return_value=json.dumps({'reply':'One task is now present.'})) as model:s.revise('A revised answer.')
    self.assertEqual(model.call_args.args[0][0]['content'],h.prompt('revision',language));self.assertEqual(s.practice_answers,1)
 def test_optional_learning_api_and_speech_available_in_all_languages(self):
  from types import SimpleNamespace
  import tempfile,threading,web
  for language in LANGUAGES:
   with self.subTest(language=language):
    s=self.session(language);s.complete=True;s.feedback={'criteria':[dict(key='motivation',score=3,evidence_records=[])],'optional_practice_choices':h.optional_choices([dict(key='motivation',score=3)],language)}
    sid='d'*32;server=SimpleNamespace(provider='apertus',model='test',sessions={sid:s},session_lock=threading.Lock())
    handler=object.__new__(web.Handler);handler.path='/api/practice/select';handler.server=server;responses=[];handler.send=lambda code,data:responses.append((code,data))
    packet=dict(target_id='optional:motivation',explanation='Chosen practice.',exercise='Name a task.',reflection='Which task?',revision_prompt='Try again.',encouragement='Keep practising.')
    with tempfile.TemporaryDirectory() as folder,patch.object(c,'ROOT',Path(folder)),patch.object(c.model_client,'apertus',return_value=json.dumps(packet)) as model:
     handler.controlled_request(dict(session_id=sid,revision=s.answers,target_id='optional:motivation'),language,'it')
    self.assertEqual(responses[0][0],200);self.assertTrue(responses[0][1]['can_revise']);self.assertTrue(responses[0][1]['speech']['language'].startswith(language))
    self.assertEqual(model.call_args.args[0][0]['content'],h.prompt('learning',language))
 def test_early_smalltalk_is_unassessed_without_model_calls_in_all_languages(self):
  for language in LANGUAGES:
   s=c.Session(language,c.POSTINGS['P-01'],c.make_plan(['Q-01-01']));s.start()
   with patch.object(c.model_client,'apertus') as model:r=s.answer('Hello.',recap=True)
   model.assert_not_called();self.assertTrue(r['complete']);self.assertTrue(all(x['score'] is None for x in r['feedback']['criteria']))
   self.assertIn(h.local_text(language,'Wir haben bisher nur den kurzen Einstieg geübt. Für eine inhaltliche Rückmeldung brauchen wir weitere Interviewfragen.'),r['reply'])
 def test_invalid_verification_fails_closed_in_every_language(self):
  for language in LANGUAGES:
   s=self.session(language);allowed=h.eligible_evidence(s)['motivation'];eid=next(iter(allowed))
   row=dict(key='motivation',score=2,evidence='',evidence_records=[],explanation='',improvement=dict(usefulness='useful',missing_detail='Task',why_needed='Reason',already_supplied=False,expected_outcome='Task',question_id='Q-03-01'))
   with patch.object(c.model_client,'apertus',return_value=json.dumps({'checks':{'gap:motivation':dict(decision='supported',reason='Missing task.',evidence_ids=['invented'])}})):
    _,checks,target=h.verify_improvements(s,[row])
   self.assertIsNone(target);self.assertIsNone(row['score']);self.assertEqual(checks['gap:motivation']['reason'],h.local_text(language,'Die Gegenprüfung ist nicht verlässlich verfügbar.'))

 def test_rejected_gap_preserves_only_explicitly_independent_positive_assessment(self):
  for language in LANGUAGES:
   for score,dependent,kept in [(3,False,True),(4,False,True),(3,True,False),(2,False,False)]:
    with self.subTest(language=language,score=score,dependent=dependent):
     s=self.session(language);evidence=h.eligible_evidence(s)['motivation'];eid=next(iter(evidence))
     row=dict(key='motivation',score=score,assessment_depends_on_gap=dependent,explanation=ANSWERS[language],evidence=ANSWERS[language],evidence_records=[dict(evidence_id=eid,**evidence[eid])],improvement=dict(usefulness='useful',missing_detail='Task',why_needed='Explain choice.',already_supplied=False,expected_outcome='Name a task.',question_id='Q-03-01'))
     with patch.object(c.model_client,'apertus',return_value=json.dumps({'checks':{'gap:motivation':dict(decision='contradicted',reason='The detail is already supplied.',evidence_ids=[eid])}})):
      _,_,target=h.verify_improvements(s,[row])
     self.assertIsNone(target);self.assertEqual(row['score'],score if kept else None)
     if kept:self.assertEqual(row['explanation'],ANSWERS[language]);self.assertTrue(row['evidence_records'])
 def test_all_unassessed_substantive_answers_still_offer_voluntary_grounded_topics(self):
  for language in LANGUAGES:
   with self.subTest(language=language):
    s=self.session(language);allowed=h.eligible_evidence(s)
    packet={'criteria':{key:dict(score=None,evidence_ids=[],explanation='No rating.',assessment_depends_on_gap=False) for key in allowed},'improvements':[]}
    with patch.object(c.model_client,'apertus',return_value=json.dumps(packet)):result=s.finish()
    self.assertTrue(result['optional_practice_choices']);self.assertIsNone(s.learning_target);self.assertFalse(result['can_revise']);self.assertEqual(s.practice_history,[])
    choice=result['optional_practice_choices'][0];self.assertEqual(choice['question_id'],'Q-03-01')
    item=next(x for x in s.feedback['criteria'] if x['key']==choice['key']);item['improvement']={'missing_detail':'REJECTED COMPANY GAP'};item['explanation']='UNVERIFIED CLAIM'
    response=dict(target_id=choice['target_id'],explanation='Optional practice.',exercise='Try your answer in one sentence.',reflection='What matters most?',revision_prompt='Try again.',encouragement='Keep practising.')
    with patch.object(c.model_client,'apertus',return_value=json.dumps(response)) as model:practice=h.choose_practice(s,choice['target_id'])
    payload=json.loads(model.call_args.args[0][1]['content']);self.assertTrue(payload['optional_practice']);self.assertEqual(payload['target']['original_answer'],ANSWERS[language]);self.assertEqual(payload['target']['question']['text'],c.question_text(s.plan[0],language));self.assertEqual(payload['target']['missing_detail'],'');self.assertNotIn('improvement',payload['target']);self.assertNotIn('score',payload['target']);self.assertNotIn('explanation',payload['target']);self.assertTrue(practice['can_revise'])
 def test_even_verified_gap_never_assigns_an_exercise_automatically(self):
  for language in LANGUAGES:
   with self.subTest(language=language):
    s=self.session(language);allowed=h.eligible_evidence(s);eid=next(iter(allowed['motivation']))
    packet={'criteria':{key:dict(score=None,evidence_ids=[],explanation='No rating.',assessment_depends_on_gap=False) for key in allowed},'improvements':[dict(criterion_key='motivation',usefulness='useful',missing_detail='A task.',why_needed='Explain choice.',already_supplied=False,expected_outcome='Name a task.',question_id='Q-03-01')]}
    packet['criteria']['motivation']=dict(score=2,evidence_ids=[eid],explanation='A task is missing.',assessment_depends_on_gap=True)
    with patch.object(c.model_client,'apertus',side_effect=[json.dumps(packet),json.dumps({'checks':{'gap:motivation':dict(decision='supported',reason='Task missing.',evidence_ids=[eid])}})]) as model:result=s.finish()
    self.assertEqual(model.call_count,2);self.assertEqual([r['task'] for r in s.requests],['evaluator','verify']);self.assertFalse(s.feedback['learning']['exercise']);self.assertIsNone(s.learning_target);self.assertTrue(result['optional_practice_choices']);self.assertFalse(result['can_revise'])

if __name__=='__main__':unittest.main()
