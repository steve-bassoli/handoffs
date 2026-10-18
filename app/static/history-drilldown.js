(() => {
  const dataOf = event => (event && event.data) || {};
  const values = value => Array.isArray(value) ? value : [];
  const hasOwn = (object, key) => Object.prototype.hasOwnProperty.call(object, key);

  const links = (ids, helpers) => {
    const list = helpers.element('ul', undefined, 'history-dependencies');
    values(ids).forEach(id => {
      const item = helpers.element('li');
      const link = helpers.element('a', `#task=${id}`);
      link.href = `#task=${encodeURIComponent(id)}`;
      item.append(link);
      list.append(item);
    });
    return list;
  };
  const group = (detail, label, ids, helpers) => {
    if (!Array.isArray(ids)) return;
    detail.append(helpers.element('p', label));
    detail.append(links(ids, helpers));
  };

  window.historyDetail = (event, helpers) => {
    if (!event) return null;
    const data = dataOf(event);
    if (event.kind === 'package_attached') {
      const detail = helpers.element('details', undefined, 'history-detail');
      detail.open = true;
      detail.append(helpers.element('summary', 'Package evidence'));
      detail.append(helpers.element('p', 'Ready for human verification.'));
      detail.append(helpers.element('p', `SHA-256: ${data.sha256 || 'Not provided'}`));
      const files = helpers.element('ul', undefined, 'history-package-files');
      values(data.files).forEach(file => files.append(helpers.element('li', file)));
      detail.append(files);
      return detail;
    }
    if (event.kind !== 'dependencies_set') return null;
    const detail = helpers.element('details', undefined, 'history-detail');
    detail.append(helpers.element('summary', 'Dependency evidence'));
    if (Array.isArray(data.added) || Array.isArray(data.removed)) {
      group(detail, 'Added prerequisites', data.added, helpers);
      group(detail, 'Removed prerequisites', data.removed, helpers);
    } else if (helpers.dependencyDelta && helpers.dependencyDelta.baselineAvailable === false) {
      detail.append(helpers.element('p', 'Change baseline unavailable for first recorded snapshot.'));
    } else if (helpers.dependencyDelta && helpers.dependencyDelta.baselineAvailable) {
      group(detail, 'Added prerequisites', helpers.dependencyDelta.added, helpers);
      group(detail, 'Removed prerequisites', helpers.dependencyDelta.removed, helpers);
    }
    group(detail, 'Current prerequisites', data.depends_on, helpers);
    return detail;
  };

  window.historyFilters = (_events, helpers) => {
    const root = helpers.element('nav', undefined, 'history-filters');
    const filters = {
      All: () => true,
      Human: event => {
        const data = dataOf(event);
        return !hasOwn(data, 'via') && !String((event || {}).kind || '').startsWith('ai_');
      },
      Automation: event => hasOwn(dataOf(event), 'via'),
      Evidence: event => (event || {}).kind === 'package_attached',
      AI: event => String((event || {}).kind || '').startsWith('ai_')
    };
    Object.entries(filters).forEach(([label, predicate]) => {
      const button = helpers.element('button', label, 'history-filter');
      button.type = 'button';
      button.addEventListener('click', () => helpers.onFilter(predicate));
      root.append(button);
    });
    return root;
  };
})();
