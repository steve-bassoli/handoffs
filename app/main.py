import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

from fastapi import BackgroundTasks, Depends, FastAPI, Header, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, HttpUrl
from typing import Literal

from app.adapters import DemoDeliveryVerifier, DemoIdentity
from app.services import RuleError, Service
from app.storage import Database
from app.ai import AIRuns, Luna
from app.artifacts import download, inventory


class PostBounty(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    goal: str = Field(min_length=1)
    criteria: list[str] = Field(min_length=1)
    repository: str = ''
    context_links: list[str] = Field(default_factory=list)
    gold: int = Field(gt=0, strict=True)
    target: str | None = None
    source_zip: str = Field(default='', max_length=4000000)


class Progress(BaseModel):
    status: Literal['working', 'blocked']
    note: str = ''


class Delivery(BaseModel):
    pr_url: HttpUrl
    evidence: str = Field(min_length=1)


class Review(BaseModel):
    decision: Literal['acknowledged', 'accepted', 'rejected']
    note: str = Field(min_length=1)


class AIStart(BaseModel):
    context: str = Field(default='', max_length=100000)
    source_zip: str = Field(default='', max_length=4000000)


class AIAnswers(BaseModel):
    answers: list[str] = Field(min_length=1, max_length=3)
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


def create_app(database=None, clock=None, grant=None, verifier=None, ai_model=None):
    @asynccontextmanager
    async def lifespan(app):
        path = database or os.environ.get('HANDOFFS_DB', str(Path('.data/handoffs.sqlite').resolve()))
        db = Database(path)
        db.migrate()
        service = Service(db, verifier or DemoDeliveryVerifier(), clock, grant)
        service.seed()
        service.ai = AIRuns(service, ai_model or Luna())
        service.ai.recover()
        app.state.service = service
        try:
            yield
        finally:
            db.engine.dispose()

    app = FastAPI(title='HANDOFFS', lifespan=lifespan)

    @app.exception_handler(RuleError)
    async def rule_error(request: Request, error: RuleError):
        return JSONResponse(status_code=error.status, content={'detail': error.message})

    def actor(request: Request, x_demo_user: str = Header(default='steve')):
        return request.app.state.service.user(DemoIdentity().resolve(x_demo_user))['id']

    @app.get('/health')
    def health():
        return {'status': 'ok', 'mode': 'demo'}

    @app.get('/api/v1/users')
    def users(request: Request):
        from app.storage import all_rows
        with request.app.state.service.db.engine.connect() as c:
            return all_rows(c, 'SELECT * FROM users ORDER BY id')

    @app.get('/api/v1/me')
    def me(request: Request, user=Depends(actor)):
        return request.app.state.service.user(user)

    @app.get('/api/v1/me/stats')
    def stats(request: Request, user=Depends(actor)):
        return request.app.state.service.stats(user)

    @app.get('/api/v1/me/transactions')
    def transactions(request: Request, user=Depends(actor), limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
        return request.app.state.service.transactions(user, limit, offset)

    @app.get('/api/v1/bounties')
    def bounties(request: Request, user=Depends(actor), view: Literal['open', 'mine', 'all'] = 'open',
                 limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), q: str = ''):
        return request.app.state.service.listing(user, view, limit, offset, q)

    @app.get('/api/v1/bounties/{bounty_id}')
    def bounty(bounty_id: str, request: Request, user=Depends(actor)):
        return request.app.state.service.get(bounty_id)

    @app.get('/api/v1/bounties/{bounty_id}/artifacts')
    def artifacts(bounty_id: str, request: Request, user=Depends(actor)):
        return inventory(request.app.state.service, bounty_id)

    @app.get('/api/v1/bounties/{bounty_id}/artifacts/download')
    def artifact_bundle(bounty_id: str, request: Request, user=Depends(actor)):
        return Response(download(request.app.state.service, bounty_id), media_type='application/zip',
                        headers={'Content-Disposition': 'attachment; filename="bounty-artifacts.zip"'})

    @app.get('/api/v1/bounties/{bounty_id}/artifacts/file')
    def artifact_file(bounty_id: str, request: Request, path: str, user=Depends(actor)):
        content = download(request.app.state.service, bounty_id, path)
        return Response(content, media_type='application/octet-stream',
                        headers={'Content-Disposition': "attachment; filename*=UTF-8''" + quote(path.rsplit('/', 1)[-1], safe='')})

    @app.post('/api/v1/bounties')
    def post(payload: PostBounty, request: Request, user=Depends(actor),
             idempotency_key: str = Header(min_length=1, max_length=200)):
        return request.app.state.service.execute(user, idempotency_key, 'post', payload.model_dump())

    @app.post('/api/v1/bounties/{bounty_id}/packages')
    def attach_package(bounty_id: str, payload: EvidencePackage, request: Request, user=Depends(actor),
                       idempotency_key: str = Header(min_length=1, max_length=200)):
        return request.app.state.service.execute(user, idempotency_key, 'attach_package', {'id': bounty_id, **payload.model_dump()})

    @app.post('/api/v1/bounties/{bounty_id}/take')
    def take(bounty_id: str, request: Request, user=Depends(actor), idempotency_key: str = Header(min_length=1, max_length=200)):
        return request.app.state.service.execute(user, idempotency_key, 'take', {'id': bounty_id})

    @app.post('/api/v1/bounties/{bounty_id}/status')
    def progress(bounty_id: str, payload: Progress, request: Request, user=Depends(actor), idempotency_key: str = Header(min_length=1, max_length=200)):
        return request.app.state.service.execute(user, idempotency_key, 'status', {'id': bounty_id, **payload.model_dump()})

    @app.post('/api/v1/bounties/{bounty_id}/deliveries')
    def deliver(bounty_id: str, payload: Delivery, request: Request, user=Depends(actor), idempotency_key: str = Header(min_length=1, max_length=200)):
        return request.app.state.service.execute(user, idempotency_key, 'deliver', {'id': bounty_id, **payload.model_dump(mode='json')})

    @app.post('/api/v1/bounties/{bounty_id}/settle')
    def settle(bounty_id: str, request: Request, user=Depends(actor), idempotency_key: str = Header(min_length=1, max_length=200)):
        return request.app.state.service.execute(user, idempotency_key, 'settle', {'id': bounty_id})

    @app.post('/api/v1/bounties/{bounty_id}/cancel')
    def cancel(bounty_id: str, request: Request, user=Depends(actor), idempotency_key: str = Header(min_length=1, max_length=200)):
        return request.app.state.service.execute(user, idempotency_key, 'cancel', {'id': bounty_id})

    @app.post('/api/v1/bounties/{bounty_id}/reviews')
    def review(bounty_id: str, payload: Review, request: Request, user=Depends(actor), idempotency_key: str = Header(min_length=1, max_length=200)):
        return request.app.state.service.execute(user, idempotency_key, 'review', {'id': bounty_id, **payload.model_dump()})

    def ai_write(request, background, user, key, action, bounty_id, payload):
        service = request.app.state.service
        result = service.execute(user, key, action, {'id': bounty_id, **payload})
        if action in ('ai_start', 'ai_answer', 'ai_retry'):
            background.add_task(service.ai.generate, bounty_id)
        return result

    @app.post('/api/v1/bounties/{bounty_id}/ai/start')
    def ai_start(bounty_id: str, payload: AIStart, request: Request, background: BackgroundTasks,
                 user=Depends(actor), idempotency_key: str = Header(min_length=1, max_length=200)):
        return ai_write(request, background, user, idempotency_key, 'ai_start', bounty_id, payload.model_dump())

    @app.post('/api/v1/bounties/{bounty_id}/ai/answers')
    def ai_answer(bounty_id: str, payload: AIAnswers, request: Request, background: BackgroundTasks,
                  user=Depends(actor), idempotency_key: str = Header(min_length=1, max_length=200)):
        return ai_write(request, background, user, idempotency_key, 'ai_answer', bounty_id, payload.model_dump())

    @app.post('/api/v1/bounties/{bounty_id}/ai/retry')
    def ai_retry(bounty_id: str, request: Request, background: BackgroundTasks,
                 user=Depends(actor), idempotency_key: str = Header(min_length=1, max_length=200)):
        return ai_write(request, background, user, idempotency_key, 'ai_retry', bounty_id, {})

    @app.post('/api/v1/bounties/{bounty_id}/ai/confirm-followups')
    def ai_confirm(bounty_id: str, payload: AIConfirm, request: Request, background: BackgroundTasks,
                   user=Depends(actor), idempotency_key: str = Header(min_length=1, max_length=200)):
        return ai_write(request, background, user, idempotency_key, 'ai_confirm', bounty_id, payload.model_dump())

    @app.get('/api/v1/bounties/{bounty_id}/ai/artifact')
    def ai_artifact(bounty_id: str, request: Request, user=Depends(actor)):
        return Response(request.app.state.service.ai.artifact(bounty_id), media_type='application/zip',
                        headers={'Content-Disposition': f'attachment; filename="bounty-{bounty_id}.zip"'})

    @app.post('/api/v1/bounties/{bounty_id}/ai/complete')
    def ai_complete(bounty_id: str, payload: AIVerification, request: Request, background: BackgroundTasks,
                    user=Depends(actor), idempotency_key: str = Header(min_length=1, max_length=200)):
        return ai_write(request, background, user, idempotency_key, 'ai_complete', bounty_id, payload.model_dump())

    @app.get('/api/v1/bounties/{bounty_id}/lineage')
    def lineage(bounty_id: str, request: Request, user=Depends(actor)):
        return request.app.state.service.lineage(bounty_id)

    static = Path(__file__).parent / 'static'
    app.mount('/static', StaticFiles(directory=static), name='static')

    @app.get('/', include_in_schema=False)
    def index():
        return FileResponse(static / 'index.html')

    return app


app = create_app()
