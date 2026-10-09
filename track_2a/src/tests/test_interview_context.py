from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import interview_context as context
import web

class InterviewContextTests(unittest.TestCase):
    def test_controller_can_update_context_without_changing_turn_count(self):
        transcript = [{'role': 'assistant', 'content': 'Question'}, {'role': 'user', 'content': 'Answer'}]
        first = web.build_messages(transcript, None, 'en', 'it', question_context=context.question_context('greeting'))
        second = web.build_messages(transcript, None, 'en', 'it', question_context=context.question_context('knowledge'))
        self.assertIn('"question_subtype": "small_talk"', first[0]['content'])
        self.assertIn('"question_subtype": "occupation_company_knowledge"', second[0]['content'])
        with self.assertRaises(ValueError): context.context_prompt({'interview_stage': 'introduction', 'question_subtype': 'made_up'})


if __name__ == "__main__": unittest.main()
