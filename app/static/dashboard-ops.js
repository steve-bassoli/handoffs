(() => {
  'use strict';
  window.renderDashboardOps = function (snapshot, helpers) {
    const object = value => value && typeof value === 'object' && !Array.isArray(value) ? value : {};
    const input = object(snapshot);
    const sources = object(input.sources);
    const make = (tag, text, className) => {
      const node = helpers.element(tag, undefined, className);
      if (text !== undefined) node.textContent = text;
      return node;
    };
    const text = value => typeof value === 'string' && value.trim() ? value : 'Unknown';
    const number = value => typeof value === 'number' && Number.isFinite(value) && value >= 0 ? String(value) : 'Unknown';
    const count = value => Number.isSafeInteger(value) && value >= 0 ? String(value) : 'Unknown';
    const money = (value, signed = false) => {
      if (!Number.isSafeInteger(value) || (!signed && value < 0)) return 'Unknown';
      const absolute = Math.abs(value);
      return `${value < 0 ? '-' : ''}$${Math.floor(absolute / 100)}.${String(absolute % 100).padStart(2, '0')}`;
    };
    const root = make('section', undefined, 'dashboard-ops');
    root.append(make('h2', 'Resources and delivery evidence'));
    const row = (card, label, value) => card.append(make('p', `${label}: ${value}`));
    const cardFor = (key, title) => {
      const source = object(sources[key]);
      const status = ['ok', 'stale', 'unavailable'].includes(source.status) ? source.status : 'unavailable';
      const card = make('article', undefined, `dashboard-ops-card ${status}`);
      card.append(make('h3', title));
      row(card, 'Source status', status === 'stale' ? 'STALE — retained historical evidence; ' + (source.stale_reason || 'refresh failed') : status);
      row(card, 'Source', text(source.source_id));
      row(card, 'Observed at', text(source.observed_at));
      row(card, 'Last attempt', text(source.last_attempt_at));
      if (status !== 'ok' && source.error_code) row(card, 'Failure category', text(source.error_code));
      root.append(card);
      return {card, status, data: status === 'unavailable' ? {} : object(source.data)};
    };
    const ledger = cardFor('ledger', 'Sponsor ledger');
    row(ledger.card, 'Source ceiling', money(ledger.data.ceiling_cents));
    row(ledger.card, 'Baseline', money(ledger.data.baseline_cents));
    row(ledger.card, 'Reservations — upper bound, not billed cost', money(ledger.data.held_upper_bound_cents));
    row(ledger.card, 'Source headroom' + (ledger.status === 'stale' ? ' (historical)' : ''), money(ledger.data.source_headroom_cents, true));
    row(ledger.card, 'Guarded allocatable headroom' + (ledger.status === 'stale' ? ' (historical; not current authority)' : ''), money(ledger.data.guarded_headroom_cents, true));
    if (ledger.status !== 'ok') row(ledger.card, 'Current allocatable authority', 'Unknown');
    row(ledger.card, 'Provenance', text(ledger.data.provenance));
    if (Array.isArray(ledger.data.holds) && ledger.data.holds.some(hold => ['unknown', 'overrun'].includes(hold.state))) {
      row(ledger.card, 'Paid work', 'Blocked pending API usage reconciliation; retained reservations are not a spendable balance');
    }
    ledger.card.append(make('p', 'Policy: $1.00 protected separately; sponsor allocation cap $1998.00. Headroom is evidence, not permission to spend. Unknown usage retains its reservation; no automatic retry.'));
    const usage = cardFor('session_usage', 'Session usage');
    row(usage.card, 'Reported usage — upper bound, not billed cost', money(usage.data.reported_upper_cents));
    usage.card.append(make('p', 'Not added to ledger reservations: overlapping evidence must not be double-counted.'));
    const accounting = make('a', 'Authorized usage accounting');
    accounting.setAttribute('href', 'https://platform.openai.com/usage');
    usage.card.append(accounting);
    const wallet = cardFor('wallet', 'Participant Gold');
    row(wallet.card, 'Gold', number(wallet.data.gold));
    wallet.card.append(make('p', 'Separate participant resource; not sponsor spending authority. Game Credits, ADMIRATION and GROWTH are not money or purchased authority.'));
    const codex = cardFor('codex', 'Codex allowance');
    row(codex.card, 'Amount', number(codex.data.amount));
    row(codex.card, 'Unit', text(codex.data.unit));
    codex.card.append(make('p', 'Independent allowance; not sponsor spending authority.'));
    const leases = cardFor('leases', 'Agent lease evidence');
    row(leases.card, 'Verified live agents' + (leases.status === 'stale' ? ' (historical)' : ''), count(leases.data.verified_live_count));
    row(leases.card, 'Interrupted occupied leases' + (leases.status === 'stale' ? ' (historical)' : ''), count(leases.data.interrupted_occupied_count));
    if (Array.isArray(leases.data.records)) {
      row(leases.card, 'Registered observations shown', Math.min(10, leases.data.records.length) + ' of ' + leases.data.records.length + '; includes historical leases');
      leases.data.records.slice(0, 10).forEach(value => {
        const record = object(value);
        row(leases.card, `Lease ${text(record.id)}`, `${text(record.state)}; evidence: ${text(record.evidence)}`);
      });
    }
    leases.card.append(make('p', 'Admission, roster membership or PID existence alone does not prove liveness.'));
    const git = cardFor('git', 'Delivery evidence');
    const commit = object(git.data.commit);
    row(git.card, 'Latest commit hash', text(commit.hash));
    git.card.append(make('p', 'Git HEAD metadata only; the working tree is not attested by this observation.'));
    row(git.card, 'Commit time', text(commit.committed_at));
    row(git.card, 'Tests', 'not recorded');
    git.card.append(make('p', 'Policy: tests gated before commit. This policy is not test-run evidence; commit metadata does not prove tests passed or human acceptance.'));
    return root;
  };
})();
