(() => {
  const meanings = {
    1: 'Ready: focused pacing.',
    2: 'Reduce load: checkpoint before continuing.',
    3: 'Stop now: preserve a minimal authorized work-only checkpoint.'
  };

  window.renderWorkCheckpoint = function (record, helpers) {
    const source = record && typeof record === 'object' ? record : {};
    const verification = source.verification || {};
    const usage = source.usage || {};
    const nextStep = source.next_step || {};
    const make = helpers.element;
    const text = (tag, value, className) => {
      const node = make(tag, undefined, className);
      node.textContent = String(value == null ? '' : value);
      return node;
    };
    const field = (label, value) => {
      const row = make('p', undefined, 'work-checkpoint-field');
      row.append(text('strong', `${label}: `));
      row.append(text('span', value));
      return row;
    };
    const list = (label, values) => {
      const section = make('section', undefined, 'work-checkpoint-checks');
      const items = make('ul');
      section.append(text('h3', label));
      (Array.isArray(values) ? values : []).forEach(value => {
        items.append(text('li', value));
      });
      section.append(items);
      return section;
    };
    const usageText = usage.status === 'unknown' && usage.reservation_retained
      ? 'Unknown usage; reservation retained.'
      : usage.status === 'known' ? 'Known usage.' : 'Usage status unavailable.';

    const card = make('section', undefined, 'work-checkpoint-card');
    card.append(text('h2', 'Work checkpoint'));
    card.append(field('Pressure', meanings[source.pressure] || 'Unknown pressure'));
    card.append(field('Pressure action', source.pressure_action));
    card.append(field('Completed work', source.completed_action));
    card.append(list('Completed verification', verification.completed));
    card.append(list('Proposed checks not run', verification.proposed_checks));
    card.append(field('Authorized next step', nextStep.instruction));
    card.append(field('Next-step kind', nextStep.kind));
    card.append(field('Authority', nextStep.requires_existing_authority
      ? 'Requires existing authority.' : 'Authority requirement unavailable.'));
    card.append(field('Usage', usageText));
    return card;
  };
})();
