"""Shared model requests for the interview coach; Python standard library only."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

from prompt_profile import load_profile, guidance
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


def ollama(model, messages, schema=None, max_tokens=2048, num_ctx=None):
    body = {'model': model, 'messages': messages, 'stream': False,
            'think': False, 'options': {'temperature': 0, 'seed': 42, 'num_predict': max_tokens}}
    if num_ctx is not None:
        body['options']['num_ctx'] = num_ctx
    if schema:
        body['format'] = schema
    response = post(os.getenv('OLLAMA_BASE_URL', 'http://127.0.0.1:11434'), '/api/chat', body)
    if response.get('done_reason') == 'length':
        raise ValueError('Ollama response was truncated; increase num_predict.')
    content = response['message']['content']
    if not content.strip():
        raise ValueError('Ollama returned empty content.')
    return content


def apertus(messages, schema=None, max_tokens=600):
    key, model, base = (os.getenv(name) for name in ('LLM_API_KEY', 'LLM_NAME', 'LLM_BASE_URL'))
    if not all((key, model, base)):
        raise ValueError('Set LLM_API_KEY, LLM_NAME, and LLM_BASE_URL.')
    body = {'model': model, 'messages': messages, 'temperature': 0, 'max_tokens': max_tokens}
    if schema is not None:
        body['response_format'] = {'type': 'json_schema', 'json_schema': {
            'name': 'coach_response', 'strict': True, 'schema': schema}}
    # Do not silently retry without constraints if a provider rejects this format.
    response = post(base, '/chat/completions', body, key)
    choice = response['choices'][0]
    if choice.get('finish_reason') == 'length':
        raise ValueError('Apertus response was truncated; increase max_tokens.')
    output = choice['message']['content']
    if not isinstance(output, str) or not output.strip():
        raise ValueError('Apertus returned an empty or invalid response.')
    return output


