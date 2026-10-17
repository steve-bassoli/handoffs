/* Unwired renderer for the round-index v1 contract. */
(function () {
  'use strict';

  function make(tag, className, value) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== undefined) node.textContent = value;
    return node;
  }

  function string(value, fallback) {
    return typeof value === 'string' && value ? value : fallback;
  }

  function recordText(record) {
    var artifacts = Array.isArray(record.artifacts) ? record.artifacts : [];
    return [record.round_id, record.recorded_date, record.lesson,
      record.evidence_state].concat(artifacts.map(function (artifact) {
      return artifact && artifact.reference;
    })).join(' ').toLowerCase();
  }

  function addLine(parent, label, value) {
    parent.append(make('p', 'round-index-field', label + ': ' + value));
  }

  function renderRecord(record) {
    var card = make('article', 'round-index-record');
    var provenance = record && record.provenance || {};
    var artifacts = record && Array.isArray(record.artifacts) ? record.artifacts : [];
    card.append(make('h3', 'round-index-title', 'Round: ' + string(record && record.round_id, 'Unknown')));
    addLine(card, 'Recorded date', record && record.recorded_date === null ? 'Unavailable' : string(record && record.recorded_date, 'Unknown'));
    addLine(card, 'Lesson', string(record && record.lesson, 'Unknown'));
    addLine(card, 'Evidence state', string(record && record.evidence_state, 'Unknown'));
    addLine(card, 'Attribution', string(provenance.attribution, 'Unknown'));
    addLine(card, 'Verification', string(provenance.verification, 'Unknown'));
    addLine(card, 'Source reference', string(provenance.source_ref, 'Unavailable'));
    var list = make('ul', 'round-index-artifacts');
    if (!artifacts.length) list.append(make('li', '', 'Artifact references: none recorded'));
    artifacts.forEach(function (artifact) {
      artifact = artifact || {};
      list.append(make('li', '', 'Artifact reference: ' + string(artifact.reference, 'Unknown') +
        ' (resolution: ' + string(artifact.resolution, 'Unknown') + ')'));
    });
    card.append(list);
    return card;
  }

  window.renderRoundIndex = function renderRoundIndex(root, envelope) {
    envelope = envelope || {};
    var records = Array.isArray(envelope.records) ? envelope.records : [];
    var provenance = envelope.provenance || {};
    var section = make('section', 'round-index');
    section.append(make('h2', 'round-index-heading', 'Expedition index'));
    addLine(section, 'Schema version', String(envelope.schema_version || 'Unknown'));
    addLine(section, 'Source availability', string(provenance.availability, 'Unknown'));
    addLine(section, 'Envelope source reference', string(provenance.source_ref, 'Unavailable'));
    var search = make('input', 'round-index-search');
    search.type = 'search';
    search.placeholder = 'Search local round records';
    search.setAttribute('aria-label', 'Search local round records');
    section.append(search);
    var results = make('div', 'round-index-results');
    section.append(results);

    function show() {
      var query = string(search.value, '').toLowerCase();
      while (results.firstChild) results.removeChild(results.firstChild);
      var matches = records.filter(function (record) { return recordText(record || {}).indexOf(query) !== -1; });
      if (!matches.length) results.append(make('p', 'round-index-empty', 'No matching round records are available.'));
      matches.forEach(function (record) { results.append(renderRecord(record || {})); });
    }
    search.addEventListener('input', show);
    show();
    if (root && typeof root.append === 'function') root.append(section);
    return section;
  };
}());
