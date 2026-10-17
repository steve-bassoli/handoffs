(() => {
  const operations = [
    ['projects', 'Projects'],
    ['project_studies', 'Project studies'],
    ['study_detail', 'Study detail']
  ];
  const transports = ['REST', 'SOAP', 'MCP'];
  const fields = [
    ['binding', 'Binding'], ['reference', 'Reference'],
    ['outcome', 'Outcome'], ['verification', 'Verification'],
    ['verification_reference', 'Verification reference'],
    ['provenance', 'Provenance'], ['synthetic', 'Synthetic']
  ];
  const value = item => item === null || item === undefined || item === ''
    ? 'unresolved' : String(item);
  const make = (tag, content, className) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (content !== undefined) node.textContent = content;
    return node;
  };
  const cellFor = (inventory, operation, transport) => {
    const cells = inventory && Array.isArray(inventory.cells) ? inventory.cells : [];
    return cells.find(cell => cell && cell.operation === operation &&
      cell.transport === transport) || {};
  };

  window.renderStudyEvidenceMatrix = (root, inventory) => {
    const section = make('section', undefined, 'study-evidence-matrix');
    section.append(make('h2', 'Offline inventory — not compatibility certification'));
    section.append(make('p', 'Inspectable offline evidence only; no live compatibility claim.'));
    const grid = make('div', undefined, 'study-evidence-cells');
    operations.forEach(([operation, operationLabel]) => {
      transports.forEach(transport => {
        const cell = cellFor(inventory, operation, transport);
        const state = ['gap', 'evidence', 'conflict'].includes(cell.state)
          ? cell.state : 'gap';
        const article = make('article', undefined, `study-evidence-cell state-${state}`);
        article.append(make('h3', `${operationLabel} / ${transport}`));
        article.append(make('p', `State: ${state}`));
        article.append(make('p', `Binding: ${value(cell.binding)}`));
        const evidence = Array.isArray(cell.evidence) ? cell.evidence : [];
        if (!evidence.length) {
          article.append(make('p', 'Evidence: none recorded (gap).'));
        } else {
          const list = make('ul', undefined, 'study-evidence-references');
          evidence.forEach(record => {
            const row = make('li');
            fields.forEach(([key, label]) => {
              const shown = key === 'synthetic'
                ? (record && record.synthetic === true ? 'yes' : 'no')
                : value(record && record[key]);
              row.append(make('span', `${label}: ${shown}; `));
            });
            list.append(row);
          });
          article.append(list);
        }
        grid.append(article);
      });
    });
    section.append(grid);
    if (root && typeof root.replaceChildren === 'function') root.replaceChildren(section);
    return section;
  };
})();
