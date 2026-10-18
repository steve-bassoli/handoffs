"""Owner-run spawn of real child tickets from a parent (true parent_id), mirroring the AI follow-up confirm path.

Not an HTTP route: it is run locally by the launcher on explicit owner instruction, so the API gains no write surface.
Children are unfunded like confirmed follow-ups; the parent is recorded as decomposed with the child IDs.
"""
import argparse
import json
from uuid import uuid4

from app.adapters import DemoDeliveryVerifier
from app.complexity import validate_task_split
from app.services import RuleError, Service, encode, now
from app.storage import Database


def spawn_children(database, parent_id, children, actor, source):
    """children: 2-9 dicts with title, goal, criteria (list), complexity, work_type.

    HIGH SIGNAL decomposition rule: a HIGH splits into two or more HIGHs or two or more MEDIUMs (never mixed); a MEDIUM into two or more LOWs.
    """
    if not 2 <= len(children) <= 9:
        raise ValueError('A decomposition has two to nine children')
    db = Database(database)
    try:
        service = Service(db, DemoDeliveryVerifier())
        with db.write() as c:
            parent = service.detail(c, parent_id)
            if parent['status'] != 'open' or parent['complexity'] not in ('HIGH', 'MEDIUM'):
                raise RuleError('Spawn only from an open HIGH or MEDIUM ticket')
            validate_task_split(parent['complexity'], [child['complexity'] for child in children])
            created = []
            for index, child in enumerate(children):
                if not child.get('title') or not child.get('goal') or not child.get('criteria'):
                    raise ValueError('Each child needs a title, goal and criteria')
                identifier = str(uuid4())
                c.exec_driver_sql('''INSERT INTO tasks(id,title,goal,criteria,repository,context_links,
                    creator,target,gold,created_at,funded,parent_id) VALUES (?,?,?,?,?,?,?,?,?,?,0,?)''',
                    (identifier, child['title'][:160], child['goal'], encode(child['criteria']), parent['repository'],
                     encode(child.get('context_links') or parent['context_links']), actor, None, 1, now(), parent['id']))
                service.event(c, identifier, 'followup_confirmed', actor, 'open', {
                    'parent_id': parent['id'], 'proposal_index': index, 'complexity': child['complexity'],
                    'work_type': child.get('work_type', 'implementation'), 'spawned_via': source,
                    'assigned_agent': child.get('assigned_agent')})
                created.append(identifier)
            service.event(c, parent['id'], 'followups_confirmed', actor, 'decomposed', {
                'children': created, 'approved_indices': list(range(len(created))), 'acceptance_verified': False,
                'spawned_via': source})
        return created
    finally:
        db.engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True)
    parser.add_argument('--parent', required=True)
    parser.add_argument('--children', required=True, help='JSON file: array of child specs')
    parser.add_argument('--actor', default='steve')
    parser.add_argument('--source', required=True, help='Who proposed the split, for example bob (light mode)')
    args = parser.parse_args()
    specs = json.load(open(args.children, encoding='utf-8'))
    print(json.dumps(spawn_children(args.db, args.parent, specs, args.actor, args.source)))


if __name__ == '__main__':
    main()
