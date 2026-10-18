(() => {
  'use strict';
  const object = v => v !== null && typeof v === 'object' && !Array.isArray(v);
  const string = v => typeof v === 'string';
  const strings = v => Array.isArray(v) && v.every(string);
  const source = 'app.complexity:DECOMPOSITION,MIN_CHILDREN,validate_bounty_split';
  const reasons = {
    valid: ['split_valid'],
    violation: ['split_invalid'],
    not_yet_split: ['no_children'],
    unknown: ['topology_invalid', 'topology_incomplete', 'coverage_incomplete', 'classification_missing']
  };
  const labels = {
    valid: 'Valid split', violation: 'Violation',
    not_yet_split: 'Not yet split', unknown: 'Unknown'
  };
  const make = (tag, text) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    return node;
  };
  function valid(projection) {
    if (!object(projection) || projection.schema_version !== 1 ||
        !Array.isArray(projection.tickets) || projection.tickets.length > 10000) return false;
    const ids = new Set();
    return projection.tickets.every(row => {
      if (!object(row) || !string(row.id) || !row.id || ids.has(row.id) ||
          !(row.parent_id === null || string(row.parent_id)) ||
          !strings(row.child_ids) || !string(row.title) ||
          !Object.prototype.hasOwnProperty.call(reasons, row.status) ||
          !strings(row.reasons) || row.reasons.length !== 1 ||
          !reasons[row.status].includes(row.reasons[0])) return false;
      ids.add(row.id);
      return true;
    });
  }
  function help(root, teaching) {
    root.append(make('h3', 'Rule help'));
    if (!object(teaching) || teaching.version !== 1 || teaching.source !== source ||
        !string(teaching.explanation) || !string(teaching.fingerprint) ||
        !/^[a-f0-9]{64}$/.test(teaching.fingerprint) ||
        !Number.isInteger(teaching.min_children) || teaching.min_children < 1 ||
        !object(teaching.rules) || !Object.values(teaching.rules).every(strings)) {
      root.append(make('p', 'Canonical rule help unavailable.'));
      return;
    }
    root.append(make('p', teaching.explanation));
    root.append(make('p', 'Source (supplied): ' + teaching.source));
    root.append(make('p', 'Fingerprint (supplied; not authenticated): ' + teaching.fingerprint));
    root.append(make('p', 'Minimum children (supplied): ' + teaching.min_children));
    const rules = make('ul');
    Object.entries(teaching.rules).forEach(([parent, children]) => {
      rules.append(make('li', parent + ' -> [' + children.join(', ') + ']'));
    });
    root.append(rules);
  }
  window.renderDecompositionVisibility = function (options = {}) {
    options = object(options) ? options : {};
    const root = make('section');
    root.className = 'decomposition-visibility';
    root.setAttribute('aria-label', 'Decomposition visibility');
    root.append(make('h2', 'Decomposition visibility'));
    root.append(make('p', 'Read-only supplied evidence; no independent verification.'));
    root.append(make('p', 'Legend: Valid split; Violation; Unknown; Not yet split. Not yet split is not a violation.'));
    help(root, options.teaching);
    if (!valid(options.visibility)) {
      root.append(make('p', 'Decomposition visibility unavailable.'));
      return root;
    }
    if (!options.visibility.tickets.length) root.append(make('p', 'No tickets supplied.'));
    const list = make('ol');
    options.visibility.tickets.forEach(record => {
      const row = make('li');
      row.setAttribute('data-ticket-id', record.id);
      row.setAttribute('data-visibility-state', record.status);
      const active = typeof options.onNavigate === 'function';
      const control = make(active ? 'button' : 'span', record.id);
      if (active) {
        control.type = 'button';
        control.setAttribute('aria-label', 'Open task ' + record.id);
        control.addEventListener('click', () => options.onNavigate(record.id));
      }
      row.append(control, make('p', record.title));
      row.append(make('p', labels[record.status]));
      record.reasons.forEach(reason => {
        const text = make('p', reason);
        text.setAttribute('data-visibility-reason', reason);
        row.append(text);
      });
      list.append(row);
    });
    root.append(list);
    return root;
  };
  function adapter(options, surface) {
    options = object(options) ? options : {};
    const root = make('section');
    root.className = 'decomposition-visibility-host';
    root.setAttribute('aria-label', surface === 'flow' ? 'Task flow with decomposition visibility' : 'Hierarchy with decomposition visibility');
    // Supplied host roots must be detached. Do not clone, clear or decorate them.
    let host = options.hostNode;
    if (!host && surface === 'flow' && typeof window.renderTicketFlow === 'function') {
      host = window.renderTicketFlow(options);
    }
    if (host) {
      root.append(host);
    } else if (surface === 'flow') {
      host = make('section');
      host.className = 'ticket-flow';
      host.setAttribute('aria-label', 'Task flow');
      host.append(make('p', 'Task flow unavailable.'));
      root.append(host);
    }
    root.append(window.renderDecompositionVisibility(options));
    return root;
  }
  window.renderDecompositionHierarchy = options => adapter(options, 'hierarchy');
  window.renderDecompositionFlow = options => adapter(options, 'flow');
})();
