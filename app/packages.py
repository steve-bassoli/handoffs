"""Validate portable evidence packages. Their contents are data, never executed."""
import base64
import argparse
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

from app.ai import read_source, source_path
from app.services import RuleError, encode


def digest(content):
    return hashlib.sha256(content).hexdigest()


def validate_package(task_id, payload):
    files = read_source(payload['package_zip'])
    try:
        manifest = json.loads(files['manifest.json'])
        if manifest['schema_version'] != 1 or manifest['task_id'] != task_id:
            raise ValueError()
        listed = {}
        for item in manifest['files']:
            path = source_path(item['path'])
            if path in listed or path == 'manifest.json':
                raise ValueError()
            listed[path] = item['sha256']
        if not listed or set(listed) != files.keys() - {'manifest.json'}:
            raise ValueError()
        if any(digest(files[path].encode('utf-8')) != checksum for path, checksum in listed.items()):
            raise ValueError()
    except (ValueError, KeyError, TypeError, AttributeError):
        raise RuleError('Package needs a schema_version 1 manifest.json with this task_id and matching SHA-256 for every file', 422) from None
    input_sha = manifest.get('input_sha256')
    if input_sha is not None and (not isinstance(input_sha, str) or not re.fullmatch('[0-9a-f]{64}', input_sha)):
        raise RuleError('Invalid input_sha256 in package manifest', 422)
    input_verified = False
    if payload.get('input_zip'):
        try:
            raw = base64.b64decode(payload['input_zip'], validate=True)
            if payload['kind'] != 'response' or not input_sha or digest(raw) != input_sha:
                raise ValueError()
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                info = archive.getinfo('task.json')
                if info.file_size > 100000 or json.loads(archive.read(info))['id'] != task_id:
                    raise ValueError()
            input_verified = True
        except (ValueError, KeyError, TypeError, zipfile.BadZipFile, RuntimeError, NotImplementedError):
            raise RuleError('Original input ZIP must match the response input_sha256 and task ID', 422) from None
    return {'kind': payload['kind'], 'sha256': digest(base64.b64decode(payload['package_zip'])),
            'files': files, 'input_sha256': input_sha, 'input_verified': input_verified,
            'note': payload.get('note', '')}


def attach(service, connection, actor, payload):
    task = service.detail(connection, payload['id'])
    if actor not in (task['creator'], task['target'], task['claimant'], task['completed_by']):
        raise RuleError('Only task participants can attach a package', 403)
    package = validate_package(task['id'], payload)
    if not any(event['kind'] == 'package_attached' and
               all(event['data'].get(key) == package[key] for key in ('kind', 'sha256', 'input_verified'))
               for event in task['events']):
        service.event(connection, task['id'], 'package_attached', actor, task['status'], package)
    return service.detail(connection, task['id'])


def build_package(repository, reference, task_id, paths, notes=''):
    """Export only explicitly selected tracked files, never a working tree or secrets."""
    from app.importer import git
    revision = git(repository, 'rev-parse', '--verify', reference + '^{commit}')
    origin = git(repository, 'remote', 'get-url', 'origin').removesuffix('.git')
    files = {}
    entries = []
    for requested in paths:
        path = source_path(requested)
        target = 'source/' + path
        if target in files:
            raise RuleError('Choose each source path only once', 422)
        raw = git(repository, 'show', revision + ':' + path, binary=True)
        # Canonical UTF-8 without BOM; retain the original blob hash for comparison.
        files[target] = raw.decode('utf-8-sig')
        entries.append({'path': target, 'sha256': digest(files[target].encode()),
                        'source_path': path, 'source_sha256': digest(raw)})
    if notes:
        files['SETUP_AND_CHECKS.md'] = notes
        entries.append({'path': 'SETUP_AND_CHECKS.md', 'sha256': digest(notes.encode())})
    files['manifest.json'] = encode({'schema_version': 1, 'task_id': task_id, 'repository': origin,
        'revision': revision, 'purpose': 'Pinned source / support; not proof of live verification', 'files': entries})
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path, content in sorted(files.items()):
            entry = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, content.encode())
    raw = buffer.getvalue()
    validate_package(task_id, {'kind': 'support', 'package_zip': base64.b64encode(raw).decode()})
    return raw


def main():
    parser = argparse.ArgumentParser(description='Build a focused support ZIP from pinned Git files. No network fetch or code execution.')
    parser.add_argument('--repository', required=True)
    parser.add_argument('--ref', required=True)
    parser.add_argument('--task-id', required=True)
    parser.add_argument('--path', action='append', required=True)
    parser.add_argument('--notes', help='Local UTF-8 setup and verification notes to include')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    notes = Path(args.notes).read_text(encoding='utf-8-sig') if args.notes else ''
    raw = build_package(args.repository, args.ref, args.task_id, args.path, notes)
    with Path(args.output).open('xb') as output:
        output.write(raw)
    print(encode({'task_id': args.task_id, 'path': args.output, 'sha256': digest(raw), 'bytes': len(raw)}))


if __name__ == '__main__':
    main()
