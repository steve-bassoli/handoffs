/* v1-r2 proposal. Relay supplies a verified renderTicketFlow adapter, if any. */
(() => {
  'use strict';
  window.renderDashboardFlow = function (model, options = {}) {
    const make = (tag, text, className) => {
      const node = typeof options.element === 'function'
        ? options.element(tag, undefined, className) : document.createElement(tag);
      node.textContent = text === undefined ? '' : text;
      if (className) node.className = className;
      return node;
    };
    const root = make('section', undefined, 'dashboard-flow');
    root.setAttribute('aria-live', 'off');
    const heading = make('h2', 'Ticket flow');
    const evidence = make('p');
    const notice = make('p');
    const nav = make('nav');
    nav.setAttribute('aria-label', 'Ticket flow');
    const list = make('ul');
    nav.appendChild(list);
    const graph = make('div');
    const activityHeading = make('h3', 'Work activity');
    const activityNote = make('p');
    const activityList = make('ol');
    const issues = make('p');
    [heading, evidence, notice, nav, graph, activityHeading, activityNote,
      activityList, issues].forEach(node => root.appendChild(node));
    const rows = new Map();
    let activityKey = null;
    const string = (value, fallback = 'unknown') =>
      typeof value === 'string' && value.length ? value : fallback;
    root.update = function (next) {
      if (!next || next.version !== 1 || !Array.isArray(next.tickets) ||
          !Array.isArray(next.activity) || !Array.isArray(next.issues) ||
          !next.coverage || typeof next.coverage !== 'object') {
        throw new TypeError('Expected dashboard flow v1 model');
      }
      const c = next.coverage;
      const doc = root.ownerDocument;
      const active = doc.activeElement;
      let focusedId = null;
      rows.forEach((row, id) => { if (row.control === active) focusedId = id; });
      const seen = new Set();
      let position = 0;
      next.tickets.forEach(ticket => {
        const id = ticket.id;
        if (seen.has(id)) return;
        seen.add(id);
        let row = rows.get(id);
        if (!row) {
          row = {li: make('li')};
          row.control = make(typeof options.onNavigate === 'function' ? 'button' : 'span');
          if (typeof options.onNavigate === 'function') {
            row.control.type = 'button';
            row.control.addEventListener('click', () => options.onNavigate(id));
          }
          row.li.appendChild(row.control);
          rows.set(id, row);
        }
        const parent = !ticket.parent_known ? 'parent unknown' :
          ticket.parent_id === null ? 'explicit root' : 'parent ' + ticket.parent_id;
        const assignment = ticket.assigned_agent === null ? 'assignment evidence unavailable' :
          'supplied confirmation: ' + ticket.assigned_agent +
          ' (' + string(ticket.assignment_source) + '; not resolved current assignment)';
        row.control.textContent = id + ' — ' + string(ticket.title) + ' — ' +
          string(ticket.status) + ' — ' + parent + ' — ' + assignment +
          (ticket.detail_available ? '' : ' — detail missing') +
          (id === next.current_id ? ' — You are here' : '');
        if (id === next.current_id) row.control.setAttribute('aria-current', 'page');
        else row.control.removeAttribute('aria-current');
        const at = list.children[position++];
        if (at !== row.li) list.insertBefore(row.li, at || null);
      });
      rows.forEach((row, id) => {
        if (!seen.has(id)) { list.removeChild(row.li); rows.delete(id); }
      });
      if (focusedId !== null && rows.has(focusedId) && doc.activeElement !== active &&
          typeof options.onNavigate === 'function') rows.get(focusedId).control.focus();
      evidence.textContent = 'Supplied evidence only; upstream completeness unknown. ' +
        'Observed: ' + string(next.observed_at) + ' (not event time). Tickets: ' +
        c.tickets_shown + '/' + c.tickets_supplied + ' supplied; missing details: ' +
        c.details_missing + '.' + (c.tickets_truncated ? ' Ticket cap applied.' : '');
      notice.textContent = seen.size ? 'Accessible ticket list available.' : 'No supplied tickets shown.';
      if (!seen.has(next.current_id)) notice.textContent += ' Current location unknown.';
      if (typeof options.onNavigate !== 'function') notice.textContent += ' Navigation unavailable.';
      graph.replaceChildren();
      if (typeof options.renderFlow === 'function') {
        try {
          const node = options.renderFlow(next, {element: make,
            onNavigate: typeof options.onNavigate === 'function' ? options.onNavigate : undefined});
          if (!node || ![1, 11].includes(node.nodeType)) throw new TypeError('No graph node');
          graph.appendChild(node);
        } catch (error) {
          graph.replaceChildren();
          notice.textContent += ' Graph unavailable; use the ticket list.';
        }
      } else notice.textContent += ' Graph not connected; use the ticket list.';
      const labels = next.activity.map(item => item.ticket_id + ' — ' + item.kind +
        ' — Event time: ' + string(item.event_time) + ' — Source index: ' + item.source_index);
      const key = JSON.stringify(labels);
      if (key !== activityKey) {
        activityList.replaceChildren();
        labels.forEach(label => activityList.appendChild(make('li', label)));
        activityKey = key;
      }
      activityNote.textContent = 'Showing ' + c.activity_shown + ' of ' + c.activity_eligible +
        ' supplied eligible events for shown tickets, in source order; not complete history.' +
        (c.activity_truncated ? ' Activity cap applied.' : '') +
        (!labels.length ? ' No supplied work events shown.' : '');
      issues.textContent = next.issues.length ?
        'Evidence limitations: ' + next.issues.join('; ') : 'No local issues reported; completeness remains unknown.';
      return root;
    };
    return root.update(model);
  };
})();
