"""Online opening overrides stay consistent in rendered questions and model context."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import interview_controller as c
class SmalltalkTests(unittest.TestCase):
 def test_default_opening_is_neutral_in_every_language(self):
  for lang in ('de','en','fr','it'):
   with self.subTest(language=lang):
    s=c.Session(lang,c.POSTINGS['P-01'],c.make_plan(['Q-01-01','Q-02-01']))
    expected=c.SMALLTALK['questions']['today'][lang]
    self.assertTrue(s.start().endswith(expected))
    self.assertEqual(c.question_context(s.plan[0],lang)['text'],expected)
 def test_all_three_variants_have_four_translations(self):
  self.assertEqual(set(c.SMALLTALK['questions']),{'today','day','feeling'})
  for key,texts in c.SMALLTALK['questions'].items():
   self.assertEqual(set(texts),{'de','en','fr','it'})
   q=copy.deepcopy(c.QUESTIONS['Q-01-01']);q['smalltalk_key']=key
   for lang,text in texts.items():
    self.assertEqual(c.question_text(q,lang),text);self.assertTrue(text.endswith('?'))
 def test_original_question_bank_is_preserved(self):
  self.assertEqual(c.QUESTIONS['Q-01-01']['text']['de'],'Hast du den Weg zu uns gut gefunden?')
if __name__=='__main__':unittest.main()
