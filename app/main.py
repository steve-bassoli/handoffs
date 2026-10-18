import os
from contextlib import asynccontextmanager
from html import escape
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import quote

from fastapi import BackgroundTasks, Depends, FastAPI, Header, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, HttpUrl
from typing import Literal

from app.adapters import DemoDeliveryVerifier, DemoIdentity
from app.services import RuleError, Service, event_via, event_intent
from app.storage import Database
from app.ai import AIRuns, Luna
from app.artifacts import download, inventory
from app.workflow import Profile
from app.proofs import Proofs, ProofUpload
from app.proof_reviewer import ProofReviewer
from app.gremlins import Comparison, compare, sabotage, witness
from app.agent_roster import roster
from app.automation_mode import AUTOMATION_HEADER, ACTION_INTENT_HEADER, current as current_mode


RESEARCH_PATH = Path(__file__).resolve().parents[1] / 'PLAN' / 'AI_RESEARCH.md'


class PostTask(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    goal: str = Field(min_length=1)
    criteria: list[str] = Field(min_length=1)
    repository: str = ''
    context_links: list[str] = Field(default_factory=list)
    gold: int = Field(gt=0, strict=True)
    target: str | None = None
    source_zip: str = Field(default='', max_length=4000000)
    complexity: Literal['HIGH', 'MEDIUM', 'LOW'] = 'HIGH'
    work_type: Literal['implementation', 'verification'] = 'implementation'
    profile: Profile | None = None


class EditTask(BaseModel):
    model_config = {'extra': 'forbid'}
    title: str = Field(min_length=1, max_length=160)
    goal: str = Field(min_length=1)
    criteria: list[str] = Field(min_length=1)
    repository: str
    context_links: list[str]
    gold: int = Field(gt=0, strict=True)
    target: str | None
    complexity: Literal['HIGH', 'MEDIUM', 'LOW']
    work_type: Literal['implementation', 'verification']


class Progress(BaseModel):
    status: Literal['working', 'blocked']
    note: str = ''


class Prerequisites(BaseModel):
    depends_on: list[str] = Field(max_length=30)


class ReopenTask(BaseModel):
    complexity: Literal['HIGH', 'MEDIUM', 'LOW']
    note: str = Field(min_length=1, max_length=2000)


class CheckpointTask(BaseModel):
    model_config = {'extra': 'forbid'}
    notes: str = Field(min_length=1, max_length=30000)


class Delivery(BaseModel):
    pr_url: HttpUrl
    evidence: str = Field(min_length=1)


class Review(BaseModel):
    decision: Literal['acknowledged', 'accepted', 'rejected']
    note: str = Field(min_length=1)


class AIModelChoice(BaseModel):
    model: Literal['sol', 'terra', 'luna'] | None = None


class AIStart(AIModelChoice):
    context: str = Field(default='', max_length=100000)
    source_zip: str = Field(default='', max_length=4000000)


class AIAnswers(AIModelChoice):
    answers: list[str] = Field(min_length=1)
    source_zip: str = Field(default='', max_length=4000000)


class AIConfirm(BaseModel):
    indices: list[int] = Field(max_length=20)


class AIVerification(BaseModel):
    evidence: str = Field(min_length=1, max_length=10000)


class EvidencePackage(BaseModel):
    kind: Literal['support', 'response']
    package_zip: str = Field(min_length=1, max_length=4000000)
    input_zip: str = Field(default='', max_length=4000000)
    note: str = Field(default='', max_length=2000)


class HumanProof(BaseModel):
    accepted: bool
    note: str = Field(min_length=1, max_length=4000)
    review_basis: Literal['ai-reviewed', 'human-only'] = 'ai-reviewed'


class CloseHuman(BaseModel):
    model_config = {'extra': 'forbid', 'str_strip_whitespace': True}
    baseline: str = Field(min_length=1)
    candidate: str = Field(min_length=1)
    environment: str = Field(min_length=1)
    evidence: str = Field(min_length=1, max_length=200000)
    filename: str = Field(default='evidence.txt', min_length=1)
    unknown: list[str] = Field(default_factory=list)


class CompleteProof(BaseModel):
    note: str = Field(min_length=1, max_length=4000)


def create_app(database=None, clock=None, grant=None, verifier=None, ai_model=None, proof_reviewer=None):
    @asynccontextmanager
    async def lifespan(app):
        path = database or os.environ.get('HANDOFFS_DB', str(Path('.data/handoffs.sqlite').resolve()))
        db = Database(path)
        db.migrate()
        service = Service(db, verifier or DemoDeliveryVerifier(), clock, grant)
        service.seed()
        service.ai = AIRuns(service, ai_model or Luna())
        service.proofs = Proofs(service, proof_reviewer or ProofReviewer())
        service.ai.recover()
        service.proofs.recover()
        app.state.service = service
        app.state.mode_path = Path(os.environ.get('HANDOFFS_AUTOMATION_MODE', Path(path).with_name('automation-mode.json')))
        app.state.dashboard_sessions = Path(os.environ.get('HANDOFFS_DASHBOARD_SESSIONS', db.path.parent / 'astra-tree')).resolve()
        app.state.dashboard_ledger = Path(os.environ.get('HANDOFFS_API_BUDGET_DB', db.path.with_name('api-budget.sqlite'))).resolve()
        try:
            yield
        finally:
            db.engine.dispose()

    app = FastAPI(title='The Commons', lifespan=lifespan)

    @app.middleware('http')
    async def automation_guard(request: Request, call_next):
        # Attribution is independent of intent. Explicit human requests may use tools in Manual.
        via = request.headers.get(AUTOMATION_HEADER)
        intent = request.headers.get(ACTION_INTENT_HEADER)
        if intent not in (None, 'user-directed', 'autonomous'):
            return JSONResponse(status_code=422, content={'detail': 'Invalid action intent'})
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE') and (via is not None or intent == 'autonomous'):
            if intent != 'user-directed' and not current_mode(getattr(request.app.state, 'mode_path', None))['automated_writes']:
                return JSONResponse(status_code=403, content={'detail': 'Manual mode: autonomous task updates are paused; explicit user-directed actions remain available'})
        token = event_via.set(via)
        intent_token = event_intent.set(intent)
        try:
            return await call_next(request)
        finally:
            event_via.reset(token)
            event_intent.reset(intent_token)

    @app.exception_handler(RuleError)
    async def rule_error(request: Request, error: RuleError):
        return JSONResponse(status_code=error.status, content={'detail': error.message})

    def actor(request: Request, x_demo_user: str = Header(default='steve')):
        return request.app.state.service.user(DemoIdentity().resolve(x_demo_user))['id']

    @app.get('/health')
    def health():
        return {'status': 'ok', 'mode': 'demo'}

    @app.get('/research', include_in_schema=False)
    def research(request: Request):
        headers = {
            'Cache-Control': 'no-store',
            'X-Content-Type-Options': 'nosniff',
            'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; form-action 'none'",
            'Referrer-Policy': 'no-referrer',
        }
        try:
            loopback = request.client is not None and ip_address(request.client.host).is_loopback
        except ValueError:
            loopback = False
        if not loopback:
            return HTMLResponse('Research is available only from this workstation.', status_code=403, headers=headers)
        try:
            record = RESEARCH_PATH.read_text(encoding='utf-8')
        except FileNotFoundError:
            return HTMLResponse('Research record is unavailable.', status_code=404, headers=headers)
        lines = record.splitlines(keepends=True)
        latest = ''.join(lines[max((i for i, line in enumerate(lines) if line.startswith('## ')), default=0):])
        return HTMLResponse(f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="30">
<title>The Commons · AI research</title>
<style>
body {{ margin: 0; border-top: 3px solid #f23f2c; color: #212529; background: #fff; font: 16px/1.6 Arial, sans-serif; }}
main {{ max-width: 1000px; margin: auto; padding: 24px; }}
h1, h2 {{ font-weight: 500; }}
p {{ color: #54545c; }}
section, details {{ border: 1px solid #ddd; padding: 20px; margin: 24px 0; }}
section {{ border-top: 3px solid #c53024; }}
pre {{ white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; }}
summary {{ cursor: pointer; color: #c53024; }}
</style>
</head>
<body><main>
<h1>The Commons · AI research</h1>
<p>Local read-only observer. Refreshes the recorded research every 30 seconds;
this page does not query the live Codex quota meter.</p>
<section><h2>Latest recorded section</h2><pre>{escape(latest)}</pre></section>
<details><summary>Full research record</summary><pre>{escape(record)}</pre></details>
</main></body></html>''', headers=headers)

    @app.get('/api/v1/users')
    def users(request: Request):
        from app.storage import all_rows
        with request.app.state.service.db.engine.connect() as c:
            return all_rows(c, 'SELECT * FROM users ORDER BY id')

    @app.get('/api/v1/automation-mode')
    def automation_mode(request: Request, user=Depends(actor)):
        record = current_mode(request.app.state.mode_path)
        return JSONResponse({key: record.get(key) for key in ('mode', 'summary', 'agents', 'automated_writes', 'set_by', 'set_utc')},
                            headers={'Cache-Control': 'no-store'})

    @app.get('/api/v1/agents')
    def agents(user=Depends(actor)):
        return JSONResponse(roster(), headers={'Cache-Control': 'no-store'})

    @app.get('/api/dashboard/live')
    def dashboard_snapshot(request: Request, task: str | None = Query(default=None, max_length=200),
                           session: str | None = Query(default=None, max_length=200),
                           x_demo_user: str | None = Header(default=None)):
        from app.dashboard_api import live_snapshot
        from app.dashboard_panels import add_panels
        if not x_demo_user:
            raise RuleError('Select a dashboard identity', 401)
        user = request.app.state.service.user(DemoIdentity().resolve(x_demo_user))['id']
        roster_data = roster()
        result = live_snapshot(request.app.state.service, user, roster_data,
            current_mode(request.app.state.mode_path), request.app.state.dashboard_sessions,
            task_id=task, session_id=session)
        add_panels(request.app.state.service, user, result, roster_data,
                   request.app.state.dashboard_ledger, Path(__file__).resolve().parents[1], task)
        return JSONResponse(result, headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})

    @app.post('/api/v1/gremlins/{breed}')
    def gremlins(breed: Literal['mimic', 'saboteur', 'witness'], payload: Comparison, user=Depends(actor)):
        try:
            return {'mimic': compare, 'saboteur': sabotage, 'witness': witness}[breed](payload.model_dump())
        except ValueError:
            raise RuleError('Use a focused synthetic comparison; Saboteur requires a passing baseline', 422) from None

    @app.get('/api/v1/me')
    def me(request: Request, user=Depends(actor)):
        return request.app.state.service.user(user)

    @app.get('/api/v1/me/stats')
    def stats(request: Request, user=Depends(actor)):
        return request.app.state.service.stats(user)

    @app.get('/api/v1/me/transactions')
    def transactions(request: Request, user=Depends(actor), limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
        return request.app.state.service.transactions(user, limit, offset)

    @app.get('/api/v1/tasks')
    def tasks(request: Request, user=Depends(actor), view: Literal['open', 'mine', 'all'] | None = None,
                 limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), q: str = '',
                 status: list[str] | None = Query(default=None), creator: str | None = None):
        statuses = None
        if status is not None:
            statuses = list(dict.fromkeys(part.strip() for value in status for part in value.split(',')))
            known = {'open', 'pending', 'working', 'blocked', 'delivered',
                     'awaiting_approval', 'settled', 'completed', 'cancelled', 'superseded', 'decomposed'}
            unknown = sorted(set(statuses) - known)
            if unknown:
                raise RuleError({'message': 'Unknown task status', 'statuses': unknown}, 422)
        effective_view = view if view is not None else ('all' if statuses is not None else 'open')
        return request.app.state.service.listing(user, effective_view, limit, offset, q, statuses, creator or None)

    @app.get('/api/v1/tasks/summary')
    def task_summary(request: Request, user=Depends(actor)):
        return JSONResponse(request.app.state.service.summary(), headers={'Cache-Control': 'no-store'})

    @app.get('/api/v1/tasks/{task_id}')
    def task(task_id: str, request: Request, user=Depends(actor)):
        return request.app.state.service.get(task_id)

    @app.get('/api/v1/tasks/{task_id}/artifacts')
    def artifacts(task_id: str, request: Request, user=Depends(actor)):
        return inventory(request.app.state.service, task_id)

    @app.get('/api/v1/tasks/{task_id}/artifacts/download')
    def artifact_bundle(task_id: str, request: Request, user=Depends(actor)):
        return Response(download(request.app.state.service, task_id), media_type='application/zip',
                        headers={'Content-Disposition': 'attachment; filename="task-artifacts.zip"'})

    @app.get('/api/v1/tasks/{task_id}/artifacts/file')
    def artifact_file(task_id: str, request: Request, path: str, user=Depends(actor)):
        content = download(request.app.state.service, task_id, path)
        return Response(content, media_type='application/octet-stream',
                        headers={'Content-Disposition': "attachment; filename*=UTF-8''" + quote(path.rsplit('/', 1)[-1], safe='')})

    @app.post('/api/v1/tasks')
    def post(payload: PostTask, request: Request, user=Depends(actor),
             idempotency_key: str = Header(min_length=1, max_length=200)):
        return request.app.state.service.execute(user, idempotency_key, 'post', payload.model_dump())

    @app.post('/api/v1/tasks/{task_id}/edit')
    def edit(task_id: str, payload: EditTask, request: Request, user=Depends(actor),
             idempotency_key: str = Header(min_length=1, max_length=200)):
        return request.app.state.service.execute(user, idempotency_key, 'edit', {'id': task_id, **payload.model_dump()})

    @app.post('/api/v1/tasks/{task_id}/packages')
    def attach_package(task_id: str, payload: EvidencePackage, request: Request, user=Depends(actor),
                       idempotency_key: str = Header(min_length=1, max_length=200)):
        return request.app.state.service.execute(user, idempotency_key, 'attach_package', {'id': task_id, **payload.model_dump()})

    @app.post('/api/v1/tasks/{task_id}/reopen')
    def reopen(task_id: str, payload: ReopenTask, request: Request, user=Depends(actor),
               idempotency_key: str = Header(min_length=1, max_length=200)):
        return request.app.state.service.execute(user, idempotency_key, 'ai_reopen', {'id': task_id, **payload.model_dump()})

    @app.post('/api/v1/tasks/{task_id}/checkpoint')
    def checkpoint(task_id: str, payload: CheckpointTask, request: Request, user=Depends(actor),
                   idempotency_key: str = Header(min_length=1, max_length=200)):
        return request.app.state.service.execute(user, idempotency_key, 'checkpoint', {'id': task_id, **payload.model_dump()})

    @app.post('/api/v1/tasks/{task_id}/take')
    def take(task_id: str, request: Request, user=Depends(actor), idempotency_key: str = Header(min_length=1, max_length=200)):
        return request.app.state.service.execute(user, idempotency_key, 'take', {'id': task_id})

    @app.post('/api/v1/tasks/{task_id}/status')
    def progress(task_id: str, payload: Progress, request: Request, user=Depends(actor), idempotency_key: str = Header(min_length=1, max_length=200)):
        return request.app.state.service.execute(user, idempotency_key, 'status', {'id': task_id, **payload.model_dump()})

    @app.post('/api/v1/tasks/{task_id}/deliveries')
    def deliver(task_id: str, payload: Delivery, request: Request, user=Depends(actor), idempotency_key: str = Header(min_length=1, max_length=200)):
        return request.app.state.service.execute(user, idempotency_key, 'deliver', {'id': task_id, **payload.model_dump(mode='json')})

    @app.post('/api/v1/tasks/{task_id}/settle')
    def settle(task_id: str, request: Request, user=Depends(actor), idempotency_key: str = Header(min_length=1, max_length=200)):
        return request.app.state.service.execute(user, idempotency_key, 'settle', {'id': task_id})

    @app.post('/api/v1/tasks/{task_id}/cancel')
    def cancel(task_id: str, request: Request, user=Depends(actor), idempotency_key: str = Header(min_length=1, max_length=200)):
        return request.app.state.service.execute(user, idempotency_key, 'cancel', {'id': task_id})

    @app.post('/api/v1/tasks/{task_id}/reviews')
    def review(task_id: str, payload: Review, request: Request, user=Depends(actor), idempotency_key: str = Header(min_length=1, max_length=200)):
        return request.app.state.service.execute(user, idempotency_key, 'review', {'id': task_id, **payload.model_dump()})

    def ai_write(request, background, user, key, action, task_id, payload):
        service = request.app.state.service
        result = service.execute(user, key, action, {'id': task_id, **payload})
        if action in ('accept', 'ai_start', 'ai_answer', 'ai_retry'):
            background.add_task(service.ai.generate, task_id)
        return result

    @app.post('/api/v1/tasks/{task_id}/accept')
    def accept(task_id: str, payload: AIStart, request: Request, background: BackgroundTasks,
               user=Depends(actor), idempotency_key: str = Header(min_length=1, max_length=200)):
        return ai_write(request, background, user, idempotency_key, 'accept', task_id, payload.model_dump())

    @app.post('/api/v1/tasks/{task_id}/ai/start')
    def ai_start(task_id: str, payload: AIStart, request: Request, background: BackgroundTasks,
                 user=Depends(actor), idempotency_key: str = Header(min_length=1, max_length=200)):
        return ai_write(request, background, user, idempotency_key, 'ai_start', task_id, payload.model_dump())

    @app.post('/api/v1/tasks/{task_id}/ai/answers')
    def ai_answer(task_id: str, payload: AIAnswers, request: Request, background: BackgroundTasks,
                  user=Depends(actor), idempotency_key: str = Header(min_length=1, max_length=200)):
        return ai_write(request, background, user, idempotency_key, 'ai_answer', task_id, payload.model_dump())

    @app.post('/api/v1/tasks/{task_id}/ai/retry')
    def ai_retry(task_id: str, request: Request, background: BackgroundTasks,
                 payload: AIModelChoice | None = None,
                 user=Depends(actor), idempotency_key: str = Header(min_length=1, max_length=200)):
        return ai_write(request, background, user, idempotency_key, 'ai_retry', task_id,
                        payload.model_dump() if payload else {})

    @app.post('/api/v1/tasks/{task_id}/ai/confirm-followups')
    def ai_confirm(task_id: str, payload: AIConfirm, request: Request, background: BackgroundTasks,
                   user=Depends(actor), idempotency_key: str = Header(min_length=1, max_length=200)):
        return ai_write(request, background, user, idempotency_key, 'ai_confirm', task_id, payload.model_dump())

    @app.get('/api/v1/tasks/{task_id}/ai/artifact')
    def ai_artifact(task_id: str, request: Request, user=Depends(actor)):
        return Response(request.app.state.service.ai.artifact(task_id), media_type='application/zip',
                        headers={'Content-Disposition': f'attachment; filename="task-{task_id}.zip"'})

    @app.post('/api/v1/tasks/{task_id}/ai/complete')
    def ai_complete(task_id: str, payload: AIVerification, request: Request, background: BackgroundTasks,
                    user=Depends(actor), idempotency_key: str = Header(min_length=1, max_length=200)):
        return ai_write(request, background, user, idempotency_key, 'ai_complete', task_id, payload.model_dump())

    @app.get('/api/v1/tasks/{task_id}/lineage')
    def lineage(task_id: str, request: Request, user=Depends(actor)):
        return request.app.state.service.lineage(task_id)

    @app.get('/api/v1/tasks/{task_id}/constellation')
    def graph(task_id: str, request: Request, user=Depends(actor)):
        return request.app.state.service.constellation(task_id)

    @app.post('/api/v1/tasks/{task_id}/proofs')
    def attach_proof(task_id: str, payload: ProofUpload, request: Request, user=Depends(actor),
                     idempotency_key: str = Header(min_length=1, max_length=200)):
        return request.app.state.service.execute(user, idempotency_key, 'ai_proof_attach', {'id': task_id, **payload.model_dump()})

    @app.get('/api/v1/tasks/{task_id}/proofs/{proof_id}')
    def proof_file(task_id: str, proof_id: str, request: Request, user=Depends(actor)):
        task = request.app.state.service.get(task_id)
        record = next((event['data'] for event in task['events'] if event['kind'] == 'proof_attached' and event['data']['proof_id'] == proof_id), None)
        if not record:
            raise RuleError('Proof artifact not found', 404)
        import base64
        return Response(base64.b64decode(record['content_base64']), media_type=record['media_type'],
            headers={'Content-Disposition': "attachment; filename*=UTF-8''" + quote(record['filename'], safe=''),
                     'X-Content-Type-Options': 'nosniff'})

    @app.post('/api/v1/tasks/{task_id}/proof-review')
    def review_proof(task_id: str, request: Request, background: BackgroundTasks, user=Depends(actor),
                     idempotency_key: str = Header(min_length=1, max_length=200)):
        service = request.app.state.service
        result = service.execute(user, idempotency_key, 'ai_proof_queue', {'id': task_id})
        background.add_task(service.proofs.run, task_id, result['proof']['review']['review_id'])
        return result

    @app.post('/api/v1/tasks/{task_id}/proof-human')
    def verify_proof(task_id: str, payload: HumanProof, request: Request, user=Depends(actor),
                     idempotency_key: str = Header(min_length=1, max_length=200)):
        return request.app.state.service.execute(user, idempotency_key, 'ai_proof_human', {'id': task_id, **payload.model_dump()})

    @app.post('/api/v1/tasks/{task_id}/close-human')
    def close_human(task_id: str, payload: CloseHuman, request: Request, user=Depends(actor),
                    idempotency_key: str = Header(min_length=1, max_length=200)):
        return request.app.state.service.execute(user, idempotency_key, 'close_human',
                                                {'id': task_id, **payload.model_dump()})

    @app.post('/api/v1/tasks/{task_id}/complete')
    def complete_proof(task_id: str, payload: CompleteProof, request: Request, user=Depends(actor),
                       idempotency_key: str = Header(min_length=1, max_length=200)):
        return request.app.state.service.execute(user, idempotency_key, 'ai_proof_complete', {'id': task_id, **payload.model_dump()})

    @app.post('/api/v1/tasks/{task_id}/profile')
    def profile(task_id: str, payload: Profile, request: Request, user=Depends(actor),
                idempotency_key: str = Header(min_length=1, max_length=200)):
        return request.app.state.service.execute(user, idempotency_key, 'ai_profile', {'id': task_id, 'profile': payload.model_dump()})

    @app.post('/api/v1/tasks/{task_id}/dependencies')
    def prerequisites(task_id: str, payload: Prerequisites, request: Request, user=Depends(actor),
                      idempotency_key: str = Header(min_length=1, max_length=200)):
        return request.app.state.service.execute(user, idempotency_key, 'ai_dependencies', {'id': task_id, **payload.model_dump()})

    static = Path(__file__).parent / 'static'
    app.mount('/static', StaticFiles(directory=static), name='static')

    @app.get('/', include_in_schema=False)
    def index():
        return FileResponse(static / 'index.html')

    @app.get('/min', include_in_schema=False)
    def min_page():
        return FileResponse(static / 'min.html', headers={'Cache-Control': 'no-store'})

    @app.get('/dashboard', include_in_schema=False)
    def dashboard_page():
        return FileResponse(static / 'dashboard.html', headers={'Cache-Control': 'no-store'})

    # Hidden, deprecated compatibility aliases: the API was /api/v1/bounties before the rename to tasks.
    # Same endpoint objects, so validation, auth, idempotency and background work are identical.
    legacy_prefix = '/api/v1/' + 'bount' + 'ies'
    for route in tuple(app.routes):
        if isinstance(route, APIRoute) and (route.path == '/api/v1/tasks' or route.path.startswith('/api/v1/tasks/')):
            app.add_api_route(legacy_prefix + route.path[len('/api/v1/tasks'):], route.endpoint,
                              methods=sorted(route.methods), status_code=route.status_code,
                              response_model=route.response_model, response_class=route.response_class,
                              dependencies=route.dependencies, deprecated=True, include_in_schema=False,
                              name='legacy_' + route.name)
    return app


app = create_app()
