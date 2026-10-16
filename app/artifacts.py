"""Read-only downloads of the information actually stored with a bounty."""
import hashlib
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
                 'history.json': encode(task['events']), 'deliveries.json': encode(task['deliveries']),
                 'context.md': '# ' + task['title'] + '\n\n' + task['goal'] + '\n\n## Acceptance criteria\n\n'
                     + '\n'.join('- ' + criterion for criterion in task['criteria'])}
        references = ([task['repository']] if task['repository'] else []) + task['context_links']
        for event in task['events']:
            for path, content in event['data'].get('source_files', {}).items():
                files['posted-source/' + path] = content
        if task['legacy']:
            legacy = task['legacy']
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
    files['START_HERE.md'] = ('# Review this bounty before accepting\n\n'
        'Read context.md and bounty.json, then inspect the attached files and history. '
        'This package contains the information stored in HANDOFFS at download time. '
        'External repositories and linked files are references only; their contents are not automatically downloaded. '
        'Opening or downloading this package does not accept the bounty or start AI work.\n')
    if task['ai_run'] and task['ai_run']['download_url']:
        files['fix.zip'] = service.ai.artifact(bounty_id)
    return {path: content if isinstance(content, bytes) else content.encode('utf-8') for path, content in files.items()}, references


def inventory(service, bounty_id):
    files, references = files_for(service, bounty_id)
    base = '/api/v1/bounties/' + quote(bounty_id, safe='') + '/artifacts'
    return {'items': [{'path': path, 'size': len(content), 'sha256': hashlib.sha256(content).hexdigest(),
                      'download_url': base + '/file?path=' + quote(path, safe='')}
                     for path, content in sorted(files.items())],
            'download_url': base + '/download', 'external_references': references}


def download(service, bounty_id, path=None):
    files, _ = files_for(service, bounty_id)
    if path is not None:
        if path not in files:
            raise RuleError('Artifact not found', 404)
        return files[path]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            archive.writestr(name, content)
    return buffer.getvalue()
