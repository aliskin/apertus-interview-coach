"""Text-only adapter contract for future speech input/output; no audio dependencies."""
import re

LANGUAGES = {'en': 'en-GB', 'de': 'de-CH', 'fr': 'fr-CH', 'it': 'it-CH'}


def speech_output(text, language, session_id, revision, kind):
    """Bound playback chunks without extra model calls or modifying visible text."""
    turn_id = f'{session_id}:{revision}:{kind}'
    chunks = []
    for sentence in re.split(r'(?<=[.!?])\s+|\n+', text.strip()):
        while len(sentence) > 240:
            boundary = sentence.rfind(' ', 0, 241)
            if boundary < 1:
                boundary = 240
            chunks.append(sentence[:boundary])
            sentence = sentence[boundary:].lstrip()
        if sentence:
            chunks.append(sentence)
    return {'version': 1, 'session_id': session_id, 'turn_id': turn_id,
            'language': LANGUAGES[language], 'kind': kind,
            'segments': [{'id': f'{turn_id}:{i}', 'text': chunk}
                         for i, chunk in enumerate(chunks)],
            'streaming': False}
