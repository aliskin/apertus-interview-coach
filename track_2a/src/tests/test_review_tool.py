"""Review portability, dataset isolation and preservation of saved annotations."""
import copy
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from review import portal, prepare, store


class ReviewToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)

    def registry(self):
        return portal.Registry(self.data)

    def dataset(self, version='demo'):
        return prepare.install(self.data, version, 'Demo review', prepare.demo_sample())

    def payload(self, registry, version='demo'):
        return {'case_id': 'DEMO-01', 'revision': 0, 'notes': 'Draft reasoning',
                'translation_issue': False, 'stage': 'introduction',
                'stage_reason': 'Only greeting is visible.', 'review_status': 'draft',
                'rules': {key: {'status': 'not_sure', 'note': 'Awaiting validation', 'evidence': ''}
                          for key in registry.stores[version].rule_ids}}

    def post(self, registry, version, payload, origin='http://127.0.0.1:8081'):
        handler = object.__new__(portal.Handler)
        handler.path = '/api/review?version=' + version
        raw = json.dumps(payload).encode()
        handler.headers = {'Origin': origin, 'Host': '127.0.0.1:8081', 'Content-Length': str(len(raw))}
        handler.rfile = BytesIO(raw)
        handler.server = SimpleNamespace(registry=registry)
        response = []
        handler.send = lambda status, body, **kw: response.append((status, body))
        handler.do_POST()
        return response[0]

    def test_empty_checkout_has_actionable_setup_error(self):
        with self.assertRaisesRegex(ValueError, 'review-demo'):
            self.registry()

    def test_demo_is_self_contained_and_does_not_reset_labels(self):
        self.dataset()
        registry = self.registry()
        registry.stores['demo'].save(self.payload(registry))
        original = registry.stores['demo'].labels_path.read_bytes()
        self.dataset()
        self.assertEqual(self.registry().stores['demo'].labels_path.read_bytes(), original)
        self.assertEqual(registry.catalog()['default'], 'demo')

    def test_changed_sample_cannot_overwrite_annotated_version(self):
        folder = self.dataset()
        original = (folder / 'sample.json').read_bytes()
        sample = prepare.demo_sample()
        sample['cases'][0]['generated']['reply'] = 'Changed output'
        with self.assertRaisesRegex(ValueError, 'new version ID'):
            prepare.install(self.data, 'demo', 'Demo review', sample)
        self.assertEqual((folder / 'sample.json').read_bytes(), original)

    def test_same_case_id_is_saved_only_in_selected_version(self):
        self.dataset('first'); self.dataset('second')
        registry = self.registry()
        payload = self.payload(registry, 'first')
        self.assertEqual(self.post(registry, 'second', payload)[0], 200)
        self.assertFalse(registry.stores['first'].labels_path.exists())
        self.assertEqual(self.post(registry, 'second', payload)[0], 409)
        self.assertEqual(self.post(registry, 'first', payload)[0], 200)

    def test_unknown_version_and_foreign_origin_do_not_write(self):
        self.dataset()
        registry = self.registry(); payload = self.payload(registry)
        self.assertEqual(self.post(registry, '../outside', payload)[0], 404)
        self.assertEqual(self.post(registry, 'demo', payload, 'https://elsewhere.example')[0], 403)
        self.assertFalse(registry.stores['demo'].labels_path.exists())

    def test_invented_evidence_quote_is_rejected(self):
        self.dataset()
        registry = self.registry(); payload = self.payload(registry)
        payload['rules']['K3']['evidence'] = 'Not in the coach response'
        self.assertEqual(self.post(registry, 'demo', payload)[0], 400)

    def test_archive_preserves_validation_and_resource_paths(self):
        self.dataset('older'); self.dataset('current')
        registry = self.registry(); payload = self.payload(registry, 'older')
        payload['review_status'] = 'validated'
        registry.stores['older'].save(payload)
        original = registry.stores['older'].labels_path.read_bytes()
        prepare.archive(self.data, 'older')
        registry = self.registry()
        self.assertEqual(registry.default, 'current')
        self.assertTrue(registry.metadata['older']['group'].startswith('Archive'))
        self.assertEqual(registry.stores['older'].labels_path.read_bytes(), original)
        self.assertEqual(registry.snapshot('older')['summary']['validated'], 1)

    def test_configuration_cannot_escape_data_directory(self):
        folder = self.dataset()
        meta = json.loads((folder / 'version.json').read_text())
        meta['labels'] = '../../../outside.json'
        (folder / 'version.json').write_text(json.dumps(meta))
        with self.assertRaisesRegex(ValueError, 'inside'):
            self.registry()

    def test_translation_must_match_the_original_turns(self):
        folder = self.dataset(); registry = self.registry()
        sample = registry.stores['demo']
        translated = {'sample_sha256': sample.sample_hash, 'provenance': 'Test reading aid',
                      'cases': {'DEMO-01': {'transcript': ['Changed'], 'source_turn_sha256': ['wrong']}}}
        (folder / 'translations.en.json').write_text(json.dumps(translated))
        with self.assertRaisesRegex(ValueError, 'transcript mismatch'):
            registry.snapshot('demo')

    def test_summary_separates_validation_uncertainty_and_violations(self):
        self.dataset(); registry = self.registry(); payload = self.payload(registry)
        payload['rules']['K1']['status'] = 'violates'
        payload['rules']['K3']['status'] = 'violates'
        payload['rules']['M1']['status'] = 'not_applicable'
        registry.stores['demo'].save(payload)
        result = registry.snapshot('demo')['summary']
        self.assertEqual(result['counts']['violates'], 2)
        self.assertEqual(result['counts']['not_sure'], 23)
        self.assertEqual(result['counts']['unlabelled'], 0)
        self.assertEqual(result['affected_cases'], 1)
        self.assertEqual(result['drafts'], 1)
        self.assertEqual(result['validated'], 0)

    def test_completed_retry_overrides_failed_record_without_erasing_success(self):
        first = self.data / 'first'; retry = self.data / 'retry'
        first.mkdir(); retry.mkdir()
        case = prepare.demo_sample()['cases'][0]
        session = {'complete': True, 'feedback': {'summary': 'Feedback'}, 'language': 'de',
                   'posting': {'occupation': case['input']['occupation']}, 'transcript': case['transcript']}
        failed = {'scenario_id': 'S-01', 'session': dict(session, complete=False)}
        (first / 'S-01.json').write_text(json.dumps(failed))
        (retry / 'S-01.json').write_text(json.dumps({'scenario_id': 'S-01', 'session': session}))
        result = prepare.recorded_sample([first, retry])
        self.assertEqual(result['eligible_outputs'], 1)
        self.assertEqual(result['excluded_generation_failures'], 1)
        self.assertEqual(result['cases'][0]['source_record'], str((retry / 'S-01.json').resolve()))
        self.assertEqual(prepare.recorded_sample([retry, first])['eligible_outputs'], 1)


if __name__ == '__main__':
    unittest.main()
