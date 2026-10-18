from datetime import datetime, timezone
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import RuleError
from app.automation_mode import set_mode
from app.api_budget import extend_prices, reserve, BudgetError


@pytest.fixture
def approvals(tmp_path, monkeypatch):
    monkeypatch.setenv('HANDOFFS_DEMO_IDENTITY', 'refuse')
    monkeypatch.delenv('ASE_PROTOTYPE_AUTO_SIGNOFF', raising=False)
    main = tmp_path / 'main.sqlite'
    with TestClient(create_app(main)) as client:
        client.app.state.credentials.set_password('steve', 'a long test-only password')
        response = client.post('/api/v1/auth/login', json={'username': 'steve', 'password': 'a long test-only password'})
        assert response.status_code == 200
        headers = {'Authorization': 'Bearer ' + response.json()['access_token']}
        def approve(action, payload):
            response = client.post('/api/v1/signoffs', headers=headers, json={'action': action, 'payload': payload, 'summary': 'Offline executor test'})
            assert response.status_code == 200
            sid = response.json()['id']
            response = client.post('/api/v1/signoffs/' + sid + '/decision', headers=headers, json={'approved': True, 'note': 'Reviewed exact payload'})
            assert response.status_code == 200
            return sid
        yield main, approve


@pytest.mark.parametrize('kind', ['mode', 'price'])
def test_executor_binding_once_and_failure(tmp_path, approvals, kind, monkeypatch):
    main, approve = approvals
    if kind == 'mode':
        target = tmp_path / 'mode.json'
        import app.automation_mode as automation_mode
        monkeypatch.setattr(automation_mode, 'LIVE_MODE_FILE', target)  # Treat the scratch file as the live setting.
        action, payload = 'automation_mode', {'mode': 'manual', 'note': 'reviewed'}
        def execute(sid, changed=False):
            return set_mode('manual', 'steve', 'changed' if changed else 'reviewed', target, signoff_id=sid, db=main)
    else:
        target = tmp_path / 'budget.sqlite'
        with sqlite3.connect(target) as c:
            c.execute('CREATE TABLE budget (id INTEGER PRIMARY KEY, ceiling INTEGER, baseline INTEGER, provenance TEXT)')
            c.execute("INSERT INTO budget VALUES (1,199800,0,'test')")
            c.execute('CREATE TABLE calls (id TEXT PRIMARY KEY, model TEXT, held INTEGER, state TEXT)')
        action, payload = 'price_checkpoint', {'until': '2026-10-20T00:00:00+00:00', 'provenance': 'reviewed'}
        def execute(sid, changed=False):
            return extend_prices(target, payload['until'], 'changed' if changed else 'reviewed', signoff_id=sid, db=main)
    with pytest.raises(RuleError):
        execute(None)
    sid = approve(action, payload)
    with pytest.raises(RuleError):
        execute(sid, changed=True)
    execute(sid)
    with pytest.raises(RuleError):
        execute(sid)
    if kind == 'price':
        reserve('gpt-6-luna', 1, path=target, now=datetime(2026, 10, 19, tzinfo=timezone.utc))
        with pytest.raises(BudgetError, match='stale'):
            reserve('gpt-6-luna', 1, path=target, now=datetime(2026, 10, 20, tzinfo=timezone.utc))
    else:
        target.unlink()
        target.mkdir()
        failed = approve(action, payload)
        with pytest.raises(ValueError, match='consumed'):
            execute(failed)
        with pytest.raises(RuleError):
            execute(failed)


def test_live_budget_owner_checkpoints_need_a_signoff(tmp_path, approvals, monkeypatch):
    import app.api_budget as api_budget
    main, approve = approvals
    live = tmp_path / 'api-budget.sqlite'
    monkeypatch.setattr(api_budget, 'LIVE_BUDGET_FILE', live)  # Treat the scratch ledger as the live one.
    with pytest.raises(BudgetError, match='requires --signoff'):
        api_budget.initialize(live, 0, 0, 'Owner')
    payload = {'operation': 'initialize', 'observed_cents': 0, 'uncertainty_cents': 0, 'provenance': 'Owner'}
    sid = approve('spend_ceiling', payload)
    api_budget.initialize(live, 0, 0, 'Owner', signoff_id=sid, db=main)
    with pytest.raises(RuleError):  # Single use.
        api_budget.reconcile_unknown(live, 'Owner', signoff_id=sid, db=main)
    scratch = tmp_path / 'scratch.sqlite'
    api_budget.initialize(scratch, 0, 0, 'Fixture')  # Scratch ledgers stay free for tests.
