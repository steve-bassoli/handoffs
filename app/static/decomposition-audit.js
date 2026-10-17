(() => {
  'use strict';
  const source = 'Service.hierarchy_violations';
  const caveat = 'Service.detail defaults missing complexity to HIGH.';
  const string = value => typeof value === 'string';
  const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  const valid = audit => {
    if (!object(audit) || audit.version !== 1 || audit.source !== source ||
        !string(audit.checked_at) || !string(audit.scope) ||
        !Array.isArray(audit.limitations) || !audit.limitations.every(string) ||
        !audit.limitations.includes(caveat)) return false;
    if (audit.status === 'unavailable') {
      return audit.violations === null && audit.error === 'Audit unavailable';
    }
    if (audit.error !== null || !Array.isArray(audit.violations)) return false;
    if (audit.status === 'checked_empty') return audit.violations.length === 0;
    return audit.status === 'findings' && audit.violations.length > 0 &&
      audit.violations.every(record => object(record) && string(record.ticket_id) &&
        record.ticket_id.length > 0 && string(record.message));
  };
  const make = (tag, text) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    return node;
  };
  window.renderDecompositionAudit = function (options = {}) {
    const audit = options && options.audit;
    const onNavigate = options && options.onNavigate;
    const root = make('section');
    root.setAttribute('aria-label', 'Decomposition audit');
    root.append(make('h2', 'Decomposition audit'));
    root.append(make('p', 'Read-only supplied evidence; no independent verification.'));
    if (!valid(audit)) {
      root.append(make('p', 'Audit unavailable'));
      root.append(make('p', 'Source, checked_at and scope: unavailable (invalid or missing payload).'));
      return root;
    }
    root.append(make('p', `Source (supplied): ${audit.source}`));
    root.append(make('p', `Freshness — checked_at (caller supplied): ${audit.checked_at}`));
    root.append(make('p', `Scope (display label only): ${audit.scope}`));
    root.append(make('p', 'Timestamp and source are provenance, not proof of freshness or correctness.'));
    root.append(make('h3', 'Limitations'));
    const limitations = make('ul');
    audit.limitations.forEach(text => limitations.append(make('li', text)));
    root.append(limitations);
    if (audit.status === 'unavailable') {
      root.append(make('p', 'Audit unavailable'));
    } else if (audit.status === 'checked_empty') {
      root.append(make('p', 'No violations reported'));
    } else {
      root.append(make('h3', 'Reported violations'));
      const rows = make('ol');
      audit.violations.forEach(record => {
        const row = make('li');
        const id = record.ticket_id;
        const control = make(typeof onNavigate === 'function' ? 'button' : 'span', id);
        if (typeof onNavigate === 'function') {
          control.type = 'button';
          control.addEventListener('click', () => onNavigate(id));
        }
        row.append(control, make('p', record.message));
        rows.append(row);
      });
      root.append(rows);
    }
    return root;
  };
})();
