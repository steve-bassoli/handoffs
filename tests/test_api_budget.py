from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import sqlite3

import httpx
import pytest

from app.api_budget import CEILING_CENTS, BudgetError, available, initialize, raise_ceiling, reserve, upper_cents


NOW = datetime(2026, 10, 17, 6, tzinfo=timezone.utc)


def test_missing_checkpoint_and_reset_cannot_create_money(tmp_path):
    path = tmp_path / 'budget.sqlite'
    with pytest.raises(BudgetError):
        reserve('gpt-6-astra', 32000, path=path, now=NOW)
    assert not path.exists()
    initialize(path, 233, 3110, 'Observed project month spend plus conservative legacy call holds')
    assert available(path) == CEILING_CENTS - 3343
    with pytest.raises(FileExistsError):
        initialize(path, 0, 0, 'Must not reset')


def test_reservation_and_reported_upper_bound_preserve_floor(tmp_path):
    path = tmp_path / 'budget.sqlite'
    initialize(path, 233, 3110, 'Owner observation')
    permit = reserve('gpt-6-astra', 32000, path=path, now=NOW)
    assert available(path) == CEILING_CENTS - 3343 - upper_cents('gpt-6-astra', 922000, 32000)
    permit.settle({'input_tokens': 1000, 'output_tokens': 500})
    held = upper_cents('gpt-6-astra', 1000, 500)
    assert available(path) == CEILING_CENTS - 3343 - held
    permit.settle({'input_tokens': 0, 'output_tokens': 0})
    assert available(path) == CEILING_CENTS - 3343 - held, 'Duplicate settlement cannot refund paid work'


def test_unknown_usage_keeps_envelope_and_blocks_more_paid_work(tmp_path):
    path = tmp_path / 'budget.sqlite'
    initialize(path, 0, 0, 'Owner')
    permit = reserve('gpt-6-astra', 32000, path=path, now=NOW)
    before = available(path)
    permit.settle()
    assert available(path) == before
    with pytest.raises(BudgetError, match='unknown API usage'):
        reserve('gpt-6-astra', 32000, path=path, now=NOW)


def test_atomic_competing_reservations_cannot_exceed_ceiling(tmp_path):
    path = tmp_path / 'budget.sqlite'
    initialize(path, 0, 0, 'Owner')

    def attempt(_):
        try:
            reserve('gpt-6-astra', 32000, path=path, now=NOW)
            return True
        except BudgetError:
            return False

    fits = CEILING_CENTS // upper_cents('gpt-6-astra', 922000, 32000)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(fits + 3)))
    assert sum(results) == fits
    assert available(path) >= 0
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT SUM(held) FROM calls').fetchone()[0] <= CEILING_CENTS


def test_stale_prices_and_unknown_models_are_not_spending_permission(tmp_path):
    path = tmp_path / 'budget.sqlite'
    initialize(path, 0, 0, 'Owner')
    with pytest.raises(BudgetError, match='stale'):
        reserve('gpt-6-astra', 32000, path=path, now=datetime(2026, 10, 19, tzinfo=timezone.utc))
    with pytest.raises(BudgetError, match='verified cost bound'):
        reserve('unpriced-model', 32000, path=path, now=NOW)


def test_explicit_offline_transport_needs_no_money_or_price_checkpoint():
    permit = reserve('fixture-model', 1, httpx.MockTransport(lambda request: httpx.Response(200)))
    permit.settle()


def test_real_provider_paths_fail_closed_before_network(tmp_path, monkeypatch):
    from app.ai import Luna
    from app.proof_reviewer import ProofReviewer
    from app.services import RuleError
    monkeypatch.setenv('OPENAI_API_KEY', 'fixture-only')
    monkeypatch.setenv('HANDOFFS_API_BUDGET_DB', str(tmp_path / 'absent.sqlite'))
    monkeypatch.setattr(httpx.Client, 'post', lambda *args, **kwargs: pytest.fail('No real POST allowed'))
    task = {'title': 'test', 'goal': 'test', 'criteria': ['one'], 'repository': '', 'context_links': [], 'complexity': 'LOW'}
    data = {'context': '', 'conversation': [], 'question_count': 0, 'source': {}}
    with pytest.raises(RuleError, match='budget accounting'):
        Luna().generate(task, data)
    observed = []
    proof = {'media_type': 'text/plain', '_record_usage': lambda **value: observed.append(value)}
    result = ProofReviewer().review(task, proof)
    assert result['verdict'] == 'inconclusive'
    assert observed[0]['stage'] == 'no_request' and observed[0]['reason'] == 'budget_unavailable'


@pytest.mark.parametrize('provider', ['workbench', 'proof'])
@pytest.mark.parametrize('failure', ['http-unreported', 'invalid-json', 'http-reported'])
def test_failed_responses_settle_real_ledger_without_retry(tmp_path, monkeypatch, provider, failure):
    from app import ai, proof_reviewer
    from test_proofs import upload
    path = tmp_path / 'budget.sqlite'
    initialize(path, 0, 0, 'Offline failure-path fixture')
    monkeypatch.setenv('OPENAI_API_KEY', 'offline-only')
    monkeypatch.setenv('HANDOFFS_AI_MODEL', 'gpt-6-luna')
    monkeypatch.setenv('HANDOFFS_PROOF_MODEL', 'gpt-6-luna')
    module = ai if provider == 'workbench' else proof_reviewer
    # Exercise real reservations with offline HTTP, rather than MockTransport's no-money path.
    monkeypatch.setattr(module, 'reserve', lambda model, limit, transport: reserve(model, limit, path=path, now=NOW))
    calls, observations = [], []

    def respond(request):
        calls.append(request)
        assert json.loads(request.content)['service_tier'] == 'default'
        if failure == 'invalid-json':
            return httpx.Response(200, text='not JSON')
        body = {'error': {'message': 'Synthetic failure'}}
        if failure == 'http-reported':
            body['usage'] = {'input_tokens': 12, 'output_tokens': 34}
        return httpx.Response(503, json=body)

    task = {'title': 'test', 'goal': 'test', 'criteria': ['one'], 'profile': {},
            'repository': '', 'context_links': [], 'complexity': 'LOW'}
    transport = httpx.MockTransport(respond)
    with pytest.raises((httpx.HTTPStatusError, ValueError)):
        if provider == 'workbench':
            data = {'context': '', 'conversation': [], 'question_count': 0, 'source': {},
                    '_record_usage': lambda delta, **metadata: observations.append(delta)}
            ai.Luna(transport).generate(task, data)
        else:
            proof = {**upload(), 'proof_id': 'offline-proof', 'binding': 'fixture',
                     '_record_usage': lambda **value: observations.append(value)}
            proof_reviewer.ProofReviewer(transport).review(task, proof)
    assert len(calls) == 1
    with sqlite3.connect(path) as db:
        held, state = db.execute('SELECT held,state FROM calls').fetchone()
    if failure == 'http-reported':
        assert state == 'reported_upper' and held == upper_cents('gpt-6-luna', 12, 34)
        assert any(v.get('input_tokens') == 12 and v.get('output_tokens') == 34 for v in observations)
    else:
        assert state == 'unknown' and held > 0
        with pytest.raises(BudgetError, match='unknown API usage'):
            reserve('gpt-6-luna', 4000, path=path, now=NOW)


def test_owner_ceiling_raise_keeps_history_and_cannot_repeat(tmp_path):
    path = tmp_path / 'budget.sqlite'
    initialize(path, 233, 3110, 'Owner observation')
    with sqlite3.connect(path) as db:
        db.execute('UPDATE budget SET ceiling=9800 WHERE id=1')  # Earlier $98 ledger.
    with pytest.raises(BudgetError):
        available(path)
    with pytest.raises(BudgetError):
        raise_ceiling(path, ' ')
    raise_ceiling(path, 'Owner chat: $1000 initial funding')
    assert available(path) == CEILING_CENTS - 3343
    with sqlite3.connect(path) as db:
        provenance = db.execute('SELECT provenance FROM budget').fetchone()[0]
    assert provenance.startswith('Owner observation | Ceiling 9800 -> ')
    with pytest.raises(BudgetError):
        raise_ceiling(path, 'Cannot repeat')
