"""Read-only legacy sources; import history without issuing spendable Gold."""
import argparse
import hashlib
import io
import json
import re
import sqlite3
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path

from app.adapters import DemoDeliveryVerifier
from app.services import Service, encode
from app.storage import Database, one

MEMBERS = {'STEVE', 'NATE', 'WILL'}
EVENT_TYPES = {'assigned', 'claimed', 'working', 'blocked', 'completed', 'acknowledged', 'accepted', 'rejected', 'review-accepted'}
LEGACY_TABLES = ('player_profiles', 'reward_events', 'pr_reward_events', 'intro_reward_events',
                 'gold_spend_events', 'capacity_readings', 'relations')


def git(repository, *arguments, binary=False):
    command = ['git', '-c', 'safe.directory=' + Path(repository).resolve().as_posix(), '-C', str(repository), *arguments]
    result = subprocess.run(command, check=True, capture_output=True)
    return result.stdout if binary else result.stdout.decode('utf-8-sig').strip()


def stamp(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Timestamp must have a timezone')
    return parsed


def remember(c, source, source_id, data):
    serialized = encode(data)
    fingerprint = hashlib.sha256(serialized.encode()).hexdigest()
    previous = one(c, 'SELECT fingerprint FROM import_records WHERE source=? AND source_id=?', (source, source_id))
    if previous:
        if previous['fingerprint'] != fingerprint:
            raise ValueError('Previously imported record changed: ' + source_id)
        return False
    c.exec_driver_sql('INSERT INTO import_records VALUES (?,?,?,?)', (source, source_id, fingerprint, serialized))
    return True


def validate_packet(manifest_path, files):
    manifest = json.loads(files[manifest_path])
    for field in ('schemaVersion', 'taskId', 'sender', 'recipient', 'createdUtc', 'title', 'queueItem', 'contextFile'):
        if field not in manifest:
            raise ValueError('Missing manifest field: ' + field)
    task_id = manifest['taskId']
    if not re.fullmatch('[a-z0-9][a-z0-9-]{0,79}', task_id):
        raise ValueError('Invalid task ID')
    if manifest['schemaVersion'] != 2 or manifest['contextFile'] != 'context.md':
        raise ValueError('Unsupported manifest schema/context')
    if manifest['sender'] not in MEMBERS or manifest['recipient'] not in MEMBERS | {'OPEN'}:
        raise ValueError('Invalid sender or recipient')
    stamp(manifest['createdUtc'])
    if 'gold' in manifest and (type(manifest['gold']) is not int or manifest['gold'] < 50):
        raise ValueError('Invalid historical Gold amount')
    directory = f"PLAN/handoffs/{task_id}-{manifest['recipient'].lower()}"
    if manifest_path != directory + '/manifest.json':
        raise ValueError('Manifest directory does not match identity')
    packet_files = {path: text for path, text in files.items() if path.startswith(directory + '/')}
    if directory + '/context.md' not in packet_files:
        raise ValueError('Missing context')
    records = []
    for path, text in packet_files.items():
        if path.startswith(directory + '/events/') and path.endswith('.json'):
            event = json.loads(text)
            for field in ('schemaVersion', 'eventId', 'taskId', 'type', 'actor', 'createdUtc', 'resultPath', 'replyTo'):
                if field not in event:
                    raise ValueError('Missing event field: ' + field)
            if event['schemaVersion'] != 1 or event['taskId'] != task_id or event['type'] not in EVENT_TYPES or event['actor'] not in MEMBERS:
                raise ValueError('Invalid event identity/type/actor')
            if path != directory + '/events/' + event['eventId'] + '.json':
                raise ValueError('Event filename differs from identity')
            stamp(event['createdUtc'])
            result = event['resultPath']
            if result and (result not in packet_files or not result.startswith((directory + '/results/', directory + '/reviews/'))):
                raise ValueError('Missing or out-of-packet result/review')
            records.append((path, event))
    if sum(event['type'] == 'assigned' for _, event in records) != 1:
        raise ValueError('Expected exactly one assigned event')
    ids = [event['eventId'] for _, event in records]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate event identity')
    for _, event in records:
        if event['type'] in {'accepted', 'rejected', 'acknowledged'}:
            if event['replyTo'] not in ids:
                raise ValueError('Review/acknowledgement references missing event')
    records.sort(key=lambda record: (stamp(record[1]['createdUtc']), record[1]['eventId']))
    return manifest, directory, packet_files, records


def import_git(db, repository, reference):
    revision = git(repository, 'rev-parse', '--verify', reference + '^{commit}')
    if not re.fullmatch('[0-9a-f]{40}', revision):
        raise ValueError('Expected one full commit revision')
    origin = git(repository, 'remote', 'get-url', 'origin')
    source = 'git:' + origin.removesuffix('.git')
    archive = git(repository, 'archive', '--format=zip', revision, 'PLAN/handoffs', binary=True)
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        files = {entry.filename: zipped.read(entry).decode('utf-8-sig') for entry in zipped.infolist() if not entry.is_dir()}
    report = {'revision': revision, 'source': source, 'packets_seen': 0, 'imported': 0, 'unchanged': 0, 'gaps': []}
    for path in sorted(path for path in files if path.endswith('/manifest.json')):
        report['packets_seen'] += 1
        try:
            manifest, directory, packet_files, records = validate_packet(path, files)
            with db.write() as c:
                bounty_id = manifest['taskId']
                existing = one(c, 'SELECT * FROM bounties WHERE id=?', (bounty_id,))
                if existing:
                    legacy = json.loads(existing['legacy']) if existing['legacy'] else {}
                    if legacy.get('source') != source or legacy.get('directory') != directory:
                        raise ValueError('Task ID conflicts with another task/source')
                else:
                    metadata = {'source': source, 'revision': revision, 'directory': directory, 'manifest': manifest,
                                'context': packet_files[directory + '/context.md']}
                    c.exec_driver_sql('INSERT INTO bounties(id,title,goal,criteria,repository,context_links,creator,target,gold,created_at,legacy,funded) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                                      (bounty_id, manifest['title'], 'Historical imported assignment', encode([]), '', encode([]),
                                       manifest['sender'].lower(), None if manifest['recipient'] == 'OPEN' else manifest['recipient'].lower(),
                                       manifest.get('gold') or 150, manifest['createdUtc'], encode(metadata), 0))
                imported_events = {r['source_id'] for r in c.exec_driver_sql('SELECT source_id FROM import_records WHERE source=?', (source,)).mappings()}
                previous_files = {file for file in imported_events if file.startswith(directory + '/')}
                if previous_files - packet_files.keys():
                    raise ValueError('Previously imported files were removed')
                if existing:
                    previous_event = one(c, 'SELECT created_at FROM events WHERE bounty_id=? ORDER BY seq DESC LIMIT 1', (bounty_id,))
                    if any(file not in imported_events and stamp(event['createdUtc']) < stamp(previous_event['created_at']) for file, event in records):
                        raise ValueError('New event predates imported history; manual reconciliation needed')
                # Check immutable files before appending anything; a conflict rolls back this packet.
                for file, text in sorted(packet_files.items()):
                    remember(c, source, file, {'content': text})
                state = 'pending'
                changed = not existing
                for file, event in records:
                    kind = event['type']
                    if kind in ('claimed', 'working'):
                        state = 'working'
                    elif kind in ('blocked', 'completed'):
                        state = kind
                    elif kind == 'review-accepted':
                        state = 'completed'
                    if file not in imported_events:
                        c.exec_driver_sql('INSERT INTO events(bounty_id,kind,actor,state,data,created_at) VALUES (?,?,?,?,?,?)',
                                          (bounty_id, 'legacy:' + kind, event['actor'].lower(), state,
                                           encode({'source_event': event, 'source_path': file, 'revision': revision}), event['createdUtc']))
                        changed = True
                report['imported' if changed else 'unchanged'] += 1
        except (ValueError, KeyError, TypeError) as error:
            report['gaps'].append({'path': path, 'reason': str(error)})
    return report


def import_database(db, database_path):
    path = Path(database_path).resolve()
    report = {'tables': {}, 'imported': 0, 'unchanged': 0, 'gaps': [], 'spendable_gold_imported': 0}
    source = 'sqlite:' + str(path)
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as original, sqlite3.connect(':memory:') as snapshot:
        original.backup(snapshot)
        snapshot.row_factory = sqlite3.Row
        tables = {row[0] for row in snapshot.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in LEGACY_TABLES:
            if table not in tables:
                report['gaps'].append({'table': table, 'reason': 'Table absent from this snapshot'})
                continue
            info = list(snapshot.execute('PRAGMA table_info(' + table + ')'))
            primary_keys = [row['name'] for row in sorted(info, key=lambda row: row['pk']) if row['pk']]
            rows = [dict(row) for row in snapshot.execute('SELECT * FROM ' + table)]
            report['tables'][table] = len(rows)
            for record in rows:
                identity = encode([record[key] for key in primary_keys]) if primary_keys else hashlib.sha256(encode(record).encode()).hexdigest()
                try:
                    with db.write() as c:
                        changed = remember(c, source, table + ':' + identity, record)
                        report['imported' if changed else 'unchanged'] += 1
                except ValueError as error:
                    report['gaps'].append({'table': table, 'reason': 'Conflicting previously imported record'})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    parser.add_argument('--repository')
    parser.add_argument('--ref', default='refs/remotes/origin/main')
    parser.add_argument('--legacy-database')
    args = parser.parse_args()
    if not args.repository and not args.legacy_database:
        parser.error('Provide --repository or --legacy-database')
    db = Database(args.database)
    db.migrate()
    Service(db, DemoDeliveryVerifier()).seed()
    report = {}
    try:
        if args.repository:
            report['git'] = import_git(db, args.repository, args.ref)
        if args.legacy_database:
            report['sqlite'] = import_database(db, args.legacy_database)
        print(json.dumps(report, indent=2))
    finally:
        db.engine.dispose()
    return int(any(value.get('gaps') for value in report.values()))


if __name__ == '__main__':
    raise SystemExit(main())
