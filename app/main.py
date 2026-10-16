import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, HttpUrl
from typing import Literal

from app.adapters import DemoDeliveryVerifier, DemoIdentity
from app.services import RuleError, Service
from app.storage import Database


class PostBounty(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    goal: str = Field(min_length=1)
    criteria: list[str] = Field(min_length=1)
    repository: str = ''
    context_links: list[str] = Field(default_factory=list)
    gold: int = Field(gt=0, strict=True)
    target: str | None = None


class Progress(BaseModel):
    status: Literal['working', 'blocked']
    note: str = ''


class Delivery(BaseModel):
    pr_url: HttpUrl
    evidence: str = Field(min_length=1)


class Review(BaseModel):
    decision: Literal['acknowledged', 'accepted', 'rejected']
    note: str = Field(min_length=1)


def create_app(database=None, clock=None, grant=None, verifier=None):
    @asynccontextmanager
    async def lifespan(app):
        path = database or os.environ.get('HANDOFFS_DB', str(Path('.data/handoffs.sqlite').resolve()))
        db = Database(path)
        db.migrate()
        service = Service(db, verifier or DemoDeliveryVerifier(), clock, grant)
        service.seed()
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

    @app.post('/api/v1/bounties')
    def post(payload: PostBounty, request: Request, user=Depends(actor),
             idempotency_key: str = Header(min_length=1, max_length=200)):
        return request.app.state.service.execute(user, idempotency_key, 'post', payload.model_dump())

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

    static = Path(__file__).parent / 'static'
    app.mount('/static', StaticFiles(directory=static), name='static')

    @app.get('/', include_in_schema=False)
    def index():
        return FileResponse(static / 'index.html')

    return app


app = create_app()
