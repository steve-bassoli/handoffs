(function () {
  'use strict';
  const text = v => typeof v === 'string' && v.trim().length > 0;
  const strings = v => Array.isArray(v) && v.every(x => typeof x === 'string');
  const object = v => v !== null && typeof v === 'object' && !Array.isArray(v);
  const keys = (v, names) => object(v) &&
    Object.keys(v).sort().join('|') === names.slice().sort().join('|');
  function validRow(row) {
    if (!keys(row, ['id', 'label', 'property_refs', 'properties', 'status', 'reported_status',
      'scope', 'reason', 'evidence', 'conflicts', 'issues', 'action', 'verification', 'next_step']) ||
      !['id', 'label', 'reported_status', 'scope', 'reason', 'action', 'verification', 'next_step']
        .every(k => text(row[k])) || !['pass', 'partial', 'gap'].includes(row.status) ||
      !strings(row.property_refs) || !row.property_refs.length || !strings(row.conflicts) ||
      !strings(row.issues) || !Array.isArray(row.properties) || !Array.isArray(row.evidence)) return false;
    if (!row.properties.every(p => keys(p, ['id', 'text', 'status']) &&
        text(p.id) && text(p.text) && text(p.status) && row.property_refs.includes(p.id))) return false;
    const path = row.id === 'decomposition' ? 'app/complexity.py' : 'PROJECT_CHARTER.md';
    if (!row.evidence.every(e => keys(e, ['path', 'sha256', 'kind']) && e.path === path &&
        typeof e.sha256 === 'string' && /^[a-f0-9]{64}$/.test(e.sha256) &&
        ['source', 'behavior'].includes(e.kind))) return false;
    if (row.status === 'gap') return true;
    if (row.properties.map(p => p.id).join('|') !== row.property_refs.join('|') ||
        !row.evidence.some(e => e.kind === 'source')) return false;
    if (row.status === 'partial') return ['partial', 'pass'].includes(row.reported_status);
    return row.id === 'decomposition' && row.reported_status === 'pass' &&
      !row.conflicts.length && !row.issues.length &&
      new Set(row.evidence.map(e => e.sha256)).size === 1 &&
      row.evidence.some(e => e.kind === 'behavior');
  }
  window.renderAseExplainer = function (model) {
    const root = document.createElement('section');
    const add = (parent, tag, value) => {
      const node = document.createElement(tag);
      node.textContent = value;
      parent.appendChild(node);
      return node;
    };
    add(root, 'h2', 'ASE adoption — evidence and next steps');
    add(root, 'p', 'Supplied guidance only; this view does not verify source bytes, run tests or establish human acceptance.');
    const valid = keys(model, ['schema_version', 'definition', 'scope', 'capabilities',
      'workflow', 'gates', 'limitations']) && model.schema_version === 'ase-adoption-v1' &&
      text(model.definition) && text(model.scope) && Array.isArray(model.capabilities) &&
      model.capabilities.length > 0 && Array.isArray(model.workflow) && model.workflow.length > 0 &&
      model.workflow.every(s => keys(s, ['id', 'action', 'verification', 'next_step']) &&
        ['id', 'action', 'verification', 'next_step'].every(k => text(s[k]))) &&
      strings(model.gates) && model.gates.length > 0 && strings(model.limitations) &&
      model.limitations.length > 0;
    if (!valid) {
      add(root, 'p', 'not assessed: missing, malformed or unsupported adoption model. No guidance is authorized by this view.');
      add(root, 'h3', 'Gates and limitations');
      add(root, 'p', 'Supplied gates and limitations unavailable; request a complete model.');
      return root;
    }
    add(root, 'p', model.definition);
    add(root, 'p', 'Scope: ' + model.scope);
    // Gates and limits precede advice, rather than being hidden below it.
    add(root, 'h3', 'Human gates');
    model.gates.forEach(value => add(root, 'p', value));
    add(root, 'h3', 'Limitations and what remains unproven');
    model.limitations.forEach(value => add(root, 'p', value));
    const ids = model.capabilities.map(r => object(r) ? r.id : null);
    model.capabilities.forEach(row => {
      const section = document.createElement('section');
      root.appendChild(section);
      const assessed = validRow(row) && ids.filter(id => id === row.id).length === 1;
      add(section, 'h3', object(row) && text(row.label) ? row.label : 'Capability not assessed');
      add(section, 'p', 'Status: ' + (assessed ? row.status : 'not assessed'));
      if (!assessed) {
        add(section, 'p', 'Malformed or contradictory supplied guidance; not assessed.');
        return;
      }
      add(section, 'p', 'Reported status: ' + row.reported_status);
      add(section, 'p', 'Scope: ' + row.scope);
      add(section, 'p', 'Reason: ' + row.reason);
      add(section, 'p', 'Property references: ' + row.property_refs.join(', '));
      row.properties.forEach(p => add(section, 'p', p.id + ': ' + p.text + ' [' + p.status + ']'));
      if (!row.evidence.length) add(section, 'p', 'Evidence: not assessed');
      row.evidence.forEach(e => add(section, 'p', 'Evidence: ' + e.path + ' | SHA-256: ' + e.sha256 + ' | ' + e.kind));
      add(section, 'p', 'Conflicts: ' + (row.conflicts.length ? row.conflicts.join('; ') : 'none reported'));
      row.issues.forEach(value => add(section, 'p', 'Unresolved: ' + value));
      if (row.status === 'gap') add(section, 'p', 'Insufficient evidence; not proof of absence.');
      if (row.status === 'partial') add(section, 'p', 'Incomplete or conflicting evidence remains unresolved.');
      add(section, 'p', 'Action: ' + row.action);
      add(section, 'p', 'Verification: ' + row.verification);
      add(section, 'p', 'Next step: ' + row.next_step);
    });
    add(root, 'h3', 'Bounded adoption checklist');
    model.workflow.forEach(step => {
      add(root, 'p', 'Action: ' + step.action);
      add(root, 'p', 'Verification: ' + step.verification);
      add(root, 'p', 'Next step: ' + step.next_step);
    });
    return root;
  };
}());
