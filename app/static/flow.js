(function () {
  'use strict';

  function value(input, fallback) {
    return input === undefined || input === null || input === '' ? fallback : String(input);
  }

  function assignedAgent(detail) {
    var events = detail && Array.isArray(detail.events) ? detail.events : [];
    for (var index = events.length - 1; index >= 0; index -= 1) {
      var event = events[index];
      if (event && event.kind === 'followup_confirmed' && event.data && event.data.assigned_agent) {
        return String(event.data.assigned_agent);
      }
    }
    return 'Unknown';
  }

  function makeMetadata(item, detail) {
    var meta = document.createElement('div');
    meta.className = 'flow-meta';
    meta.textContent = 'Complexity: ' + value(detail && detail.complexity, 'Unknown') +
      ' · Assigned: ' + assignedAgent(detail) +
      ' · Status: ' + value(detail && detail.status, value(item.status, 'Unknown'));
    return meta;
  }

  window.renderTicketFlow = function (options) {
    options = options || {};
    var lineage = options.lineage || {};
    var items = Array.isArray(lineage.items) ? lineage.items : [];
    var details = options.detailsById || {};
    var byId = Object.create(null);
    var byParent = Object.create(null);
    var visited = Object.create(null);
    var root = document.createElement('section');

    root.className = 'ticket-flow';
    root.setAttribute('aria-label', 'Task flow');

    items.forEach(function (item) {
      var id;
      var parent;
      if (!item || item.id === undefined || item.id === null) return;
      id = String(item.id);
      parent = item.parent_id === undefined || item.parent_id === null ? '' : String(item.parent_id);
      if (!byId[id]) byId[id] = item;
      if (!byParent[parent]) byParent[parent] = [];
      byParent[parent].push(item);
    });

    function render(item) {
      var id;
      var detail;
      var node;
      var card;
      var children;
      var childRow;

      if (!item || item.id === undefined || item.id === null) return null;
      id = String(item.id);
      if (visited[id]) return null;
      visited[id] = true;

      detail = details[item.id] || details[id] || {};
      node = document.createElement('div');
      node.className = 'flow-node';
      card = document.createElement('button');
      card.type = 'button';
      card.className = 'flow-card';
      card.textContent = id + ' — ' + value(item.title, 'Untitled task');
      card.setAttribute('aria-label', 'Open task ' + id + ': ' + value(item.title, 'Untitled task'));
      card.addEventListener('click', function () {
        if (typeof options.onNavigate === 'function') options.onNavigate(item.id);
      });

      if (String(item.id) === String(options.currentId)) {
        var current = document.createElement('span');
        card.classList.add('is-current');
        card.setAttribute('aria-current', 'page');
        current.className = 'flow-current-label';
        current.textContent = ' You are here';
        card.appendChild(current);
      }

      node.appendChild(card);
      node.appendChild(makeMetadata(item, detail));
      children = byParent[id] || [];
      childRow = document.createElement('div');
      childRow.className = 'flow-children';
      children.forEach(function (child) {
        var childNode = render(child);
        if (childNode) childRow.appendChild(childNode);
      });
      if (childRow.childElementCount) node.appendChild(childRow);
      return node;
    }

    if (lineage.root_id !== undefined && lineage.root_id !== null && byId[String(lineage.root_id)]) {
      var declaredRoot = render(byId[String(lineage.root_id)]);
      if (declaredRoot) root.appendChild(declaredRoot);
    } else {
      (byParent[''] || []).forEach(function (item) {
        var topLevel = render(item);
        if (topLevel) root.appendChild(topLevel);
      });
    }

    items.forEach(function (item) {
      var remaining = render(item);
      if (remaining) root.appendChild(remaining);
    });

    return root;
  };
}());
