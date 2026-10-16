import hashlib
import json
import os
from datetime import datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.context import project_legacy
from app.storage import all_rows, one


def now():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, sort_keys=True)


class RuleError(Exception):
    def __init__(self, message, status=409):
        self.message = message
        self.status = status


class Service:
    def __init__(self, db, verifier, clock=None, grant=None):
        self.db = db
        self.verifier = verifier
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

    def transfer(self, c, source, destination, gold, kind, bounty_id=None):
        if gold <= 0:
            raise RuleError('Gold must be positive', 422)
        if source != 'issuance' and self.balance(c, source) < gold:
            raise RuleError('Insufficient Gold')
        transaction = str(uuid4())
        c.exec_driver_sql('INSERT INTO gold_transactions VALUES (?,?,?,?)', (transaction, kind, bounty_id, now()))
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
            work = all_rows(c, """SELECT e.state FROM bounties b JOIN events e ON e.seq=(SELECT MAX(seq) FROM events WHERE bounty_id=b.id)
                WHERE b.creator=? OR b.target=? OR EXISTS(SELECT 1 FROM events x WHERE x.bounty_id=b.id AND x.actor=? AND x.kind='taken')""", (user, user, user))
            return {'user_id': user, 'available_gold': available, 'reserved_gold': reserved,
                    'monthly_gold': one(c, 'SELECT gold FROM monthly_allocations WHERE user_id=? AND month=?', (user, month))['gold'],
                    'month': month, 'next_allocation': next_month.isoformat(), 'simulated_identity': True,
                    'active_count': sum(r['state'] in ('open', 'pending', 'working', 'blocked', 'delivered') for r in work),
                    'completed_count': sum(r['state'] in ('settled', 'completed') for r in work)}

    def transactions(self, user, limit, offset):
        with self.db.engine.connect() as c:
            return all_rows(c, "SELECT t.*, e.amount, a.kind AS account_kind FROM gold_transactions t JOIN gold_entries e ON e.transaction_id=t.id JOIN accounts a ON a.id=e.account_id WHERE a.user_id=? ORDER BY e.seq DESC LIMIT ? OFFSET ?", (user, limit, offset))

    def event(self, c, bounty_id, kind, actor, state, data=None):
        c.exec_driver_sql('INSERT INTO events(bounty_id,kind,actor,state,data,created_at) VALUES (?,?,?,?,?,?)',
                          (bounty_id, kind, actor, state, encode(data or {}), now()))

    def detail(self, c, bounty_id):
        bounty = one(c, 'SELECT * FROM bounties WHERE id=?', (bounty_id,))
        if not bounty:
            raise RuleError('Bounty not found', 404)
        events = all_rows(c, 'SELECT * FROM events WHERE bounty_id=? ORDER BY seq', (bounty_id,))
        for event in events:
            event['data'] = json.loads(event['data'])
        bounty['criteria'] = json.loads(bounty['criteria'])
        bounty['context_links'] = json.loads(bounty['context_links'])
        bounty['legacy'] = json.loads(bounty['legacy']) if bounty['legacy'] else None
        project_legacy(bounty)
        if bounty['legacy']:
            documents = all_rows(c, 'SELECT source_id,data FROM import_records WHERE source=? AND source_id LIKE ? ORDER BY source_id',
                                 (bounty['legacy']['source'], bounty['legacy']['directory'] + '/%'))
            bounty['legacy']['documents'] = [{'path': d['source_id'], **json.loads(d['data'])} for d in documents if not d['source_id'].endswith('.json')]
        bounty['status'] = events[-1]['state']
        bounty['claimant'] = next((e['actor'] for e in reversed(events) if e['kind'] == 'taken'), None)
        bounty['completed_by'] = next((e['actor'] for e in reversed(events)
                                      if e['kind'] in ('legacy:completed', 'locally_verified')), None)
        bounty['events'] = events
        bounty['packages'] = [{'id': event['seq'], 'actor': event['actor'], 'created_at': event['created_at'],
                              **{key: value for key, value in event['data'].items() if key != 'files'}}
                             for event in events if event['kind'] == 'package_attached']
        bounty['deliveries'] = all_rows(c, 'SELECT * FROM deliveries WHERE bounty_id=? ORDER BY created_at,id', (bounty_id,))
        ai = getattr(self, 'ai', None)
        row = one(c, 'SELECT * FROM ai_runs WHERE bounty_id=?', (bounty_id,))
        if ai and row:
            row['data'] = json.loads(row['data'])
            bounty['ai_run'] = ai.public(row)
        else:
            bounty['ai_run'] = None
        return bounty

    def get(self, bounty_id):
        with self.db.engine.connect() as c:
            return self.detail(c, bounty_id)

    def listing(self, user, view, limit, offset, query=''):
        with self.db.engine.connect() as c:
            records = all_rows(c, '''SELECT b.*, e.state AS status,
                (SELECT actor FROM events WHERE bounty_id=b.id AND kind='taken' ORDER BY seq DESC LIMIT 1) AS claimant
                FROM bounties b JOIN events e ON e.seq=(SELECT MAX(seq) FROM events WHERE bounty_id=b.id)
                WHERE (?='all' OR (?='open' AND (e.state='open' OR (e.state='pending' AND b.funded=0 AND b.target IS NULL))) OR
                (?='mine' AND (b.creator=? OR b.target=? OR EXISTS(SELECT 1 FROM events x WHERE x.bounty_id=b.id AND x.actor=? AND x.kind='taken'))))
                AND (b.title LIKE ? OR b.id LIKE ?) ORDER BY b.created_at DESC,b.id LIMIT ? OFFSET ?''',
                (view, view, view, user, user, user, '%' + query + '%', '%' + query + '%', limit, offset))
            fields = ('id', 'title', 'gold', 'status', 'creator', 'target', 'claimant', 'created_at', 'funded', 'parent_id')
            return {'items': [{key: r[key] for key in fields} for r in records], 'limit': limit,
                    'offset': offset, 'checked_at': now()}

    def execute(self, actor, key, action, payload):
        fingerprint = hashlib.sha256(encode([action, payload]).encode()).hexdigest()
        with self.db.write() as c:
            cached = one(c, 'SELECT * FROM operations WHERE actor=? AND key=?', (actor, key))
            if cached:
                if cached['fingerprint'] != fingerprint:
                    raise RuleError('Idempotency key already used for different input')
                return json.loads(cached['result'])
            if not action.startswith('ai_') and action != 'attach_package':
                self.grant_month(c, actor)
            result = getattr(self, 'do_' + action)(c, actor, payload)
            c.exec_driver_sql('INSERT INTO operations VALUES (?,?,?,?)', (actor, key, fingerprint, encode(result)))
            return result

    def do_post(self, c, actor, payload):
        from app.ai import read_source
        source = read_source(payload.get('source_zip'))
        bounty_id = str(uuid4())
        target = payload.get('target')
        if target and not one(c, 'SELECT id FROM users WHERE id=?', (target,)):
            raise RuleError('Unknown target', 422)
        c.exec_driver_sql('INSERT INTO bounties(id,title,goal,criteria,repository,context_links,creator,target,gold,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
                          (bounty_id, payload['title'], payload['goal'], encode(payload['criteria']),
                           payload['repository'], encode(payload['context_links']), actor, target, payload['gold'], now()))
        c.exec_driver_sql('INSERT INTO accounts VALUES (?,?,?)', ('escrow:' + bounty_id, actor, 'escrow'))
        self.transfer(c, 'wallet:' + actor, 'escrow:' + bounty_id, payload['gold'], 'bounty_funded', bounty_id)
        self.event(c, bounty_id, 'posted', actor, 'open', {'source_files': source} if source else None)
        return self.detail(c, bounty_id)

    def do_attach_package(self, c, actor, payload):
        from app.packages import attach
        return attach(self, c, actor, payload)

    def require_live(self, bounty):
        if not bounty['funded'] and not bounty['parent_id']:
            raise RuleError('Legacy record is historical and unfunded')

    def do_take(self, c, actor, payload):
        bounty = self.detail(c, payload['id'])
        self.require_live(bounty)
        if bounty['status'] != 'open':
            raise RuleError('Bounty is already taken or closed')
        if actor == bounty['creator'] or bounty['target'] not in (None, actor):
            raise RuleError('This bounty is not available to this user', 403)
        self.event(c, bounty['id'], 'taken', actor, 'working')
        return self.detail(c, bounty['id'])

    def do_status(self, c, actor, payload):
        bounty = self.detail(c, payload['id'])
        self.require_live(bounty)
        if actor != bounty['claimant']:
            raise RuleError('Only the claimant can update progress', 403)
        if bounty['status'] not in ('working', 'blocked'):
            raise RuleError('Bounty is not in progress')
        self.event(c, bounty['id'], payload['status'], actor, payload['status'], {'note': payload['note']})
        return self.detail(c, bounty['id'])

    def do_deliver(self, c, actor, payload):
        bounty = self.detail(c, payload['id'])
        self.require_live(bounty)
        if actor != bounty['claimant']:
            raise RuleError('Only the claimant can deliver', 403)
        if bounty['status'] not in ('working', 'blocked'):
            raise RuleError('Bounty is not in progress')
        verification = self.verifier.verify(payload['pr_url'])
        delivery_id = str(uuid4())
        c.exec_driver_sql('INSERT INTO deliveries VALUES (?,?,?,?,?,?,?)',
                          (delivery_id, bounty['id'], actor, payload['pr_url'], payload['evidence'], int(verification['simulated']), now()))
        self.event(c, bounty['id'], 'delivered', actor, 'delivered', {'delivery_id': delivery_id, 'verification': verification})
        if verification['verified'] and bounty['funded']:
            self.settle(c, bounty['id'], actor)
        return self.detail(c, bounty['id'])

    def settle(self, c, bounty_id, actor):
        bounty = self.detail(c, bounty_id)
        self.require_live(bounty)
        if bounty['status'] != 'delivered':
            raise RuleError('Bounty is not awaiting payment')
        delivered = next(e for e in reversed(bounty['events']) if e['kind'] == 'delivered')
        if not delivered['data']['verification']['verified']:
            raise RuleError('Delivery is not verified')
        self.transfer(c, 'escrow:' + bounty_id, 'wallet:' + bounty['claimant'], bounty['gold'], 'bounty_paid', bounty_id)
        self.event(c, bounty_id, 'paid', actor, 'settled', {'delivery_id': delivered['data']['delivery_id']})

    def do_settle(self, c, actor, payload):
        bounty = self.detail(c, payload['id'])
        if actor not in (bounty['creator'], bounty['claimant']):
            raise RuleError('Only participants can request settlement', 403)
        self.settle(c, bounty['id'], actor)
        return self.detail(c, bounty['id'])

    def do_cancel(self, c, actor, payload):
        bounty = self.detail(c, payload['id'])
        self.require_live(bounty)
        if actor != bounty['creator']:
            raise RuleError('Only the requester can cancel', 403)
        if bounty['status'] != 'open':
            raise RuleError('Only unclaimed bounties can be cancelled in this prototype')
        if bounty['funded']:
            self.transfer(c, 'escrow:' + bounty['id'], 'wallet:' + actor, bounty['gold'], 'bounty_refunded', bounty['id'])
        self.event(c, bounty['id'], 'cancelled', actor, 'cancelled')
        return self.detail(c, bounty['id'])

    def do_review(self, c, actor, payload):
        bounty = self.detail(c, payload['id'])
        self.require_live(bounty)
        if actor != bounty['creator']:
            raise RuleError('Only the requester can review', 403)
        if not bounty['deliveries']:
            raise RuleError('Nothing has been delivered')
        self.event(c, bounty['id'], payload['decision'], actor, bounty['status'], {'note': payload['note']})
        return self.detail(c, bounty['id'])

    def do_ai_start(self, c, actor, payload):
        return self.ai.start(c, actor, payload)

    def do_ai_answer(self, c, actor, payload):
        return self.ai.answer(c, actor, payload)

    def do_ai_confirm(self, c, actor, payload):
        return self.ai.confirm(c, actor, payload)

    def do_ai_retry(self, c, actor, payload):
        return self.ai.retry(c, actor, payload)

    def do_ai_complete(self, c, actor, payload):
        return self.ai.complete(c, actor, payload)

    def lineage(self, bounty_id):
        with self.db.engine.connect() as c:
            task = self.detail(c, bounty_id)
            root = task['id']
            while task['parent_id']:
                task = self.detail(c, task['parent_id'])
                root = task['id']
            rows = all_rows(c, '''WITH RECURSIVE tree(id) AS (
                SELECT id FROM bounties WHERE id=? UNION ALL
                SELECT b.id FROM bounties b JOIN tree ON b.parent_id=tree.id
            ) SELECT b.id,b.parent_id,b.title,e.state AS status FROM bounties b JOIN tree ON b.id=tree.id
              JOIN events e ON e.seq=(SELECT MAX(seq) FROM events WHERE bounty_id=b.id)
              ORDER BY b.created_at,b.id''', (root,))
            return {'root_id': root, 'items': rows}
