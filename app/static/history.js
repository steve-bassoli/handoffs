(() => {
  const labels = {
    dependencies_set: 'Dependencies changed', posted: 'Task posted',
    package_attached: 'Package attached', ai_followups: 'AI follow-up',
    ai_usage: 'AI usage recorded', ai_source: 'AI source recorded',
    ai_started: 'AI run started', taken: 'Work taken', ai_failed: 'AI run failed',
    ai_model_changed: 'AI model changed', ai_retried: 'AI run retried',
    ai_answers: 'AI answers recorded', ai_ask: 'AI asked a question',
    opportunity_updated: 'Task updated', reopened: 'Task reopened',
    'legacy:assigned': 'Legacy work assigned',
    'legacy:completed': 'Legacy work completed'
  };
  const list = value => Array.isArray(value) ? value.join(', ') : '';
  const timestamp = event => {
    const value = Date.parse(event.created_at || '');
    return Number.isNaN(value) ? null : value;
  };
  const detail = event => {
    const data = event.data || {};
    switch (event.kind) {
      case 'dependencies_set': return `Prerequisites: ${list(data.depends_on) || 'none'}`;
      case 'posted': return `${data.work_type || 'Work'} · ${data.complexity || 'unspecified complexity'}`;
      case 'package_attached': return `${data.kind || 'Package'} · ${list(data.files) || 'no files listed'}`;
      case 'ai_followups': return `${data.model || 'AI'} · ${data.outcome || 'follow-ups'}`;
      case 'ai_usage': return `${data.model || 'AI'} · ${data.delta ? `${data.delta.input_tokens || 0} input tokens` : 'usage update'}`;
      case 'ai_source': return `${Object.keys(data.sha256 || {}).length} source file hashes recorded`;
      case 'ai_started': return `${data.model || 'AI'} started`;
      case 'taken': return 'Work started';
      case 'ai_failed': return `${data.code || 'AI failure'}${data.stage ? ` · ${data.stage}` : ''}`;
      case 'ai_model_changed': return `${data.previous_model || 'previous model'} → ${data.model || 'new model'}`;
      case 'ai_retried': return 'AI run retried';
      case 'ai_answers': return `${(data.answers || []).length} answer(s) recorded`;
      case 'ai_ask': return `${(data.questions || []).length} question(s) asked`;
      case 'opportunity_updated': return data.updated?.title || data.note || 'Task details updated';
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
      return right - left;
    });
    const root = make('section', undefined, 'history-timeline');
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
