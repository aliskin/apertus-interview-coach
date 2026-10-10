import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import voice


class VoiceTests(unittest.TestCase):
    def test_ordered_unicode_chunks_preserve_spoken_content(self):
        text = 'Bonjour !\n' + ('Très bien expliqué ' * 40) + '. À bientôt.'
        output = voice.speech_output(text, 'fr', 'session', 1, 'interview')
        self.assertEqual(output['language'], 'fr-CH')
        self.assertFalse(output['streaming'])
        self.assertEqual(' '.join(s['text'] for s in output['segments']).split(), text.split())
        self.assertTrue(all(0 < len(s['text']) <= 240 for s in output['segments']))
        self.assertEqual(len({s['id'] for s in output['segments']}), len(output['segments']))

    def test_recap_without_new_answer_has_distinct_playback_identity(self):
        question = voice.speech_output('Why?', 'en', 'session', 2, 'interview')
        recap = voice.speech_output('Keep practising.', 'en', 'session', 2, 'feedback')
        self.assertNotEqual(question['turn_id'], recap['turn_id'])
        self.assertNotEqual(question['segments'][0]['id'], recap['segments'][0]['id'])

    def test_long_unbroken_text_is_bounded_and_not_lost(self):
        text = 'ü' * 501
        output = voice.speech_output(text, 'de', 'session', 0, 'opening')
        self.assertEqual(''.join(s['text'] for s in output['segments']), text)
        self.assertTrue(all(len(s['text']) <= 240 for s in output['segments']))
