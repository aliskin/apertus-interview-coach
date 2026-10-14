"""Serve local review datasets; no model requests are made by this server."""
import argparse
import hashlib
import json
import re
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

if __package__:
    from . import store as review
else:
    import store as review

VERSION_ID = re.compile(r'^[a-z0-9][a-z0-9-]*$')


def summary(snapshot):
    counts = {status: 0 for status in review.STATUSES}
    categories = []
    affected = set()
    drafts = validated = 0
    for result in snapshot['reviews'].values():
        drafts += result.get('review_status', 'draft') == 'draft'
        validated += result.get('review_status') == 'validated'
        for label in result['rules'].values():
            counts[label['status']] += 1
    for group in snapshot['groups']:
        ids = {rule['id'] for rule in group['rules']}
        hits = cases = 0
        for cid, result in snapshot['reviews'].items():
            n = sum(result['rules'][key]['status'] == 'violates' for key in ids)
            hits += n
            cases += bool(n)
            if n:
                affected.add(cid)
        categories.append({'title': group['title'], 'key': group['rules'][0]['id'][0],
                           'violations': hits, 'cases': cases, 'rule_ids': sorted(ids)})
    total = len(snapshot['cases']) * sum(len(g['rules']) for g in snapshot['groups'])
    counts['unlabelled'] = total - sum(counts.values())
    return {'counts': counts, 'categories': categories, 'affected_cases': len(affected),
            'saved': len(snapshot['reviews']), 'drafts': drafts, 'validated': validated,
            'total': len(snapshot['cases'])}


def resource(root, config_dir, name):
    path = (config_dir / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Review resources must stay inside the selected data directory.')
    return path


class Registry:
    def __init__(self, data=review.DATA, guidelines=None, default=None):
        self.data = Path(data).resolve()
        self.stores = {}
        self.metadata = {}
        guidelines = Path(guidelines or review.ROOT / 'data/interview/feedback_guidelines.json')
        active = sorted((self.data / 'versions').glob('*/version.json'))
        archived = sorted((self.data / 'archive').glob('*/version/version.json'))
        for config_path in active + archived:
            meta = json.loads(config_path.read_text())
            vid = meta['id']
            if not VERSION_ID.fullmatch(vid) or vid in self.stores:
                raise ValueError('Review version IDs must be unique safe names.')
            meta = dict(meta, config_directory=str(config_path.parent))
            if config_path in archived:
                meta['group'] = 'Archive · earlier experiments'
            self.metadata[vid] = meta
            self.stores[vid] = review.ReviewStore(
                resource(self.data, config_path.parent, meta['sample']),
                resource(self.data, config_path.parent, meta['legacy_translations']),
                guidelines,
                resource(self.data, config_path.parent, meta['labels']))
        if not self.stores:
            raise ValueError('No review datasets. Run make review-demo, or import runs with src/review/prepare.py.')
        active_ids = [vid for vid, meta in self.metadata.items()
                      if not meta.get('group', '').startswith('Archive')]
        self.default = default or (active_ids or list(self.stores))[0]
        if self.default not in self.stores:
            raise ValueError('Requested default version does not exist.')

    def snapshot(self, vid):
        store = self.stores[vid]
        meta = self.metadata[vid]
        translated = resource(self.data, Path(meta['config_directory']),
                              meta.get('translations', meta['legacy_translations']))
        if translated.exists() and translated != store.translations_path:
            data = json.loads(translated.read_text())
            if data.get('sample_sha256') != store.sample_hash or set(data['cases']) != set(store.cases):
                raise ValueError('Translation sample mismatch.')
            for cid, case in store.cases.items():
                item = data['cases'][cid]
                hashes = [hashlib.sha256(t['content'].encode()).hexdigest()
                          for t in case.get('transcript', [])]
                if len(item.get('transcript', [])) != len(hashes) or item.get('source_turn_sha256') != hashes:
                    raise ValueError('Translation transcript mismatch.')
            store.translations = data
        result = store.snapshot()
        result['version'] = {k: meta[k] for k in ('id', 'title', 'description', 'group')}
        result['summary'] = summary(result)
        return result

    def catalog(self):
        return {'default': self.default, 'versions': [
            {**{k: meta[k] for k in ('id', 'title', 'description', 'group')},
             'summary': self.snapshot(vid)['summary']}
            for vid, meta in self.metadata.items()]}


class Handler(review.Handler):
    def do_GET(self):
        route = urlsplit(self.path)
        registry = self.server.registry
        try:
            if route.path == '/api/versions':
                return self.send(200, registry.catalog())
            if route.path in ('/api/review', '/api/export'):
                vid = parse_qs(route.query).get('version', [registry.default])[0]
                if vid not in registry.stores:
                    return self.send(404, {'error': 'Unknown coach version'})
                if route.path == '/api/review':
                    return self.send(200, registry.snapshot(vid))
                store = registry.stores[vid]
                with store.lock:
                    return self.send(200, store.read_labels(), download=True)
            self.path = route.path
            return super().do_GET()
        except (KeyError, ValueError, OSError) as exc:
            return self.send(400, {'error': str(exc)})

    def do_POST(self):
        route = urlsplit(self.path)
        if route.path != '/api/review':
            return self.send(404, {'error': 'Not found'})
        if self.headers.get('Origin') not in (None, 'http://' + self.headers.get('Host', '')):
            return self.send(403, {'error': 'Save from the local review page.'})
        registry = self.server.registry
        vid = parse_qs(route.query).get('version', [registry.default])[0]
        if vid not in registry.stores:
            return self.send(404, {'error': 'Unknown coach version'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 200000:
                raise ValueError('Empty or oversized review')
            saved = registry.stores[vid].save(json.loads(self.rfile.read(length)))
            self.send(200, {'review': saved, 'summary': registry.snapshot(vid)['summary']})
        except review.Conflict as exc:
            self.send(409, {'error': str(exc)})
        except (ValueError, TypeError) as exc:
            self.send(400, {'error': str(exc)})
        except OSError:
            self.send(500, {'error': 'Could not save to disk. Your changes are still on the page.'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8081)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--data-root', type=Path, default=review.DATA)
    parser.add_argument('--guidelines', type=Path)
    parser.add_argument('--default-version')
    args = parser.parse_args()
    try:
        registry = Registry(args.data_root, args.guidelines, args.default_version)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.registry = registry
    print(f'Manual review: http://{args.host}:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
