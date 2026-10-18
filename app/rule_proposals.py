"""Protected rule-text proposals decided in the digest (task 2c56ad7a).

A proposal is docs/proposals/<name>/agent-rules.json: a full replacement for rules/agent-rules.json. Each signed-in
person decides once per digest. When two different people have accepted the same digest and nobody has declined it,
the server writes the APPROVALS.json entry from those recorded decisions and then the rules file, byte for byte, after
checking that the result loads under the existing two-human rule. A human commits the files; they take effect at restart.
"""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from app.services import RuleError
from app.storage import all_rows

ROOT = Path(__file__).resolve().parents[1]
NEEDED = 2


def rules_dir():
    return Path(os.environ.get('ASE_RULES_DIR', ROOT / 'rules'))


def proposals_dir():
    return Path(os.environ.get('ASE_PROPOSALS_DIR', ROOT / 'docs' / 'proposals'))


def _title(folder):
    readme = folder / 'README.md'
    if readme.is_file():
        for line in readme.read_text(encoding='utf-8').splitlines():
            if line.startswith('# '):
                return line[2:].strip()[:160]
    return folder.name


def _author(folder):
    readme = folder / 'README.md'
    if readme.is_file():
        for line in readme.read_text(encoding='utf-8').splitlines():
            if line.startswith('Author:'):
                return line[len('Author:'):].strip().split('.')[0][:120]
    return None


def pending(c):
    """Proposals that differ from the live rules file, with their changed texts and decisions so far."""
    live_raw = (rules_dir() / 'agent-rules.json').read_bytes()
    live = json.loads(live_raw)
    found = []
    for path in sorted(proposals_dir().glob('*/agent-rules.json')):
        raw = path.read_bytes()
        if raw == live_raw:
            continue
        try:
            data = json.loads(raw)
            if set(data) != {'texts', 'compositions'} or set(data['texts']) != set(live['texts']):
                continue  # Malformed or reshaped proposals are not decidable here.
        except ValueError:
            continue
        sha = hashlib.sha256(raw).hexdigest()
        changed = [{'name': name, 'old': live['texts'][name], 'new': value}
                   for name, value in data['texts'].items() if live['texts'][name] != value]
        if data['compositions'] != live['compositions']:
            changed.append({'name': 'compositions', 'old': json.dumps(live['compositions']), 'new': json.dumps(data['compositions'])})
        decisions = [dict(r) for r in all_rows(c, 'SELECT decided_by,decision,note,decided_at FROM rule_approvals '
                                                  'WHERE sha256=? ORDER BY id', (sha,))]
        found.append({'id': path.parent.name, 'sha256': sha, 'title': _title(path.parent), 'author': _author(path.parent),
                      'path': path, 'changed': changed, 'decisions': decisions})
    return found


def why(proposal):
    accepted = [d['decided_by'] for d in proposal['decisions'] if d['decision'] == 'yes']
    declined = [d['decided_by'] for d in proposal['decisions'] if d['decision'] == 'no']
    text = f"{len(accepted)} of {NEEDED} approvals" + (f" ({', '.join(accepted)})" if accepted else '')
    if declined:
        text += f"; declined by {', '.join(declined)}, so it cannot apply unless the proposal changes"
    return text + '. Each person approves for themselves.'


def _write(path, raw):
    temporary = path.with_name(path.name + '.writing')
    temporary.write_bytes(raw)
    os.replace(temporary, path)


def apply(proposal, accepted):
    """Write the approval entry, then the rules file, after proving the pair loads under the two-human check."""
    from app.rules import load_rules
    raw = proposal['path'].read_bytes()
    if hashlib.sha256(raw).hexdigest() != proposal['sha256']:
        raise RuleError('The proposal changed; review the current version', 409)
    names = [row['decided_by'] for row in accepted]
    entry = {'sha256': proposal['sha256'], 'approved_by': names, 'approved_at': accepted[-1]['decided_at'],
             'note': ('Approved in Decisions: ' + ', '.join(f"{row['decided_by']} at {row['decided_at']}" for row in accepted) +
                      f". Proposal docs/proposals/{proposal['id']}. Written by the server from signed-in decisions (task 2c56ad7a); "
                      'a person commits the files.')}
    approvals_path, rules_path = rules_dir() / 'APPROVALS.json', rules_dir() / 'agent-rules.json'
    ledger = json.loads(approvals_path.read_bytes())
    ledger_raw = (json.dumps(ledger + [entry], indent=2) + '\n').encode('utf-8')
    check = proposal['path'].with_name('approvals.check.json')
    try:
        check.write_bytes(ledger_raw)
        load_rules(proposal['path'], check)  # Fails closed before anything live is touched.
    finally:
        check.unlink(missing_ok=True)
    _write(approvals_path, ledger_raw)  # An entry for a digest that is not live yet is harmless.
    _write(rules_path, raw)
    return entry


def decide(c, actor, payload, current):
    """Record one person's decision on a proposal; apply it on the second distinct acceptance with no decline."""
    proposal = next((p for p in pending(c) if p['id'] == payload['id'] and p['sha256'] == payload['revision']), None)
    if proposal is None or current is None:
        raise RuleError('This proposal is no longer waiting on you', 409)
    if any(d['decided_by'] == actor for d in proposal['decisions']):
        raise RuleError('You already decided this proposal', 409)
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    c.exec_driver_sql('INSERT INTO rule_approvals(proposal,sha256,decided_by,principal_id,decision,note,decided_at) '
                      'VALUES (?,?,?,?,?,?,?)', (proposal['id'], proposal['sha256'], actor, payload['_principal_id'],
                                                 payload['decision'], payload['note'], now))
    decisions = proposal['decisions'] + [{'decided_by': actor, 'decision': payload['decision'], 'note': payload['note'], 'decided_at': now}]
    accepted = [d for d in decisions if d['decision'] == 'yes']
    declined = any(d['decision'] == 'no' for d in decisions)
    result = {'kind': 'rule_texts', 'id': proposal['id'], 'decision': payload['decision'], 'approvals': len(accepted),
              'applied': False, 'restart_required': False}
    if payload['decision'] == 'yes' and len(accepted) >= NEEDED and not declined:
        entry = apply(proposal, accepted)
        result.update(applied=True, restart_required=True, approved_by=entry['approved_by'],
                      message=(f"Approved by {' and '.join(entry['approved_by'])}. The server wrote rules/agent-rules.json and "
                               'rules/APPROVALS.json; a person must commit them, and the new texts take effect at restart.'))
    elif payload['decision'] == 'yes':
        result['message'] = f'Your approval is recorded ({len(accepted)} of {NEEDED}); the change applies when a second person accepts.'
    elif payload['decision'] == 'no':
        result['message'] = 'Declined. The change cannot apply unless the proposal changes.'
    else:
        result['message'] = 'Change requested; your note is recorded with the proposal.'
    return result
