"""Private saved replies through the existing relay; no task execution."""
import asyncio
import json
import os
from pathlib import Path
import re
from typing import Literal
from uuid import uuid4

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app import astra_chat
from app.agent_conduit import stamp
from app.api_budget import BudgetError, upper_cents
from app.astra_agents import AgentLimitError

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None
    import msvcrt

ROOT = Path(__file__).resolve().parents[1] / '.data' / 'architect-chat'
TIMEOUT = 610
_RUNNING = set()


class Turn(BaseModel):
    model_config = {'extra': 'forbid'}
    architect: Literal['bob-the-architect', 'sue-the-architect', 'ada-the-architect']
    message: str = Field(min_length=1, max_length=100000)
    thread_id: str | None = Field(default=None, pattern=r'^[0-9a-f]{32}$')


def human(request: Request):
    identity = getattr(request.state, 'identity', {})
    if identity.get('principal') != 'human' or not identity.get('user_id'):
        raise HTTPException(401, 'Sign in with a human session to use architect chat')
    return identity['user_id']


def directory(root, identifier):
    if not re.fullmatch(r'[0-9a-f]{32}', identifier):
        raise HTTPException(404, 'Conversation not found')
    return Path(root) / identifier


def try_lock(handle):
    """Exclusive, non-blocking; raises BlockingIOError when another reply holds the thread."""
    if fcntl:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return
    handle.seek(0)
    try:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        raise BlockingIOError from None


def write(path, record):
    temporary = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8') as handle:
        json.dump(record, handle, ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def read(root, identifier, user):
    try:
        record = json.loads((directory(root, identifier) / 'thread.json').read_text(encoding='utf-8'))
    except FileNotFoundError:
        raise HTTPException(404, 'Conversation not found') from None
    if record['user'] != user:
        raise HTTPException(404, 'Conversation not found')
    return record


def listing(root, user):
    items = []
    for path in Path(root).glob('*/thread.json'):
        record = json.loads(path.read_text(encoding='utf-8'))
        if record['user'] == user:
            items.append({key: record[key] for key in ('thread_id', 'architect', 'updated_utc', 'state')})
    return {'items': sorted(items, key=lambda item: item['updated_utc'], reverse=True)}


def send(root, user, payload, transport=None):
    astra_chat.checked_text(payload.message)
    identifier = payload.thread_id or uuid4().hex
    folder = directory(root, identifier)
    folder.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    folder.mkdir(exist_ok=True, mode=0o700)
    with (folder / '.lock').open('a') as lock:
        try:
            try_lock(lock)
        except BlockingIOError:
            raise HTTPException(409, 'A reply is already running; refresh, do not resend') from None
        metadata = folder / 'thread.json'
        if metadata.exists():
            record = read(root, identifier, user)
            if record['architect'] != payload.architect:
                raise HTTPException(409, 'This conversation belongs to another architect')
        else:
            record = {'thread_id': identifier, 'user': user, 'architect': payload.architect,
                      'created_utc': stamp(), 'updated_utc': stamp(), 'state': 'ready',
                      'messages': [], 'previous_run': None}
        if record['state'] != 'ready':
            raise HTTPException(409, 'Previous reply is pending or stopped. No retry dispatched; review its saved status')
        ordinal = uuid4().hex
        prompt = folder / (ordinal + '-prompt.txt')
        with os.fdopen(os.open(prompt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8') as handle:
            handle.write(payload.message)
        run = folder / ordinal
        record['messages'].append({'role': 'user', 'who': user, 'content': payload.message, 'at_utc': stamp()})
        record['state'] = 'pending'
        record['updated_utc'] = stamp()
        write(metadata, record)
        cost, code = None, 200
        try:
            previous = folder / record['previous_run'] if record['previous_run'] else None
            result = astra_chat.talk(prompt, run, previous_run=previous, transport=transport, persona=payload.architect)
            usage = result['receipt'].get('usage')
            if usage is not None:
                cost = {'state': 'reported_upper', 'amount': upper_cents('gpt-6-astra', usage['input_tokens'], usage['output_tokens']), 'unit': 'USD cents'}
            text = json.loads((run / 'answer.json').read_text(encoding='utf-8'))['text']
            if result['state'] != 'completed' or not text or not (run / 'conversation.json').exists():
                record['state'] = 'blocked'
                text = 'Reply stopped (' + result['state'] + '). Usage may be unknown; existing reservations are retained. No automatic retry.'
                code = 503
            else:
                record['state'] = 'ready'
                record['previous_run'] = ordinal
        except AgentLimitError:
            record['state'] = 'blocked'
            text = 'Architect capacity is unavailable or an interrupted lease awaits recovery. No automatic retry.'
            code = 503
        except BudgetError:
            record['state'] = 'blocked'
            text = 'Reply refused by existing budget accounting. Headroom, prices or usage require review; spending limits were not changed. No automatic retry.'
            code = 402
        except Exception:
            record['state'] = 'blocked'
            text = 'Reply failed; dispatch or usage may be unknown. No automatic retry. Review the saved run before further requests.'
            code = 503
        record['messages'].append({'role': 'assistant', 'who': payload.architect, 'content': text, 'at_utc': stamp(), 'cost': cost})
        record['updated_utc'] = stamp()
        write(metadata, record)
        return code, record


def response(record, code=200):
    return JSONResponse(record, status_code=code, headers={'Cache-Control': 'no-store'})


def install(app):
    def root(request):
        return getattr(request.app.state, 'architect_chat_root', ROOT)

    @app.get('/api/v1/architect-chat')
    def list_chat(request: Request, user=Depends(human)):
        try:
            return response(listing(root(request), user))
        except (OSError, ValueError, KeyError):
            raise HTTPException(503, 'Saved conversations unavailable; refresh later') from None

    @app.get('/api/v1/architect-chat/{thread_id}')
    def get_chat(thread_id: str, request: Request, user=Depends(human)):
        try:
            return response(read(root(request), thread_id, user))
        except (OSError, ValueError, KeyError):
            raise HTTPException(503, 'Saved conversation unavailable; refresh later') from None

    @app.post('/api/v1/architect-chat')
    async def post_chat(payload: Turn, request: Request, user=Depends(human)):
        try:
            astra_chat.checked_text(payload.message)
        except ValueError:
            raise HTTPException(422, 'Use nonempty text within 100000 UTF-8 bytes, without secrets') from None
        payload = payload.model_copy(update={'thread_id': payload.thread_id or uuid4().hex})
        task = asyncio.create_task(asyncio.to_thread(send, root(request), user, payload))
        _RUNNING.add(task)
        def observe(future):
            _RUNNING.discard(future)
            if not future.cancelled():
                future.exception()
        task.add_done_callback(observe)
        try:
            code, record = await asyncio.wait_for(asyncio.shield(task), TIMEOUT)
        except asyncio.TimeoutError:
            return response({'detail': 'Reply wait timed out. The call may still be running; refresh the saved conversation, do not resend. No automatic retry.', 'thread_id': payload.thread_id}, 503)
        except HTTPException:
            raise
        except Exception:
            return response({'detail': 'Storage or reply failed. Refresh before sending again; no automatic retry.', 'thread_id': payload.thread_id}, 503)
        if code != 200:
            record = {**record, 'detail': record['messages'][-1]['content']}
        return response(record, code)
