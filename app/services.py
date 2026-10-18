import hashlib
import json
import os
from contextvars import ContextVar
from datetime import datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.context import project_legacy
from app.prototype import auto_signoff_active
from app.workflow import ROLES, constellation, dependencies, disposition, phase, profile, validate_dependencies
from app.storage import all_rows, one


event_via = ContextVar('event_via', default=None)
event_intent = ContextVar('event_intent', default=None)
event_identity = ContextVar('event_identity', default=None)
auto_signoff = ContextVar('auto_signoff', default=False)


def now():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, sort_keys=True)


class RuleError(Exception):
    def __init__(self, message, status=409):
        self.message = message
        self.status = status


class Service:
    def __init__(self, db, verifier, clock=None, grant=None, demo_identity='refuse'):
        self.db = db
        self.verifier = verifier
        self.demo_identity = demo_identity
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.grant = grant if grant is not None else int(os.environ.get('HANDOFFS_MONTHLY_GOLD', '1000'))
        if self.grant <= 0:
            raise ValueError('HANDOFFS_MONTHLY_GOLD must be positive')

    def seed(self):
        with self.db.write() as c:
            c.exec_driver_sql("INSERT OR IGNORE INTO accounts VALUES ('issuance',NULL,'issuance')")
            for user, name, alias in [('steve', 'Steve', 'Steffen'), ('nate', 'Nate', 'Revrick'), ('will', 'Will', 'Bob')]:
                c.exec_driver_sql('INSERT OR IGNORE INTO users VALUES (?,?,?)', (user, name, alias))
                c.exec_driver_sql('INSERT OR IGNORE INTO accounts VALUES (?,?,?)', ('wallet:' + user, user, 'wallet'))

    def user(self, user_id):
        with self.db.engine.connect() as c:
            user = one(c, 'SELECT * FROM users WHERE id=?', (user_id,))
        if not user:
            raise RuleError('Unknown demo user', 401)
        return {**user, 'simulated_identity': True}

    def balance(self, c, account):
        return one(c, 'SELECT COALESCE(SUM(amount),0) AS gold FROM gold_entries WHERE account_id=?', (account,))['gold']

    def transfer(self, c, source, destination, gold, kind, task_id=None):
        if gold <= 0:
            raise RuleError('Gold must be positive', 422)
        if source != 'issuance' and self.balance(c, source) < gold:
            raise RuleError('Insufficient Gold')
        transaction = str(uuid4())
        c.exec_driver_sql('INSERT INTO gold_transactions VALUES (?,?,?,?)', (transaction, kind, task_id, now()))
        for account, amount in [(source, -gold), (destination, gold)]:
            c.exec_driver_sql('INSERT INTO gold_entries(transaction_id,account_id,amount) VALUES (?,?,?)', (transaction, account, amount))

    def grant_month(self, c, user):
        month = self.clock().astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m')
        existing = one(c, 'SELECT * FROM monthly_allocations WHERE user_id=? AND month=?', (user, month))
        if not existing:
            c.exec_driver_sql('INSERT INTO monthly_allocations VALUES (?,?,?)', (user, month, self.grant))
            self.transfer(c, 'issuance', 'wallet:' + user, self.grant, 'monthly_grant')
        return month

    def stats(self, user):
        with self.db.write() as c:
            month = self.grant_month(c, user)
            available = self.balance(c, 'wallet:' + user)
            reserved = one(c, "SELECT COALESCE(SUM(e.amount),0) AS gold FROM accounts a LEFT JOIN gold_entries e ON e.account_id=a.id WHERE a.user_id=? AND a.kind='escrow'", (user,))['gold']
            year, month_number = map(int, month.split('-'))
            next_month = datetime(year + (month_number == 12), month_number % 12 + 1, 1, tzinfo=ZoneInfo('America/New_York'))
            work = all_rows(c, """SELECT e.state FROM tasks b JOIN events e ON e.seq=(SELECT MAX(seq) FROM events WHERE task_id=b.id)
                WHERE b.creator=? OR b.target=? OR EXISTS(SELECT 1 FROM events x WHERE x.task_id=b.id AND x.actor=? AND x.kind='taken')""", (user, user, user))
            return {'user_id': user, 'available_gold': available, 'reserved_gold': reserved,
                    'monthly_gold': one(c, 'SELECT gold FROM monthly_allocations WHERE user_id=? AND month=?', (user, month))['gold'],
                    'month': month, 'next_allocation': next_month.isoformat(), 'simulated_identity': True,
                    'active_count': sum(r['state'] in ('open', 'pending', 'working', 'blocked', 'delivered', 'awaiting_approval', 'decomposed') for r in work),
                    'completed_count': sum(r['state'] in ('settled', 'completed') for r in work)}

    def transactions(self, user, limit, offset):
        with self.db.engine.connect() as c:
            return all_rows(c, "SELECT t.*, e.amount, a.kind AS account_kind FROM gold_transactions t JOIN gold_entries e ON e.transaction_id=t.id JOIN accounts a ON a.id=e.account_id WHERE a.user_id=? ORDER BY e.seq DESC LIMIT ? OFFSET ?", (user, limit, offset))

    def event(self, c, task_id, kind, actor, state, data=None):
        record = dict(data or {})
        identity = event_identity.get()
        # Payloads cannot forge these fields; non-request work carries none.
        if identity:
            record['principal'] = identity['principal']
            record['principal_id'] = identity['principal_id']
        else:
            record.pop('principal', None); record.pop('principal_id', None)
        if auto_signoff.get():
            record['signoff'] = 'prototype-auto'
        via = event_via.get()
        if via is not None:
            record['via'] = via
        if event_intent.get() is not None:
            record['action_intent'] = event_intent.get()
        c.exec_driver_sql('INSERT INTO events(task_id,kind,actor,state,data,created_at) VALUES (?,?,?,?,?,?)',
                          (task_id, kind, actor, state, encode(record), now()))

    def detail(self, c, task_id):
        task = one(c, 'SELECT * FROM tasks WHERE id=?', (task_id,))
        if not task:
            raise RuleError('Task not found', 404)
        events = all_rows(c, 'SELECT * FROM events WHERE task_id=? ORDER BY seq', (task_id,))
        for event in events:
            event['data'] = json.loads(event['data'])
        task['criteria'] = json.loads(task['criteria'])
        task['context_links'] = json.loads(task['context_links'])
        task['legacy'] = json.loads(task['legacy']) if task['legacy'] else None
        project_legacy(task)
        if task['legacy']:
            documents = all_rows(c, 'SELECT source_id,data FROM import_records WHERE source=? AND source_id LIKE ? ORDER BY source_id',
                                 (task['legacy']['source'], task['legacy']['directory'] + '/%'))
            task['legacy']['documents'] = [{'path': d['source_id'], **json.loads(d['data'])} for d in documents if not d['source_id'].endswith('.json')]
        task['status'] = events[-1]['state']
        task['complexity'] = next((event['data']['complexity'] for event in reversed(events)
                                    if event['data'].get('complexity') in ('HIGH', 'MEDIUM', 'LOW')), 'HIGH')
        task['work_type'] = next((event['data']['work_type'] for event in reversed(events)
                                   if event['data'].get('work_type') in ('implementation', 'verification')), 'implementation')
        task['claimant'] = next((e['actor'] for e in reversed(events) if e['kind'] == 'taken'), None)
        task['completed_by'] = next((e['data'].get('worker', e['actor']) for e in reversed(events)
                                      if e['kind'] in ('legacy:completed', 'locally_verified', 'proof_completed')), None)
        task['events'] = events
        task['checkpoint'] = next((e['data']['checkpoint'] for e in events if e['kind'] == 'posted' and 'checkpoint' in e['data']), None)
        task['continuation_id'] = next((e['data']['continuation_id'] for e in reversed(events) if e['kind'] == 'checkpointed'), None)
        task['profile'] = profile(events)
        task['depends_on'] = dependencies(events)
        task['phase'] = phase(task['status'])
        task['disposition'] = disposition(task['status'])
        task['coordinates'] = {'complexity': task['complexity'], 'phase': task['phase'],
            'validation_target': (task['profile'] or {}).get('validation_scope')}
        task['roles'] = ROLES
        task['packages'] = [{'id': event['seq'], 'actor': event['actor'], 'created_at': event['created_at'],
                              **{key: value for key, value in event['data'].items() if key != 'files'}}
                             for event in events if event['kind'] == 'package_attached']
        task['deliveries'] = all_rows(c, 'SELECT * FROM deliveries WHERE task_id=? ORDER BY created_at,id', (task_id,))
        ai = getattr(self, 'ai', None)
        task['ai_options'] = ai.options() if ai else None
        row = one(c, 'SELECT * FROM ai_runs WHERE task_id=?', (task_id,))
        if ai and row:
            row['data'] = json.loads(row['data'])
            task['ai_run'] = ai.public(row)
        else:
            task['ai_run'] = None
        if getattr(self, 'proofs', None):
            self.proofs.project(c, task)
        return task

    def get(self, task_id):
        with self.db.engine.connect() as c:
            exact = one(c, 'SELECT id FROM tasks WHERE id=?', (task_id,))
            if not exact:
                # Literal prefixes, not SQL LIKE patterns. Writes retain exact IDs.
                if len(task_id) < 8:
                    raise RuleError('Task not found', 404)
                matches = all_rows(c, 'SELECT id FROM tasks WHERE substr(id,1,?)=? ORDER BY id',
                                   (len(task_id), task_id))
                if not matches:
                    raise RuleError('Task not found', 404)
                if len(matches) > 1:
                    raise RuleError({'message': 'Ambiguous task prefix',
                                     'matches': [row['id'] for row in matches]}, 409)
                task_id = matches[0]['id']
            return self.detail(c, task_id)

    def summary(self):
        # A single statement projects all latest states and metadata; no detail() loop.
        with self.db.engine.connect() as c:
            rows = all_rows(c, '''SELECT b.id,b.title,e.state AS status,
                (SELECT actor FROM events WHERE task_id=b.id AND kind='taken'
                 ORDER BY seq DESC LIMIT 1) AS claimant,
                COALESCE((SELECT json_extract(data,'$.complexity') FROM events
                 WHERE task_id=b.id AND json_extract(data,'$.complexity') IN ('HIGH','MEDIUM','LOW')
                 ORDER BY seq DESC LIMIT 1),'HIGH') AS complexity
                FROM tasks b JOIN events e ON e.seq=(SELECT MAX(seq) FROM events WHERE task_id=b.id)
                ORDER BY b.created_at DESC,b.id''')
        counts, active = {}, []
        for row in rows:
            state = row['status']
            counts[state] = counts.get(state, 0) + 1
            # Reuse workflow phase for closure; decomposition delegates work to children.
            if phase(state) != 'Closed' and state != 'decomposed':
                active.append({**row, 'short_id': row['id'][:8]})
        return {'counts': counts, 'total': len(rows), 'active': active, 'checked_at': now()}

    def listing(self, user, view, limit, offset, query='', statuses=None, creator=None):
        with self.db.engine.connect() as c:
            scope = '''FROM tasks b JOIN events e ON e.seq=(SELECT MAX(seq) FROM events WHERE task_id=b.id)
                WHERE (?='all' OR (?='open' AND (e.state='open' OR (e.state='pending' AND b.funded=0 AND b.target IS NULL))) OR
                (?='mine' AND (b.creator=? OR b.target=? OR EXISTS(SELECT 1 FROM events x WHERE x.task_id=b.id AND x.actor=? AND x.kind='taken'))))
                AND (b.title LIKE ? OR b.id LIKE ?)
                AND (? IS NULL OR e.state IN (SELECT value FROM json_each(?)))'''
            params = (view, view, view, user, user, user, '%' + query + '%', '%' + query + '%',
                      encode(statuses) if statuses is not None else None, encode(statuses or []))
            # Facet ignores the creator filter so the picker keeps every choice.
            creators = [r['creator'] for r in all_rows(c, 'SELECT DISTINCT b.creator ' + scope + ' ORDER BY b.creator', params)]
            records = all_rows(c, '''SELECT b.*, e.state AS status,
                (SELECT actor FROM events WHERE task_id=b.id AND kind='taken' ORDER BY seq DESC LIMIT 1) AS claimant
                ''' + scope + ''' AND (? IS NULL OR b.creator=?)
                ORDER BY b.created_at DESC,b.id LIMIT ? OFFSET ?''', params + (creator, creator, limit, offset))
            for record in records:
                classification = one(c, "SELECT json_extract(data,'$.complexity') AS complexity FROM events WHERE task_id=? AND json_extract(data,'$.complexity') IN ('HIGH','MEDIUM','LOW') ORDER BY seq DESC LIMIT 1", (record['id'],))
                record['complexity'] = classification['complexity'] if classification else 'HIGH'
                record['phase'] = phase(record['status'])
                record['disposition'] = disposition(record['status'])
            fields = ('id', 'title', 'gold', 'status', 'creator', 'target', 'claimant', 'created_at', 'funded', 'parent_id', 'complexity', 'phase', 'disposition')
            return {'items': [{key: r[key] for key in fields} for r in records], 'limit': limit,
                    'offset': offset, 'creators': creators, 'checked_at': now()}

    def execute(self, actor, key, action, payload):
        # Authorization must precede the actor-scoped idempotency cache.
        token = None
        if action in ('ai_proof_human', 'close_human') and self.require_human_acceptance(actor):
            token = auto_signoff.set(True)
        try:
            return self._execute(actor, key, action, payload)
        finally:
            if token is not None:
                auto_signoff.reset(token)

    def _execute(self, actor, key, action, payload):
        fingerprint = hashlib.sha256(encode([action, payload]).encode()).hexdigest()
        with self.db.write() as c:
            cached = one(c, 'SELECT * FROM operations WHERE actor=? AND key=?', (actor, key))
            if cached:
                if cached['fingerprint'] != fingerprint:
                    raise RuleError('Idempotency key already used for different input')
                return json.loads(cached['result'])
            if payload.get('id') and action != 'attach_package':
                latest = one(c, 'SELECT state FROM events WHERE task_id=? ORDER BY seq DESC LIMIT 1', (payload['id'],))
                if latest and latest['state'] == 'superseded':
                    raise RuleError('This task is closed; use its linked continuation')
            if not action.startswith('ai_') and action not in ('attach_package', 'checkpoint'):
                self.grant_month(c, actor)
            result = getattr(self, 'do_' + action)(c, actor, payload)
            c.exec_driver_sql('INSERT INTO operations VALUES (?,?,?,?)', (actor, key, fingerprint, encode(result)))
            return result

    def do_post(self, c, actor, payload):
        from app.ai import read_source
        source = read_source(payload.get('source_zip'))
        task_id = str(uuid4())
        target = payload.get('target')
        if target and not one(c, 'SELECT id FROM users WHERE id=?', (target,)):
            raise RuleError('Unknown target', 422)
        c.exec_driver_sql('INSERT INTO tasks(id,title,goal,criteria,repository,context_links,creator,target,gold,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
                          (task_id, payload['title'], payload['goal'], encode(payload['criteria']),
                           payload['repository'], encode(payload['context_links']), actor, target, payload['gold'], now()))
        c.exec_driver_sql('INSERT INTO accounts VALUES (?,?,?)', ('escrow:' + task_id, actor, 'escrow'))
        self.transfer(c, 'wallet:' + actor, 'escrow:' + task_id, payload['gold'], 'task_funded', task_id)
        self.event(c, task_id, 'posted', actor, 'open', {'complexity': payload.get('complexity', 'HIGH'),
                                                       'work_type': payload.get('work_type', 'implementation'),
                                                       **({'profile': payload['profile']} if payload.get('profile') else {}),
                                                       **({'source_files': source} if source else {})})
        return self.detail(c, task_id)

    def do_edit(self, c, actor, payload):
        task = self.detail(c, payload['id'])
        if actor != task['creator']:
            raise RuleError('Only the creator can edit this task', 403)
        if task['status'] != 'open' or task['claimant'] is not None:
            raise RuleError('Only open, unclaimed tasks can be edited')
        fields = ('title', 'goal', 'criteria', 'complexity', 'work_type',
                  'context_links', 'repository', 'target', 'gold')
        if set(payload) != {'id', *fields}:
            raise RuleError('Edit requires exactly the editable task fields', 422)
        target = payload['target']
        if target and not one(c, 'SELECT id FROM users WHERE id=?', (target,)):
            raise RuleError('Unknown target', 422)
        gold = payload['gold']
        if type(gold) is not int or gold <= 0:
            raise RuleError('Gold must be a positive integer', 422)
        changes = {field: {'before': task[field], 'after': payload[field]}
                   for field in fields if task[field] != payload[field]}
        difference = gold - task['gold']
        if difference:
            if not task['funded']:
                raise RuleError('Gold cannot be changed on an unfunded task')
            wallet, escrow = 'wallet:' + actor, 'escrow:' + task['id']
            source, destination = (wallet, escrow) if difference > 0 else (escrow, wallet)
            self.transfer(c, source, destination, abs(difference), 'task_edited', task['id'])
        c.exec_driver_sql(
            'UPDATE tasks SET title=?,goal=?,criteria=?,repository=?,context_links=?,target=?,gold=? WHERE id=?',
            (payload['title'], payload['goal'], encode(payload['criteria']),
             payload['repository'], encode(payload['context_links']), target, gold, task['id']))
        # Classification is projected from events; never rewrite an earlier event.
        classification = {field: payload[field] for field in ('complexity', 'work_type')
                          if field in changes}
        self.event(c, task['id'], 'edited', actor, 'open',
                   {'changes': changes, **classification})
        return self.detail(c, task['id'])

    def do_checkpoint(self, c, actor, payload):
        from app.checkpoints import checkpoint
        return checkpoint(self, c, actor, payload)

    def workflow_nodes(self, c):
        records = all_rows(c, '''SELECT b.id,b.title,b.parent_id,e.state AS status FROM tasks b
            JOIN events e ON e.seq=(SELECT MAX(seq) FROM events WHERE task_id=b.id)''')
        for record in records:
            latest = one(c, "SELECT data FROM events WHERE task_id=? AND kind='dependencies_set' ORDER BY seq DESC LIMIT 1", (record['id'],))
            record['depends_on'] = json.loads(latest['data'])['depends_on'] if latest else []
            record['phase'] = phase(record['status'])
        return records

    def constellation(self, task_id):
        with self.db.engine.connect() as c:
            self.detail(c, task_id)
            graph = constellation(self.workflow_nodes(c))
        connected = {task_id}
        while True:
            expanded = connected | {edge[key] for edge in graph['edges'] if edge['from'] in connected or edge['to'] in connected for key in ('from', 'to')}
            if expanded == connected:
                break
            connected = expanded
        return {'nodes': [node for node in graph['nodes'] if node['id'] in connected],
                'edges': [edge for edge in graph['edges'] if edge['from'] in connected]}

    def workflow_owner(self, c, actor, task_id):
        task = self.detail(c, task_id)
        if actor not in (task['creator'], task['claimant']):
            raise RuleError('Only requester or current worker can change the workflow contract', 403)
        if task['phase'] == 'Closed':
            raise RuleError('Closed workflow records are immutable; use an explicit reopening')
        return task

    def do_ai_profile(self, c, actor, payload):
        task = self.workflow_owner(c, actor, payload['id'])
        if ('sk-' + 'proj-') in encode(payload['profile']):
            raise RuleError('Keep secrets out of task context', 422)
        self.event(c, task['id'], 'profile_recorded', actor, task['status'], {'profile': payload['profile']})
        return self.detail(c, task['id'])

    def do_ai_dependencies(self, c, actor, payload):
        task = self.workflow_owner(c, actor, payload['id'])
        try:
            validate_dependencies(self.workflow_nodes(c), task['id'], payload['depends_on'])
        except ValueError as error:
            raise RuleError(str(error), 422) from None
        self.event(c, task['id'], 'dependencies_set', actor, task['status'], {'depends_on': payload['depends_on']})
        return self.detail(c, task['id'])

    def do_ai_reopen(self, c, actor, payload):
        task = self.detail(c, payload['id'])
        if actor not in (task['creator'], task['target'], task['claimant'], task['completed_by']):
            raise RuleError('Only task participants can reopen it', 403)
        if task['status'] not in ('completed', 'settled'):
            raise RuleError('Only a completed task can be reopened')
        if task['ai_run']:
            raise RuleError('A prior AI run must remain intact; this reopen path supports tasks without an existing run')
        self.event(c, task['id'], 'reopened', actor, 'open', {'complexity': payload['complexity'],
            'note': payload['note'], 'previous_state': task['status'], 'previous_completed_by': task['completed_by']})
        return self.detail(c, task['id'])

    def do_attach_package(self, c, actor, payload):
        from app.packages import attach
        return attach(self, c, actor, payload)

    def require_live(self, task):
        if not task['funded'] and not task['parent_id']:
            raise RuleError('Legacy record is historical and unfunded')

    def do_take(self, c, actor, payload):
        task = self.detail(c, payload['id'])
        self.require_live(task)
        if task['status'] != 'open':
            raise RuleError('Task is already taken or closed')
        if task['target'] not in (None, actor):
            raise RuleError('This task is not available to this user', 403)
        self.event(c, task['id'], 'taken', actor, 'working')
        return self.detail(c, task['id'])

    def do_status(self, c, actor, payload):
        task = self.detail(c, payload['id'])
        self.require_live(task)
        if actor != task['claimant']:
            raise RuleError('Only the claimant can update progress', 403)
        if task['status'] not in ('working', 'blocked'):
            raise RuleError('Task is not in progress')
        self.event(c, task['id'], payload['status'], actor, payload['status'], {'note': payload['note']})
        return self.detail(c, task['id'])

    def do_deliver(self, c, actor, payload):
        task = self.detail(c, payload['id'])
        self.require_live(task)
        if actor != task['claimant']:
            raise RuleError('Only the claimant can deliver', 403)
        if task['status'] not in ('working', 'blocked'):
            raise RuleError('Task is not in progress')
        verification = self.verifier.verify(payload['pr_url'])
        if verification['verified']:
            self.proofs.require(c, task)
        delivery_id = str(uuid4())
        c.exec_driver_sql('INSERT INTO deliveries VALUES (?,?,?,?,?,?,?)',
                          (delivery_id, task['id'], actor, payload['pr_url'], payload['evidence'], int(verification['simulated']), now()))
        self.event(c, task['id'], 'delivered', actor, 'delivered', {'delivery_id': delivery_id, 'verification': verification})
        if verification['verified'] and task['funded']:
            self.settle(c, task['id'], actor)
        return self.detail(c, task['id'])

    def settle(self, c, task_id, actor):
        task = self.detail(c, task_id)
        self.require_live(task)
        if task['status'] != 'delivered':
            raise RuleError('Task is not awaiting payment')
        delivered = next(e for e in reversed(task['events']) if e['kind'] == 'delivered')
        if not delivered['data']['verification']['verified']:
            raise RuleError('Delivery is not verified')
        receipt = self.proofs.require(c, task)
        self.transfer(c, 'escrow:' + task_id, 'wallet:' + task['claimant'], task['gold'], 'task_paid', task_id)
        self.event(c, task_id, 'paid', actor, 'settled', {'delivery_id': delivered['data']['delivery_id'], **receipt})

    def do_settle(self, c, actor, payload):
        task = self.detail(c, payload['id'])
        if actor not in (task['creator'], task['claimant']):
            raise RuleError('Only participants can request settlement', 403)
        self.settle(c, task['id'], actor)
        return self.detail(c, task['id'])

    def do_cancel(self, c, actor, payload):
        task = self.detail(c, payload['id'])
        self.require_live(task)
        if actor != task['creator']:
            raise RuleError('Only the requester can cancel', 403)
        if task['status'] != 'open':
            raise RuleError('Only unclaimed tasks can be cancelled in this prototype')
        if task['funded']:
            self.transfer(c, 'escrow:' + task['id'], 'wallet:' + actor, task['gold'], 'task_refunded', task['id'])
        self.event(c, task['id'], 'cancelled', actor, 'cancelled')
        return self.detail(c, task['id'])

    def do_review(self, c, actor, payload):
        task = self.detail(c, payload['id'])
        self.require_live(task)
        if actor != task['creator']:
            raise RuleError('Only the requester can review', 403)
        if not task['deliveries']:
            raise RuleError('Nothing has been delivered')
        self.event(c, task['id'], payload['decision'], actor, task['status'], {'note': payload['note']})
        return self.detail(c, task['id'])

    def do_ai_start(self, c, actor, payload):
        return self.ai.start(c, actor, payload)

    def do_accept(self, c, actor, payload):
        # One transaction: take rules apply, and an AI start failure leaves the task unclaimed.
        self.do_take(c, actor, {'id': payload['id']})
        return self.ai.start(c, actor, payload)

    def do_ai_answer(self, c, actor, payload):
        return self.ai.answer(c, actor, payload)

    def do_ai_confirm(self, c, actor, payload):
        return self.ai.confirm(c, actor, payload)

    def do_ai_retry(self, c, actor, payload):
        return self.ai.retry(c, actor, payload)

    def do_ai_complete(self, c, actor, payload):
        return self.ai.complete(c, actor, payload)

    def do_close_human(self, c, actor, payload):
        import base64
        task = self.detail(c, payload['id'])
        if actor != task['claimant']:
            raise RuleError('Only the claimant can update progress', 403)
        # execute owns the transaction; any refusal rolls back every step.
        value = dict(task.get('profile') or {})
        value.setdefault('validation_scope', 'SIM')
        value.setdefault('migration_stage', 'WRAP')
        value.update(baseline_revision=payload['baseline'],
                     candidate_revision=payload['candidate'],
                     environment=payload['environment'],
                     knowledge={'known': [], 'assumed': [],
                                'unknown': payload.get('unknown', [])})
        self.do_ai_profile(c, actor, {'id': task['id'], 'profile': value})
        self.do_ai_proof_attach(c, actor, {
            'id': task['id'], 'filename': payload.get('filename', 'evidence.txt'),
            'media_type': 'text/plain',
            'content_base64': base64.b64encode(payload['evidence'].encode('utf-8')).decode('ascii'),
            'description': payload['evidence'][:2000]})
        self.do_ai_proof_human(c, actor, {
            'id': task['id'], 'accepted': True, 'note': payload['evidence'][:2000],
            'review_basis': 'human-only'})
        return self.do_ai_proof_complete(c, actor, {
            'id': task['id'], 'note': payload['evidence'][:2000]})

    def do_ai_proof_attach(self, c, actor, payload):
        return self.proofs.attach(c, actor, payload)

    def do_ai_proof_queue(self, c, actor, payload):
        return self.proofs.queue(c, actor, payload['id'])

    def require_human_acceptance(self, actor):
        identity = event_identity.get() or {}
        principal = identity.get('principal')
        allowed = principal == 'human' or (
            principal == 'demo-header' and self.demo_identity == 'allow')
        if identity.get('user_id') != actor or not identity.get('principal_id'):
            raise RuleError('Human acceptance requires a signed-in person', 403)
        if allowed:
            return False
        # Prototype-only bypass with a hard cutoff (app/prototype.py); recorded as signoff: prototype-auto.
        if auto_signoff_active():
            return True
        raise RuleError('Human acceptance requires a signed-in person', 403)

    def do_ai_proof_human(self, c, actor, payload):
        self.require_human_acceptance(actor)
        return self.proofs.human(c, actor, payload)

    def do_ai_proof_complete(self, c, actor, payload):
        return self.proofs.complete(c, actor, payload)

    def hierarchy_violations(self):
        """Audit every parent and its children against the HIGH SIGNAL decomposition rule (read-only)."""
        from app.complexity import validate_task_split
        found = []
        with self.db.engine.connect() as c:
            parents = all_rows(c, 'SELECT parent_id, GROUP_CONCAT(id) AS children FROM tasks WHERE parent_id IS NOT NULL GROUP BY parent_id')
            for row in parents:
                parent = self.detail(c, row['parent_id'])
                kids = [self.detail(c, child) for child in row['children'].split(',')]
                try:
                    validate_task_split(parent['complexity'], [kid['complexity'] for kid in kids])
                except ValueError as error:
                    found.append({'parent': parent['id'], 'parent_level': parent['complexity'],
                                  'children': {kid['id']: kid['complexity'] for kid in kids}, 'reason': str(error)})
        return found

    def lineage(self, task_id):
        with self.db.engine.connect() as c:
            task = self.detail(c, task_id)
            root = task['id']
            while task['parent_id']:
                task = self.detail(c, task['parent_id'])
                root = task['id']
            rows = all_rows(c, '''WITH RECURSIVE tree(id) AS (
                SELECT id FROM tasks WHERE id=? UNION ALL
                SELECT b.id FROM tasks b JOIN tree ON b.parent_id=tree.id
            ) SELECT b.id,b.parent_id,b.title,e.state AS status FROM tasks b JOIN tree ON b.id=tree.id
              JOIN events e ON e.seq=(SELECT MAX(seq) FROM events WHERE task_id=b.id)
              ORDER BY b.created_at,b.id''', (root,))
            return {'root_id': root, 'items': rows}
