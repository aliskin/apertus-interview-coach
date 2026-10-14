"""Create a review version from recorded interviews, a demonstration, or archive a version."""
import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path

if __package__:
    from . import store, portal
else:
    import store
    import portal


def write(path, value):
    text = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text() != text:
            raise ValueError('Existing data differs; choose a new version ID: ' + str(path))
        return
    temporary = path.with_suffix('.tmp')
    temporary.write_text(text)
    temporary.replace(path)


def install(data, version, title, sample):
    if not portal.VERSION_ID.fullmatch(version):
        raise ValueError('Use a version ID containing lowercase letters, digits and hyphens.')
    folder = Path(data) / 'versions' / version
    if (Path(data) / 'archive' / version).exists():
        raise ValueError('An archived version has this ID; choose a new ID.')
    sample_path = folder / 'sample.json'
    write(sample_path, sample)
    write(folder / 'reading-aid.json', {
        'sample_sha256': hashlib.sha256(sample_path.read_bytes()).hexdigest(),
        'provenance': 'Original text. Optional translations are reading aids, not authoritative evidence.',
        'cases': {c['case_id']: {'question': 'Interview review', 'answer': '', 'reply': '',
                               'hint': '', 'occupation': c['input']['occupation'].get('name_de', '')}
                  for c in sample['cases']}})
    write(folder / 'version.json', {'id': version, 'title': title,
          'description': f"{len(sample['cases'])} interviews · labels saved locally",
          'group': 'Full interviews', 'sample': 'sample.json', 'labels': 'labels.json',
          'legacy_translations': 'reading-aid.json', 'translations': 'translations.en.json'})
    return folder


def demo_sample():
    transcript = [
        {'role': 'assistant', 'stage': 'introduction', 'content': 'Wie geht es dir heute?'},
        {'role': 'user', 'stage': 'introduction', 'content': 'Gut, danke. Ich bin etwas nervös.'},
        {'role': 'assistant', 'stage': 'feedback',
         'content': 'Du hast freundlich geantwortet: „Gut, danke.“ Wir haben erst den Einstieg geübt. '
                    'Als Nächstes kannst du deine Vorstellung in zwei Sätzen üben. Danke fürs Üben.'}]
    return {'kind': 'full_interview_manual_review', 'source_file': 'Built-in fictional demonstration; no model calls.',
            'sampling': 'One demonstration, not a benchmark.', 'eligible_outputs': 1,
            'excluded_generation_failures': 0, 'coach_model': 'Demonstration text', 'cases': [{
                'case_id': 'DEMO-01', 'repeat': 1,
                'input': {'question': transcript[0]['content'], 'answer': transcript[1]['content'],
                          'language': 'de', 'occupation': {'name_de': 'Lehrstelle'},
                          'phase_key': 'greeting'},
                'generated': {'reply': transcript[2]['content'], 'hint': ''}, 'transcript': transcript}]}


def recorded_sample(folders):
    selected = {}
    omitted = []
    for folder in folders:
        for path in sorted(Path(folder).glob('*.json')):
            record = json.loads(path.read_text())
            session = record.get('session', record)
            if not isinstance(session, dict) or 'transcript' not in session:
                continue
            cid = record.get('scenario_id', path.stem)
            if not session.get('complete') or not session.get('feedback'):
                omitted.append(str(path))
                continue
            # Later completed records replace earlier ones; failed overrides never erase success.
            selected[cid] = (record, session, path)
    if not selected:
        raise ValueError('No completed interviews with feedback found.')
    cases = []
    for cid, (record, session, path) in sorted(selected.items()):
        transcript = session['transcript']
        cases.append({'case_id': cid, 'repeat': 1, 'source_record': str(path.resolve()),
                      'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                      'input': {'question': 'Complete interview',
                                'answer': '\n\n'.join(t['content'] for t in transcript if t['role'] == 'user'),
                                'language': session['language'], 'occupation': session['posting']['occupation'],
                                'phase_key': 'whole_interview'},
                      'generated': {'reply': '\n\n'.join(t['content'] for t in transcript if t['role'] == 'assistant'), 'hint': ''},
                      'transcript': transcript, 'posting': session['posting'],
                      'structured_feedback': session['feedback'],
                      'analysis_trace': {'analyses': session.get('answer_analyses', []),
                                         'decisions': session.get('turn_decisions', []),
                                         'evidence_records': session.get('evidence_records', [])}})
    return {'kind': 'full_interview_manual_review', 'source_file': ', '.join(map(str, folders)),
            'sampling': 'Completed records; later source folders provide successful overrides.',
            'eligible_outputs': len(cases), 'excluded_generation_failures': len(omitted),
            'omitted_records': omitted, 'cases': cases}


def archive(data, version):
    if not portal.VERSION_ID.fullmatch(version):
        raise ValueError('Invalid version ID.')
    data = Path(data).resolve()
    source = data / 'versions' / version
    target = data / 'archive' / version / 'version'
    config = json.loads((source / 'version.json').read_text())
    paths = {k: portal.resource(data, source, config[k])
             for k in ('sample', 'labels', 'legacy_translations', 'translations') if k in config}
    if target.exists():
        raise ValueError('Archive target already exists.')
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))
    for key, path in paths.items():
        if path.is_relative_to(source):
            path = target / path.relative_to(source)
        config[key] = os.path.relpath(path, target)
    config['group'] = 'Archive · earlier experiments'
    (target / 'version.json').write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n')
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--demo', action='store_true')
    action.add_argument('--run', type=Path, nargs='+', help='Source directories, ordered from baseline to overrides.')
    action.add_argument('--archive', metavar='VERSION')
    parser.add_argument('--version', default='demo')
    parser.add_argument('--title', default='Manual review demonstration')
    parser.add_argument('--data-root', type=Path, default=store.DATA)
    args = parser.parse_args()
    try:
        if args.archive:
            result = archive(args.data_root, args.archive)
        else:
            if args.run and args.version == 'demo':
                parser.error('Give imported interviews their own --version ID and --title.')
            sample = demo_sample() if args.demo else recorded_sample(args.run)
            result = install(args.data_root, args.version, args.title, sample)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(result)


if __name__ == '__main__':
    main()
