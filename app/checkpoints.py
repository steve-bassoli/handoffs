"""Atomic progress checkpoints; closure here is never acceptance or payment."""
from uuid import uuid4

from app.services import RuleError, encode, now
from app.storage import all_rows, one
from app.workflow import phase


def checkpoint(service, c, actor, payload):
    task = service.detail(c, payload['id'])
    if actor not in (task['creator'], task['claimant']):
        raise RuleError('Only requester or current worker can checkpoint a task', 403)
    if task['status'] not in ('open', 'working', 'blocked', 'decomposed', 'awaiting_approval', 'delivered'):
        raise RuleError('Only unresolved tasks can be checkpointed')
    notes = payload['notes'].strip()
    if not notes or len(notes) > 30000:
        raise RuleError('Provide progress, remaining work and evidence notes (up to 30000 characters)', 422)
    if ('sk-' + 'proj-') in notes or '-----BEGIN PRIVATE KEY-----' in notes:
        raise RuleError('Keep credentials out of checkpoint notes', 422)
    children = all_rows(c, 'SELECT id FROM tasks WHERE parent_id=? ORDER BY id', (task['id'],))
    involved = [task['id']] + [child['id'] for child in children]
    for identifier in involved:
        running = one(c, "SELECT id FROM ai_runs WHERE task_id=? AND status IN ('queued','running')", (identifier,))
        detail = service.detail(c, identifier)
        review = (detail.get('proof') or {}).get('review') or {}
        if running or review.get('verdict') in ('queued', 'running'):
            raise RuleError('Wait for active work or review to stop before checkpointing')
    parent = service.detail(c, task['parent_id']) if task['parent_id'] else None
    if parent and phase(parent['status']) == 'Closed':
        raise RuleError('Cannot replace a child of a closed workflow')
    from app.complexity import validate_task_split
    try:
        if children:
            validate_task_split(task['complexity'], [service.detail(c, child['id'])['complexity'] for child in children])
        if parent:
            siblings = all_rows(c, 'SELECT id FROM tasks WHERE parent_id=?', (parent['id'],))
            validate_task_split(parent['complexity'], [service.detail(c, child['id'])['complexity'] for child in siblings])
    except ValueError as error:
        raise RuleError(str(error), 422) from None

    continuation_id = str(uuid4())
    checkpoint_data = {'previous_task_id': task['id'], 'notes': notes,
        'previous_state': task['status'], 'previous_claimant': task['claimant'],
        'previous_parent_id': task['parent_id'], 'children': [child['id'] for child in children],
        'artifact_url': '/api/v1/tasks/' + task['id'] + '/artifacts/download',
        'acceptance_carried_forward': False}
    links = list(dict.fromkeys(task['context_links'] + ['/#task=' + task['id'], checkpoint_data['artifact_url']]))
    target = task['claimant'] or task['target']
    c.exec_driver_sql('''INSERT INTO tasks
        (id,title,goal,criteria,repository,context_links,creator,target,gold,created_at,funded,parent_id)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
        (continuation_id, task['title'], task['goal'], encode(task['criteria']), task['repository'],
         encode(links), task['creator'], target, task['gold'], now(), task['funded'], task['parent_id']))
    c.exec_driver_sql('INSERT INTO accounts VALUES (?,?,?)', ('escrow:' + continuation_id, task['creator'], 'escrow'))
    reserved = service.balance(c, 'escrow:' + task['id'])
    if reserved:
        service.transfer(c, 'escrow:' + task['id'], 'escrow:' + continuation_id,
                         reserved, 'task_checkpointed', continuation_id)
    service.event(c, continuation_id, 'posted', actor, 'open',
        {'complexity': task['complexity'], 'work_type': task['work_type'],
         'checkpoint': checkpoint_data, **({'profile': task['profile']} if task['profile'] else {})})
    if task['depends_on']:
        service.event(c, continuation_id, 'dependencies_set', actor, 'open', {'depends_on': task['depends_on']})

    # Replace one workflow node, not a decomposition. Parent counts/levels remain unchanged.
    if parent:
        c.exec_driver_sql('UPDATE tasks SET parent_id=NULL WHERE id=?', (task['id'],))
        service.event(c, parent['id'], 'child_continued', actor, parent['status'],
                      {'previous_task_id': task['id'], 'continuation_id': continuation_id})
    for child in children:
        detail = service.detail(c, child['id'])
        c.exec_driver_sql('UPDATE tasks SET parent_id=? WHERE id=?', (continuation_id, child['id']))
        service.event(c, child['id'], 'parent_continued', actor, detail['status'],
                      {'previous_task_id': task['id'], 'continuation_id': continuation_id})
    for node in service.workflow_nodes(c):
        if node['id'] == task['id'] or node['phase'] == 'Closed' or task['id'] not in node['depends_on']:
            continue
        service.event(c, node['id'], 'dependencies_set', actor, node['status'],
            {'depends_on': [continuation_id if identifier == task['id'] else identifier
                            for identifier in node['depends_on']],
             'checkpoint_replaced': task['id']})
    service.event(c, task['id'], 'checkpointed', actor, 'superseded',
                  {'continuation_id': continuation_id, **checkpoint_data})
    return service.detail(c, continuation_id)
