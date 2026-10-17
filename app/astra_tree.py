"""Time-boxed Astra tree: a HIGH root, MEDIUM leads and LOW workers with a local message relay.

The trusted launcher holds every lease, pins every shelf and routes messages. Agents only read their
own pinned sources and return JSON; nothing they write is executed, applied, published or accepted.
Each round runs root -> leads -> workers; a node sees its parent's latest directive and its children's
latest reports. At most three levels, three children per parent and thirteen nodes.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import json
import os
from pathlib import Path
import threading
import time

import httpx

from app.agent_conduit import MISSION, converse, digest, read_source, save, stamp
from app.api_budget import upper_cents
from app.astra_agents import agent_lease
from app.automation_mode import MODES as AUTOMATION_MODES, MODEL_SETTINGS, current, models_by_level

MESSAGE_LIMIT = 4000
MAX_MESSAGES = 10
LEVELS = {1: 'HIGH', 2: 'MEDIUM', 3: 'LOW'}
MODELS = MODEL_SETTINGS  # Single-model plans (no automation mode): astra, sol, terra or luna for every level.
SHARED = ('messages is an array of {to, text}; to is an agent name, "parent", "children", "siblings" or "all". '
          'files are proposed relative path/content objects, never applied. pressure is 1-3.')
ROLE_RULES = {
    'coordinator': (' TREE ROLE coordinator (HIGH root). You plan rounds for your named children, route questions, '
        'resolve conflicting claims and decide when the goal is sufficiently met. Reply with one JSON object: summary, '
        'directives (object: child name -> instruction for the next round), messages, done (true only when no further '
        'round is useful), synthesis (object with plan, files, checks, limitations, open_questions_for_humans), '
        'pressure. You cannot launch agents. ' + SHARED),
    'lead': (' TREE ROLE lead (MEDIUM). Turn your parent directive into LOW instructions for your named workers, review '
        'their reports, resolve overlaps between them and report upward. Reply with one JSON object: summary, report '
        '(what your parent needs), directives (object: worker name -> instruction), messages, files, checks, '
        'limitations, pressure. You cannot launch agents. ' + SHARED),
    'worker': (' TREE ROLE worker (LOW). Follow your directive, answer questions in your inbox, and use read_source for '
        'evidence. Reply with one JSON object: summary, findings (array of {claim, evidence, status: '
        'observed|inferred|unknown}), messages, files, checks, limitations, pressure. ' + SHARED),
}


def clip(value, limit):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + ' …[clipped by relay]'


def pin(shelf):
    """Pin each alias to its current bytes and reject unreadable or secret-bearing sources before any paid call."""
    sources = {alias: {'path': str(Path(path).resolve()), 'sha256': digest(Path(path).read_bytes())}
               for alias, path in shelf.items()}
    if not sources or len(sources) > 40:
        raise ValueError('Each shelf needs 1-40 sources')
    for alias in sources:
        read_source(sources, alias)
    return sources


def outgoing(sender, candidate, names, nodes=None):
    """Validated messages only; unknown recipients are dropped, not guessed."""
    node = (nodes or {}).get(sender, {})
    parent = node.get('parent')
    groups = {'all': [n for n in names if n != sender],
              'parent': [parent] if parent else [],
              'children': list(node.get('children', [])),
              'siblings': [n for n in (nodes or {}).get(parent, {}).get('children', []) if n != sender] if parent else []}
    messages = []
    for item in (candidate or {}).get('messages', [])[:MAX_MESSAGES]:
        if isinstance(item, dict) and isinstance(item.get('text'), str) and item['text'].strip():
            target = item.get('to')
            recipients = groups.get(target) if target in groups else [target] if target in names and target != sender else []
            messages += [{'from': sender, 'to': name, 'text': clip(item['text'], MESSAGE_LIMIT)} for name in recipients]
    return messages


class Tree:
    def __init__(self, plan, session, minutes, transport=None, clock=time.monotonic, mode=None):
        self.plan, self.session, self.transport, self.clock = plan, Path(session), transport, clock
        self.started = clock()
        self.mode = mode
        if mode is not None:
            if mode not in AUTOMATION_MODES:
                raise ValueError('Automation mode must be one of ' + ', '.join(AUTOMATION_MODES))
            self.level_models = models_by_level(mode)
        elif plan.get('model', 'astra') in MODELS:
            self.level_models = {level: MODELS[plan.get('model', 'astra')] for level in (1, 2, 3)}
        else:
            raise ValueError('Plan model must be one of ' + ', '.join(MODELS))
        self.deadline = self.started + minutes * 60
        self.nodes = {'coordinator': {'role': 'Coordinates the tree.', 'shelf': plan['coordinator']['shelf'],
                                      'parent': None, 'level': 1, 'max_requests': 3, 'children': []}}
        self.add('coordinator', plan.get('children', plan.get('workers', [])))
        if len(self.nodes) > 13:
            raise ValueError('A tree has at most thirteen nodes')
        if mode is not None and (len(self.nodes) > AUTOMATION_MODES[mode]['agents'] or
                                 max(node['level'] for node in self.nodes.values()) > len(self.level_models)):
            raise ValueError(f"{mode} mode allows {AUTOMATION_MODES[mode]['summary']}")
        self.names = list(self.nodes)
        self.phases = [[name for name in self.names if self.nodes[name]['level'] == level] for level in (1, 2, 3)]
        self.phases = [phase for phase in self.phases if phase]
        self.shelves = {name: pin(node['shelf']) for name, node in self.nodes.items()}
        self.ordinals = {name: 1 for name in self.names}
        self.inbox = {name: [] for name in self.names}
        self.last = {name: None for name in self.names}
        self.state = {name: None for name in self.names}
        self.stopped = set()
        self.rounds = []
        self.lock = threading.Lock()

    def add(self, parent, children):
        level = self.nodes[parent]['level'] + 1
        if children and (level > 3 or not 1 <= len(children) <= 3):
            raise ValueError('At most three levels and one to three children per parent')
        for child in children:
            name = child['name']
            if name in self.nodes or name in ('all', 'parent', 'children', 'siblings'):
                raise ValueError('Agent names must be unique and not a message group')
            self.nodes[name] = {'role': child['role'], 'shelf': child['shelf'], 'parent': parent, 'level': level,
                                'max_requests': child.get('max_requests', 6 if level == 3 or not child.get('children') else 4),
                                'children': []}
            self.nodes[parent]['children'].append(name)
            self.add(name, child.get('children', []))

    def kind(self, name):
        node = self.nodes[name]
        return 'coordinator' if node['parent'] is None else 'lead' if node['children'] else 'worker'

    def minutes_left(self):
        return max(0, round((self.deadline - self.clock()) / 60, 1))

    def log(self, event):
        with self.lock, (self.session / 'board.jsonl').open('a', encoding='utf-8') as handle:
            handle.write(json.dumps({'at_utc': stamp(), **event}, ensure_ascii=False) + '\n')

    def client(self):
        return httpx.Client(headers={'Authorization': 'Bearer ' + os.environ.get('OPENAI_API_KEY', '')},
                            transport=self.transport, timeout=httpx.Timeout(600, connect=15))

    def content(self, name, round_number, final):
        node = self.nodes[name]
        parent = node['parent']
        directives = (self.last[parent] or {}).get('directives') if parent else None
        directive = directives.get(name, '') if isinstance(directives, dict) else ''
        siblings = self.nodes[parent]['children'] if parent else []
        with self.lock:
            inbox, self.inbox[name] = self.inbox[name], []
        return {'session_goal': self.plan['goal'], 'authority': self.plan['authority'], 'round': round_number,
                'minutes_remaining': self.minutes_left(), 'final_synthesis_required': final,
                'your_name': name, 'complexity': LEVELS[node['level']], 'your_role': node['role'],
                'parent': parent, 'directive': clip(directive, 6000),
                'children': {child: self.nodes[child]['role'] for child in node['children']},
                'siblings': {other: self.nodes[other]['role'] for other in siblings if other != name},
                'stopped_agents': sorted(self.stopped),
                'worker_reports': {child: {'state': self.state[child], 'report': clip(self.last[child], 20000)}
                                   for child in node['children'] if self.state[child]},
                'inbox': inbox, 'your_previous_output': clip(self.last[name], 12000),
                'source_shelf': list(self.shelves[name]),
                'reply_format': 'one JSON object'}  # json_object output requires the word in the input.

    def turn(self, name, round_number, final=False):
        content = self.content(name, round_number, final)
        model, effort, max_output = self.level_models[self.nodes[name]['level']]
        history = [{'role': 'user', 'content': json.dumps(content, ensure_ascii=False)}]
        with self.client() as client:
            state, receipts, used, candidate = converse(
                client, self.session / name, history, self.shelves[name], 1 if final else self.nodes[name]['max_requests'],
                transport=self.transport, instructions=MISSION + ROLE_RULES[self.kind(name)],
                first_ordinal=self.ordinals[name],
                candidate_name=f'round-{round_number:02}{"-final" if final else ""}.json',
                answer_by=None if final else self.deadline - 300, stop_at=None if final else self.deadline, clock=self.clock,
                model=model, effort=effort, max_output=max_output)
        self.ordinals[name] += len(receipts)  # Refused dispatches save nothing, so ordinals stay unique.
        record = {'round': round_number, 'agent': name, 'level': LEVELS[self.nodes[name]['level']], 'model': model, 'state': state,
                  'requests': len(receipts), 'final': final, 'receipts': receipts,
                  'summary': clip((candidate or {}).get('summary', ''), 2000)}
        self.log({'event': 'turn', **{k: v for k, v in record.items() if k != 'receipts'}})
        self.state[name] = state
        if candidate is not None:
            self.last[name] = candidate
            if candidate.get('pressure') == 3:
                self.stopped.add(name)
                self.log({'event': 'pressure_stop', 'agent': name})
        return record, candidate

    def phase(self, names, round_number, final=False):
        active = [name for name in names if name not in self.stopped]
        if not active:
            return []
        with ThreadPoolExecutor(max_workers=len(active)) as pool:
            futures = [(name, pool.submit(self.turn, name, round_number, final)) for name in active]
        results = []
        for name, future in futures:
            record, candidate = future.result()
            self.rounds.append(record)
            results.append((record, candidate))
            for message in outgoing(name, candidate, self.names, self.nodes):
                with self.lock:
                    self.inbox[message['to']].append(message)
                self.log({'event': 'message', **message})
        return results

    def run(self):
        with ExitStack() as stack:
            leases = {}
            for name in self.names:
                (self.session / name).mkdir(parents=True)
                parent = self.nodes[name]['parent']
                leases[name] = stack.enter_context(agent_lease(
                    self.session / name, (leases[parent] or {}).get('id') if parent else None,
                    'coordinator' if parent is None else 'worker', self.transport))
                if leases[name]:
                    save(self.session / name / 'agent.json', leases[name])
            save(self.session / 'plan.json', {**self.plan, 'pinned_shelves': self.shelves,
                 'tree': {name: {k: v for k, v in node.items() if k != 'shelf'} for name, node in self.nodes.items()},
                 'minutes': round((self.deadline - self.started) / 60, 1), 'started_utc': stamp(),
                 'leases': leases, 'automatic_retry': False, 'candidates_applied': False, 'human_accepted': False})
            round_number, finished, leaves_ran = 0, False, False
            while self.clock() < self.deadline and 'coordinator' not in self.stopped and not finished:
                round_number += 1
                for depth, names in enumerate(self.phases):
                    results = self.phase(names, round_number)
                    if depth == 0:
                        record, root = results[0]
                        if record['state'] != 'candidate_prepared':
                            finished = True
                        elif root.get('done') is True and round_number > 1:
                            finished = 'done'
                        if len(self.phases) == 1 and not finished:
                            finished = 'done'  # A single-agent tree answers once.
                        if finished:
                            break
                    elif depth == len(self.phases) - 1:
                        leaves_ran = True
                        if not any(record['state'] == 'candidate_prepared' for record, _ in results):
                            finished = True
            if finished != 'done' and leaves_ran and 'coordinator' not in self.stopped:
                for names in reversed(self.phases[:-1]):
                    self.phase(names, round_number + 1, final=True)
        return self.finish()

    def finish(self):
        receipts = [receipt for record in self.rounds for receipt in record['receipts']]
        upper = sum(upper_cents(record['model'], r['usage']['input_tokens'], r['usage']['output_tokens'])
                    for record in self.rounds for r in record['receipts'] if r.get('usage'))
        root = self.last['coordinator']
        summary = {'at_utc': stamp(), 'mode': self.mode, 'models': {LEVELS[level]: settings[0] for level, settings in self.level_models.items()},
                   'elapsed_minutes': round((self.clock() - self.started) / 60, 1),
                   'turns': [{k: v for k, v in record.items() if k != 'receipts'} for record in self.rounds],
                   'requests': len(receipts), 'unknown_usage': sum(r['usage_state'] != 'reported' for r in receipts),
                   'reported_input_tokens': sum(r.get('usage', {}).get('input_tokens', 0) for r in receipts),
                   'reported_output_tokens': sum(r.get('usage', {}).get('output_tokens', 0) for r in receipts),
                   'upper_bound_cents_for_reported_usage': upper, 'stopped_agents': sorted(self.stopped),
                   'final_synthesis': root.get('synthesis') if isinstance(root, dict) else None,
                   'automatic_retry': False, 'candidates_applied': False, 'human_accepted': False}
        save(self.session / 'summary.json', summary)
        return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--session', type=Path, required=True)
    parser.add_argument('--minutes', type=float, required=True)
    args = parser.parse_args()
    if not os.environ.get('OPENAI_API_KEY'):
        parser.exit(2, 'No API key; no request dispatched\n')
    if not 0 < args.minutes <= 60:
        parser.exit(2, 'Session length must be within (0, 60] minutes\n')
    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    mode = current()['mode']  # The system-wide owner setting always decides the tree shape and models.
    if plan.get('mode') not in (None, mode):
        parser.exit(2, f"Plan asks for {plan['mode']} mode but the system is in {mode} mode\n")
    try:
        tree = Tree(plan, args.session, args.minutes, mode=mode)
    except ValueError as error:
        parser.exit(2, f'{error}\n')
    args.session.mkdir(parents=True)  # Only after the plan fits the mode.
    print(json.dumps(tree.run(), indent=2))


if __name__ == '__main__':
    main()
