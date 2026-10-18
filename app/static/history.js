(() => {
  const labels = {
    dependencies_set: 'Dependencies changed', posted: 'Task posted',
    package_attached: 'Package attached', ai_followups: 'AI follow-up',
    ai_usage: 'AI usage recorded', ai_source: 'AI source recorded',
    ai_started: 'AI run started', taken: 'Work taken', ai_failed: 'AI run failed',
    ai_model_changed: 'AI model changed', ai_retried: 'AI run retried',
    ai_answers: 'AI answers recorded', ai_ask: 'AI asked a question',
    opportunity_updated: 'Task updated', edited: 'Task edited', reopened: 'Task reopened',
    working: 'Work resumed', blocked: 'Work blocked', cancelled: 'Task cancelled',
    followup_confirmed: 'Child task confirmed', followups_confirmed: 'Child tasks confirmed',
    profile_recorded: 'Context recorded', proof_attached: 'Proof attached',
    proof_review_queued: 'Proof review queued', proof_review_started: 'Proof review started',
    proof_review_usage: 'Proof review usage recorded', proof_reviewed: 'Proof review recorded',
    proof_human_reviewed: 'Human proof decision recorded', proof_completed: 'Verified task completed',
    ai_interrupted: 'AI run interrupted', ai_deliver: 'AI preparation ready', ai_evidence: 'AI evidence prepared',
    delivered: 'Delivery recorded', paid: 'Reserved Gold released',
    acknowledged: 'Delivery acknowledged', accepted: 'Delivery accepted', rejected: 'Delivery rejected',
    'legacy:assigned': 'Legacy work assigned',
    'legacy:completed': 'Legacy work completed'
  };
  const list = value => Array.isArray(value) ? value.join(', ') : '';
  const files = value => Array.isArray(value) ? value.map(item => typeof item === 'string' ? item : item.path).filter(Boolean).join(', ')
    : value && typeof value === 'object' ? Object.keys(value).join(', ') : '';
  const count = value => Number.isFinite(value) && value >= 0 ? String(value) : 'unknown';
  const usage = data => {
    const delta = data.delta || data.usage || {};
    return `${data.model || 'AI'} · ${count(delta.input_tokens)} input / ${count(delta.output_tokens)} output tokens`;
  };
  const timestamp = event => {
    const value = Date.parse(event.created_at || '');
    return Number.isNaN(value) ? null : value;
  };
  const detail = event => {
    const data = event.data || {};
    switch (event.kind) {
      case 'dependencies_set': return `Prerequisites: ${list(data.depends_on) || 'none'}`;
      case 'posted': return `${data.work_type || 'Work'} · ${data.complexity || 'unspecified complexity'}`;
      case 'package_attached': return `${data.kind || 'Package'} · ${files(data.files) || 'no files listed'} · SHA-256 ${data.sha256 || 'not recorded'}`;
      case 'ai_followups': return `${data.model || 'AI'} · ${data.outcome || 'follow-ups'}`;
      case 'ai_usage': case 'proof_review_usage': return usage(data);
      case 'ai_source': return `${Object.keys(data.sha256 || {}).length} source file hashes recorded`;
      case 'ai_started': return `${data.model || 'AI'} started`;
      case 'taken': return 'Work started';
      case 'ai_failed': return `${data.code || 'AI failure'}${data.stage ? ` · ${data.stage}` : ''}`;
      case 'ai_model_changed': return `${data.previous_model || 'previous model'} → ${data.model || 'new model'}`;
      case 'ai_retried': return 'AI run retried';
      case 'ai_answers': return `${(data.answers || []).length} answer(s) recorded`;
      case 'ai_ask': return `${(data.questions || []).length} question(s) asked`;
      case 'opportunity_updated': return data.updated?.title || data.note || 'Task details updated';
      case 'edited': return `Changed fields: ${Object.keys(data.changes || {}).join(', ') || 'not recorded'}`;
      case 'working': return data.note || 'Work is in progress';
      case 'blocked': return data.note || 'Work is blocked';
      case 'cancelled': return data.note || 'Task cancelled; no completion claimed';
      case 'profile_recorded': return `${data.profile?.validation_scope || 'Unspecified scope'} · ${data.profile?.baseline_revision || 'baseline not recorded'} → ${data.profile?.candidate_revision || 'candidate not recorded'}`;
      case 'followup_confirmed': return `Parent ${data.parent_id || 'not recorded'} · ${data.complexity || 'unspecified complexity'} · ${data.assigned_agent || 'agent not recorded'}`;
      case 'followups_confirmed': return `${Array.isArray(data.children) ? data.children.length : 'Unknown'} child task(s) confirmed`;
      case 'proof_attached': return `${data.filename || 'Proof file'} · SHA-256 ${data.sha256 || 'not recorded'}`;
      case 'proof_review_queued': return 'Review queued; no verdict yet';
      case 'proof_review_started': return 'Review running; no verdict yet';
      case 'proof_reviewed': return `${data.verdict || 'unknown verdict'} · ${data.reason || 'reason not recorded'}`;
      case 'proof_human_reviewed': return `${data.accepted === true ? 'Accepted' : data.accepted === false ? 'Rejected' : 'Decision not recorded'} · ${data.review_basis || 'review basis not recorded'} · ${data.note || 'no note'}`;
      case 'proof_completed': return `${data.worker || event.actor || 'Worker not recorded'} · ${data.verification_method || 'verification method not recorded'} · ${data.note || 'Completion recorded'}`;
      case 'ai_interrupted': return data.note || 'Preparation interrupted; no result claimed';
      case 'ai_deliver': case 'ai_evidence': return data.summary || 'Preparation ready for verification';
      case 'delivered': return `Delivery ${data.delivery_id || 'not recorded'} · ${data.verification?.simulated ? 'simulated verification' : 'verification recorded'}`;
      case 'paid': return `Delivery ${data.delivery_id || 'not recorded'} · reserved demo Gold released`;
      case 'acknowledged': case 'accepted': case 'rejected': return data.note || 'Requester decision recorded';
      case 'reopened': return data.note || `Reopened from ${data.previous_state || 'a previous state'}`;
      case 'legacy:assigned': return `Revision ${data.revision || 'unknown'}`;
      case 'legacy:completed': return `Revision ${data.revision || 'unknown'}`;
      default: return data.note || 'Event details recorded';
    }
  };
  const dependencyDeltas = events => {
    const deltas = new WeakMap();
    let previous;
    events.slice().sort((a, b) => timestamp(a) - timestamp(b)).forEach(event => {
      const dependsOn = event.data && event.data.depends_on;
      if (event.kind !== 'dependencies_set' || !Array.isArray(dependsOn)) return;
      if (timestamp(event) === null) {
        deltas.set(event, {baselineAvailable: false});
        return;
      }
      if (!previous) {
        deltas.set(event, {baselineAvailable: false});
      } else {
        const before = new Set(previous);
        const after = new Set(dependsOn);
        deltas.set(event, {
          baselineAvailable: true,
          added: dependsOn.filter(id => !before.has(id)),
          removed: previous.filter(id => !after.has(id))
        });
      }
      previous = dependsOn;
    });
    return deltas;
  };
  window.renderHistory = function (events, helpers) {
    const make = helpers.element;
    const source = Array.isArray(events) ? events : [];
    const deltas = dependencyDeltas(source);
    const ordered = source.slice().sort((a, b) => {
      const left = timestamp(a), right = timestamp(b);
      if (left === null || right === null) return left === null && right !== null ? 1 : right === null && left !== null ? -1 : 0;
      return right - left || (b.seq || 0) - (a.seq || 0);
    });
    const root = make('section', undefined, 'history-timeline');
    root.append(make('h3', 'Task history'));
    const rows = make('div', undefined, 'history-events');
    const renderRows = predicate => {
      rows.replaceChildren();
      ordered.filter(predicate || (() => true)).forEach(event => {
        const row = make('article', undefined, 'history-event');
        const data = event.data || {};
        row.append(make('strong', labels[event.kind] || event.kind));
        row.append(make('span', detail(event), 'history-detail'));
        const actor = Object.prototype.hasOwnProperty.call(data, 'via')
          ? `${event.actor || 'Unknown actor'} via ${data.via}`
          : (event.actor || 'Unknown actor');
        row.append(make('span', actor, 'history-actor'));
        const time = make('time', timestamp(event) === null ? 'Time unavailable' : new Date(timestamp(event)).toLocaleString(), 'history-time');
        if (timestamp(event) !== null) time.dateTime = event.created_at;
        row.append(time);
        const expanded = window.historyDetail && window.historyDetail(event, Object.assign({}, helpers, {
          dependencyDelta: deltas.get(event)
        }));
        if (expanded) row.append(expanded);
        rows.append(row);
      });
    };
    if (window.historyFilters) {
      root.append(window.historyFilters(ordered, Object.assign({}, helpers, {onFilter: renderRows})));
    }
    renderRows();
    root.append(rows);
    return root;
  };
})();
