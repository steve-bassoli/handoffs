"""Relay one explicitly selected message to Astra; never execute its answer."""
import argparse
import json
import os
from pathlib import Path
import re

import httpx

from app.agent_conduit import request, save, stamp
from app.api_budget import available, RULES


MISSION = ('Empower humans, including people without personal AI quota. Preserve agency, privacy, consent '
    'and protected resources. No coercion, debt, mandatory work, seizure or purchased authority. '
    'Report effort, usage, uncertainty, failures and unexecuted checks honestly. REST with a useful '
    'checkpoint at capacity or uncertainty. RO3 supports grounded decomposition; never force three '
    'or override facts, safety, consent or evidence. Do not claim feelings or incorruptibility. '
    'Answer the selected user message; do not infer authority to execute, publish or accept work. ' + RULES)


def checked_text(value):
    if not isinstance(value, str) or not value.strip() or len(value.encode('utf-8')) > 100000:
        raise ValueError('A nonempty selected message of at most 100000 UTF-8 bytes is required')
    if re.search(r'sk-[A-Za-z0-9_-]{20,}|-----BEGIN (?:RSA |EC )?PRIVATE KEY-----', value):
        raise ValueError('Selected text rejected by secret check')
    return value


def talk(prompt_file, run, previous_run=None, transport=None):
    prompt = checked_text(Path(prompt_file).read_text(encoding='utf-8-sig'))
    messages = []
    if previous_run:
        previous = json.loads((Path(previous_run) / 'conversation.json').read_text(encoding='utf-8'))
        if previous.get('status') != 'completed' or not isinstance(previous.get('messages'), list):
            raise ValueError('Only a completed, explicitly selected Astra conversation can continue')
        for item in previous['messages']:
            if not isinstance(item, dict) or set(item) != {'role', 'content'} or item['role'] not in ('user', 'assistant'):
                raise ValueError('Invalid selected conversation')
            messages.append({'role': item['role'], 'content': checked_text(item['content'])})
    messages.append({'role': 'user', 'content': prompt})
    key = os.environ.get('OPENAI_API_KEY')
    if not key:
        raise ValueError('No API key; no request dispatched')
    payload = {'model': 'gpt-6-astra', 'reasoning': {'effort': 'max'}, 'service_tier': 'default',
        'store': False, 'stream': True, 'instructions': MISSION, 'input': messages, 'max_output_tokens': 32000}
    if len(json.dumps(payload, ensure_ascii=False).encode('utf-8')) > 240000:
        raise ValueError('Selected conversation exceeds request byte limit; no request dispatched')
    run = Path(run)
    run.mkdir()  # Never replay an existing or interrupted run.
    save(run / 'prompt.json', {'at_utc': stamp(), 'messages': messages,
        'previous_run': str(previous_run) if previous_run else None, 'instructions': MISSION})
    with httpx.Client(headers={'Authorization': 'Bearer ' + key}, transport=transport,
                      timeout=httpx.Timeout(600, connect=15)) as client:
        result, receipt = request(client, payload, run, 1, transport)
    text = ''.join(part.get('text', '') for item in (result or {}).get('output', []) if item.get('type') == 'message'
        for part in item.get('content', []) if part.get('type') == 'output_text')
    completed = receipt.get('provider_status') == 'completed' and receipt['usage_state'] == 'reported' and not receipt.get('error_class')
    state = 'completed' if completed else 'rest_incomplete' if receipt['usage_state'] == 'reported' else 'rest_unknown_usage'
    save(run / 'answer.json', {'state': state, 'text': text, 'automatic_retry': False})
    if completed and text:
        save(run / 'conversation.json', {'status': 'completed', 'messages': messages + [{'role': 'assistant', 'content': text}]})
    summary = {'at_utc': stamp(), 'state': state, 'receipt': receipt, 'answer_file': str(run / 'answer.json'),
        'automatic_retry': False, 'answer_executed': False, 'human_accepted': False}
    save(run / 'summary.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prompt-file', type=Path)
    parser.add_argument('--run', type=Path)
    parser.add_argument('--previous-run', type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.check:
        print(json.dumps({'key_configured': bool(os.environ.get('OPENAI_API_KEY')),
            'local_headroom_cents_not_balance': available(), 'paid_request_sent': False}))
        return
    if not args.prompt_file or not args.run:
        parser.error('--prompt-file and --run are required without --check')
    print(json.dumps(talk(args.prompt_file, args.run, args.previous_run)))


if __name__ == '__main__':
    main()
