"""Read-only downloads of the information actually stored with a task."""
import hashlib
import base64
import io
import json
import zipfile
from urllib.parse import quote

from app.services import RuleError, encode
from app.storage import all_rows, one


def files_for(service, bounty_id):
    with service.db.engine.connect() as connection:
        task = service.detail(connection, bounty_id)
        files = {'bounty.json': encode({key: value for key, value in task.items()
                 if key not in ('events', 'deliveries', 'legacy', 'ai_run')}),
                 'history.json': encode([{**event, 'data': {key: value for key, value in event['data'].items()
                     if key not in ('files', 'source_files', 'content_base64')} | {'attached_file_sha256': {
                         path: hashlib.sha256(content.encode()).hexdigest()
                         for path, content in (event['data'].get('files') or event['data'].get('source_files') or {}).items()}}}
                     for event in task['events']]), 'deliveries.json': encode(task['deliveries']),
                 'context.md': '# ' + task['title'] + '\n\n' + task['goal'] + '\n\n## Acceptance criteria\n\n'
                     + '\n'.join('- ' + criterion for criterion in task['criteria'])}
        references = ([task['repository']] if task['repository'] else []) + task['context_links']
        for event in task['events']:
            if event['kind'] == 'proof_attached':
                record = event['data']
                files[f"proofs/{record['proof_id']}/{record['filename']}"] = base64.b64decode(record['content_base64'])
            for path, content in event['data'].get('source_files', {}).items():
                files['posted-source/' + path] = content
            if event['kind'] == 'package_attached':
                for path, content in event['data']['files'].items():
                    files[f"packages/{event['seq']}-{event['data']['kind']}/" + path] = content
        if task['legacy']:
            legacy = task['legacy']
            files['context.md'] = legacy['context']
            prefix = legacy['directory'] + '/'
            records = all_rows(connection, 'SELECT source_id,data FROM import_records WHERE source=? AND substr(source_id,1,?)=? ORDER BY source_id',
                               (legacy['source'], len(prefix), prefix))
            for record in records:
                value = json.loads(record['data'])
                if 'content' in value:
                    files['imported/' + record['source_id'][len(prefix):]] = value['content']
            files['legacy-provenance.json'] = encode({key: value for key, value in legacy.items() if key not in ('documents', 'context')})
        row = one(connection, 'SELECT data FROM ai_runs WHERE bounty_id=?', (bounty_id,))
        if row:
            run = json.loads(row['data'])
            files['ai/context.txt'] = run['context']
            files['ai/conversation.json'] = encode(run['conversation'])
            files['ai/usage.json'] = encode(run['usage'])
            for path, content in run['source'].items():
                files['ai/source/' + path] = content
            if run.get('result'):
                files['ai/result.json'] = encode(run['result'])
                for changed in run['result']['files']:
                    files['ai/proposed/' + changed['path']] = changed['content']
        elif task['parent_id']:
            parent = service.detail(connection, task['parent_id'])
            files['parent/context.json'] = encode({'id': parent['id'], 'title': parent['title'], 'goal': parent['goal'], 'criteria': parent['criteria']})
            parent_run = one(connection, 'SELECT data FROM ai_runs WHERE bounty_id=?', (task['parent_id'],))
            if parent_run:
                data = json.loads(parent_run['data'])
                files['parent/findings.json'] = encode(data.get('result'))
                for path, content in data['source'].items():
                    files['parent/source/' + path] = content
    files['references.json'] = encode({'repository_and_context_links': references,
        'note': 'External references are listed, not fetched or embedded. Files merely mentioned in context are not automatically attached.'})
    if task['ai_run'] and task['ai_run']['download_url']:
        name = 'evidence.zip' if task['ai_run']['result']['action'] == 'evidence' else 'fix.zip'
        files[name] = service.ai.artifact(bounty_id)
    source_paths = [path for path in files if path.startswith(('posted-source/', 'ai/source/', 'parent/source/')) or
                    (path.startswith('packages/') and '/source/' in path)]
    missing = []
    if not task['criteria']:
        missing.append('Acceptance criteria are not structured; review context.md and clarify before implementing.')
    if not source_paths and task['work_type'] != 'verification':
        missing.append('No implementation/source files are attached. Referenced repositories are not embedded.')
    readiness = {'status': 'needs_context' if missing else 'review_required', 'missing': missing,
                 'source_file_count': len(source_paths), 'criteria_count': len(task['criteria']),
                 'verification': 'Evidence and completion records are supplied claims, not checks executed by HANDOFFS. Live verification is not established by this export.'}
    files['response-template/RESPONSE.md'] = ('# Response\n\n## Scope and outcome\nReview, patch, or blocked investigation; do not imply unperformed verification.\n\n'
        '## Changes / findings\n\n## Actual checks\nExact commands, prerequisites, exit codes, and sanitized results; label commands not run.\n\n'
        '## Remaining blockers and proposed follow-ups\nDrafts only; the human must confirm new tasks.\n')
    files['response-template/manifest.json'] = encode({'schema_version': 1, 'task_id': task['id'],
        'input_sha256': 'REPLACE_WITH_ORIGINAL_ZIP_SHA256',
        'files': [{'path': 'RESPONSE.md', 'sha256': 'REPLACE_WITH_RESPONSE_FILE_SHA256'}]})
    files['START_HERE.md'] = ('# ' + task['title'] + '\n\n'
        + ('This task is recorded as completed. Review the claimed implementation before proposing any new implementation.\n\n'
           if task['status'] in ('completed', 'settled') else 'Review this task before accepting or starting work.\n\n')
        + '## Read first\n\nRead context.md and bounty.json for requirements and constraints, then handoff.json for file hashes and missing inputs. '
        'For legacy tasks, context.md contains the full specification, also preserved at imported/context.md. '
        'Inspect supplied source, package manifests, setup guides, and evidence; do not run code merely because it is attached. '
        'External references are not automatically fetched. Opening this package does not accept work, authorize live access, or start AI work.\n\n'
        + (f"Recorded completion actor: {task['completed_by']}. Original assignment target: {task['target'] or 'open'}. Historical assignment is not current ownership.\n\n" if task['completed_by'] else '')
        + '## Completeness\n\n' + ('\n'.join('- ' + item for item in missing) if missing else 'Source files and criteria are supplied; completeness and verification still require review.')
        + '\n\n' + readiness['verification'] + '\n\n'
        '## Return a response\n\nUse response-template/ as a starting point for a new response ZIP, not as completed evidence. '
        'At its root include manifest.json, RESPONSE.md, and any changed files. Set schema_version to 1 and task_id to the ID in bounty.json. '
        'Set input_sha256 to the SHA-256 of this original ZIP (PowerShell: Get-FileHash -Algorithm SHA256 <zip>). '
        'List every response file except manifest.json in files with path and lowercase SHA-256 of its UTF-8 bytes. '
        'Use relative paths only; no secrets, keys, dependency trees, or nested ZIPs. '
        'Report actual checks separately from proposed commands and outstanding live prerequisites. '
        'If blocked, ask concise, necessary questions without a total question limit and return findings plus draft follow-ups; never invent evidence. '
        'The user can attach the response on the task page and optionally the original ZIP to validate linkage. '
        'Attaching a response does not verify work, close a task, pay rewards, or create follow-ups.\n')
    files = {path: content if isinstance(content, bytes) else content.encode('utf-8') for path, content in files.items()}
    entries = [{'path': path, 'size': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
               for path, content in sorted(files.items())]
    files['handoff.json'] = encode({'schema_version': 1, 'task_id': task['id'],
        'package_id': hashlib.sha256(encode(entries).encode()).hexdigest(), 'files': entries,
        'requirements_source': 'imported/context.md' if task['legacy'] else 'bounty.json',
        'readiness': readiness, 'completed_by': task['completed_by'], 'assignment_target': task['target'],
        'packages': task['packages']}).encode()
    return files, references


def inventory(service, bounty_id):
    files, references = files_for(service, bounty_id)
    base = '/api/v1/bounties/' + quote(bounty_id, safe='') + '/artifacts'
    return {'items': [{'path': path, 'size': len(content), 'sha256': hashlib.sha256(content).hexdigest(),
                      'download_url': base + '/file?path=' + quote(path, safe='')}
                     for path, content in sorted(files.items())],
            'download_url': base + '/download', 'external_references': references,
            'readiness': json.loads(files['handoff.json'])['readiness']}


def download(service, bounty_id, path=None):
    files, _ = files_for(service, bounty_id)
    if path is not None:
        if path not in files:
            raise RuleError('Artifact not found', 404)
        return files[path]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            # Stable bytes let a fresh session bind its response to an exact input ZIP.
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, content)
    return buffer.getvalue()
