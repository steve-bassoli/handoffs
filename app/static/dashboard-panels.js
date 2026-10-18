(function () {
  'use strict';
  window.connectDashboardPanels = function (controller, helpers) {
    const make = helpers.make;
    const flowState = make('p');
    let flowRoot = null, graphRoot = null, graphKey = null, lastOps = null;
    const navigate = id => { location.href = '/#task=' + encodeURIComponent(id); };
    controller.register('flow', (element, snapshot, state) => {
      if (!flowState.parentNode) element.replaceChildren(flowState);
      flowState.textContent = state.stale ? 'Stale observations · retained task evidence' : 'Task observations received';
      if (!snapshot || !snapshot.flow) return;
      if (!flowRoot) {
        flowRoot = window.renderDashboardFlow(snapshot.flow, {
          onNavigate: navigate,
          renderFlow: model => {
            const key = JSON.stringify([model.tickets, model.current_id]);
            if (key !== graphKey) {
              graphRoot = window.renderTicketFlow({lineage: {items: model.tickets}, currentId: model.current_id,
                detailsById: Object.fromEntries(model.tickets.map(task => [task.id, {status: task.status, complexity: task.complexity, claimant: task.claimant,
                  events: task.assigned_agent ? [{kind: 'followup_confirmed', data: {assigned_agent: task.assigned_agent}}] : []}])),
                onNavigate: navigate});
              graphKey = key;
            }
            return graphRoot;
          }
        });
        element.appendChild(flowRoot);
      } else flowRoot.update(snapshot.flow);
    });
    controller.register('ops', (element, snapshot, state) => {
      if (!snapshot || !snapshot.ops) { element.textContent = 'No resource observations received.'; return; }
      const current = {...snapshot.ops, sources: {...snapshot.ops.sources}};
      Object.keys(current.sources).forEach(key => {
        let source = current.sources[key];
        const old = lastOps && lastOps.sources[key];
        if (source.status !== 'ok' && source.source_id && old && old.source_id === source.source_id && ['ok', 'stale'].includes(old.status)) {
          source = {...source, status: 'stale', data: old.data, observed_at: old.observed_at};
        }
        if (state.stale && source.status === 'ok') source = {...source, status: 'stale',
          stale_reason: state.paused ? 'polling paused' : state.authentication ? 'authentication stopped' : 'snapshot read failed'};
        current.sources[key] = source;
      });
      lastOps = current;
      const active = document.activeElement;
      const focusedLink = element.contains(active) && active.tagName === 'A' ? active.getAttribute('href') : null;
      const mode = snapshot.mode;
      element.replaceChildren(make('p', 'Mode: ' + (mode.value || 'unknown') +
        ' · Configured agent capacity: ' + (mode.agents === null ? 'unknown' : mode.agents) +
        ' · Autonomous campaign writes: ' + (mode.automated_writes === null ? 'unknown' : mode.automated_writes ? 'enabled' : 'paused')),
        window.renderDashboardOps(current, {element: make}));
      if (focusedLink) {
        const link = Array.from(element.querySelectorAll('a')).find(node => node.getAttribute('href') === focusedLink);
        if (link) link.focus();
      }
    });
  };
}());
