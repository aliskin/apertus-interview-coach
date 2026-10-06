"""Dependency-free browser interface for short interview practice."""
import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import experiment

STATIC = Path(__file__).parent / 'static'
LOCALES = json.loads((STATIC / 'locales.json').read_text(encoding='utf-8'))
SCENARIOS = json.loads((STATIC / 'scenarios.json').read_text(encoding='utf-8'))
OPENING = SCENARIOS['it']['translations']['en']['opening']
LANGUAGES = {'en': 'English', 'de': 'German (Swiss spelling, use ss instead of ß)', 'fr': 'French', 'it': 'Italian'}
PROMPT_DIR = Path(__file__).parent / 'prompts/web'
SHARED_PROMPT = (PROMPT_DIR / 'shared.txt').read_text(encoding='utf-8').strip()
OUTPUT_PROMPT = (PROMPT_DIR / 'output.txt').read_text(encoding='utf-8').strip()
STAGES = ('after_first_answer', 'followup', 'final_recap')
DEFAULT_MAX_ANSWERS = 12
# Leave room for the next answer and model reply without silently truncating history.
MAX_CONTEXT_CHARS = 24000
RECAP_CONTEXT_THRESHOLD = 16000
MAX_MESSAGE_CHARS = 4000
STAGE_PROMPTS = {stage: (PROMPT_DIR / f'{stage}.txt').read_text(encoding='utf-8').strip()
                 for stage in STAGES}


def session_stage(transcript, recap=False, max_answers=DEFAULT_MAX_ANSWERS):
    count = sum(item['role'] == 'user' for item in transcript)
    if not 1 <= count <= max_answers:
        raise ValueError('Candidate answer count is outside the session limit.')
    if recap or count >= max_answers or sum(len(item['content']) for item in transcript) >= RECAP_CONTEXT_THRESHOLD:
        return 'final_recap'
    return 'after_first_answer' if count == 1 else 'followup'


def build_messages(transcript, profile, language, scenario, recap=False, max_answers=DEFAULT_MAX_ANSWERS):
    """Select the task from the explicit action and server runtime safeguards."""
    stage = session_stage(transcript, recap, max_answers)
    count = sum(item['role'] == 'user' for item in transcript)
    context = SCENARIOS[scenario]
    parts = [SHARED_PROMPT,
             experiment.guidance(profile, 'coach', 'interaction').strip(),
             'Scenario: ' + context['context'] + '. ' + context['guidance'],
             'Response language: ' + LANGUAGES[language] + '. Use an informal, respectful tone.',
             f'Session state: {count} candidate answers so far; maximum {max_answers}. '
             + ('The user requested a recap.' if recap else 'The user submitted another answer.')
             + (' A session safeguard requires a recap now.' if stage == 'final_recap' and not recap else ''),
             OUTPUT_PROMPT, STAGE_PROMPTS[stage]]
    return [{'role': 'system', 'content': '\n\n'.join(part for part in parts if part)}, *transcript]


def respond(transcript, provider, model, profile, language='en', scenario='it', recap=False, max_answers=DEFAULT_MAX_ANSWERS):
    count = sum(item['role'] == 'user' for item in transcript)
    stage = session_stage(transcript, recap, max_answers)
    if provider == 'demo':
        if stage == 'final_recap':
            packet = {'reply': LOCALES[language]['demo3'], 'hint': '', 'suggest_recap': False, 'can_continue': False}
        elif count <= 2:
            packet = {'reply': LOCALES[language][f'demo{count}'], 'hint': LOCALES[language][f'demoHint{count}'],
                      'suggest_recap': False, 'can_continue': True}
        elif count <= 4:
            packet = {'reply': LOCALES[language][f'demoFollowup{count}'], 'hint': LOCALES[language][f'demoFollowupHint{count}'],
                      'suggest_recap': count == 4, 'can_continue': True}
        else:
            packet = {'reply': LOCALES[language]['demoWrap'], 'hint': '', 'suggest_recap': True, 'can_continue': False}
        return json.dumps(packet, ensure_ascii=False)
    messages = build_messages(transcript, profile, language, scenario, recap, max_answers)
    return experiment.apertus(messages) if provider == 'apertus' else experiment.ollama(model, messages)


def coaching_fields(output, language, complete):
    """Validate same-call wrap-up guidance without adding repair calls."""
    fallback = LOCALES[language]['genericHint']
    content = output.strip()
    if content.startswith('```') and content.endswith('```'):
        content = content.split('\n', 1)[-1].rsplit('```', 1)[0].strip()
    try:
        packet = json.loads(content)
    except json.JSONDecodeError:
        if content.startswith('{'):
            raise ValueError('Invalid coach response. Please try again.') from None
        packet = {'reply': output}
    if not isinstance(packet, dict) or not isinstance(packet.get('reply'), str) or not packet['reply'].strip() or len(packet['reply']) > MAX_MESSAGE_CHARS:
        raise ValueError('Invalid coach response. Please try again.')
    suggest = packet.get('suggest_recap', False)
    can_continue = packet.get('can_continue', True)
    if type(suggest) is not bool or type(can_continue) is not bool:
        raise ValueError('Invalid coach response. Please try again.')
    if not can_continue:
        suggest = True
    hint = packet.get('hint')
    if not isinstance(hint, str) or not hint.strip() or len(hint) > 600:
        hint = fallback
    return {'reply': packet['reply'].strip(), 'hint': '' if complete or not can_continue else hint.strip(),
            'complete': complete, 'suggest_recap': suggest and not complete, 'can_continue': can_continue and not complete}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Avoid logging candidate answers or request bodies.
        pass

    def send(self, status, payload, content_type='application/json'):
        data = json.dumps(payload).encode() if content_type == 'application/json' else payload
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == '/api/config':
            return self.send(200, {'provider': self.server.provider, 'opening': OPENING, 'locales': LOCALES, 'scenarios': SCENARIOS, 'max_answers': self.server.max_answers})
        files = {'/': ('index.html', 'text/html; charset=utf-8'), '/style.css': ('style.css', 'text/css'), '/app.js': ('app.js', 'text/javascript')}
        if self.path not in files:
            return self.send(404, {'error': 'Not found'})
        name, mime = files[self.path]
        self.send(200, (STATIC / name).read_bytes(), mime)

    def do_POST(self):
        if self.path not in ('/api/answer', '/api/recap'):
            return self.send(404, {'error': 'Not found'})
        # Same-origin requests only; the API never accepts credentials or endpoint URLs.
        if self.headers.get('Origin') not in (None, 'http://' + self.headers.get('Host', '')):
            return self.send(403, {'error': 'Open practice from this server address.'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 200000:
                raise ValueError('Request is too large or empty.')
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError('Invalid request.')
            language = payload.get('language', 'en')
            if not isinstance(language, str) or language not in LANGUAGES:
                raise ValueError('Unsupported language.')
            scenario = payload.get('scenario', 'it')
            if not isinstance(scenario, str) or scenario not in SCENARIOS:
                raise ValueError('Unsupported scenario.')
            transcript = payload['transcript']
            recap = self.path == '/api/recap'
            max_answers = self.server.max_answers
            if not isinstance(transcript, list) or not 2 <= len(transcript) <= 2 * max_answers + 1 or (not recap and len(transcript) % 2 != 0):
                raise ValueError('Start a new practice session.')
            for index, item in enumerate(transcript):
                if not isinstance(item, dict) or item.get('role') != ('assistant' if index % 2 == 0 else 'user'):
                    raise ValueError('Invalid conversation.')
                if not isinstance(item.get('content'), str) or not 0 < len(item['content'].strip()) <= MAX_MESSAGE_CHARS:
                    raise ValueError('Please enter an answer of up to 4,000 characters.')
            if transcript[0]['content'] != SCENARIOS[scenario]['translations'][language]['opening']:
                raise ValueError('Start a new practice session.')
            if sum(len(item['content']) for item in transcript) > MAX_CONTEXT_CHARS:
                raise ValueError('Conversation exceeds the context limit. Start a new practice session.')
            stage = session_stage(transcript, recap, max_answers)
            output = respond(transcript, self.server.provider, self.server.model, self.server.profile, language, scenario, recap, max_answers)
            self.send(200, coaching_fields(output, language, stage == 'final_recap'))
        except (ValueError, KeyError, TypeError) as exc:
            self.send(400, {'error': str(exc)})
        except (RuntimeError, OSError):
            self.send(502, {'error': 'The coach could not connect. Check the model server settings, then try again. Your answer is still here.'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider', choices=['apertus', 'ollama', 'demo'], default=os.getenv('COACH_PROVIDER', 'apertus'))
    parser.add_argument('--model', default=os.getenv('COACH_MODEL', 'llama3:8b'))
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--profile', type=Path)
    parser.add_argument('--max-answers', type=int, default=os.getenv('MAX_ANSWERS') or str(DEFAULT_MAX_ANSWERS))
    args = parser.parse_args()
    if not 2 <= args.max_answers <= 50:
        parser.error('--max-answers must be between 2 and 50.')
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.max_answers = args.max_answers
    server.provider, server.model = args.provider, args.model
    server.profile = experiment.load_profile(args.profile)
    print(f'Interview practice: http://{args.host}:{args.port} ({args.provider})', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
