import copy,json,sys,tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import interview_controller as c
import hybrid as h
import web

class PersistenceAccountingTests(unittest.TestCase):
 def fixture(self):
  s=c.Session('de',c.POSTINGS['P-01'],c.make_plan(['Q-03-01','Q-05-01']));s.start();identifier='a'*32
  handler=object.__new__(web.Handler);handler.path='/api/answer';handler.server=SimpleNamespace(sessions={identifier:s},session_lock=threading.Lock(),provider='apertus');handler.send=lambda *args:None
  return s,identifier,handler
 def spend(self,s,*args,**kwargs):
  s.record_answer('A new answer.');s.model_calls+=2;s.requests.extend([dict(task='analysis'),dict(task='speaker')]);s.index+=1
  return dict(reply='Next question',complete=False,state=s.state())
 def test_repeated_disk_failure_retains_costs_without_accepting_dialogue(self):
  original,sid,handler=self.fixture();before=copy.deepcopy(original.transcript)
  with patch.object(c.Session,'answer',lambda session,*args,**kwargs:self.spend(session,*args,**kwargs)),patch.object(handler,'persist_session',side_effect=OSError('disk full')):
   for _ in range(2):
    with self.assertRaises(OSError):handler.controlled_request(dict(session_id=sid,revision=0,answer='Test'),'de','it')
  self.assertEqual(original.model_calls,4);self.assertEqual(len(original.requests),4);self.assertEqual(original.transcript,before);self.assertEqual(original.answers,0);self.assertEqual(original.index,0)
 def test_failed_full_write_can_persist_rollback_accounting_and_survive_restart(self):
  original,sid,handler=self.fixture()
  with tempfile.TemporaryDirectory() as folder,patch.object(c,'ROOT',Path(folder)):
   real=handler.persist_session;attempts=[]
   def persist(identifier,session):
    attempts.append(session.answers)
    if len(attempts)==1:raise OSError('temporary save failure')
    real(identifier,session)
   with patch.object(c.Session,'answer',lambda session,*args,**kwargs:self.spend(session,*args,**kwargs)),patch.object(handler,'persist_session',side_effect=persist),self.assertRaises(OSError):handler.controlled_request(dict(session_id=sid,revision=0,answer='Test'),'de','it')
   restored=c.Session(**json.loads((Path(folder)/'data/sessions'/f'{sid}.json').read_text()))
  self.assertEqual(attempts,[1,0]);self.assertEqual(restored.model_calls,2);self.assertEqual(restored.answers,0)
 def test_success_commits_dialogue_and_accounting_once(self):
  original,sid,handler=self.fixture()
  with patch.object(c.Session,'answer',lambda session,*args,**kwargs:self.spend(session,*args,**kwargs)),patch.object(handler,'persist_session') as save:handler.controlled_request(dict(session_id=sid,revision=0,answer='Test'),'de','it')
  committed=handler.server.sessions[sid];self.assertEqual(committed.answers,1);self.assertEqual(committed.model_calls,2);self.assertEqual(original.model_calls,0);save.assert_called_once()
 def test_practice_save_failure_also_rolls_back_revision_and_keeps_cost(self):
  original,sid,handler=self.fixture();original.complete=True;handler.path='/api/revise'
  def revise(s,*args):
   s.practice_answers+=1;s.model_calls+=1;s.requests.append(dict(task='revision'))
   return dict(reply='Revision feedback',state=s.state())
  with patch.object(c.Session,'revise',revise),patch.object(handler,'persist_session',side_effect=OSError('disk full')),self.assertRaises(OSError):handler.controlled_request(dict(session_id=sid,revision=0,answer='Test'),'de','it')
  self.assertEqual(original.model_calls,1);self.assertEqual(original.practice_answers,0);self.assertEqual(getattr(original,'practice_events',0),0)
