(function () {
  'use strict';
  const allowed = new Set([
    'https://arxiv.org/pdf/2508.07407',
    'https://arxiv.org/pdf/2505.22954'
  ]);
  const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  const text = value => typeof value === 'string' ? value : 'Unavailable';
  const list = value => Array.isArray(value) ? value : [];
  function add(parent, tag, value) {
    const node = document.createElement(tag);
    node.textContent = text(value);
    parent.appendChild(node);
    return node;
  }
  function provenanceValid(value) {
    return record(value) && typeof value.source === 'string' && value.source.length > 0 &&
      typeof value.sha256 === 'string' && /^[a-f0-9]{64}$/.test(value.sha256) &&
      typeof value.external_reviewed === 'boolean';
  }
  window.renderAseDefinition = function (input) {
    const model = record(input) ? input : {};
    const root = document.createElement('section');
    root.setAttribute('aria-label', 'ASE definition');
    add(root, 'h2', 'ASE definition');
    add(root, 'p', 'Schema: ' + text(model.schema_version));
    add(root, 'p', model.definition);
    function group(title, values, render) {
      add(root, 'h3', title);
      const ul = document.createElement('ul');
      root.appendChild(ul);
      if (!values.length) add(ul, 'li', 'Unavailable');
      values.forEach(value => {
        const li = document.createElement('li');
        ul.appendChild(li);
        render(li, value);
      });
    }
    group('Properties', list(model.properties), (li, value) => {
      const item = record(value) ? value : {};
      add(li, 'p', 'ID: ' + text(item.id));
      add(li, 'p', item.text);
      add(li, 'p', 'Status: ' + text(item.status));
    });
    group('Prior work', list(model.prior_work), (li, value) => {
      const item = record(value) ? value : {};
      add(li, 'p', 'ID: ' + text(item.id));
      add(li, 'p', item.summary);
      add(li, 'p', 'Status: ' + text(item.status));
      const valid = provenanceValid(item.provenance);
      if (typeof item.url === 'string' && allowed.has(item.url) && valid) {
        const link = add(li, 'a', item.url);
        link.setAttribute('href', item.url);
      } else {
        add(li, 'p', 'Citation URL: ' + text(item.url));
      }
      if (typeof item.url !== 'string' || !allowed.has(item.url) || !valid) {
        add(li, 'p', 'Evidence unavailable');
      }
      const p = record(item.provenance) ? item.provenance : {};
      add(li, 'p', 'Source: ' + text(p.source));
      add(li, 'p', 'SHA-256: ' + text(p.sha256));
      add(li, 'p', 'external_reviewed: ' +
        (typeof p.external_reviewed === 'boolean' ? String(p.external_reviewed) : 'Unavailable'));
    });
    group('Qualifications and limits', list(model.limits), (li, value) => add(li, 'p', value));
    return root;
  };
}());
