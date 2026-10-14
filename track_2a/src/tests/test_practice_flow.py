"""Practice persistence, evidence separation and failed-recap recovery."""
import copy
import json
import sys
import tempfile
import threading
import unittest
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import hybrid as h
import interview_controller as c
import web
from review.prepare import recorded_sample
import test_verified_learning as fixtures

class PracticeFlowTests(unittest.TestCase):
    def session(self):
        helper=fixtures.VerifiedLearningTests()
        s=helper.session();s.complete=True
        s.feedback={'criteria':[helper.criterion(s)],'optional_practice_choices':[{'target_id':'optional:motivation','key':'motivation','label':'Motivation','question_id':'Q-03-01'}]}
        return s

    def choose(self,s):
        packet=dict(target_id='optional:motivation',explanation='Freiwillig üben.',exercise='Antworte in genau zwei Sätzen.',reflection='Welche Tätigkeit interessiert dich?',revision_prompt='Versuche es neu.',encouragement='Übe weiter.')
        with patch.object(c.model_client,'apertus',return_value=json.dumps(packet)):
            h.choose_practice(s,'optional:motivation')
        return packet

    def valid_recap(self,s):
        allowed=h.eligible_evidence(s)
        rows={key:dict(score=None,evidence_ids=[],explanation='Nicht beurteilt.',improvement=h.no_improvement()) for key in allowed}
        rows['motivation']=dict(score=3,evidence_ids=[next(iter(allowed['motivation']))],explanation='Interesse genannt.',improvement=h.no_improvement())
        return json.dumps(fixtures.evaluator_packet({'criteria':rows}))

    def test_revisions_receive_exercise_and_most_recent_answer(self):
        s=self.session();packet=self.choose(s);original=s.learning_target['original_answer']
        with patch.object(c.model_client,'apertus',return_value=json.dumps({'reply':'Du nennst eine Tätigkeit.'})) as model:
            s.revise('Ich möchte Bauteile zeichnen.')
            first=json.loads(model.call_args.args[0][1]['content'])
            s.revise('Ich möchte Bauteile zeichnen. Das gefällt mir.')
            second=json.loads(model.call_args.args[0][1]['content'])
        self.assertEqual(first['target']['exercise'],packet['exercise'])
        self.assertEqual(first['previous_answer'],original)
        self.assertEqual(second['previous_answer'],'Ich möchte Bauteile zeichnen.')
        self.assertEqual(s.learning_target['original_answer'],original)
        self.assertEqual(s.learning_target['previous_answer'],second['new_answer'])

    def test_practice_survives_serialization_and_review_import_without_changing_evidence(self):
        s=self.session();before=copy.deepcopy(h.eligible_evidence(s));answers=copy.deepcopy(h.full_answers(s))
        packet=self.choose(s)
        with patch.object(c.model_client,'apertus',return_value=json.dumps({'reply':'Zwei Sätze sind vorhanden.'})):
            s.revise('Ich zeichne gern. Ich möchte es lernen.')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'session.json';path.write_text(json.dumps(asdict(s)))
            restored=c.Session(**json.loads(path.read_text()))
            case=recorded_sample([folder])['cases'][0]
        self.assertEqual(restored.transcript,s.transcript)
        self.assertIn(packet['exercise'],case['generated']['reply'])
        self.assertIn('Zwei Sätze sind vorhanden.',case['generated']['reply'])
        self.assertIn('Ich zeichne gern.',case['input']['answer'])
        self.assertEqual(h.eligible_evidence(s),before)
        self.assertEqual(h.full_answers(s),answers)
        self.assertEqual([t['action'] for t in s.transcript[-3:]],['practice_assignment','practice_revision','revision_feedback'])

    def test_failed_revision_does_not_accept_answer_or_change_target(self):
        s=self.session();self.choose(s);before=copy.deepcopy(s.transcript);target=copy.deepcopy(s.learning_target)
        with patch.object(c.model_client,'apertus',side_effect=RuntimeError('offline')):
            with self.assertRaises(RuntimeError):s.revise('A new answer.')
        self.assertEqual(s.practice_answers,0);self.assertEqual(s.transcript,before)
        self.assertEqual(s.learning_target,target);self.assertEqual(s.model_calls,2)

    def test_failed_recap_keeps_answers_and_retries_without_replaying_interview(self):
        s=self.session();s.complete=False;original_answers=s.answers;before=h.full_answers(s)
        with patch.object(c.model_client,'apertus',return_value='{}'):failed=s.finish()
        self.assertFalse(failed['complete']);self.assertTrue(failed['recap_retryable'])
        self.assertFalse(failed['can_continue']);self.assertTrue(s.roleplay_finished)
        self.assertEqual(h.full_answers(s),before);old_revision=s.state()['revision']
        with patch.object(c.model_client,'apertus',return_value=self.valid_recap(s)),patch.object(s,'analyse_answer') as analysis:
            result=s.answer('',recap=True)
            analysis.assert_not_called()
        self.assertTrue(result['complete']);self.assertEqual(s.answers,original_answers)
        self.assertGreater(s.state()['revision'],old_revision)
        self.assertEqual(s.recap_status,'complete')
        self.assertLess(s.model_calls,5*s.answers)

    def test_budget_exhaustion_never_closes_session_or_makes_more_requests(self):
        s=self.session();s.complete=False;s.model_calls=5*s.answers-1
        with patch.object(c.model_client,'apertus') as model:result=s.finish()
        model.assert_not_called();self.assertFalse(result['complete'])
        self.assertFalse(result['recap_retryable']);self.assertIsNone(s.feedback)
        with self.assertRaises(ValueError):s.answer('Another interview answer')

    def test_transport_failure_is_saved_as_unavailable_not_completed(self):
        s=self.session();s.complete=False
        with patch.object(c.model_client,'apertus',side_effect=RuntimeError('offline')):result=s.finish()
        self.assertFalse(result['complete']);self.assertEqual(s.recap_status,'unavailable')
        self.assertTrue(result['recap_retryable'])

    def test_failed_recap_http_retry_replays_but_explicit_retry_generates_again(self):
        s=self.session();s.complete=False;sid='d'*32
        handler=object.__new__(web.Handler);handler.path='/api/recap'
        handler.server=SimpleNamespace(provider='apertus',sessions={sid:s},session_lock=threading.Lock())
        responses=[];handler.send=lambda status,data:responses.append((status,data))
        payload={'session_id':sid,'revision':s.state()['revision'],'answer':''}
        with tempfile.TemporaryDirectory() as folder,patch.object(c,'ROOT',Path(folder)):
            with patch.object(c.model_client,'apertus',return_value='{}') as model:
                handler.controlled_request(payload,'de','it');calls=model.call_count
                handler.controlled_request(payload,'de','it');self.assertEqual(model.call_count,calls)
            self.assertEqual(responses[0],responses[1])
            restored=c.Session(**json.loads((Path(folder)/'data/sessions'/f'{sid}.json').read_text()))
            handler.server.sessions[sid]=restored
            payload['revision']=restored.state()['revision']
            with patch.object(c.model_client,'apertus',return_value=self.valid_recap(restored)):
                handler.controlled_request(payload,'de','it')
        self.assertTrue(responses[-1][1]['complete'])
        self.assertNotEqual(responses[0][1]['speech']['turn_id'],responses[-1][1]['speech']['turn_id'])

    def test_retry_can_use_last_remaining_call_without_exceeding_budget(self):
        s=self.session();s.complete=False;s.model_calls=5*s.answers-2
        with patch.object(c.model_client,'apertus',return_value=self.valid_recap(s)) as model:
            result=s.finish()
        self.assertTrue(result['complete']);self.assertEqual(model.call_count,1)
        self.assertEqual(s.model_calls,5*s.answers-1)

    def test_valid_unassessed_packet_is_not_a_failed_recap(self):
        s=self.session();s.complete=False
        rows={key:dict(score=None,evidence_ids=[],explanation='Nicht ausreichend beurteilt.',improvement=h.no_improvement()) for key in h.eligible_evidence(s)}
        with patch.object(c.model_client,'apertus',return_value=json.dumps(fixtures.evaluator_packet({'criteria':rows}))):
            result=s.finish()
        self.assertTrue(result['complete']);self.assertEqual(s.recap_status,'complete')
        self.assertTrue(all(row['score'] is None for row in s.feedback['criteria']))

    def test_final_interview_answer_is_saved_when_recap_fails(self):
        s=c.Session('de',c.POSTINGS['P-01'],c.make_plan(['Q-03-01']));s.start()
        answer='Ich mag praktische Arbeit.'
        analysis=dict(observations=[dict(statement=answer,quote=answer)],answer_status='answered',missing_information='',support_quote='',company_question_quote='',resolved_record_ids=[],conflict_record_ids=[])
        speaker=dict(acknowledgement='Danke für deine Antwort.',question='')
        with patch.object(c.model_client,'apertus',side_effect=[json.dumps(analysis),json.dumps(speaker),'{}']):
            failed=s.answer(answer)
        self.assertFalse(failed['complete']);self.assertTrue(failed['recap_retryable'])
        self.assertEqual(s.answers,1);self.assertEqual(h.full_answers(s)[0]['answer'],answer)
        with patch.object(c.model_client,'apertus',return_value=self.valid_recap(s)) as model:
            result=s.answer('',recap=True)
        self.assertTrue(result['complete']);self.assertEqual(model.call_count,1)
        self.assertEqual(s.answers,1);self.assertEqual(s.model_calls,4)
