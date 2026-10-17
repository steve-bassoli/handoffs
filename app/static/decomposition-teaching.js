(function () {
  'use strict';
  const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  const string = value => typeof value === 'string';
  const strings = value => Array.isArray(value) && value.every(string);
  function fields(value, names) {
    return object(value) && Object.keys(value).length === names.length &&
      names.every(name => Object.prototype.hasOwnProperty.call(value, name));
  }
  function hasShape(t) {
    return fields(t, ['version', 'source', 'min_children', 'rules', 'explanation', 'examples', 'fingerprint']) &&
      Number.isInteger(t.version) && Number.isInteger(t.min_children) &&
      string(t.source) && string(t.explanation) && string(t.fingerprint) &&
      object(t.rules) && Object.values(t.rules).every(strings) &&
      Array.isArray(t.examples) && t.examples.every(example =>
        fields(example, ['id', 'explanation', 'splits', 'valid']) &&
        string(example.id) && string(example.explanation) && typeof example.valid === 'boolean' &&
        Array.isArray(example.splits) && example.splits.every(split =>
          fields(split, ['parent', 'children']) && string(split.parent) && strings(split.children)));
  }
  function add(parent, tag, text) {
    const node = document.createElement(tag);
    node.textContent = text;
    parent.appendChild(node);
    return node;
  }
  window.renderDecompositionTeaching = function (options) {
    const panel = document.createElement('section');
    panel.setAttribute('aria-label', 'Decomposition teaching reference');
    add(panel, 'h2', 'Decomposition teaching');
    const teaching = object(options) ? options.teaching : undefined;
    if (teaching === undefined || teaching === null) {
      add(panel, 'p', 'Teaching reference unavailable.');
      return panel;
    }
    if (!hasShape(teaching)) {
      add(panel, 'p', 'Teaching reference malformed.');
      return panel;
    }
    add(panel, 'p', teaching.explanation);
    const metadata = add(panel, 'dl', '');
    [['Version', String(teaching.version)], ['Source', teaching.source],
      ['Fingerprint (supplied; not authenticated)', teaching.fingerprint],
      ['Minimum children', String(teaching.min_children)]].forEach(pair => {
      add(metadata, 'dt', pair[0]);
      add(metadata, 'dd', pair[1]);
    });
    add(panel, 'h3', 'Supplied rules');
    const rules = add(panel, 'ul', '');
    Object.entries(teaching.rules).forEach(([parent, children]) => {
      add(rules, 'li', parent + ' -> [' + children.join(', ') + ']');
    });
    add(panel, 'h3', 'Supplied examples');
    const examples = add(panel, 'ul', '');
    teaching.examples.forEach(example => {
      const item = add(examples, 'li', '');
      add(item, 'h4', example.id);
      add(item, 'p', example.explanation);
      add(item, 'p', 'Supplied outcome: ' + (example.valid ? 'valid' : 'invalid'));
      const trace = add(item, 'ol', '');
      example.splits.forEach(split => {
        add(trace, 'li', split.parent + ' -> [' + split.children.join(', ') + ']');
      });
    });
    return panel;
  };
}());
