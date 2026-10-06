"""Load optional task guidance without the local human-review workflow."""
import hashlib
import json
from pathlib import Path


def load_profile(path):
    if not path:
        return None
    profile = json.loads(Path(path).read_text())
    if profile.get('kind') != 'prompt_profile' or profile.get('version') != 1:
        raise ValueError('Not a supported prompt profile.')
    for role in ('coach', 'judge'):
        if not isinstance(profile.get(role), dict):
            raise ValueError('Profile must contain coach and judge guidance.')
        for stage, rules in profile[role].items():
            if stage not in ('interaction', 'followup', 'feedback') or not isinstance(rules, list):
                raise ValueError('Invalid profile stage or rules.')
            if any(not isinstance(rule, str) or not rule.strip() for rule in rules):
                raise ValueError('Guidance must contain non-empty text.')
    return {'sha256': hashlib.sha256(Path(path).read_bytes()).hexdigest(), 'content': profile}


def guidance(profile, role, stage):
    if not profile:
        return ''
    rules = profile['content'][role].get(stage, [])
    return '\nHuman-reviewed guidance for this task:\n' + '\n'.join('- ' + r for r in rules) if rules else ''

