from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import sqlite3

import httpx
import pytest

from app.api_budget import BudgetError, available, initialize, reserve, upper_cents


NOW = datetime(2026, 10, 17, 6, tzinfo=timezone.utc)


def test_missing_checkpoint_and_reset_cannot_create_money(tmp_path):
    path = tmp_path / 'budget.sqlite'
    with pytest.raises(BudgetError):
        reserve('gpt-6-astra', 32000, path=path, now=NOW)
    assert not path.exists()
    initialize(path, 233, 3110, 'Observed project month spend plus conservative legacy call holds')
    assert available(path) == 6457
    with pytest.raises(FileExistsError):
        initialize(path, 0, 0, 'Must not reset')


def test_reservation_and_reported_upper_bound_preserve_floor(tmp_path):
    path = tmp_path / 'budget.sqlite'
    initialize(path, 233, 3110, 'Owner observation')
    permit = reserve('gpt-6-astra', 32000, path=path, now=NOW)
    assert available(path) == 6457 - upper_cents('gpt-6-astra', 922000, 32000)
    permit.settle({'input_tokens': 1000, 'output_tokens': 500})
    held = upper_cents('gpt-6-astra', 1000, 500)
    assert available(path) == 6457 - held
    permit.settle({'input_tokens': 0, 'output_tokens': 0})
    assert available(path) == 6457 - held, 'Duplicate settlement cannot refund paid work'


def test_unknown_usage_keeps_envelope_and_blocks_more_paid_work(tmp_path):
    path = tmp_path / 'budget.sqlite'
    initialize(path, 0, 0, 'Owner')
    permit = reserve('gpt-6-astra', 32000, path=path, now=NOW)
    before = available(path)
    permit.settle()
    assert available(path) == before
    with pytest.raises(BudgetError, match='unknown API usage'):
        reserve('gpt-6-astra', 32000, path=path, now=NOW)


def test_atomic_competing_reservations_cannot_exceed_98_dollars(tmp_path):
    path = tmp_path / 'budget.sqlite'
    initialize(path, 0, 0, 'Owner')

    def attempt(_):
        try:
            reserve('gpt-6-astra', 32000, path=path, now=NOW)
            return True
        except BudgetError:
            return False

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(attempt, range(6)))
    assert sum(results) == 3
    assert available(path) >= 0
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT SUM(held) FROM calls').fetchone()[0] <= 9800


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
