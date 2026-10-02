"""Small interview experiment: Python standard library only."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler

ROOT = Path(__file__).resolve().parents[1]


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def post(base, route, payload, key=None):
    parsed = urlparse(base)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise ValueError('Use an http(s) API base URL.')
    if key and parsed.scheme != 'https' and parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('Use HTTPS for a remote API with an API key.')
    headers = {'Content-Type': 'application/json'}
    if key:
        headers['Authorization'] = f'Bearer {key}'
    req = Request(base.rstrip('/') + route, json.dumps(payload).encode(), headers)
    try:
        with build_opener(NoRedirect).open(req, timeout=300) as response:
            return json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f'API returned HTTP {exc.code}; check endpoint, model, and credentials.') from None
    except (URLError, TimeoutError) as exc:
        raise RuntimeError('Cannot reach API or request timed out; check the server and base URL.') from None


def ollama(model, messages, schema=None):
    body = {'model': model, 'messages': messages, 'stream': False,
            'think': False, 'options': {'temperature': 0, 'seed': 42, 'num_predict': 2048}}
    if schema:
        body['format'] = schema
    response = post(os.getenv('OLLAMA_BASE_URL', 'http://127.0.0.1:11434'), '/api/chat', body)
    if response.get('done_reason') == 'length':
        raise ValueError('Ollama response was truncated; increase num_predict.')
    content = response['message']['content']
    if not content.strip():
        raise ValueError('Ollama returned empty content.')
    return content


def messages_for(case, context, prompt):
    return [{'role': 'system', 'content': prompt + '\nStudent context: ' + context
             + '\nTask: ' + case['task']}, *case['messages']]


def generate(args):
    suite = json.loads((ROOT / 'data/first_interview_en.json').read_text())
    prompt = (ROOT / 'src/prompts/coach.txt').read_text()
    key = os.getenv('LLM_API_KEY')
    model = os.getenv('LLM_NAME')
    base = os.getenv('LLM_BASE_URL')
    if args.provider == 'apertus' and not all((key, model, base)):
        raise ValueError('Set LLM_API_KEY, LLM_NAME, and LLM_BASE_URL (including the provider API prefix, e.g. /v1).')
    records = []
    for case in suite['cases']:
        messages = messages_for(case, suite['context'], prompt)
        if args.provider == 'sample':
            output = case['sample_output']
        elif args.provider == 'ollama':
            output = ollama(args.model, messages)
        else:
            response = post(base, '/chat/completions', {
                'model': model, 'messages': messages, 'temperature': 0,
                'max_tokens': 600}, key)
            choice = response['choices'][0]
            if choice.get('finish_reason') == 'length':
                raise ValueError('Apertus response was truncated; increase max_tokens.')
            output = choice['message']['content']
        if not isinstance(output, str) or not output.strip():
            raise ValueError('Model returned an empty or invalid response.')
        records.append({'id': case['id'], 'stage': case['stage'],
                        'task': case['task'], 'messages': messages, 'output': output})
        print(f"Generated {case['id']}", flush=True)
    return {'version': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
            'provider': args.provider,
            'model': model if args.provider == 'apertus' else args.model if args.provider == 'ollama' else 'handwritten-example',
            'temperature': 0, 'context': suite['context'], 'coach_prompt': prompt,
            'cases': records}


CRITERIA = {
    'followup': {
        'adaptation': 'Responds to the actual answer: elicits an example if vague, explores it if specific.',
        'grounding': 'Does not invent student experience or assume professional knowledge.',
        'support': 'Approachable and respectful for a 16-year-old; no personality or employability judgments.',
        'flow': 'One clear interview question, no premature coaching feedback or multiple requests.'},
    'feedback': {
        'grounding': 'Names one strength supported by specific evidence from the student answers.',
        'actionability': 'Gives one concrete, manageable improvement relevant to this answer.',
        'support': 'Constructive, age-appropriate; no personality or employability judgments.',
        'ownership': 'Invites a retry in the student’s own words without inventing achievements or demanding a memorised script.'}}


def judge_schema(criteria):
    item = {'type': 'object', 'properties': {
        'score': {'type': 'integer', 'minimum': 1, 'maximum': 5},
        'reason': {'type': 'string', 'minLength': 1},
        'evidence': {'type': 'string', 'minLength': 1}},
        'required': ['score', 'reason', 'evidence'], 'additionalProperties': False}
    return {'type': 'object', 'properties': {key: item for key in criteria},
            'required': list(criteria), 'additionalProperties': False}


def score_warnings(scores, criteria):
    warnings = []
    if not isinstance(scores, dict):
        return ['Judge response must be an object.']
    if set(scores) != set(criteria):
        warnings.append('Judge returned missing or unexpected criteria.')
    for name in criteria:
        item = scores.get(name)
        if not isinstance(item, dict):
            warnings.append(f'{name}: missing or invalid criterion object.')
            continue
        if set(item) != {'score', 'reason', 'evidence'}:
            warnings.append(f'{name}: missing or unexpected score fields.')
        if type(item.get('score')) is not int or not 1 <= item['score'] <= 5:
            warnings.append(f'{name}.score: expected an integer from 1 to 5.')
        for field in ('reason', 'evidence'):
            if not isinstance(item.get(field), str) or not item[field].strip():
                warnings.append(f'{name}.{field}: expected non-empty text.')
    return warnings


def validate_scores(scores, criteria):
    warnings = score_warnings(scores, criteria)
    if warnings:
        raise ValueError(' '.join(warnings))


def save_checkpoint(path, report):
    # Replace atomically so an interrupted write leaves the previous JSON intact.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix=path.name + '.', suffix='.tmp', delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(report, handle, indent=2, ensure_ascii=False)
            handle.write('\n')
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def evaluate(args):
    raw = args.input.read_bytes()
    run = json.loads(raw)
    prompt = (ROOT / 'src/prompts/judge.txt').read_text()
    if not run['cases']:
        raise ValueError('Input contains no cases.')
    results = []
    report = {'version': 2, 'created_at': datetime.now(timezone.utc).isoformat(),
              'input_sha256': hashlib.sha256(raw).hexdigest(), 'judge_model': args.model,
              'judge_prompt': prompt, 'rubric': CRITERIA, 'temperature': 0, 'seed': 42,
              'source_provider': run['provider'], 'source_model': run['model'],
              'status': 'in_progress', 'expected_cases': len(run['cases']),
              'results': results, 'mean_by_stage': {}, 'valid_cases_by_stage': {}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Claim a new filename before making any model requests.
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
        handle.write('\n')
    for case in run['cases']:
        criteria = CRITERIA[case['stage']]
        schema = judge_schema(criteria)
        # Exclude model identity and illustrative answers to reduce preference bias.
        payload = {'context': run['context'], 'task': case['task'],
                   'conversation': [m for m in case['messages'] if m['role'] != 'system'],
                   'candidate_response': case['output'], 'criteria': criteria}
        messages = [{'role': 'system', 'content': prompt + '\nJSON schema: ' + json.dumps(schema)},
                    {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}]
        record = {'id': case['id'], 'stage': case['stage'], 'scores': None,
                  'raw_response': None, 'mean': None, 'status': 'warning', 'warnings': []}
        try:
            record['raw_response'] = ollama(args.model, messages, schema)
            record['scores'] = json.loads(record['raw_response'])
            record['warnings'] = score_warnings(record['scores'], criteria)
        except (ValueError, RuntimeError, KeyError, OSError, TypeError) as exc:
            record['warnings'].append(str(exc))
        if not record['warnings']:
            record['status'] = 'ok'
            record['mean'] = sum(x['score'] for x in record['scores'].values()) / len(criteria)
        results.append(record)
        for stage in {r['stage'] for r in results}:
            valid = [r['mean'] for r in results if r['stage'] == stage and r['status'] == 'ok']
            report['valid_cases_by_stage'][stage] = len(valid)
            report['mean_by_stage'][stage] = sum(valid) / len(valid) if valid else None
        save_checkpoint(args.output, report)
        if record['warnings']:
            print(f"Warning: {case['id']}: {' '.join(record['warnings'])} "
                  'Response saved; excluded from averages.', file=sys.stderr, flush=True)
        else:
            print(f"Judged {case['id']}: {record['mean']:.2f}/5", flush=True)
    report['status'] = 'completed_with_warnings' if any(r['warnings'] for r in results) else 'completed'
    save_checkpoint(args.output, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    gen = sub.add_parser('generate')
    gen.add_argument('--provider', choices=['apertus', 'sample', 'ollama'], default='apertus')
    gen.add_argument('--model', default='llama3:8b', help='Only used for an Ollama coach smoke test.')
    judge = sub.add_parser('evaluate')
    judge.add_argument('--input', type=Path, required=True)
    judge.add_argument('--model', default=os.getenv('JUDGE_MODEL', 'qwen3.5:9b'))
    for command in (gen, judge):
        command.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError('Output already exists; choose a new filename to preserve previous runs.')
        if args.command == 'evaluate':
            evaluate(args)
        else:
            result = generate(args)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open('x') as handle:
                json.dump(result, handle, indent=2, ensure_ascii=False)
                handle.write('\n')
        print(f'Saved {args.output}')
    except (ValueError, RuntimeError, KeyError, OSError, TypeError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
