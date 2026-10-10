"""Dependency-free browser interface for short interview practice."""
import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import model_client as experiment
import interview_context
import interview_controller
import copy
import threading
import uuid
import voice
from dataclasses import asdict

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
COACH_SCHEMA = {
    'type': 'object',
    'properties': {
        'reply': {'type': 'string', 'minLength': 1, 'maxLength': MAX_MESSAGE_CHARS},
        'hint': {'type': 'string', 'maxLength': 600},
        'suggest_recap': {'type': 'boolean'},
        'can_continue': {'type': 'boolean'},
    },
    'required': ['reply', 'hint', 'suggest_recap', 'can_continue'],
    'additionalProperties': False,
}
STAGE_PROMPTS = {stage: (PROMPT_DIR / f'{stage}.txt').read_text(encoding='utf-8').strip()
                 for stage in STAGES}


def session_stage(transcript, recap=False, max_answers=DEFAULT_MAX_ANSWERS):
    count = sum(item['role'] == 'user' for item in transcript)
    if not 1 <= count <= max_answers:
        raise ValueError('Candidate answer count is outside the session limit.')
    if recap or count >= max_answers or sum(len(item['content']) for item in transcript) >= RECAP_CONTEXT_THRESHOLD:
        return 'final_recap'
    return 'after_first_answer' if count == 1 else 'followup'


def build_messages(transcript, profile, language, scenario, recap=False, max_answers=DEFAULT_MAX_ANSWERS, question_context=None):
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
             interview_context.context_prompt({'interview_stage': 'feedback', 'question_subtype': 'session_recap'}
                                              if stage == 'final_recap' else question_context),
             OUTPUT_PROMPT, STAGE_PROMPTS[stage]]
    return [{'role': 'system', 'content': '\n\n'.join(part for part in parts if part)}, *transcript]


def respond(transcript, provider, model, profile, language='en', scenario='it', recap=False, max_answers=DEFAULT_MAX_ANSWERS, question_context=None):
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
    messages = build_messages(transcript, profile, language, scenario, recap, max_answers, question_context)
    return (experiment.apertus(messages, COACH_SCHEMA) if provider == 'apertus'
            else experiment.ollama(model, messages, COACH_SCHEMA))


def coaching_fields(output, language, complete, strict=False):
    """Validate same-call wrap-up guidance without adding repair calls."""
    fallback = LOCALES[language]['genericHint']
    content = output.strip()
    if not strict and content.startswith('```') and content.endswith('```'):
        content = content.split('\n', 1)[-1].rsplit('```', 1)[0].strip()
    try:
        packet = json.loads(content)
    except json.JSONDecodeError:
        if strict or content.startswith('{'):
            raise ValueError('Invalid coach response. Please try again.') from None
        packet = {'reply': output}
    if not isinstance(packet, dict) or not isinstance(packet.get('reply'), str) or not packet['reply'].strip() or len(packet['reply']) > MAX_MESSAGE_CHARS:
        raise ValueError('Invalid coach response. Please try again.')
    if strict and (set(packet) != set(COACH_SCHEMA['required'])
                   or not isinstance(packet.get('hint'), str) or len(packet['hint']) > 600):
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
        if self.path not in ('/api/answer', '/api/recap', '/api/session/start'):
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
            if self.path == '/api/session/start' or payload.get('session_id'):
                return self.controlled_request(payload, language, scenario)
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
            self.send(200, coaching_fields(output, language, stage == 'final_recap', strict=True))
        except (ValueError, KeyError, TypeError) as exc:
            self.send(400, {'error': str(exc)})
        except (RuntimeError, OSError):
            self.send(502, {'error': 'The coach could not connect. Check the model server settings, then try again. Your answer is still here.'})


    def controlled_request(self, payload, language, scenario):
        # Server-owned state: clients cannot replace transcripts, plans or stage metadata.
        with self.server.session_lock:
            if self.path == '/api/session/start':
                posting_id = {'it':'P-11','retail':'P-06','hospitality':'P-13','technical':'P-01','first-job':'P-03'}[scenario]
                ids=['Q-01-01','Q-02-01','Q-03-01','Q-03-04','Q-04-04','Q-05-01','Q-05-03','Q-06-01','Q-07-01','Q-SIT-02','Q-08-02','Q-09-01','Q-10-01']
                session=interview_controller.Session(language,interview_controller.POSTINGS[posting_id],interview_controller.make_plan(ids))
                session.provider=self.server.provider;session.model=self.server.model
                opening=session.start();identifier=uuid.uuid4().hex
                self.server.sessions[identifier]=session
                self.persist_session(identifier,session)
                return self.send(200,{'session_id':identifier,'opening':opening,'state':session.state(),'max_answers':len(session.plan)*2,
                                     'speech':voice.speech_output(opening,language,identifier,0,'opening')})
            identifier=payload['session_id']
            if not isinstance(identifier,str) or len(identifier)!=32:raise ValueError('Invalid session.')
            original=self.server.sessions.get(identifier)
            if original is None:raise ValueError('Session not found. Start a new session.')
            if original.language!=language:raise ValueError('Session language cannot change.')
            if payload.get('revision')!=original.answers:raise ValueError('Session changed. Reload before submitting again.')
            if original.complete:raise ValueError('Session is complete. Start a new session.')
            session=copy.deepcopy(original)
            if self.server.provider=='demo':
                text=payload.get('answer','')
                if not isinstance(text,str) or len(text)>4000:raise ValueError('Invalid answer.')
                if not text.strip() and self.path!='/api/recap':raise ValueError('An answer is required.')
                if not text.strip() and not session.answers:raise ValueError('Answer at least one question before recap.')
                if text.strip():session.transcript.append({'role':'user','content':text.strip()});session.answers+=1
                done=self.path=='/api/recap' or session.index+1==len(session.plan)
                if done:session.complete=True;session.current_stage='feedback';session.question_subtype='session_recap';reply=LOCALES[language]['demo3']
                else:
                    session.index+=1;session.main_question_count+=1;session.set_question(session.plan[session.index]);reply=interview_controller.question_text(session.plan[session.index],language)
                session.transcript.append({'role':'assistant','content':reply})
                result={'reply':reply,'hint':'','complete':done,'can_continue':not done,'suggest_recap':False,'state':session.state()}
            else:
                try:
                    result=session.answer(payload.get('answer',''),recap=self.path=='/api/recap')
                except (ValueError,KeyError,TypeError,RuntimeError,OSError):
                    # Roll back dialogue, but retain spent requests for accurate retry accounting.
                    original.model_calls=session.model_calls;original.requests=session.requests
                    original.validation_warnings=session.validation_warnings
                    self.persist_session(identifier,original)
                    raise
            result['speech']=voice.speech_output(result['reply'],language,identifier,session.answers,
                                                'feedback' if session.complete else 'interview')
            self.persist_session(identifier,session);self.server.sessions[identifier]=session
            return self.send(200,result)

    def persist_session(self,identifier,session):
        folder=interview_controller.ROOT/'data/sessions';folder.mkdir(parents=True,exist_ok=True)
        temporary=folder/(identifier+'.tmp');temporary.write_text(json.dumps(asdict(session),ensure_ascii=False));temporary.replace(folder/(identifier+'.json'))


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
    server.sessions = {}
    folder=interview_controller.ROOT/'data/sessions'
    if folder.exists():
        for saved in folder.glob('*.json'):
            try:server.sessions[saved.stem]=interview_controller.Session(**json.loads(saved.read_text()))
            except (ValueError,TypeError):pass
    server.session_lock = threading.Lock()
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
