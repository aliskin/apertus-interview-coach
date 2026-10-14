"""Local, model-free guideline labeling for interview-coach outputs."""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))
import argparse
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data/manual_review'
STATIC = Path(__file__).parent / 'static'
STATUSES = {'meets', 'violates', 'not_applicable', 'not_sure'}
STAGES = {
    'introduction': 'Introduction: greeting, small talk, self-presentation',
    'motivation': 'Motivation: job/company interest, knowledge, future goals',
    'strengths_weaknesses': 'Strengths & weaknesses: self-reflection, school, trial days, teamwork',
    'situational': 'Situational: hypothetical, job-specific and difficult questions',
    'candidate_questions': 'Candidate questions: coach answers as the company',
    'feedback': 'Feedback: coach only, 11 criteria and next steps',
    'whole_interview': 'Whole interview: all stages plus final feedback',
}
PHASE_STAGES = {'greeting': 'introduction', 'self_presentation': 'introduction',
                'motivation': 'motivation', 'knowledge': 'motivation', 'future': 'motivation',
                'strengths_development': 'strengths_weaknesses', 'situational': 'situational',
                'candidate_questions': 'candidate_questions'}


class Conflict(ValueError):
    pass


class ReviewStore:
    def __init__(self, sample_path, translations_path, guidelines_path, labels_path):
        self.translations_path = translations_path.resolve()
        self.sample = json.loads(sample_path.read_text(encoding='utf-8'))
        self.sample_hash = hashlib.sha256(sample_path.read_bytes()).hexdigest()
        self.translations = json.loads(translations_path.read_text(encoding='utf-8'))
        if self.translations.get('sample_sha256') != self.sample_hash:
            raise ValueError('Translations belong to a different sample; preserve the originals and prepare matching translations.')
        self.groups = json.loads(guidelines_path.read_text(encoding='utf-8'))['groups']
        self.guidelines_hash = hashlib.sha256(guidelines_path.read_bytes()).hexdigest()
        self.rule_ids = {rule['id'] for group in self.groups for rule in group['rules']}
        self.cases = {case['case_id']: case for case in self.sample['cases']}
        if len(self.cases) != len(self.sample['cases']) or not self.cases:
            raise ValueError('Sample IDs must be unique and nonempty.')
        if set(self.translations['cases']) != set(self.cases):
            raise ValueError('Translations must cover exactly the sampled cases.')
        for translation in self.translations['cases'].values():
            if not all(isinstance(translation.get(key), str) for key in ('question', 'answer', 'reply', 'hint', 'occupation')):
                raise ValueError('Incomplete English translation.')
        self.labels_path = labels_path
        self.lock = threading.Lock()
        if labels_path.exists():
            self.read_labels()  # Reject reuse for a different sample or guideline version.

    def empty_labels(self):
        return {'schema_version': 1, 'kind': 'manual_feedback_labels',
                'sample_sha256': self.sample_hash, 'guidelines_sha256': self.guidelines_hash,
                'reviews': {}}

    def read_labels(self):
        if not self.labels_path.exists():
            return self.empty_labels()
        labels = json.loads(self.labels_path.read_text(encoding='utf-8'))
        if labels.get('sample_sha256') != self.sample_hash or labels.get('guidelines_sha256') != self.guidelines_hash:
            raise ValueError('Existing labels belong to a different sample or guideline version; choose a new --labels file.')
        if labels.get('kind') != 'manual_feedback_labels' or not isinstance(labels.get('reviews'), dict):
            raise ValueError('Invalid labels file.')
        return labels

    def snapshot(self):
        with self.lock:
            labels = self.read_labels()
        # No judge scores, annotations, source quality, prompts, or credentials.
        return {'cases': [{**case, 'suggested_stage': PHASE_STAGES.get(case['input']['phase_key']),
                          'translation': self.translations['cases'][case['case_id']]}
                          for case in self.sample['cases']],
                'groups': [{'title': group['title_en'], 'rules': [{'id': r['id'], 'text': r['en']} for r in group['rules']]}
                           for group in self.groups],
                'stages': STAGES, 'reviews': labels['reviews'], 'sample': {key: self.sample.get(key) for key in
                    ('source_file', 'seed', 'sampling', 'eligible_outputs', 'excluded_generation_failures', 'coach_model')},
                'translation_notice': self.translations['provenance'],
                'labels_file': str(self.labels_path)}

    def save(self, payload):
        if not isinstance(payload, dict) or set(payload) != {'case_id', 'revision', 'rules', 'notes', 'translation_issue', 'stage', 'stage_reason', 'review_status'}:
            raise ValueError('Invalid review fields.')
        case_id = payload['case_id']
        if not isinstance(case_id, str) or case_id not in self.cases:
            raise ValueError('Unknown sampled case.')
        if type(payload['revision']) is not int or payload['revision'] < 0:
            raise ValueError('Invalid review revision.')
        if payload['stage'] not in STAGES or payload['review_status'] not in ('draft', 'validated'):
            raise ValueError('Choose an interview stage and review status.')
        if not isinstance(payload['stage_reason'], str) or not payload['stage_reason'].strip() or len(payload['stage_reason']) > 4000:
            raise ValueError('Explain the stage classification before saving.')
        if not isinstance(payload['notes'], str) or len(payload['notes']) > 10000 or type(payload['translation_issue']) is not bool:
            raise ValueError('Invalid notes or translation flag.')
        rules = payload['rules']
        if not isinstance(rules, dict) or set(rules) != self.rule_ids:
            raise ValueError('Label every guideline, using Not sure or Not applicable where needed.')
        original = self.cases[case_id]['generated']
        for rule_id, label in rules.items():
            if not isinstance(label, dict) or set(label) != {'status', 'evidence', 'note'}:
                raise ValueError(f'{rule_id}: invalid label fields.')
            if not isinstance(label['status'], str) or label['status'] not in STATUSES:
                raise ValueError(f'{rule_id}: choose Meets, Violates, Not applicable, or Not sure.')
            if not all(isinstance(label[key], str) and len(label[key]) <= 4000 for key in ('evidence', 'note')):
                raise ValueError(f'{rule_id}: invalid evidence or note.')
            if label['evidence'] and not any(label['evidence'] in original.get(field, '') for field in ('reply', 'hint')):
                raise ValueError(f'{rule_id}: evidence must be an exact original coach quote; use the note for an absent element.')
        with self.lock:
            labels = self.read_labels()
            previous = labels['reviews'].get(case_id, {})
            if previous.get('revision', 0) != payload['revision']:
                raise Conflict('This example was saved in another tab. Reload before editing it.')
            review = {**payload, 'revision': payload['revision'] + 1,
                      'saved_at': datetime.now(timezone.utc).isoformat()}
            labels['reviews'][case_id] = review
            self.labels_path.parent.mkdir(parents=True, exist_ok=True)
            # Atomic replacement protects the previous complete file from interrupted writes.
            descriptor, name = tempfile.mkstemp(prefix='.labels-', suffix='.json', dir=self.labels_path.parent)
            try:
                with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
                    json.dump(labels, handle, ensure_ascii=False, indent=2)
                    handle.write('\n')
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(name, self.labels_path)
            finally:
                if os.path.exists(name):
                    os.unlink(name)
        return review


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send(self, status, body, mime='application/json; charset=utf-8', download=False):
        data = json.dumps(body, ensure_ascii=False).encode('utf-8') if mime.startswith('application/json') else body
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        if download:
            self.send_header('Content-Disposition', 'attachment; filename="manual-feedback-labels.json"')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == '/api/review':
            return self.send(200, self.server.store.snapshot())
        if self.path == '/api/export':
            with self.server.store.lock:
                return self.send(200, self.server.store.read_labels(), download=True)
        files = {'/': ('manual-review.html', 'text/html; charset=utf-8'),
                 '/manual-review.css': ('manual-review.css', 'text/css; charset=utf-8'),
                 '/manual-review.js': ('manual-review.js', 'text/javascript; charset=utf-8')}
        if self.path not in files:
            return self.send(404, {'error': 'Not found'})
        name, mime = files[self.path]
        self.send(200, (STATIC / name).read_bytes(), mime)

    def do_POST(self):
        if self.path != '/api/review':
            return self.send(404, {'error': 'Not found'})
        if self.headers.get('Origin') not in (None, 'http://' + self.headers.get('Host', '')):
            return self.send(403, {'error': 'Save from the local review page.'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 200000:
                raise ValueError('Empty or oversized review.')
            payload = json.loads(self.rfile.read(length))
            review = self.server.store.save(payload)
            self.send(200, {'review': review})
        except Conflict as exc:
            self.send(409, {'error': str(exc)})
        except (ValueError, TypeError) as exc:
            self.send(400, {'error': str(exc)})
        except OSError:
            self.send(500, {'error': 'Could not save to disk. Your changes are still on the page; try saving again.'})

