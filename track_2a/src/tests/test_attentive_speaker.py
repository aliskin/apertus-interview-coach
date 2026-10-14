"""Conversation control: relevance remains a manual judgement; repetition is deterministic."""
import sys,json,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import hybrid as h
import interview_controller as c
class AttentiveSpeakerTests(unittest.TestCase):
 def session(self):
  s=c.Session('de',c.POSTINGS['P-01'],c.make_plan(['Q-03-01','Q-05-01']));s.conversation_policy='fixed';s.start();s.answers=2;return s
 def test_context_has_actual_next_question_and_recent_reactions(self):
  s=self.session();s.speaker_reactions=['Du hast den Schnuppertag erwähnt.'];captured=[]
  def call(messages,schema,validate,*args,**kwargs):
   captured.append(json.loads(messages[-1]['content']));p={'acknowledgement':'Die Arbeit an den Geräten hat dir gefallen.','question':''};validate(p);return p
  with patch.object(s,'call',side_effect=call):h.speak(s,'Mir haben die Geräte gefallen.',s.plan[0],s.plan[1],'advance','')
  self.assertEqual(captured[0]['next_question'],c.question_context(s.plan[1],'de'));self.assertEqual(captured[0]['recent_reactions_do_not_copy'],['Du hast den Schnuppertag erwähnt.'])
 def test_recent_repeat_is_omitted_without_extra_call(self):
  s=self.session();s.speaker_reactions=['Du hast den Schnuppertag erwähnt.']
  with patch.object(c.model_client,'apertus',return_value=json.dumps({'acknowledgement':'Du hast den Schnuppertag erwähnt!','question':''})):
   ack,question,action=h.speak(s,'Ein Schnuppertag.',s.plan[0],s.plan[1],'advance','')
  self.assertEqual(ack,'');self.assertEqual(s.model_calls,1);self.assertEqual(action,'advance')
 def test_empty_reaction_is_valid(self):
  s=self.session()
  with patch.object(c.model_client,'apertus',return_value=json.dumps({'acknowledgement':'','question':''})):
   self.assertEqual(h.speak(s,'Ja.',s.plan[0],s.plan[1],'advance',''),('','','advance'))
 def test_invalid_reaction_falls_back_to_question_without_stock_thanks(self):
  s=self.session()
  with patch.object(c.model_client,'apertus',return_value=json.dumps({'acknowledgement':'Das zeigt Teamfähigkeit.','question':''})):
   self.assertEqual(h.speak(s,'Ja.',s.plan[0],s.plan[1],'advance',''),('','','advance'))
if __name__=='__main__':unittest.main()
