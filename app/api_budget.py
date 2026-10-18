"""Local sponsor envelopes, not an invoice, bank balance or participant wallet."""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
import os
from pathlib import Path
import sqlite3
import uuid

import httpx


from app.rules import RULES
# Official Standard long-context cache-write/input maximum and output rates, USD/M.
# https://developers.openai.com/api/docs/pricing, inspected 2026-10-17.
RATES = {'gpt-6-astra': ('25', '75'), 'gpt-6.1-sol': ('5', '15'),
         'gpt-6-sol': ('5', '15'), 'gpt-6-luna': ('.25', '.75'),
         'gpt-5.6-sol': ('10', '30'), 'gpt-5.6-terra': ('5', '18'), 'gpt-5.6-luna': ('.5', '1.8')}
# Owner chat 2026-10-18 12:45 UTC: about $39 spent since 2026-10-17, budget safe for 8 hours.
# Prices were not re-inspected; this extends the 2026-10-17 inspection on the owner's word.
# Owner chat 2026-10-18 14:55 UTC: "go auto, we are fine until 6 pm tonight" (18:00 EDT = 22:00 UTC); still not re-inspected.
PRICES_EXPIRE = datetime(2026, 10, 18, 22, tzinfo=timezone.utc)
CEILING_CENTS = 199800  # Owner chat 2026-10-17: $1000 initial funding plus $999 more, $1 protected.
AUTHORIZED_CEILINGS = (99900, CEILING_CENTS)  # Earlier owner checkpoint stays valid until raised.
MAX_INPUT = 922000  # Inspected model pages; reserve the whole input capacity, not guessed tokenization.


class BudgetError(ValueError):
    pass


def upper_cents(model, inputs, outputs):
    if model not in RATES or any(type(n) is not int or n < 0 for n in (inputs, outputs)):
        raise BudgetError('No verified cost bound for this request')
    incoming, outgoing = map(Decimal, RATES[model])
    # Conservative rates plus 20% buffer; not a promise about taxes/external spend.
    return int(((incoming * inputs + outgoing * outputs) * Decimal('120') / 1000000).to_integral_value(rounding=ROUND_CEILING))


def budget_path():
    database = Path(os.environ.get('HANDOFFS_DB', Path(__file__).resolve().parents[1] / '.data' / 'handoffs.sqlite'))
    return Path(os.environ.get('HANDOFFS_API_BUDGET_DB', database.with_name('api-budget.sqlite')))


LIVE_BUDGET_FILE = Path(__file__).resolve().parents[1] / '.data' / 'api-budget.sqlite'


def owner_signoff(action, path, payload, signoff_id, db):
    """The live ledger's owner checkpoints each consume one sign-off (3babb128); scratch ledgers (tests) need none."""
    if signoff_id is None and Path(path).resolve() != LIVE_BUDGET_FILE.resolve():
        return
    if not signoff_id:
        raise BudgetError('Changing the live API budget requires --signoff')
    from app.executor_signoffs import consume_signoff
    consume_signoff('spend_ceiling', {'operation': action, **payload}, signoff_id=signoff_id, db=db)


def initialize(path, observed_cents, uncertainty_cents, provenance, *, signoff_id=None, db=None):
    """Explicit local owner setup only. Never called by a model, HTTP route or reserve."""
    if any(type(n) is not int or n < 0 for n in (observed_cents, uncertainty_cents)) or not provenance:
        raise BudgetError('A sourced, nonnegative owner checkpoint is required')
    if observed_cents + uncertainty_cents > CEILING_CENTS:
        raise BudgetError('Checkpoint exceeds the protected allocation')
    owner_signoff('initialize', path, {'observed_cents': observed_cents, 'uncertainty_cents': uncertainty_cents, 'provenance': provenance}, signoff_id, db)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb'):
        pass  # Exclusive creation: never reset an existing budget.
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE budget (id INTEGER PRIMARY KEY CHECK(id=1), ceiling INTEGER NOT NULL, baseline INTEGER NOT NULL, provenance TEXT NOT NULL)')
        db.execute('INSERT INTO budget VALUES (1,?,?,?)', (CEILING_CENTS, observed_cents + uncertainty_cents, provenance))
        db.execute('CREATE TABLE calls (id TEXT PRIMARY KEY, model TEXT NOT NULL, held INTEGER NOT NULL, state TEXT NOT NULL)')


def raise_ceiling(path, provenance, *, signoff_id=None, db=None):
    """Explicit local owner update only: move an existing ledger up to CEILING_CENTS, keeping its history."""
    if not isinstance(provenance, str) or not provenance.strip():
        raise BudgetError('A sourced owner authorization is required')
    owner_signoff('raise_ceiling', path, {'ceiling_cents': CEILING_CENTS, 'provenance': provenance}, signoff_id, db)
    with connection(path) as db:
        db.execute('BEGIN IMMEDIATE')
        ceiling, prior = db.execute('SELECT ceiling,provenance FROM budget WHERE id=1').fetchone()
        if ceiling >= CEILING_CENTS:
            raise BudgetError('Ceiling is already at or above the authorized allocation')
        db.execute('UPDATE budget SET ceiling=?,provenance=? WHERE id=1',
                   (CEILING_CENTS, f'{prior} | Ceiling {ceiling} -> {CEILING_CENTS} cents: {provenance}'))



def reconcile_unknown(path, provenance, *, signoff_id=None, db=None):
    """Explicit local owner checkpoint: keep every unknown call's full envelope as spent and let paid work continue.

    Never reduces a hold, never retries the call, and never clears an overrun.
    """
    if not isinstance(provenance, str) or not provenance.strip():
        raise BudgetError('A sourced owner authorization is required')
    owner_signoff('reconcile_unknown', path, {'provenance': provenance}, signoff_id, db)
    with connection(path) as db:
        db.execute('BEGIN IMMEDIATE')
        rows = db.execute("SELECT id, held FROM calls WHERE state='unknown'").fetchall()
        if not rows:
            return 0
        db.execute("UPDATE calls SET state='unknown_conservative' WHERE state='unknown'")
        prior = db.execute('SELECT provenance FROM budget WHERE id=1').fetchone()[0]
        db.execute('UPDATE budget SET provenance=? WHERE id=1', (
            f"{prior} | Conservative hold kept for {len(rows)} unknown call(s), {sum(h for _, h in rows)} cents: {provenance}",))
        return len(rows)

def connection(path):
    if not Path(path).is_file():
        raise BudgetError('API budget accounting is unavailable; no paid request was sent')
    return sqlite3.connect(Path(path).resolve().as_uri() + '?mode=rw', uri=True, timeout=10)


def extend_prices(path, until_iso, provenance, *, signoff_id, db=None):
    """Owner-authorized external-store effect; approval commits before mutation."""
    from app.executor_signoffs import consume_signoff, FAIL_CLOSED
    try:
        until = datetime.fromisoformat(until_iso)
    except (TypeError, ValueError):
        raise BudgetError('Use an ISO timestamp with an explicit timezone') from None
    if until.tzinfo is None or until.utcoffset() is None:
        raise BudgetError('Use an ISO timestamp with an explicit timezone')
    if not isinstance(provenance, str) or not provenance.strip():
        raise BudgetError('A sourced owner authorization is required')
    consume_signoff('price_checkpoint', {'until': until_iso, 'provenance': provenance}, signoff_id=signoff_id, db=db)
    try:
        with connection(path) as ledger:
            ledger.execute('BEGIN IMMEDIATE')
            ledger.execute('SELECT ceiling FROM budget WHERE id=1').fetchone()
            ledger.execute('CREATE TABLE IF NOT EXISTS price_checkpoints (id INTEGER PRIMARY KEY, until_iso TEXT NOT NULL, provenance TEXT NOT NULL)')
            ledger.execute('INSERT INTO price_checkpoints(until_iso,provenance) VALUES (?,?)', (until.isoformat(), provenance))
    except Exception as error:
        raise BudgetError(FAIL_CLOSED) from error


def prices_expire(db):
    expiry = PRICES_EXPIRE
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='price_checkpoints'").fetchone():
        for (value,) in db.execute('SELECT until_iso FROM price_checkpoints'):
            try:
                checkpoint = datetime.fromisoformat(value)
                if checkpoint.tzinfo is None or checkpoint.utcoffset() is None:
                    raise ValueError('Missing timezone')
                expiry = max(expiry, checkpoint)
            except (TypeError, ValueError):
                raise BudgetError('Invalid stored API price checkpoint') from None
    return expiry


def available(path=None):
    try:
        with connection(path or budget_path()) as db:
            ceiling, baseline = db.execute('SELECT ceiling,baseline FROM budget WHERE id=1').fetchone()
            held = db.execute('SELECT COALESCE(SUM(held),0) FROM calls').fetchone()[0]
            if ceiling not in AUTHORIZED_CEILINGS or min(baseline, held) < 0:
                raise BudgetError('Invalid protected API budget')
            return max(0, ceiling - baseline - held)
    except (sqlite3.Error, TypeError, OSError):
        raise BudgetError('API budget accounting is unavailable; no paid request was sent') from None


class Reservation:
    def __init__(self, path=None, identifier=None, model=None):
        self.path, self.identifier, self.model = path, identifier, model

    def post(self, client, *args, **kwargs):
        try:
            return client.post(*args, **kwargs)
        except Exception:
            self.settle()
            raise

    def settle(self, usage=None):
        if self.identifier is None:
            return  # An explicitly offline MockTransport has no provider expenditure.
        known = (isinstance(usage, dict) and all(type(usage.get(key)) is int and usage[key] >= 0
                  for key in ('input_tokens', 'output_tokens')))
        with connection(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT held,state FROM calls WHERE id=?', (self.identifier,)).fetchone()
            if not row or row[1] != 'pending':
                return
            bound = upper_cents(self.model, usage['input_tokens'], usage['output_tokens']) if known else row[0]
            # Never reduce an envelope when a provider observation exceeds its bound.
            if bound > row[0]:
                db.execute('UPDATE calls SET state=? WHERE id=?', ('overrun', self.identifier))
                db.commit()
                raise BudgetError('Provider usage exceeded its reserved bound; stop paid work')
            db.execute('UPDATE calls SET held=?,state=? WHERE id=?', (bound, 'reported_upper' if known else 'unknown', self.identifier))


def reserve(model, max_output_tokens, transport=None, path=None, now=None):
    if isinstance(transport, httpx.MockTransport):
        return Reservation()
    checkpoint_now = now or datetime.now(timezone.utc)
    if type(max_output_tokens) is not int or not 1 <= max_output_tokens <= 128000:
        raise BudgetError('Invalid output ceiling')
    bound = upper_cents(model, MAX_INPUT, max_output_tokens)
    path, identifier = Path(path or budget_path()), uuid.uuid4().hex
    try:
        with connection(path) as db:
            db.execute('BEGIN IMMEDIATE')
            ceiling, baseline = db.execute('SELECT ceiling,baseline FROM budget WHERE id=1').fetchone()
            held = db.execute('SELECT COALESCE(SUM(held),0) FROM calls').fetchone()[0]
            if checkpoint_now >= prices_expire(db):
                raise BudgetError('API price checkpoint is stale; verify it before paid work')
            if db.execute("SELECT COUNT(*) FROM calls WHERE state IN ('unknown','overrun')").fetchone()[0]:
                raise BudgetError('Reconcile unknown API usage before more paid work')
            if ceiling not in AUTHORIZED_CEILINGS or min(baseline, held) < 0 or baseline + held + bound > ceiling:
                raise BudgetError('Protected API reserve: insufficient verified headroom; no request sent')
            db.execute('INSERT INTO calls VALUES (?,?,?,?)', (identifier, model, bound, 'pending'))
    except (sqlite3.Error, TypeError, OSError):
        raise BudgetError('API budget accounting is unavailable; no paid request was sent') from None
    return Reservation(path, identifier, model)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    extend = commands.add_parser('extend-prices')
    extend.add_argument('--path', default=str(budget_path()), help='Budget database')
    extend.add_argument('--db', help='Main ASE approval database')
    extend.add_argument('--until', required=True)
    extend.add_argument('--provenance', required=True)
    extend.add_argument('--signoff', required=True)
    args = parser.parse_args()
    extend_prices(args.path, args.until, args.provenance, signoff_id=args.signoff, db=args.db)


if __name__ == '__main__':
    main()

