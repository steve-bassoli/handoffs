(function () {
  'use strict';
  const ids = ['decomposition', 'human_gates', 'humane_limits'];
  const text = v => typeof v === 'string' && v.trim().length > 0;
  const strings = v => Array.isArray(v) && v.every(x => typeof x === 'string');
  const keys = (v, names) => v !== null && typeof v === 'object' &&
    !Array.isArray(v) && Object.keys(v).sort().join('|') === names.slice().sort().join('|');
  function validRow(row, id) {
    if (!keys(row, ['id', 'status', 'scope', 'reason', 'evidence', 'conflicts']) ||
        row.id !== id || !text(row.scope) || !text(row.reason) ||
        !['pass', 'partial', 'gap'].includes(row.status) || !strings(row.conflicts) ||
        !Array.isArray(row.evidence)) return false;
    const path = id === 'decomposition' ? 'app/complexity.py' : 'PROJECT_CHARTER.md';
    if (!row.evidence.every(e => keys(e, ['path', 'sha256', 'kind']) && e.path === path &&
        typeof e.sha256 === 'string' && /^[a-f0-9]{64}$/.test(e.sha256) &&
        ['source', 'behavior'].includes(e.kind))) return false;
    if (row.status === 'gap') return true;
    if (!row.evidence.some(e => e.kind === 'source')) return false;
    if (row.status === 'partial') return true;
    return id === 'decomposition' && !row.conflicts.length &&
      new Set(row.evidence.map(e => e.sha256)).size === 1 &&
      row.evidence.some(e => e.kind === 'behavior');
  }
  window.renderAseConformance = function (model) {
    const root = document.createElement('section');
    const add = (parent, tag, value) => {
      const node = document.createElement(tag);
      node.textContent = value;
      parent.appendChild(node);
      return node;
    };
    add(root, 'h2', 'ASE conformance — reported, scoped evidence');
    add(root, 'p', 'Reported checks are not human verification or certification. No aggregate score is computed.');
    const validModel = keys(model, ['schema_version', 'scope', 'properties', 'limitations']) &&
      model.schema_version === 'ase-narrow-v1' && text(model.scope) && strings(model.limitations) &&
      Array.isArray(model.properties) && model.properties.length === ids.length &&
      model.properties.every((r, i) => r && r.id === ids[i]);
    add(root, 'p', validModel ? 'Scope: ' + model.scope : 'not assessed: malformed or unsupported model');
    ids.forEach((id, index) => {
      const section = document.createElement('section');
      root.appendChild(section);
      const row = validModel ? model.properties[index] : null;
      const valid = validModel && validRow(row, id);
      add(section, 'h3', id);
      add(section, 'p', 'Status: ' + (valid ? row.status : 'not assessed'));
      if (!valid) add(section, 'p', 'Malformed, missing or contradictory assessment; not assessed.');
      if (row && typeof row === 'object') {
        add(section, 'p', 'Scope: ' + (text(row.scope) ? row.scope : 'not assessed'));
        add(section, 'p', 'Reason: ' + (text(row.reason) ? row.reason : 'not assessed'));
        if (!Array.isArray(row.evidence) || !row.evidence.length) {
          add(section, 'p', 'Evidence: not assessed');
        } else row.evidence.forEach(e => {
          if (!e || typeof e !== 'object') {
            add(section, 'p', 'Evidence: malformed; not assessed');
            return;
          }
          add(section, 'p', 'Evidence path: ' + (typeof e.path === 'string' ? e.path : 'not assessed'));
          add(section, 'p', 'SHA-256: ' + (typeof e.sha256 === 'string' ? e.sha256 : 'not assessed'));
          add(section, 'p', 'Kind: ' + (typeof e.kind === 'string' ? e.kind : 'not assessed'));
        });
        add(section, 'p', 'Conflicts: ' + (strings(row.conflicts) ?
          (row.conflicts.length ? row.conflicts.join('; ') : 'none reported') : 'not assessed'));
      } else add(section, 'p', 'Evidence: not assessed');
      if (valid && row.status === 'gap') {
        add(section, 'p', 'Insufficient evidence; behavior was not assessed. This is not proof of feature absence.');
      }
    });
    add(root, 'h3', 'Limitations');
    add(root, 'p', 'This view validates reported structure, not source bytes or execution of named checks.');
    if (validModel && model.limitations.length) model.limitations.forEach(item => add(root, 'p', item));
    else add(root, 'p', 'Reported limitations unavailable; not assessed.');
    return root;
  };
}());
