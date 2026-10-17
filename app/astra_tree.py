"""Time-boxed Astra tree: one coordinator, up to three peer workers, and a local message relay.

The trusted launcher holds every lease, pins every shelf and routes messages. Agents only read their
own pinned sources and return JSON; nothing they write is executed, applied, published or accepted.
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

MESSAGE_LIMIT = 4000
MAX_MESSAGES = 10
ROLE_RULES = {
    'coordinator': (' TREE ROLE coordinator. You plan rounds for your named workers, route questions, resolve '
        'conflicting claims and decide when the goal is sufficiently met. Reply with one JSON object: summary, '
        'directives (object: worker name -> instruction for the next round), messages (array of {to, text}; to is a '
        'worker name or "all"), done (true only when no further worker round is useful), synthesis (object with plan, '
        'files, checks, limitations, open_questions_for_humans), pressure (1-3). You cannot launch agents.'),
    'worker': (' TREE ROLE worker. Follow the coordinator directive, answer questions in your inbox, and use '
        'read_source for evidence. Reply with one JSON object: summary, findings (array of {claim, evidence, '
        'status: observed|inferred|unknown}), messages (array of {to, text}; to is a peer name, "coordinator" or '
        '"all"), files (proposed relative path/content objects, never applied), checks, limitations, pressure (1-3).'),
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


def outgoing(sender, candidate, names):
    """Validated messages only; unknown recipients are dropped, not guessed."""
    messages = []
    for item in (candidate or {}).get('messages', [])[:MAX_MESSAGES]:
        if isinstance(item, dict) and isinstance(item.get('text'), str) and item['text'].strip():
            target = item.get('to')
            recipients = [n for n in names if n != sender] if target == 'all' else [target] if target in names and target != sender else []
            messages += [{'from': sender, 'to': name, 'text': clip(item['text'], MESSAGE_LIMIT)} for name in recipients]
    return messages


class Tree:
    def __init__(self, plan, session, minutes, transport=None, clock=time.monotonic):
        self.plan, self.session, self.transport, self.clock = plan, Path(session), transport, clock
        self.started = clock()
        self.deadline = self.started + minutes * 60
        self.coordinator = plan['coordinator']
        self.workers = {worker['name']: worker for worker in plan['workers']}
        if not 1 <= len(self.workers) <= 3 or 'coordinator' in self.workers:
            raise ValueError('A tree has one coordinator and one to three uniquely named workers')
        self.names = ['coordinator', *self.workers]
        self.shelves = {'coordinator': pin(self.coordinator['shelf']),
                        **{name: pin(worker['shelf']) for name, worker in self.workers.items()}}
        self.ordinals = {name: 1 for name in self.names}
        self.inbox = {name: [] for name in self.names}
        self.last = {name: None for name in self.names}
        self.stopped = set()
        self.rounds = []
        self.lock = threading.Lock()

    def minutes_left(self):
        return max(0, round((self.deadline - self.clock()) / 60, 1))

    def log(self, event):
        with self.lock, (self.session / 'board.jsonl').open('a', encoding='utf-8') as handle:
            handle.write(json.dumps({'at_utc': stamp(), **event}, ensure_ascii=False) + '\n')

    def turn(self, name, client, round_number, content, max_requests, final=False):
        run = self.session / name
        history = [{'role': 'user', 'content': json.dumps(content, ensure_ascii=False)}]
        role = 'coordinator' if name == 'coordinator' else 'worker'
        state, receipts, used, candidate = converse(
            client, run, history, self.shelves[name], max_requests, transport=self.transport,
            instructions=MISSION + ROLE_RULES[role], first_ordinal=self.ordinals[name],
            candidate_name=f'round-{round_number:02}{"-final" if final else ""}.json',
            answer_by=None if final else self.deadline - 300, stop_at=None if final else self.deadline, clock=self.clock)
        self.ordinals[name] += len(receipts)  # Refused dispatches save nothing, so ordinals stay unique.
        record = {'round': round_number, 'agent': name, 'state': state, 'requests': len(receipts),
                  'final': final, 'receipts': receipts, 'summary': clip((candidate or {}).get('summary', ''), 2000)}
        self.log({'event': 'turn', **{k: v for k, v in record.items() if k != 'receipts'}})
        if candidate is not None:
            self.last[name] = candidate
            if candidate.get('pressure') == 3:
                self.stopped.add(name)
                self.log({'event': 'pressure_stop', 'agent': name})
        return record, candidate

    def client(self):
        return httpx.Client(headers={'Authorization': 'Bearer ' + os.environ.get('OPENAI_API_KEY', '')},
                            transport=self.transport, timeout=httpx.Timeout(600, connect=15))

    def deliver(self, messages):
        for message in messages:
            self.inbox[message['to']].append(message)
            self.log({'event': 'message', **message})

    def coordinator_turn(self, client, round_number, reports, final=False):
        content = {'session_goal': self.plan['goal'], 'authority': self.plan['authority'], 'round': round_number,
                   'minutes_remaining': self.minutes_left(), 'final_synthesis_required': final,
                   'team': {name: worker['role'] for name, worker in self.workers.items()},
                   'stopped_agents': sorted(self.stopped), 'worker_reports': reports,
                   'inbox': self.inbox['coordinator'], 'your_previous_output': clip(self.last['coordinator'], 12000),
                   'source_shelf': list(self.shelves['coordinator'])}
        self.inbox['coordinator'] = []
        record, candidate = self.turn('coordinator', client, round_number, content, 1 if final else 3, final)
        self.deliver(outgoing('coordinator', candidate, self.names))
        return record, candidate

    def worker_turn(self, name, round_number, directive, inbox):
        content = {'session_goal': self.plan['goal'], 'authority': self.plan['authority'], 'round': round_number,
                   'minutes_remaining': self.minutes_left(), 'your_name': name, 'your_role': self.workers[name]['role'],
                   'team': {other: worker['role'] for other, worker in self.workers.items() if other != name},
                   'coordinator_directive': clip(directive, 6000), 'inbox': inbox,
                   'your_previous_report': clip(self.last[name], 12000), 'source_shelf': list(self.shelves[name])}
        with self.client() as client:
            return self.turn(name, client, round_number, content, self.workers[name].get('max_requests', 6))

    def run(self):
        with ExitStack() as stack:
            leases = {}
            for name in self.names:
                (self.session / name).mkdir(parents=True)
                parent = None if name == 'coordinator' else (leases['coordinator'] or {}).get('id')
                role = 'coordinator' if name == 'coordinator' else 'worker'
                leases[name] = stack.enter_context(agent_lease(self.session / name, parent, role, self.transport))
                if leases[name]:
                    save(self.session / name / 'agent.json', leases[name])
            save(self.session / 'plan.json', {**self.plan, 'pinned_shelves': self.shelves,
                 'minutes': round((self.deadline - self.started) / 60, 1), 'started_utc': stamp(),
                 'leases': leases, 'automatic_retry': False, 'candidates_applied': False, 'human_accepted': False})
            reports, coordinator, round_number = {}, None, 0
            with self.client() as client:
                while self.clock() < self.deadline and 'coordinator' not in self.stopped:
                    round_number += 1
                    record, coordinator = self.coordinator_turn(client, round_number, reports)
                    self.rounds.append(record)
                    if record['state'] != 'candidate_prepared' or (coordinator.get('done') is True and round_number > 1):
                        break
                    directives = coordinator.get('directives') if isinstance(coordinator.get('directives'), dict) else {}
                    active = [name for name in self.workers if name not in self.stopped]
                    inboxes = {name: self.inbox[name] for name in active}
                    for name in active:
                        self.inbox[name] = []
                    with ThreadPoolExecutor(max_workers=len(active) or 1) as pool:
                        futures = {name: pool.submit(self.worker_turn, name, round_number, directives.get(name, ''), inboxes[name])
                                   for name in active}
                    reports = {}
                    for name, future in futures.items():
                        record, candidate = future.result()
                        self.rounds.append(record)
                        reports[name] = {'state': record['state'], 'report': clip(candidate, 20000)}
                        self.deliver(outgoing(name, candidate, self.names))
                    if not any(record['state'] == 'candidate_prepared' for record in self.rounds[-len(active):]) and active:
                        break
                finished = coordinator and coordinator.get('done') is True and round_number > 1
                if not finished and reports and 'coordinator' not in self.stopped:
                    record, coordinator = self.coordinator_turn(client, round_number + 1, reports, final=True)
                    self.rounds.append(record)
        return self.finish(coordinator)

    def finish(self, coordinator):
        receipts = [receipt for record in self.rounds for receipt in record['receipts']]
        upper = sum(upper_cents('gpt-6-astra', r['usage']['input_tokens'], r['usage']['output_tokens'])
                    for r in receipts if r.get('usage'))
        summary = {'at_utc': stamp(), 'elapsed_minutes': round((self.clock() - self.started) / 60, 1),
                   'turns': [{k: v for k, v in record.items() if k != 'receipts'} for record in self.rounds],
                   'requests': len(receipts), 'unknown_usage': sum(r['usage_state'] != 'reported' for r in receipts),
                   'reported_input_tokens': sum(r.get('usage', {}).get('input_tokens', 0) for r in receipts),
                   'reported_output_tokens': sum(r.get('usage', {}).get('output_tokens', 0) for r in receipts),
                   'upper_bound_cents_for_reported_usage': upper, 'stopped_agents': sorted(self.stopped),
                   'final_synthesis': coordinator.get('synthesis') if isinstance(coordinator, dict) else None,
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
    args.session.mkdir(parents=True)
    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    print(json.dumps(Tree(plan, args.session, args.minutes).run(), indent=2))


if __name__ == '__main__':
    main()
